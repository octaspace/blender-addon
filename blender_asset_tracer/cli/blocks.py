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
"""List count and total size of datablocks in a blend file."""

import collections
import logging
import pathlib

from .. import blendfile
from . import common

log = logging.getLogger(__name__)


class BlockTypeInfo:
    def __init__(self):
        self.total_bytes = 0
        self.num_blocks = 0
        self.sizes = []
        self.blocks = []
        self.name = "unset"


def add_parser(subparsers):
    """Add argparser for this subcommand."""

    parser = subparsers.add_parser("blocks", help=__doc__)
    parser.set_defaults(func=cli_blocks)
    parser.add_argument("blendfile", type=pathlib.Path)
    parser.add_argument(
        "-d",
        "--dump",
        default=False,
        action="store_true",
        help="Hex-dump the biggest block",
    )
    parser.add_argument(
        "-l",
        "--limit",
        default=10,
        type=int,
        help="Limit the number of DNA types shown, default is 10",
    )


def by_total_bytes(info: BlockTypeInfo) -> int:
    return info.total_bytes


def block_key(block: blendfile.BlendFileBlock) -> str:
    return "%s-%s" % (block.dna_type_name, block.code.decode())


def cli_blocks(args):
    bpath = args.blendfile
    if not bpath.exists():
        log.fatal("File %s does not exist", args.blendfile)
        return 3

    per_blocktype = collections.defaultdict(BlockTypeInfo)

    print("Opening %s" % bpath)
    bfile = blendfile.BlendFile(bpath)

    print("Inspecting %s" % bpath)
    for block in bfile.blocks:
        if block.code == b"DNA1":
            continue
        index_as = block_key(block)

        info = per_blocktype[index_as]
        info.name = index_as
        info.total_bytes += block.size
        info.num_blocks += 1
        info.sizes.append(block.size)
        info.blocks.append(block)

    fmt = "%-35s %10s %10s %10s %10s"
    print(fmt % ("Block type", "Total Size", "Num blocks", "Avg Size", "Median"))
    print(fmt % (35 * "-", 10 * "-", 10 * "-", 10 * "-", 10 * "-"))
    infos = sorted(per_blocktype.values(), key=by_total_bytes, reverse=True)
    for info in infos[: args.limit]:
        median_size = sorted(info.sizes)[len(info.sizes) // 2]
        print(
            fmt
            % (
                info.name,
                common.humanize_bytes(info.total_bytes),
                info.num_blocks,
                common.humanize_bytes(info.total_bytes // info.num_blocks),
                common.humanize_bytes(median_size),
            )
        )

    print(70 * "-")
    # From the blocks of the most space-using category, the biggest block.
    biggest_block = sorted(infos[0].blocks, key=lambda blck: blck.size, reverse=True)[0]
    print(
        "Biggest %s block is %s at address %s"
        % (
            block_key(biggest_block),
            common.humanize_bytes(biggest_block.size),
            biggest_block.addr_old,
        )
    )

    print("Finding what points there")
    addr_to_find = biggest_block.addr_old
    found_pointer = False
    for block in bfile.blocks:
        for prop_path, prop_value in block.items_recursive():
            if not isinstance(prop_value, int) or prop_value != addr_to_find:
                continue
            print("    ", block, prop_path)
            found_pointer = True

    if not found_pointer:
        print("Nothing points there")

    if args.dump:
        print("Hexdump:")
        bfile.fileobj.seek(biggest_block.file_offset)
        data = bfile.fileobj.read(biggest_block.size)
        line_len_bytes = 32
        import codecs

        for offset in range(0, len(data), line_len_bytes):
            line = codecs.encode(data[offset : offset + line_len_bytes], "hex").decode()
            print(
                "%6d -" % offset,
                " ".join(line[i : i + 2] for i in range(0, len(line), 2)),
            )
