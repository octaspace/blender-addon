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
# (c) 2014, Blender Foundation - Campbell Barton
# (c) 2018, Blender Foundation - Sybren A. Stüvel
"""Block walkers.

From a Blend file data block, iter_assts() yields all the referred-to assets.
"""

import functools
import logging
import typing

from blender_asset_tracer import blendfile, bpathlib, cdefs
from blender_asset_tracer.blendfile import iterators
from . import result, modifier_walkers

log = logging.getLogger(__name__)

_warned_about_types = set()  # type: typing.Set[bytes]
_funcs_for_code = {}  # type: typing.Dict[bytes, typing.Callable]


def iter_assets(block: blendfile.BlendFileBlock) -> typing.Iterator[result.BlockUsage]:
    """Generator, yield the assets used by this data block."""
    assert block.code != b"DATA"

    try:
        block_reader = _funcs_for_code[block.code]
    except KeyError:
        if block.code in _warned_about_types:
            return

        blocktype = block.code.decode()
        filepath = block.get(b"filepath", "", as_str=True)
        if filepath:
            log.debug(
                "No reader implemented for block type %r (filepath=%r)",
                blocktype,
                filepath,
            )
        else:
            log.debug("No reader implemented for block type %r", blocktype)
        _warned_about_types.add(block.code)
        return

    log.debug("Tracing block %r", block)
    yield from block_reader(block)


def dna_code(block_code: str):
    """Decorator, marks decorated func as handler for that DNA code."""

    assert isinstance(block_code, str)

    def decorator(wrapped):
        _funcs_for_code[block_code.encode()] = wrapped
        return wrapped

    return decorator


def skip_packed(wrapped):
    """Decorator, skip blocks where 'packedfile' is set to true."""

    @functools.wraps(wrapped)
    def wrapper(block: blendfile.BlendFileBlock, *args, **kwargs):
        if block.get(b"packedfile", default=False):
            log.debug("Datablock %r is packed; skipping", block.id_name)
            return

        yield from wrapped(block, *args, **kwargs)

    return wrapper


@dna_code("CF")
def cache_file(block: blendfile.BlendFileBlock) -> typing.Iterator[result.BlockUsage]:
    """Cache file data blocks."""
    path, field = block.get(b"filepath", return_field=True)
    yield result.BlockUsage(block, path, path_full_field=field)


@dna_code("IM")
@skip_packed
def image(block: blendfile.BlendFileBlock) -> typing.Iterator[result.BlockUsage]:
    """Image data blocks."""
    # old files miss this
    image_source = block.get(b"source", default=cdefs.IMA_SRC_FILE)
    if image_source not in {
        cdefs.IMA_SRC_FILE,
        cdefs.IMA_SRC_SEQUENCE,
        cdefs.IMA_SRC_MOVIE,
        cdefs.IMA_SRC_TILED,
    }:
        log.debug("skiping image source type %s", image_source)
        return

    pathname, field = block.get(b"name", return_field=True)
    is_sequence = image_source in {cdefs.IMA_SRC_SEQUENCE, cdefs.IMA_SRC_TILED}

    yield result.BlockUsage(block, pathname, is_sequence, path_full_field=field)


@dna_code("LI")
def library(block: blendfile.BlendFileBlock) -> typing.Iterator[result.BlockUsage]:
    """Library data blocks."""
    path, field = block.get(b"name", return_field=True)
    yield result.BlockUsage(block, path, path_full_field=field)

    # The 'filepath' also points to the blend file. However, this is set to the
    # absolute path of the file by Blender (see BKE_library_filepath_set). This
    # is thus not a property we have to report or rewrite.


@dna_code("ME")
def mesh(block: blendfile.BlendFileBlock) -> typing.Iterator[result.BlockUsage]:
    """Mesh data blocks."""
    block_external = block.get_pointer((b"ldata", b"external"), None)
    if block_external is None:
        block_external = block.get_pointer((b"fdata", b"external"), None)
    if block_external is None:
        return

    path, field = block_external.get(b"filename", return_field=True)
    yield result.BlockUsage(block, path, path_full_field=field)


@dna_code("MC")
def movie_clip(block: blendfile.BlendFileBlock) -> typing.Iterator[result.BlockUsage]:
    """MovieClip data blocks."""
    path, field = block.get(b"name", return_field=True)
    # TODO: The assumption that this is not a sequence may not be true for all modifiers.
    yield result.BlockUsage(block, path, is_sequence=False, path_full_field=field)


@dna_code("OB")
def object_block(block: blendfile.BlendFileBlock) -> typing.Iterator[result.BlockUsage]:
    """Object data blocks."""
    ctx = modifier_walkers.ModifierContext(owner=block)

    # 'ob->modifiers[...].filepath'
    for mod_idx, block_mod in enumerate(iterators.modifiers(block)):
        block_name = b"%s.modifiers[%d]" % (block.id_name, mod_idx)
        mod_type = block_mod[b"modifier", b"type"]
        log.debug("Tracing modifier %s, type=%d", block_name.decode(), mod_type)

        try:
            mod_handler = modifier_walkers.modifier_handlers[mod_type]
        except KeyError:
            continue
        yield from mod_handler(ctx, block_mod, block_name)


@dna_code("SC")
def scene(block: blendfile.BlendFileBlock) -> typing.Iterator[result.BlockUsage]:
    """Scene data blocks."""
    # Sequence editor is the only interesting bit.
    block_ed = block.get_pointer(b"ed")
    if block_ed is None:
        return

    single_asset_types = {
        cdefs.SEQ_TYPE_MOVIE,
        cdefs.SEQ_TYPE_SOUND_RAM,
        cdefs.SEQ_TYPE_SOUND_HD,
    }
    asset_types = single_asset_types.union({cdefs.SEQ_TYPE_IMAGE})

    for seq, seq_type in iterators.sequencer_strips(block_ed):
        if seq_type not in asset_types:
            continue

        seq_strip = seq.get_pointer(b"strip")
        if seq_strip is None:
            continue
        seq_stripdata = seq_strip.get_pointer(b"stripdata")
        if seq_stripdata is None:
            continue

        dirname, dn_field = seq_strip.get(b"dir", return_field=True)
        basename, bn_field = seq_stripdata.get(b"name", return_field=True)
        asset_path = bpathlib.BlendPath(dirname) / basename

        is_sequence = seq_type not in single_asset_types
        yield result.BlockUsage(
            seq_strip,
            asset_path,
            is_sequence=is_sequence,
            path_dir_field=dn_field,
            path_base_field=bn_field,
        )


@dna_code("SO")
@skip_packed
def sound(block: blendfile.BlendFileBlock) -> typing.Iterator[result.BlockUsage]:
    """Sound data blocks."""
    path, field = block.get(b"name", return_field=True)
    yield result.BlockUsage(block, path, path_full_field=field)


@dna_code("VF")
@skip_packed
def vector_font(block: blendfile.BlendFileBlock) -> typing.Iterator[result.BlockUsage]:
    """Vector Font data blocks."""
    path, field = block.get(b"name", return_field=True)
    if path == b"<builtin>":  # builtin font
        return
    yield result.BlockUsage(block, path, path_full_field=field)


@dna_code("LA")
@skip_packed
def lamp(block: blendfile.BlendFileBlock) -> typing.Iterator[result.BlockUsage]:
    """Lamp data blocks."""
    block_ntree = block.get_pointer(b"nodetree", None)
    if block_ntree is None:
        return
    for node in iterators.listbase(block_ntree.get_pointer((b"nodes", b"first"))):
        storage = node.get_pointer(b"storage")
        if not storage:
            continue

        # A storage block of `NodeShaderTexIES` type has a `filepath`, but not
        # all types that can be pointed to by the `storage` pointer do.
        path, field = storage.get(b"filepath", return_field=True, default=None)
        if path is None:
            continue

        yield result.BlockUsage(storage, path, path_full_field=field)


@dna_code("VO")
@skip_packed
def open_vdb(block: blendfile.BlendFileBlock) -> typing.Iterator[result.BlockUsage]:
    """OpenVDB data blocks."""
    path, field = block.get(b"filepath", return_field=True)
    is_sequence = bool(block.get(b"is_sequence"))

    yield result.BlockUsage(block, path, path_full_field=field, is_sequence=is_sequence)
