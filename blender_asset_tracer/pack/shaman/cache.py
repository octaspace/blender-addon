# ***** BEGIN GPL LICENSE BLOCK *****
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
# ***** END GPL LICENCE BLOCK *****
#
# (c) 2019, Blender Foundation - Sybren A. Stüvel

import base64
import hashlib
import json
import logging
import sys
import time
import typing
from collections import deque
from pathlib import Path

from . import time_tracker

CACHE_ROOT = Path().home() / ".cache/shaman-client/shasums"
MAX_CACHE_FILES_AGE_SECS = 3600 * 24 * 60  # 60 days

log = logging.getLogger(__name__)


class TimeInfo:
    computing_checksums = 0.0
    checksum_cache_handling = 0.0


def find_files(root: Path) -> typing.Iterable[Path]:
    """Recursively finds files in the given root path.

    Directories are recursed into, and file paths are yielded.
    Symlinks are yielded if they refer to a regular file.
    """
    queue = deque([root])
    while queue:
        path = queue.popleft()

        # Ignore hidden files/dirs; these can be things like '.svn' or '.git',
        # which shouldn't be sent to Shaman.
        if path.name.startswith("."):
            continue

        if path.is_dir():
            for child in path.iterdir():
                queue.append(child)
            continue

        # Only yield symlinks if they link to (a link to) a normal file.
        if path.is_symlink():
            symlinked = path.resolve()
            if symlinked.is_file():
                yield path
            continue

        if path.is_file():
            yield path


def compute_checksum(filepath: Path) -> str:
    """Compute the SHA256 checksum for the given file."""
    blocksize = 32 * 1024

    log.debug("Computing checksum of %s", filepath)
    with time_tracker.track_time(TimeInfo, "computing_checksums"):
        hasher = hashlib.sha256()
        with filepath.open("rb") as infile:
            while True:
                block = infile.read(blocksize)
                if not block:
                    break
                hasher.update(block)
        checksum = hasher.hexdigest()
    return checksum


def _cache_path(filepath: Path) -> Path:
    """Compute the cache file for the given file path."""

    fs_encoding = sys.getfilesystemencoding()
    filepath = filepath.absolute()

    # Reverse the directory, because most variation is in the last bytes.
    rev_dir = str(filepath.parent)[::-1]
    encoded_path = filepath.stem + rev_dir + filepath.suffix
    cache_key = (
        base64.urlsafe_b64encode(encoded_path.encode(fs_encoding)).decode().rstrip("=")
    )

    cache_path = CACHE_ROOT / cache_key[:10] / cache_key[10:]
    return cache_path


def compute_cached_checksum(filepath: Path) -> str:
    """Computes the SHA256 checksum.

    The checksum is cached to disk. If the cache is still valid, it is used to
    skip the actual SHA256 computation.
    """

    with time_tracker.track_time(TimeInfo, "checksum_cache_handling"):
        current_stat = filepath.stat()
        cache_path = _cache_path(filepath)

        try:
            with cache_path.open("r") as cache_file:
                payload = json.load(cache_file)
        except (OSError, ValueError):
            # File may not exist, or have invalid contents.
            pass
        else:
            checksum = payload.get("checksum", "")
            cached_mtime = payload.get("file_mtime", 0.0)
            cached_size = payload.get("file_size", -1)

            if (
                checksum
                and current_stat.st_size == cached_size
                and abs(cached_mtime - current_stat.st_mtime) < 0.01
            ):
                cache_path.touch()
                return checksum

    checksum = compute_checksum(filepath)

    with time_tracker.track_time(TimeInfo, "checksum_cache_handling"):
        payload = {
            "checksum": checksum,
            "file_mtime": current_stat.st_mtime,
            "file_size": current_stat.st_size,
        }

        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with cache_path.open("w") as cache_file:
                json.dump(payload, cache_file)
        except IOError as ex:
            log.warning("Unable to write checksum cache file %s: %s", cache_path, ex)

    return checksum


def cleanup_cache() -> None:
    """Remove all cache files that are older than MAX_CACHE_FILES_AGE_SECS."""

    if not CACHE_ROOT.exists():
        return

    with time_tracker.track_time(TimeInfo, "checksum_cache_handling"):
        queue = deque([CACHE_ROOT])
        rmdir_queue = []

        now = time.time()
        num_removed_files = 0
        num_removed_dirs = 0
        while queue:
            path = queue.popleft()

            if path.is_dir():
                queue.extend(path.iterdir())
                rmdir_queue.append(path)
                continue

            assert path.is_file()
            path.relative_to(CACHE_ROOT)

            age = now - path.stat().st_mtime
            # Don't trust files from the future either.
            if 0 <= age <= MAX_CACHE_FILES_AGE_SECS:
                continue

            path.unlink()
            num_removed_files += 1

        for dirpath in reversed(rmdir_queue):
            assert dirpath.is_dir()
            dirpath.relative_to(CACHE_ROOT)

            try:
                dirpath.rmdir()
                num_removed_dirs += 1
            except OSError:
                pass

    if num_removed_dirs or num_removed_files:
        log.info(
            "Cache Cleanup: removed %d dirs and %d files",
            num_removed_dirs,
            num_removed_files,
        )
