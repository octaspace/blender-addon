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
"""Low-level functions called by file2block.

Those can expand data blocks and yield their dependencies (e.g. other data
blocks necessary to render/display/work with the given data block).
"""
import logging
import typing

from .. import blendfile, cdefs
from ..blendfile import iterators

# Don't warn about these types at all.
_warned_about_types = {b"LI", b"DATA"}
_funcs_for_code = {}  # type: typing.Dict[bytes, typing.Callable]
log = logging.getLogger(__name__)


def expand_block(
    block: blendfile.BlendFileBlock,
) -> typing.Iterator[blendfile.BlendFileBlock]:
    """Generator, yield the data blocks used by this data block."""

    try:
        expander = _funcs_for_code[block.code]
    except KeyError:
        if block.code not in _warned_about_types:
            log.debug("No expander implemented for block type %r", block.code.decode())
            _warned_about_types.add(block.code)
        return

    log.debug("Expanding block %r", block)
    for dependency in expander(block):
        if not dependency:
            # Filter out falsy blocks, i.e. None values.
            # Allowing expanders to yield None makes them more consise.
            continue
        if dependency.code == b"DATA":
            log.warn(
                "expander yielded block %s which will be ignored in later iteration",
                dependency,
            )
        yield dependency


def dna_code(block_code: str):
    """Decorator, marks decorated func as expander for that DNA code."""

    assert isinstance(block_code, str)

    def decorator(wrapped):
        _funcs_for_code[block_code.encode()] = wrapped
        return wrapped

    return decorator


def _expand_generic_material(block: blendfile.BlendFileBlock):
    array_len = block.get(b"totcol")
    yield from block.iter_array_of_pointers(b"mat", array_len)


def _expand_generic_mtex(block: blendfile.BlendFileBlock):
    if not block.dna_type.has_field(b"mtex"):
        # mtex was removed in Blender 2.8
        return

    for mtex in block.iter_fixed_array_of_pointers(b"mtex"):
        yield mtex.get_pointer(b"tex")
        yield mtex.get_pointer(b"object")


def _expand_generic_nodetree(block: blendfile.BlendFileBlock):
    if block.dna_type.dna_type_id == b"ID":
        # This is a placeholder for a linked node tree.
        yield block
        return

    assert (
        block.dna_type.dna_type_id == b"bNodeTree"
    ), f"Expected bNodeTree, got {block.dna_type.dna_type_id.decode()})"

    nodes = block.get_pointer((b"nodes", b"first"))

    # See DNA_node_types.h
    socket_types_with_value_pointer = {
        cdefs.SOCK_OBJECT,  #  bNodeSocketValueObject
        cdefs.SOCK_IMAGE,  #  bNodeSocketValueImage
        cdefs.SOCK_COLLECTION,  #  bNodeSocketValueCollection
        cdefs.SOCK_TEXTURE,  #  bNodeSocketValueTexture
        cdefs.SOCK_MATERIAL,  #  bNodeSocketValueMaterial
    }

    for node in iterators.listbase(nodes):
        if node[b"type"] == cdefs.CMP_NODE_R_LAYERS:
            continue

        # The 'id' property points to whatever is used by the node
        # (like the image in an image texture node).
        yield node.get_pointer(b"id")

        # Default values of inputs can also point to ID datablocks.
        inputs = node.get_pointer((b"inputs", b"first"))
        for input in iterators.listbase(inputs):
            if input[b"type"] not in socket_types_with_value_pointer:
                continue
            value_container = input.get_pointer(b"default_value")
            if not value_container:
                continue
            value = value_container.get_pointer(b"value")
            yield value


def _expand_generic_idprops(block: blendfile.BlendFileBlock):
    """Yield ID datablocks and their libraries referenced from ID properties."""

    # TODO(@sybren): this code is very crude, and happens to work on ID
    # properties of Geometry Nodes modifiers, which is what it was written for.
    # It should probably be rewritten to properly iterate over & recurse into
    # all groups.
    settings_props = block.get_pointer((b"settings", b"properties"))
    if not settings_props:
        return

    subprops = settings_props.get_pointer((b"data", b"group", b"first"))
    for idprop in iterators.listbase(subprops):
        if idprop[b"type"] != cdefs.IDP_ID:
            continue
        id_datablock = idprop.get_pointer((b"data", b"pointer"))
        if not id_datablock:
            continue
        yield id_datablock


def _expand_generic_nodetree_id(block: blendfile.BlendFileBlock):
    if block.bfile.header.version >= 500 and block.bfile.file_subversion >= 4:
        # Introduced in Blender 5.0, commit bd61e69be5a7c96f1e5da1c86aafc17b839e049f
        block_ntree = block.get_pointer(b"compositing_node_group", None)
    else:
        block_ntree = block.get_pointer(b"nodetree", None)
    if block_ntree is not None:
        yield from _expand_generic_nodetree(block_ntree)


def _expand_generic_animdata(block: blendfile.BlendFileBlock):
    block_adt = block.get_pointer(b"adt")
    if block_adt:
        yield block_adt.get_pointer(b"action")
    # TODO, NLA


@dna_code("AR")
def _expand_armature(block: blendfile.BlendFileBlock):
    yield from _expand_generic_animdata(block)


@dna_code("CU")
def _expand_curve(block: blendfile.BlendFileBlock):
    yield from _expand_generic_animdata(block)
    yield from _expand_generic_material(block)

    for fieldname in (
        b"vfont",
        b"vfontb",
        b"vfonti",
        b"vfontbi",
        b"bevobj",
        b"taperobj",
        b"textoncurve",
    ):
        yield block.get_pointer(fieldname)


@dna_code("GR")
def _expand_group(block: blendfile.BlendFileBlock):
    log.debug("Collection/group Block: %s (name=%s)", block, block.id_name)

    objects = block.get_pointer((b"gobject", b"first"))
    for item in iterators.listbase(objects):
        yield item.get_pointer(b"ob")

    # Recurse through child collections.
    try:
        children = block.get_pointer((b"children", b"first"))
    except KeyError:
        # 'children' was introduced in Blender 2.8 collections
        pass
    else:
        for child in iterators.listbase(children):
            subcoll = child.get_pointer(b"collection")
            if subcoll is None:
                continue

            if subcoll.dna_type_id == b"ID":
                # This issue happened while recursing a linked-in 'Hidden'
                # collection in the Chimes set of the Spring project. Such
                # collections named 'Hidden' were apparently created while
                # converting files from Blender 2.79 to 2.80. This error
                # isn't reproducible with just Blender 2.80.
                yield subcoll
                continue

            log.debug(
                "recursing into child collection %s (name=%r, type=%r)",
                subcoll,
                subcoll.id_name,
                subcoll.dna_type_name,
            )
            yield from _expand_group(subcoll)


@dna_code("LA")
def _expand_lamp(block: blendfile.BlendFileBlock):
    yield from _expand_generic_animdata(block)
    yield from _expand_generic_nodetree_id(block)
    yield from _expand_generic_mtex(block)


@dna_code("MA")
def _expand_material(block: blendfile.BlendFileBlock):
    yield from _expand_generic_animdata(block)
    yield from _expand_generic_nodetree_id(block)
    yield from _expand_generic_mtex(block)

    try:
        yield block.get_pointer(b"group")
    except KeyError:
        # Groups were removed from Blender 2.8
        pass


@dna_code("MB")
def _expand_metaball(block: blendfile.BlendFileBlock):
    yield from _expand_generic_animdata(block)
    yield from _expand_generic_material(block)


@dna_code("ME")
def _expand_mesh(block: blendfile.BlendFileBlock):
    yield from _expand_generic_animdata(block)
    yield from _expand_generic_material(block)
    yield block.get_pointer(b"texcomesh")
    # TODO, TexFace? - it will be slow, we could simply ignore :S


@dna_code("NT")
def _expand_node_tree(block: blendfile.BlendFileBlock):
    yield from _expand_generic_animdata(block)
    yield from _expand_generic_nodetree(block)


@dna_code("OB")
def _expand_object(block: blendfile.BlendFileBlock):
    yield from _expand_generic_animdata(block)
    yield from _expand_generic_material(block)

    yield block.get_pointer(b"data")

    if block[b"transflag"] & cdefs.OB_DUPLIGROUP:
        yield block.get_pointer(b"dup_group")

    yield block.get_pointer(b"proxy")
    yield block.get_pointer(b"proxy_group")

    # 'ob->pose->chanbase[...].custom'
    block_pose = block.get_pointer(b"pose")
    if block_pose:
        assert block_pose.dna_type.dna_type_id == b"bPose"
        # sdna_index_bPoseChannel = block_pose.file.sdna_index_from_id[b'bPoseChannel']
        channels = block_pose.get_pointer((b"chanbase", b"first"))
        for pose_chan in iterators.listbase(channels):
            yield pose_chan.get_pointer(b"custom")

    # Expand the objects 'ParticleSettings' via 'ob->particlesystem[...].part'
    # sdna_index_ParticleSystem = block.file.sdna_index_from_id.get(b'ParticleSystem')
    # if sdna_index_ParticleSystem is not None:
    psystems = block.get_pointer((b"particlesystem", b"first"))
    for psystem in iterators.listbase(psystems):
        yield psystem.get_pointer(b"part")

    # Modifiers can also refer to other datablocks, which should also get expanded.
    for block_mod in iterators.modifiers(block):
        mod_type = block_mod[b"modifier", b"type"]
        # Currently only node groups are supported. If the support should expand
        # to more types, something more intelligent than this should be made.
        if mod_type == cdefs.eModifierType_Nodes:
            yield from _expand_generic_idprops(block_mod)
            yield block_mod.get_pointer(b"node_group")


@dna_code("PA")
def _expand_particle_settings(block: blendfile.BlendFileBlock):
    yield from _expand_generic_animdata(block)
    yield from _expand_generic_mtex(block)

    block_ren_as = block[b"ren_as"]
    if block_ren_as == cdefs.PART_DRAW_GR:
        yield block.get_pointer(b"dup_group")
    elif block_ren_as == cdefs.PART_DRAW_OB:
        yield block.get_pointer(b"dup_ob")


@dna_code("SC")
def _expand_scene(block: blendfile.BlendFileBlock):
    yield from _expand_generic_animdata(block)
    yield from _expand_generic_nodetree_id(block)
    yield block.get_pointer(b"camera")
    yield block.get_pointer(b"world")
    yield block.get_pointer(b"set", default=None)
    yield block.get_pointer(b"clip", default=None)

    # sdna_index_Base = block.file.sdna_index_from_id[b'Base']
    # for item in bf_utils.iter_ListBase(block.get_pointer((b'base', b'first'))):
    #     yield item.get_pointer(b'object', sdna_index_refine=sdna_index_Base)
    bases = block.get_pointer((b"base", b"first"))
    for base in iterators.listbase(bases):
        yield base.get_pointer(b"object")

    # Sequence Editor
    block_ed = block.get_pointer(b"ed")
    if not block_ed:
        return

    strip_type_to_field = {
        cdefs.SEQ_TYPE_SCENE: b"scene",
        cdefs.SEQ_TYPE_MOVIECLIP: b"clip",
        cdefs.SEQ_TYPE_MASK: b"mask",
        cdefs.SEQ_TYPE_SOUND_RAM: b"sound",
    }
    for strip, strip_type in iterators.sequencer_strips(block_ed):
        try:
            field_name = strip_type_to_field[strip_type]
        except KeyError:
            continue
        yield strip.get_pointer(field_name)


@dna_code("TE")
def _expand_texture(block: blendfile.BlendFileBlock):
    yield from _expand_generic_animdata(block)
    yield from _expand_generic_nodetree_id(block)
    yield block.get_pointer(b"ima")


@dna_code("WO")
def _expand_world(block: blendfile.BlendFileBlock):
    yield from _expand_generic_animdata(block)
    yield from _expand_generic_nodetree_id(block)
    yield from _expand_generic_mtex(block)
