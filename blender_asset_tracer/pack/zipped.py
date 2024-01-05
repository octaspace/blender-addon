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
"""ZIP file packer.

Note: There is no official file name encoding for ZIP files. Expect trouble
when you want to use the ZIP cross-platform and you have non-ASCII names.
"""
import logging
import pathlib

from . import Packer, transfer

log = logging.getLogger(__name__)

# Suffixes to store uncompressed in the zip.
STORE_ONLY = {".jpg", ".jpeg", ".exr", ".blend"}


class ZipPacker(Packer):
    """Creates a zipped BAT Pack instead of a directory."""

    def _create_file_transferer(self) -> transfer.FileTransferer:
        target_path = pathlib.Path(self._target_path)
        return ZipTransferrer(target_path.absolute())


class ZipTransferrer(transfer.FileTransferer):
    """Creates a ZIP file instead of writing to a directory.

    Note: There is no official file name encoding for ZIP files. If you have
    unicode file names, they will be encoded as UTF-8. WinZip interprets all
    file names as encoded in CP437, also known as DOS Latin.
    """

    def __init__(self, zippath: pathlib.Path) -> None:
        super().__init__()
        self.zippath = zippath

    def run(self) -> None:
        import zipfile

        zippath = self.zippath.absolute()

        with zipfile.ZipFile(str(zippath), "w") as outzip:
            for src, dst, act in self.iter_queue():
                assert src.is_absolute(), "expecting only absolute paths, not %r" % src

                dst = pathlib.Path(dst).absolute()
                try:
                    relpath = dst.relative_to(zippath)

                    # Don't bother trying to compress already-compressed files.
                    if src.suffix.lower() in STORE_ONLY:
                        compression = zipfile.ZIP_STORED
                        log.debug("ZIP %s -> %s (uncompressed)", src, relpath)
                    else:
                        compression = zipfile.ZIP_STORED
                        log.debug("ZIP %s -> %s", src, relpath)
                    outzip.write(
                        str(src), arcname=str(relpath), compress_type=compression
                    )

                    if act == transfer.Action.MOVE:
                        self.delete_file(src)
                except Exception:
                    # We have to catch exceptions in a broad way, as this is running in
                    # a separate thread, and exceptions won't otherwise be seen.
                    log.exception("Error transferring %s to %s", src, dst)
                    # Put the files to copy back into the queue, and abort. This allows
                    # the main thread to inspect the queue and see which files were not
                    # copied. The one we just failed (due to this exception) should also
                    # be reported there.
                    self.queue.put((src, dst, act))
                    return
