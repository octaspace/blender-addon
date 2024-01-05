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
import collections
import logging
import pathlib
import random
import typing

import requests

import blender_asset_tracer.pack.transfer as bat_transfer
from blender_asset_tracer import bpathlib

MAX_DEFERRED_PATHS = 8
MAX_FAILED_PATHS = 8

response_file_unknown = "file-unknown"
response_already_uploading = "already-uploading"


class FileInfo:
    def __init__(self, checksum: str, filesize: int, abspath: pathlib.Path):
        self.checksum = checksum
        self.filesize = filesize
        self.abspath = abspath


class ShamanTransferrer(bat_transfer.FileTransferer):
    """Sends files to a Shaman server."""

    class AbortUpload(Exception):
        """Raised from the upload callback to abort an upload."""

    def __init__(
        self,
        auth_token: str,
        project_root: pathlib.Path,
        shaman_endpoint: str,
        checkout_id: str,
    ) -> None:
        from . import client

        super().__init__()
        self.client = client.ShamanClient(auth_token, shaman_endpoint)
        self.project_root = project_root
        self.checkout_id = checkout_id
        self.log = logging.getLogger(__name__)

        self._file_info = {}  # type: typing.Dict[str, FileInfo]

        # When the Shaman creates a checkout, it'll return the location of that
        # checkout. This can then be combined with the project-relative path
        # of the to-be-rendered blend file (e.g. the one 'bat pack' was pointed
        # at).
        self._checkout_location = ""

        self.uploaded_files = 0
        self.uploaded_bytes = 0

    # noinspection PyBroadException
    def run(self) -> None:
        try:
            self.uploaded_files = 0
            self.uploaded_bytes = 0

            # Construct the Shaman Checkout Definition file.
            # This blocks until we know the entire list of files to transfer.
            (
                definition_file,
                allowed_relpaths,
                delete_when_done,
            ) = self._create_checkout_definition()
            if not definition_file:
                # An error has already been logged.
                return

            self.log.info(
                "Created checkout definition file of %d KiB",
                len(definition_file) // 1024,
            )
            self.log.info("Feeding %d files to the Shaman", len(self._file_info))
            if self.log.isEnabledFor(logging.INFO):
                for path in self._file_info:
                    self.log.info("   - %s", path)

            # Try to upload all the files.
            failed_paths = set()  # type: typing.Set[str]
            max_tries = 50
            for try_index in range(max_tries):
                # Send the file to the Shaman and see what we still need to send there.
                to_upload = self._send_checkout_def_to_shaman(
                    definition_file, allowed_relpaths
                )
                if to_upload is None:
                    # An error has already been logged.
                    return

                if not to_upload:
                    break

                # Send the files that still need to be sent.
                self.log.info("Upload attempt %d", try_index + 1)
                failed_paths = self._upload_files(to_upload)
                if not failed_paths:
                    break

                # Having failed paths at this point is expected when multiple
                # clients are sending the same files. Instead of retrying on a
                # file-by-file basis, we just re-send the checkout definition
                # file to the Shaman and obtain a new list of files to upload.

            if failed_paths:
                self.log.error("Aborting upload due to too many failures")
                self.error_set(
                    "Giving up after %d attempts to upload the files" % max_tries
                )
                return

            self.log.info("All files uploaded succesfully")
            self._request_checkout(definition_file)

            # Delete the files that were supposed to be moved.
            for src in delete_when_done:
                self.delete_file(src)

        except Exception as ex:
            # We have to catch exceptions in a broad way, as this is running in
            # a separate thread, and exceptions won't otherwise be seen.
            self.log.exception("Error transferring files to Shaman")
            self.error_set("Unexpected exception transferring files to Shaman: %s" % ex)

    # noinspection PyBroadException
    def _create_checkout_definition(
        self,
    ) -> typing.Tuple[bytes, typing.Set[str], typing.List[pathlib.Path]]:
        """Create the checkout definition file for this BAT pack.

        :returns: the checkout definition (as bytes), a set of paths in that file,
            and list of paths to delete.

        If there was an error and file transfer was aborted, the checkout
        definition file will be empty.
        """
        from . import cache

        definition_lines = []  # type: typing.List[bytes]
        delete_when_done = []  # type: typing.List[pathlib.Path]

        # We keep track of the relative paths we want to send to the Shaman,
        # so that the Shaman cannot ask us to upload files we didn't want to.
        relpaths = set()  # type: typing.Set[str]

        for src, dst, act in self.iter_queue():
            try:
                checksum = cache.compute_cached_checksum(src)
                filesize = src.stat().st_size
                # relpath = dst.relative_to(self.project_root)
                relpath = bpathlib.strip_root(dst).as_posix()

                self._file_info[relpath] = FileInfo(
                    checksum=checksum,
                    filesize=filesize,
                    abspath=src,
                )
                line = "%s %s %s" % (checksum, filesize, relpath)
                definition_lines.append(line.encode("utf8"))
                relpaths.add(relpath)

                if act == bat_transfer.Action.MOVE:
                    delete_when_done.append(src)
            except Exception:
                # We have to catch exceptions in a broad way, as this is running in
                # a separate thread, and exceptions won't otherwise be seen.
                msg = "Error transferring %s to %s" % (src, dst)
                self.log.exception(msg)
                # Put the files to copy back into the queue, and abort. This allows
                # the main thread to inspect the queue and see which files were not
                # copied. The one we just failed (due to this exception) should also
                # be reported there.
                self.queue.put((src, dst, act))
                self.error_set(msg)
                return b"", set(), delete_when_done

        cache.cleanup_cache()
        return b"\n".join(definition_lines), relpaths, delete_when_done

    def _send_checkout_def_to_shaman(
        self, definition_file: bytes, allowed_relpaths: typing.Set[str]
    ) -> typing.Optional[collections.deque]:
        """Send the checkout definition file to the Shaman.

        :return: An iterable of paths (relative to the project root) that still
            need to be uploaded, or None if there was an error.
        """
        resp = self.client.post(
            "checkout/requirements",
            data=definition_file,
            stream=True,
            headers={"Content-Type": "text/plain"},
            timeout=15,
        )
        if resp.status_code >= 300:
            msg = "Error from Shaman, code %d: %s" % (resp.status_code, resp.text)
            self.log.error(msg)
            self.error_set(msg)
            return None

        to_upload = collections.deque()  # type: collections.deque
        for line in resp.iter_lines():
            response, path = line.decode().split(" ", 1)
            self.log.debug("   %s: %s", response, path)

            if path not in allowed_relpaths:
                msg = "Shaman requested path we did not intend to upload: %r" % path
                self.log.error(msg)
                self.error_set(msg)
                return None

            if response == response_file_unknown:
                to_upload.appendleft(path)
            elif response == response_already_uploading:
                to_upload.append(path)
            elif response == "ERROR":
                msg = "Error from Shaman: %s" % path
                self.log.error(msg)
                self.error_set(msg)
                return None
            else:
                msg = "Unknown response from Shaman for path %r: %r" % (path, response)
                self.log.error(msg)
                self.error_set(msg)
                return None

        return to_upload

    def _upload_files(self, to_upload: collections.deque) -> typing.Set[str]:
        """Actually upload the files to Shaman.

        Returns the set of files that we did not upload.
        """
        failed_paths = set()  # type: typing.Set[str]
        deferred_paths = set()

        def defer(some_path: str):
            nonlocal to_upload

            self.log.info(
                "   %s deferred (already being uploaded by someone else)", some_path
            )
            deferred_paths.add(some_path)

            # Instead of deferring this one file, randomize the files to upload.
            # This prevents multiple deferrals when someone else is uploading
            # files from the same project (because it probably happens alphabetically).
            all_files = list(to_upload)
            random.shuffle(all_files)
            to_upload = collections.deque(all_files)

        if not to_upload:
            self.log.info(
                "All %d files are at the Shaman already", len(self._file_info)
            )
            self.report_transferred(0)
            return failed_paths

        self.log.info(
            "Going to upload %d of %d files", len(to_upload), len(self._file_info)
        )
        while to_upload:
            # After too many failures, just retry to get a fresh set of files to upload.
            if len(failed_paths) > MAX_FAILED_PATHS:
                self.log.info("Too many failures, going to abort this iteration")
                failed_paths.update(to_upload)
                return failed_paths

            path = to_upload.popleft()
            fileinfo = self._file_info[path]
            self.log.info("   %s", path)

            headers = {
                "X-Shaman-Original-Filename": path,
            }
            # Let the Shaman know whether we can defer uploading this file or not.
            can_defer = (
                len(deferred_paths) < MAX_DEFERRED_PATHS
                and path not in deferred_paths
                and len(to_upload)
            )
            if can_defer:
                headers["X-Shaman-Can-Defer-Upload"] = "true"

            url = "files/%s/%d" % (fileinfo.checksum, fileinfo.filesize)
            try:
                with fileinfo.abspath.open("rb") as infile:
                    resp = self.client.post(url, data=infile, headers=headers)

            except requests.ConnectionError as ex:
                if can_defer:
                    # Closing the connection with an 'X-Shaman-Can-Defer-Upload: true' header
                    # indicates that we should defer the upload. Requests doesn't give us the
                    # reply, even though it was written by the Shaman before it closed the
                    # connection.
                    defer(path)
                else:
                    self.log.info(
                        "   %s could not be uploaded, might retry later: %s", path, ex
                    )
                    failed_paths.add(path)
                continue

            if resp.status_code == 208:
                # For small files we get the 208 response, because the server closes the
                # connection after we sent the entire request. For bigger files the server
                # responds sooner, and Requests gives us the above ConnectionError.
                if can_defer:
                    defer(path)
                else:
                    self.log.info("   %s skipped (already existed on the server)", path)
                continue

            if resp.status_code >= 300:
                msg = "Error from Shaman uploading %s, code %d: %s" % (
                    fileinfo.abspath,
                    resp.status_code,
                    resp.text,
                )
                self.log.error(msg)
                self.error_set(msg)
                return failed_paths

            failed_paths.discard(path)
            self.uploaded_files += 1
            file_size = fileinfo.abspath.stat().st_size
            self.uploaded_bytes += file_size
            self.report_transferred(file_size)

        if not failed_paths:
            self.log.info(
                "Done uploading %d bytes in %d files",
                self.uploaded_bytes,
                self.uploaded_files,
            )
        else:
            self.log.info(
                "Uploaded %d bytes in %d files so far",
                self.uploaded_bytes,
                self.uploaded_files,
            )

        return failed_paths

    def report_transferred(self, bytes_transferred: int):
        if self._abort.is_set():
            self.log.warning("Interrupting ongoing upload")
            raise self.AbortUpload("interrupting ongoing upload")
        super().report_transferred(bytes_transferred)

    def _request_checkout(self, definition_file: bytes):
        """Ask the Shaman to create a checkout of this BAT pack."""

        if not self.checkout_id:
            self.log.warning("NOT requesting checkout at Shaman")
            return

        self.log.info(
            "Requesting checkout at Shaman for checkout_id=%r", self.checkout_id
        )
        resp = self.client.post(
            "checkout/create/%s" % self.checkout_id,
            data=definition_file,
            headers={"Content-Type": "text/plain"},
        )
        if resp.status_code >= 300:
            msg = "Error from Shaman, code %d: %s" % (resp.status_code, resp.text)
            self.log.error(msg)
            self.error_set(msg)
            return

        self._checkout_location = resp.text.strip()
        self.log.info("Response from Shaman, code %d: %s", resp.status_code, resp.text)

    @property
    def checkout_location(self) -> str:
        """Returns the checkout location, or '' if no checkout was made."""
        if not self._checkout_location:
            return ""
        return self._checkout_location
