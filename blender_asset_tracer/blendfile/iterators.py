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
# (c) 2009, At Mind B.V. - Jeroen Bakker
# (c) 2014, Blender Foundation - Campbell Barton
# (c) 2018, Blender Foundation - Sybren A. Stüvel
import typing
import copy

from .. import cdefs
from . import BlendFileBlock
from .dna import FieldPath


def listbase(
    block: typing.Optional[BlendFileBlock], next_path: FieldPath = b"next"
) -> typing.Iterator[BlendFileBlock]:
    """Generator, yields all blocks in the ListBase linked list."""
    while block:
        yield block
        next_ptr = block[next_path]
        if next_ptr == 0:
            break
        block = block.bfile.dereference_pointer(next_ptr)


def sequencer_strips(
    sequence_editor: BlendFileBlock,
) -> typing.Iterator[typing.Tuple[BlendFileBlock, int]]:
    """Generator, yield all sequencer strip blocks with their type number.

    Recurses into meta strips, yielding both the meta strip itself and the
    strips contained within it.

    See blender_asset_tracer.cdefs.SEQ_TYPE_xxx for the type numbers.
    """

    def iter_seqbase(seqbase) -> typing.Iterator[typing.Tuple[BlendFileBlock, int]]:
        for seq in listbase(seqbase):
            seq.refine_type(b"Sequence")
            seq_type = seq[b"type"]
            yield seq, seq_type

            if seq_type == cdefs.SEQ_TYPE_META:
                # Recurse into this meta-sequence.
                subseq = seq.get_pointer((b"seqbase", b"first"))
                yield from iter_seqbase(subseq)

    sbase = sequence_editor.get_pointer((b"seqbase", b"first"))
    yield from iter_seqbase(sbase)


def modifiers(object_block: BlendFileBlock) -> typing.Iterator[BlendFileBlock]:
    """Generator, yield the object's modifiers."""

    # 'ob->modifiers[...]'
    mods = object_block.get_pointer((b"modifiers", b"first"))
    yield from listbase(mods, next_path=(b"modifier", b"next"))


def dynamic_array(block: BlendFileBlock) -> typing.Iterator[BlendFileBlock]:
    """
    Generator that yields each element of a dynamic array as a separate block.

    Dynamic arrays are multiple contiguous elements accessed via a single pointer.
    BAT interprets these as a single data block, making it hard to access individual elements.
    This function divides the array into individual blocks by creating modified copies of the original block.
    """

    offset = block.file_offset
    element_size = block.dna_type.size

    for i in range(block.count):
        new_block = copy.copy(block)
        new_block.file_offset = offset
        new_block.size = element_size

        yield new_block
        offset += element_size
