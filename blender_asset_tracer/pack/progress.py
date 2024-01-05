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
"""Callback class definition for BAT Pack progress reporting."""
import threading

import functools
import logging
import pathlib
import queue
import typing
from typing import Optional

from ..trace import progress
from .. import trace

log = logging.getLogger(__name__)


class Callback(trace.progress.Callback):
    """BAT Pack progress reporting."""

    def pack_start(self) -> None:
        """Called when packing starts."""

    def pack_done(
        self,
        output_blendfile: pathlib.PurePath,
        missing_files: typing.Set[pathlib.Path],
    ) -> None:
        """Called when packing is done."""

    def pack_aborted(self, reason: str):
        """Called when packing was aborted."""

    def trace_blendfile(self, filename: pathlib.Path) -> None:
        """Called for every blendfile opened when tracing dependencies."""

    def trace_asset(self, filename: pathlib.Path) -> None:
        """Called for every asset found when tracing dependencies.

        Note that this can also be a blend file.
        """

    def rewrite_blendfile(self, orig_filename: pathlib.Path) -> None:
        """Called for every rewritten blendfile."""

    def transfer_file(self, src: pathlib.Path, dst: pathlib.PurePath) -> None:
        """Called when a file transfer starts."""

    def transfer_file_skipped(self, src: pathlib.Path, dst: pathlib.PurePath) -> None:
        """Called when a file is skipped because it already exists."""

    def transfer_progress(self, total_bytes: int, transferred_bytes: int) -> None:
        """Called during file transfer, with per-pack info (not per file).

        :param total_bytes: The total amount of bytes to be transferred for
            the current packing operation. This can increase while transfer
            is happening, when more files are discovered (because transfer
            starts in a separate thread before all files are found).
        :param transferred_bytes: The total amount of bytes transfered for
            the current packing operation.
        """

    def missing_file(self, filename: pathlib.Path) -> None:
        """Called for every asset that does not exist on the filesystem."""


class ThreadSafeCallback(Callback):
    """Thread-safe wrapper for Callback instances.

    Progress calls are queued until flush() is called. The queued calls are
    called in the same thread as the one calling flush().
    """

    def __init__(self, wrapped: Callback) -> None:
        self.log = log.getChild("ThreadSafeCallback")
        self.wrapped = wrapped

        # Thread-safe queue for passing progress reports on the main thread.
        self._reporting_queue = queue.Queue()  # type: queue.Queue[typing.Callable]
        self._main_thread_id = threading.get_ident()

    def _queue(self, func: typing.Callable, *args, **kwargs):
        partial = functools.partial(func, *args, **kwargs)

        if self._main_thread_id == threading.get_ident():
            partial()
        else:
            self._reporting_queue.put(partial)

    def pack_start(self) -> None:
        self._queue(self.wrapped.pack_start)

    def pack_done(
        self,
        output_blendfile: pathlib.PurePath,
        missing_files: typing.Set[pathlib.Path],
    ) -> None:
        self._queue(self.wrapped.pack_done, output_blendfile, missing_files)

    def pack_aborted(self, reason: str):
        self._queue(self.wrapped.pack_aborted, reason)

    def trace_blendfile(self, filename: pathlib.Path) -> None:
        self._queue(self.wrapped.trace_blendfile, filename)

    def trace_asset(self, filename: pathlib.Path) -> None:
        self._queue(self.wrapped.trace_asset, filename)

    def transfer_file(self, src: pathlib.Path, dst: pathlib.PurePath) -> None:
        self._queue(self.wrapped.transfer_file, src, dst)

    def transfer_file_skipped(self, src: pathlib.Path, dst: pathlib.PurePath) -> None:
        self._queue(self.wrapped.transfer_file_skipped, src, dst)

    def transfer_progress(self, total_bytes: int, transferred_bytes: int) -> None:
        self._queue(self.wrapped.transfer_progress, total_bytes, transferred_bytes)

    def missing_file(self, filename: pathlib.Path) -> None:
        self._queue(self.wrapped.missing_file, filename)

    def flush(self, timeout: Optional[float] = None) -> None:
        """Call the queued calls, call this in the main thread."""

        while True:
            try:
                call = self._reporting_queue.get(
                    block=timeout is not None, timeout=timeout
                )
            except queue.Empty:
                return

            try:
                call()
            except Exception:
                # Don't let the handling of one callback call
                # block the entire flush process.
                self.log.exception("Error calling %s", call)
