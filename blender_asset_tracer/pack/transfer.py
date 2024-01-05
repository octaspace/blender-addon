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
import abc
import enum
import logging
import pathlib
import queue
import threading
import time
import typing
from typing import Optional

from . import progress

log = logging.getLogger(__name__)


class FileTransferError(IOError):
    """Raised when one or more files could not be transferred."""

    def __init__(self, message, files_remaining: typing.List[pathlib.Path]) -> None:
        super().__init__(message)
        self.files_remaining = files_remaining


class Action(enum.Enum):
    COPY = 1
    MOVE = 2


QueueItem = typing.Tuple[pathlib.Path, pathlib.PurePath, Action]


class FileTransferer(threading.Thread, metaclass=abc.ABCMeta):
    """Abstract superclass for file transfer classes.

    Implement a run() function in a subclass that performs the actual file
    transfer.
    """

    def __init__(self) -> None:
        super().__init__()
        self.log = log.getChild("FileTransferer")

        # For copying in a different process. By using a priority queue the files
        # are automatically sorted alphabetically, which means we go through all files
        # in a single directory at a time. This should be faster to copy than random
        # access. The order isn't guaranteed, though, as we're not waiting around for
        # all file paths to be known before copying starts.

        # maxsize=100 is just a guess as to a reasonable upper limit. When this limit
        # is reached, the main thread will simply block while waiting for this thread
        # to finish copying a file.
        self.queue = queue.PriorityQueue(
            maxsize=100
        )  # type: queue.PriorityQueue[QueueItem]
        self.done = threading.Event()
        self._abort = threading.Event()  # Indicates user-requested abort

        self.__error_mutex = threading.Lock()
        self.__error = threading.Event()  # Indicates abort due to some error
        self.__error_message = ""

        # Instantiate a dummy progress callback so that we can call it
        # without checking for None all the time.
        self.progress_cb = progress.ThreadSafeCallback(progress.Callback())
        self.total_queued_bytes = 0
        self.total_transferred_bytes = 0

    @abc.abstractmethod
    def run(self):
        """Perform actual file transfer in a thread."""

    def queue_copy(self, src: pathlib.Path, dst: pathlib.PurePath):
        """Queue a copy action from 'src' to 'dst'."""
        if src.is_dir():
            raise TypeError(f"only files can be copied, not directories: {src}")
        assert (
            not self.done.is_set()
        ), "Queueing not allowed after done_and_join() was called"
        assert (
            not self._abort.is_set()
        ), "Queueing not allowed after abort_and_join() was called"
        if self.__error.is_set():
            return
        self.queue.put((src, dst, Action.COPY))
        self.total_queued_bytes += src.stat().st_size

    def queue_move(self, src: pathlib.Path, dst: pathlib.PurePath):
        """Queue a move action from 'src' to 'dst'."""
        if src.is_dir():
            raise TypeError(f"only files can be moved, not directories: {src}")
        assert (
            not self.done.is_set()
        ), "Queueing not allowed after done_and_join() was called"
        assert (
            not self._abort.is_set()
        ), "Queueing not allowed after abort_and_join() was called"
        if self.__error.is_set():
            return
        self.queue.put((src, dst, Action.MOVE))
        self.total_queued_bytes += src.stat().st_size

    def report_transferred(self, bytes_transferred: int):
        """Report transfer of `block_size` bytes."""

        self.total_transferred_bytes += bytes_transferred
        self.progress_cb.transfer_progress(
            self.total_queued_bytes, self.total_transferred_bytes
        )

    def done_and_join(self) -> None:
        """Indicate all files have been queued, and wait until done.

        After this function has been called, the queue_xxx() methods should not
        be called any more.

        :raises FileTransferError: if there was an error transferring one or
            more files.
        """

        self.done.set()
        self.join()

        if not self.queue.empty():
            # Flush the queue so that we can report which files weren't copied yet.
            files_remaining = self._files_remaining()
            assert files_remaining
            raise FileTransferError(
                "%d files couldn't be transferred" % len(files_remaining),
                files_remaining,
            )

    def _files_remaining(self) -> typing.List[pathlib.Path]:
        """Source files that were queued but not transferred."""
        files_remaining = []
        while not self.queue.empty():
            src, dst, act = self.queue.get_nowait()
            files_remaining.append(src)
        return files_remaining

    def abort(self) -> None:
        """Abort the file transfer, immediately returns."""
        log.info("Aborting")
        self._abort.set()

    def abort_and_join(self) -> None:
        """Abort the file transfer, and wait until done."""

        self.abort()
        self.join()

        files_remaining = self._files_remaining()
        if not files_remaining:
            return
        log.warning(
            "%d files couldn't be transferred, starting with %s",
            len(files_remaining),
            files_remaining[0],
        )

    def iter_queue(self) -> typing.Iterable[QueueItem]:
        """Generator, yield queued items until the work is done."""

        while True:
            if self._abort.is_set() or self.__error.is_set():
                return

            try:
                src, dst, action = self.queue.get(timeout=0.5)
                self.progress_cb.transfer_file(src, dst)
                yield src, dst, action
            except queue.Empty:
                if self.done.is_set():
                    return

    def join(self, timeout: Optional[float] = None) -> None:
        """Wait for the transfer to finish/stop."""

        if timeout:
            run_until = time.time() + timeout
        else:
            run_until = float("inf")

        # We can't simply block the thread, we have to keep watching the
        # progress queue.
        while self.is_alive():
            if time.time() > run_until:
                self.log.warning("Timeout while waiting for transfer to finish")
                return

            self.progress_cb.flush(timeout=0.5)

        # Since Thread.join() neither returns anything nor raises any exception
        # when timing out, we don't even have to call it any more.

    def delete_file(self, path: pathlib.Path):
        """Deletes a file, only logging a warning if deletion fails."""
        log.debug("Deleting %s, file has been transferred", path)
        try:
            path.unlink()
        except IOError as ex:
            log.warning("Unable to delete %s: %s", path, ex)

    @property
    def has_error(self) -> bool:
        return self.__error.is_set()

    def error_set(self, message: str):
        """Indicate an error occurred, and provide a message."""

        with self.__error_mutex:
            # Avoid overwriting previous error messages.
            if self.__error.is_set():
                return

            self.__error.set()
            self.__error_message = message

    def error_message(self) -> str:
        """Retrieve the error messsage, or an empty string if no error occurred."""
        with self.__error_mutex:
            if not self.__error.is_set():
                return ""
            return self.__error_message
