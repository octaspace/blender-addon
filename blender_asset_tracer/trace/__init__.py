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
import pathlib
import typing

from blender_asset_tracer import blendfile
from . import result, blocks2assets, file2blocks, progress

log = logging.getLogger(__name__)

codes_to_skip = {
    # These blocks never have external assets:
    b"ID",
    b"WM",
    b"SN",
    # These blocks are skipped for now, until we have proof they point to
    # assets otherwise missed:
    b"GR",
    b"WO",
    b"BR",
    b"LS",
}


def deps(
    bfilepath: pathlib.Path, progress_cb: typing.Optional[progress.Callback] = None
) -> typing.Iterator[result.BlockUsage]:
    """Open the blend file and report its dependencies.

    :param bfilepath: File to open.
    :param progress_cb: Progress callback object.
    """

    bi = file2blocks.BlockIterator()
    if progress_cb:
        bi.progress_cb = progress_cb
    bfile = bi.open_blendfile(bfilepath)

    # Remember which block usages we've reported already, without keeping the
    # blocks themselves in memory.
    seen_hashes = set()  # type: typing.Set[int]

    for block in asset_holding_blocks(bi.iter_blocks(bfile)):
        for block_usage in blocks2assets.iter_assets(block):
            usage_hash = hash(block_usage)
            if usage_hash in seen_hashes:
                continue
            seen_hashes.add(usage_hash)
            yield block_usage


def asset_holding_blocks(
    blocks: typing.Iterable[blendfile.BlendFileBlock],
) -> typing.Iterator[blendfile.BlendFileBlock]:
    """Generator, yield data blocks that could reference external assets."""
    for block in blocks:
        assert isinstance(block, blendfile.BlendFileBlock)
        code = block.code

        # The longer codes are either arbitrary data or data blocks that
        # don't refer to external assets. The former data blocks will be
        # visited when we hit the two-letter datablocks that use them.
        if len(code) > 2 or code in codes_to_skip:
            continue

        yield block
