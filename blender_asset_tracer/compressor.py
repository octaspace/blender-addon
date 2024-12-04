"""shutil-like functionality while compressing blendfiles on the fly."""

import gzip
import logging
import pathlib
import shutil

from .blendfile import magic_compression

log = logging.getLogger(__name__)

# Arbitrarily chosen block size, in bytes.
BLOCK_SIZE = 256 * 2**10


def move(src: pathlib.Path, dest: pathlib.Path):
    """Move a file from src to dest, gzip-compressing if not compressed yet.

    Only compresses files ending in .blend; others are moved as-is.
    """
    my_log = log.getChild("move")
    my_log.debug("Moving %s to %s", src, dest)

    if src.suffix.lower() == ".blend":
        _move_or_copy(src, dest, my_log, source_must_remain=False)
    else:
        shutil.move(str(src), str(dest))


def copy(src: pathlib.Path, dest: pathlib.Path):
    """Copy a file from src to dest, gzip-compressing if not compressed yet.

    Only compresses files ending in .blend; others are copied as-is.
    """
    my_log = log.getChild("copy")
    my_log.debug("Copying %s to %s", src, dest)

    if src.suffix.lower() == ".blend":
        _move_or_copy(src, dest, my_log, source_must_remain=True)
    else:
        shutil.copy2(str(src), str(dest))


def _move_or_copy(
    src: pathlib.Path,
    dest: pathlib.Path,
    my_log: logging.Logger,
    *,
    source_must_remain: bool,
):
    """Either move or copy a file, gzip-compressing if not compressed yet.

    :param src: File to copy/move.
    :param dest: Path to copy/move to.
    :source_must_remain: True to copy, False to move.
    :my_log: Logger to use for logging.
    """
    srcfile = src.open("rb")
    try:
        comp_type = magic_compression.find_compression_type(srcfile)
        if comp_type != magic_compression.Compression.NONE:
            # Either already compressed or not a blend file.
            # Either way we shouldn't attempt compressing this file.
            srcfile.close()
            my_log.debug("Source file %s is compressed already", src)
            if source_must_remain:
                shutil.copy2(str(src), str(dest))
            else:
                shutil.move(str(src), str(dest))
            return

        my_log.debug("Compressing %s on the fly while copying to %s", src, dest)
        srcfile.seek(0)
        with gzip.open(str(dest), mode="wb") as destfile:
            shutil.copyfileobj(srcfile, destfile, BLOCK_SIZE)

        srcfile.close()
        if not source_must_remain:
            my_log.debug("Deleting source file %s", src)
            src.unlink()
    finally:
        if not srcfile.closed:
            srcfile.close()
