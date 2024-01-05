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
# (c) 2018, Blender Foundation - Sybren A. Stüvel
import logging
import multiprocessing.pool
import pathlib
import shutil
import typing

from .. import compressor
from . import transfer

log = logging.getLogger(__name__)


class AbortTransfer(Exception):
    """Raised when an error was detected and file transfer should be aborted."""


class FileCopier(transfer.FileTransferer):
    """Copies or moves files in source directory order."""

    # When we don't compress the files, the process is I/O bound,
    # and trashing the storage by using multiple threads will
    # only slow things down.
    transfer_threads = 1  # type: typing.Optional[int]

    def __init__(self):
        super().__init__()
        self.files_transferred = 0
        self.files_skipped = 0
        self.already_copied = set()

        # (is_dir, action)
        self.transfer_funcs = {
            (False, transfer.Action.COPY): self.copyfile,
            (True, transfer.Action.COPY): self.copytree,
            (False, transfer.Action.MOVE): self.move,
            (True, transfer.Action.MOVE): self.move,
        }

    def run(self) -> None:

        pool = multiprocessing.pool.ThreadPool(processes=self.transfer_threads)
        dst = pathlib.Path()
        for src, pure_dst, act in self.iter_queue():
            try:
                dst = pathlib.Path(pure_dst)

                if self.has_error or self._abort.is_set():
                    raise AbortTransfer()

                if self._skip_file(src, dst, act):
                    continue

                # We want to do this in this thread, as it's not thread safe itself.
                dst.parent.mkdir(parents=True, exist_ok=True)

                pool.apply_async(self._thread, (src, dst, act))
            except AbortTransfer:
                # either self._error or self._abort is already set. We just have to
                # let the system know we didn't handle those files yet.
                self.queue.put((src, dst, act), timeout=1.0)
            except Exception as ex:
                # We have to catch exceptions in a broad way, as this is running in
                # a separate thread, and exceptions won't otherwise be seen.
                if self._abort.is_set():
                    log.debug("Error transferring %s to %s: %s", src, dst, ex)
                else:
                    msg = "Error transferring %s to %s" % (src, dst)
                    log.exception(msg)
                    self.error_set(msg)
                # Put the files to copy back into the queue, and abort. This allows
                # the main thread to inspect the queue and see which files were not
                # copied. The one we just failed (due to this exception) should also
                # be reported there.
                self.queue.put((src, dst, act), timeout=1.0)
                break

        log.debug("All transfer threads queued")
        pool.close()
        log.debug("Waiting for transfer threads to finish")
        pool.join()
        log.debug("All transfer threads finished")

        if self.files_transferred:
            log.info("Transferred %d files", self.files_transferred)
        if self.files_skipped:
            log.info("Skipped %d files", self.files_skipped)

    def _thread(self, src: pathlib.Path, dst: pathlib.Path, act: transfer.Action):
        try:
            tfunc = self.transfer_funcs[src.is_dir(), act]

            if self.has_error or self._abort.is_set():
                raise AbortTransfer()

            log.info("%s %s -> %s", act.name, src, dst)
            tfunc(src, dst)
        except AbortTransfer:
            # either self._error or self._abort is already set. We just have to
            # let the system know we didn't handle those files yet.
            self.queue.put((src, dst, act), timeout=1.0)
        except Exception as ex:
            # We have to catch exceptions in a broad way, as this is running in
            # a separate thread, and exceptions won't otherwise be seen.
            if self._abort.is_set():
                log.debug("Error transferring %s to %s: %s", src, dst, ex)
            else:
                msg = "Error transferring %s to %s" % (src, dst)
                log.exception(msg)
                self.error_set(msg)
            # Put the files to copy back into the queue, and abort. This allows
            # the main thread to inspect the queue and see which files were not
            # copied. The one we just failed (due to this exception) should also
            # be reported there.
            self.queue.put((src, dst, act), timeout=1.0)

    def _skip_file(
        self, src: pathlib.Path, dst: pathlib.Path, act: transfer.Action
    ) -> bool:
        """Skip this file (return True) or not (return False)."""
        st_src = src.stat()  # must exist, or it wouldn't be queued.
        if not dst.exists():
            return False

        st_dst = dst.stat()
        if st_dst.st_size != st_src.st_size or st_dst.st_mtime < st_src.st_mtime:
            return False

        log.info("SKIP %s; already exists", src)
        if act == transfer.Action.MOVE:
            log.debug("Deleting %s", src)
            src.unlink()
        self.files_skipped += 1
        return True

    def _move(self, srcpath: pathlib.Path, dstpath: pathlib.Path):
        """Low-level file move."""
        shutil.move(str(srcpath), str(dstpath))

    def _copy(self, srcpath: pathlib.Path, dstpath: pathlib.Path):
        """Low-level file copy. dstpath needs to be a file and not a directory."""
        shutil.copyfile(str(srcpath), str(dstpath))

    def move(self, srcpath: pathlib.Path, dstpath: pathlib.Path):
        s_stat = srcpath.stat()
        self._move(srcpath, dstpath)

        self.files_transferred += 1
        self.report_transferred(s_stat.st_size)

    def copyfile(self, srcpath: pathlib.Path, dstpath: pathlib.Path):
        """Copy a file, skipping when it already exists."""

        if self._abort.is_set() or self.has_error:
            return

        if (srcpath, dstpath) in self.already_copied:
            log.debug("SKIP %s; already copied", srcpath)
            return

        s_stat = srcpath.stat()  # must exist, or it wouldn't be queued.
        if dstpath.exists():
            d_stat = dstpath.stat()
            if d_stat.st_size == s_stat.st_size and d_stat.st_mtime >= s_stat.st_mtime:
                log.info("SKIP %s; already exists", srcpath)
                self.progress_cb.transfer_file_skipped(srcpath, dstpath)
                self.files_skipped += 1
                return

        log.debug("Copying %s -> %s", srcpath, dstpath)
        self._copy(srcpath, dstpath)

        self.already_copied.add((srcpath, dstpath))
        self.files_transferred += 1

        self.report_transferred(s_stat.st_size)

    def copytree(
        self,
        src: pathlib.Path,
        dst: pathlib.Path,
        symlinks=False,
        ignore_dangling_symlinks=False,
    ):
        """Recursively copy a directory tree.

        Copy of shutil.copytree() with some changes:

        - Using pathlib
        - The destination directory may already exist.
        - Existing files with the same file size are skipped.
        - Removed ability to ignore things.
        """

        if (src, dst) in self.already_copied:
            log.debug("SKIP %s; already copied", src)
            return

        if self.has_error or self._abort.is_set():
            raise AbortTransfer()

        dst.mkdir(parents=True, exist_ok=True)
        errors = []  # type: typing.List[typing.Tuple[pathlib.Path, pathlib.Path, str]]
        for srcpath in src.iterdir():
            if self.has_error or self._abort.is_set():
                raise AbortTransfer()

            dstpath = dst / srcpath.name
            try:
                if srcpath.is_symlink():
                    linkto = srcpath.resolve()
                    if symlinks:
                        # We can't just leave it to `copy_function` because legacy
                        # code with a custom `copy_function` may rely on copytree
                        # doing the right thing.
                        linkto.symlink_to(dstpath)
                        shutil.copystat(
                            str(srcpath), str(dstpath), follow_symlinks=not symlinks
                        )
                    else:
                        # ignore dangling symlink if the flag is on
                        if not linkto.exists() and ignore_dangling_symlinks:
                            continue
                        # otherwise let the copy occurs. copy2 will raise an error
                        if srcpath.is_dir():
                            self.copytree(srcpath, dstpath, symlinks)
                        else:
                            self.copyfile(srcpath, dstpath)
                elif srcpath.is_dir():
                    self.copytree(srcpath, dstpath, symlinks)
                else:
                    # Will raise a SpecialFileError for unsupported file types
                    self.copyfile(srcpath, dstpath)
            # catch the Error from the recursive copytree so that we can
            # continue with other files
            except shutil.Error as err:
                errors.extend(err.args[0])
            except OSError as why:
                errors.append((srcpath, dstpath, str(why)))
        try:
            shutil.copystat(str(src), str(dst))
        except OSError as why:
            # Copying file access times may fail on Windows
            if getattr(why, "winerror", None) is None:
                errors.append((src, dst, str(why)))
        if errors:
            raise shutil.Error(errors)

        self.already_copied.add((src, dst))

        return dst


class CompressedFileCopier(FileCopier):
    # When we compress the files on the fly, the process is CPU-bound
    # so we benefit greatly by multi-threading (packing a Spring scene
    # lighting file took 6m30s single-threaded and 2min13 multi-threaded.
    transfer_threads = None  # type: typing.Optional[int]

    def _move(self, srcpath: pathlib.Path, dstpath: pathlib.Path):
        compressor.move(srcpath, dstpath)

    def _copy(self, srcpath: pathlib.Path, dstpath: pathlib.Path):
        compressor.copy(srcpath, dstpath)
