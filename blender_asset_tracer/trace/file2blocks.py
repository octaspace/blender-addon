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
"""Expand data blocks.

The expansion process follows pointers and library links to construct the full
set of actually-used data blocks. This set consists of all data blocks in the
initial blend file, and all *actually linked-to* data blocks in linked
blend files.
"""

import collections
import logging
import pathlib
import queue
import typing

from .. import blendfile, bpathlib
from . import expanders, progress

_funcs_for_code = {}  # type: typing.Dict[bytes, typing.Callable]
log = logging.getLogger(__name__)


# noinspection PyProtectedMember
class BlockQueue(queue.PriorityQueue):
    """PriorityQueue that sorts by filepath and file offset"""

    def _put(self, item: blendfile.BlendFileBlock):
        super()._put((item.bfile.filepath, item.file_offset, item))

    def _get(self) -> blendfile.BlendFileBlock:
        _, _, item = super()._get()
        return item


class BlockIterator:
    """Expand blocks with dependencies from other libraries.

    This class exists so that we have some context for the recursive expansion
    without having to pass those variables to each recursive call.
    """

    def __init__(self) -> None:
        # Set of (blend file Path, block address) of already-reported blocks.
        self.blocks_yielded = set()  # type: typing.Set[typing.Tuple[pathlib.Path, int]]

        # Queue of blocks to visit
        self.to_visit = BlockQueue()

        self.progress_cb = progress.Callback()

    def open_blendfile(self, bfilepath: pathlib.Path) -> blendfile.BlendFile:
        """Open a blend file, sending notification about this to the progress callback."""

        log.info("opening: %s", bfilepath)
        self.progress_cb.trace_blendfile(bfilepath)
        return blendfile.open_cached(bfilepath)

    def iter_blocks(
        self,
        bfile: blendfile.BlendFile,
        limit_to: typing.Set[blendfile.BlendFileBlock] = set(),
    ) -> typing.Iterator[blendfile.BlendFileBlock]:
        """Expand blocks with dependencies from other libraries."""

        log.info("inspecting: %s", bfile.filepath)
        if limit_to:
            self._queue_named_blocks(bfile, limit_to)
        else:
            self._queue_all_blocks(bfile)

        blocks_per_lib = yield from self._visit_blocks(bfile, limit_to)
        yield from self._visit_linked_blocks(blocks_per_lib)

    def _visit_blocks(self, bfile, limit_to):
        bpath = bpathlib.make_absolute(bfile.filepath)
        root_dir = bpathlib.BlendPath(bpath.parent)

        # Mapping from library path to data blocks to expand.
        blocks_per_lib = collections.defaultdict(set)

        while not self.to_visit.empty():
            block = self.to_visit.get()
            assert isinstance(block, blendfile.BlendFileBlock)
            if (bpath, block.addr_old) in self.blocks_yielded:
                continue

            if block.code == b"ID":
                # ID blocks represent linked-in assets. Those are the ones that
                # should be loaded from their own blend file and "expanded" to
                # the entire set of data blocks required to render them. We
                # defer the handling of those so that we can work with one
                # blend file at a time.
                lib = block.get_pointer(b"lib")
                lib_bpath = bpathlib.BlendPath(lib[b"name"]).absolute(root_dir)
                blocks_per_lib[lib_bpath].add(block)

                # The library block itself should also be reported, because it
                # represents a blend file that is a dependency as well.
                self.to_visit.put(lib)
                continue

            self._queue_dependencies(block)
            self.blocks_yielded.add((bpath, block.addr_old))
            yield block

        return blocks_per_lib

    def _visit_linked_blocks(self, blocks_per_lib):
        # We've gone through all the blocks in this file, now open the libraries
        # and iterate over the blocks referred there.
        for lib_bpath, idblocks in blocks_per_lib.items():
            lib_path = bpathlib.make_absolute(lib_bpath.to_path())

            if not lib_path.exists():
                log.warning("Library %s does not exist", lib_path)
                continue

            log.debug("Expanding %d blocks in %s", len(idblocks), lib_path)
            libfile = self.open_blendfile(lib_path)
            yield from self.iter_blocks(libfile, idblocks)

    def _queue_all_blocks(self, bfile: blendfile.BlendFile):
        log.debug("Queueing all blocks from file %s", bfile.filepath)
        for block in bfile.blocks:
            # Don't bother visiting DATA blocks, as we won't know what
            # to do with them anyway.
            if block.code == b"DATA":
                continue
            self.to_visit.put(block)

    def _queue_named_blocks(
        self, bfile: blendfile.BlendFile, limit_to: typing.Set[blendfile.BlendFileBlock]
    ):
        """Queue only the blocks referred to in limit_to.

        :param bfile:
        :param limit_to: set of ID blocks that name the blocks to queue.
            The queued blocks are loaded from the actual blend file, and
            selected by name.
        """

        for to_find in limit_to:
            assert to_find.code == b"ID"
            name_to_find = to_find[b"name"]
            code = name_to_find[:2]
            log.debug("Finding block %r with code %r", name_to_find, code)
            same_code = bfile.find_blocks_from_code(code)
            for block in same_code:
                if block.id_name == name_to_find:
                    log.debug("Queueing %r from file %s", block, bfile.filepath)
                    self.to_visit.put(block)

    def _queue_dependencies(self, block: blendfile.BlendFileBlock):
        for block in expanders.expand_block(block):
            assert isinstance(block, blendfile.BlendFileBlock), "unexpected %r" % block
            self.to_visit.put(block)


def iter_blocks(
    bfile: blendfile.BlendFile,
) -> typing.Iterator[blendfile.BlendFileBlock]:
    """Generator, yield all blocks in this file + required blocks in libs."""
    bi = BlockIterator()
    yield from bi.iter_blocks(bfile)
