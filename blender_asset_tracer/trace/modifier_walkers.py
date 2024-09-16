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
"""Modifier handling code used in blocks2assets.py

The modifier_xxx() functions all yield result.BlockUsage objects for external
files used by the modifiers.
"""

import logging
import typing

from .. import blendfile, bpathlib, cdefs
from . import result

log = logging.getLogger(__name__)
modifier_handlers = {}  # type: typing.Dict[int, typing.Callable]


class ModifierContext:
    """Meta-info for modifier expansion.

    Currently just contains the object on which the modifier is defined.
    """

    def __init__(self, owner: blendfile.BlendFileBlock) -> None:
        assert owner.dna_type_name == "Object"
        self.owner = owner


def mod_handler(dna_num: int):
    """Decorator, marks decorated func as handler for that modifier number."""

    assert isinstance(dna_num, int)

    def decorator(wrapped):
        modifier_handlers[dna_num] = wrapped
        return wrapped

    return decorator


@mod_handler(cdefs.eModifierType_MeshCache)
def modifier_filepath(
    ctx: ModifierContext, modifier: blendfile.BlendFileBlock, block_name: bytes
) -> typing.Iterator[result.BlockUsage]:
    """Just yield the 'filepath' field."""
    path, field = modifier.get(b"filepath", return_field=True)
    yield result.BlockUsage(
        modifier, path, path_full_field=field, block_name=block_name
    )


@mod_handler(cdefs.eModifierType_MeshSequenceCache)
def modifier_mesh_sequence_cache(
    ctx: ModifierContext, modifier: blendfile.BlendFileBlock, block_name: bytes
) -> typing.Iterator[result.BlockUsage]:
    """Yield the Alembic file(s) used by this modifier"""
    cache_file = modifier.get_pointer(b"cache_file")
    if cache_file is None:
        return

    is_sequence = bool(cache_file[b"is_sequence"])
    cache_block_name = cache_file.id_name
    assert cache_block_name is not None

    path, field = cache_file.get(b"filepath", return_field=True)
    yield result.BlockUsage(
        cache_file,
        path,
        path_full_field=field,
        is_sequence=is_sequence,
        block_name=cache_block_name,
    )


@mod_handler(cdefs.eModifierType_Ocean)
def modifier_ocean(
    ctx: ModifierContext, modifier: blendfile.BlendFileBlock, block_name: bytes
) -> typing.Iterator[result.BlockUsage]:
    if not modifier[b"cached"]:
        return

    path, field = modifier.get(b"cachepath", return_field=True)
    # The path indicates the directory containing the cached files.
    yield result.BlockUsage(
        modifier, path, is_sequence=True, path_full_field=field, block_name=block_name
    )


def _get_texture(
    prop_name: bytes, dblock: blendfile.BlendFileBlock, block_name: bytes
) -> typing.Iterator[result.BlockUsage]:
    """Yield block usages from a texture propery.

    Assumes dblock[prop_name] is a texture data block.
    """
    if dblock is None:
        return

    tx = dblock.get_pointer(prop_name)
    yield from _get_image(b"ima", tx, block_name)


def _get_image(
    prop_name: bytes,
    dblock: typing.Optional[blendfile.BlendFileBlock],
    block_name: bytes,
) -> typing.Iterator[result.BlockUsage]:
    """Yield block usages from an image propery.

    Assumes dblock[prop_name] is an image data block.
    """
    if not dblock:
        return

    try:
        ima = dblock.get_pointer(prop_name)
    except KeyError as ex:
        # No such property, just return.
        log.debug("_get_image() called with non-existing property name: %s", ex)
        return

    if not ima:
        return

    path, field = ima.get(b"name", return_field=True)
    yield result.BlockUsage(ima, path, path_full_field=field, block_name=block_name)


@mod_handler(cdefs.eModifierType_Displace)
@mod_handler(cdefs.eModifierType_Wave)
def modifier_texture(
    ctx: ModifierContext, modifier: blendfile.BlendFileBlock, block_name: bytes
) -> typing.Iterator[result.BlockUsage]:
    return _get_texture(b"texture", modifier, block_name)


@mod_handler(cdefs.eModifierType_WeightVGEdit)
@mod_handler(cdefs.eModifierType_WeightVGMix)
@mod_handler(cdefs.eModifierType_WeightVGProximity)
def modifier_mask_texture(
    ctx: ModifierContext, modifier: blendfile.BlendFileBlock, block_name: bytes
) -> typing.Iterator[result.BlockUsage]:
    return _get_texture(b"mask_texture", modifier, block_name)


@mod_handler(cdefs.eModifierType_UVProject)
def modifier_image(
    ctx: ModifierContext, modifier: blendfile.BlendFileBlock, block_name: bytes
) -> typing.Iterator[result.BlockUsage]:
    yield from _get_image(b"image", modifier, block_name)


def _walk_point_cache(
    ctx: ModifierContext,
    block_name: bytes,
    bfile: blendfile.BlendFile,
    pointcache: blendfile.BlendFileBlock,
    extension: bytes,
):
    flag = pointcache[b"flag"]
    if flag & cdefs.PTCACHE_EXTERNAL:
        path, field = pointcache.get(b"path", return_field=True)
        log.info("    external cache at %s", path)
        bpath = bpathlib.BlendPath(path)
        yield result.BlockUsage(
            pointcache,
            bpath,
            path_full_field=field,
            is_sequence=True,
            block_name=block_name,
        )
    elif flag & cdefs.PTCACHE_DISK_CACHE:
        # See ptcache_path() in pointcache.c
        name, field = pointcache.get(b"name", return_field=True)
        if not name:
            # See ptcache_filename() in pointcache.c
            idname = ctx.owner[b"id", b"name"]
            name = idname[2:].hex().upper().encode()
        path = b"//%b%b/%b_*%b" % (
            cdefs.PTCACHE_PATH,
            bfile.filepath.stem.encode(),
            name,
            extension,
        )
        log.info("   disk cache at %s", path)
        bpath = bpathlib.BlendPath(path)
        yield result.BlockUsage(
            pointcache,
            bpath,
            path_full_field=field,
            is_sequence=True,
            block_name=block_name,
        )


@mod_handler(cdefs.eModifierType_ParticleSystem)
def modifier_particle_system(
    ctx: ModifierContext, modifier: blendfile.BlendFileBlock, block_name: bytes
) -> typing.Iterator[result.BlockUsage]:
    psys = modifier.get_pointer(b"psys")
    if psys is None:
        return

    pointcache = psys.get_pointer(b"pointcache")
    if pointcache is None:
        return

    yield from _walk_point_cache(
        ctx, block_name, modifier.bfile, pointcache, cdefs.PTCACHE_EXT
    )


@mod_handler(cdefs.eModifierType_Fluidsim)
def modifier_fluid_sim(
    ctx: ModifierContext, modifier: blendfile.BlendFileBlock, block_name: bytes
) -> typing.Iterator[result.BlockUsage]:
    my_log = log.getChild("modifier_fluid_sim")

    fss = modifier.get_pointer(b"fss")
    if fss is None:
        my_log.debug(
            "Modifier %r (%r) has no fss", modifier[b"modifier", b"name"], block_name
        )
        return

    path, field = fss.get(b"surfdataPath", return_field=True)

    # This may match more than is used by Blender, but at least it shouldn't
    # miss any files.
    # The 'fluidsurface' prefix is defined in source/blender/makesdna/DNA_object_fluidsim_types.h
    bpath = bpathlib.BlendPath(path)
    yield result.BlockUsage(
        fss, bpath, path_full_field=field, is_sequence=True, block_name=block_name
    )


@mod_handler(cdefs.eModifierType_Smokesim)
def modifier_smoke_sim(
    ctx: ModifierContext, modifier: blendfile.BlendFileBlock, block_name: bytes
) -> typing.Iterator[result.BlockUsage]:
    my_log = log.getChild("modifier_smoke_sim")

    domain = modifier.get_pointer(b"domain")
    if domain is None:
        my_log.debug(
            "Modifier %r (%r) has no domain", modifier[b"modifier", b"name"], block_name
        )
        return

    pointcache = domain.get_pointer(b"point_cache")
    if pointcache is None:
        return

    format = domain.get(b"cache_file_format")
    extensions = {
        cdefs.PTCACHE_FILE_PTCACHE: cdefs.PTCACHE_EXT,
        cdefs.PTCACHE_FILE_OPENVDB: cdefs.PTCACHE_EXT_VDB,
    }
    yield from _walk_point_cache(
        ctx, block_name, modifier.bfile, pointcache, extensions[format]
    )


@mod_handler(cdefs.eModifierType_Fluid)
def modifier_fluid(
    ctx: ModifierContext, modifier: blendfile.BlendFileBlock, block_name: bytes
) -> typing.Iterator[result.BlockUsage]:
    my_log = log.getChild("modifier_fluid")

    domain = modifier.get_pointer(b"domain")
    if domain is None:
        my_log.debug(
            "Modifier %r (%r) has no domain", modifier[b"modifier", b"name"], block_name
        )
        return

    # See fluid_bake_startjob() in physics_fluid.c
    path = domain[b"cache_directory"]
    path, field = domain.get(b"cache_directory", return_field=True)

    log.info("   fluid cache at %s", path)
    bpath = bpathlib.BlendPath(path)
    yield result.BlockUsage(
        domain,
        bpath,
        path_full_field=field,
        is_sequence=True,
        block_name=block_name,
    )


@mod_handler(cdefs.eModifierType_Cloth)
def modifier_cloth(
    ctx: ModifierContext, modifier: blendfile.BlendFileBlock, block_name: bytes
) -> typing.Iterator[result.BlockUsage]:
    pointcache = modifier.get_pointer(b"point_cache")
    if pointcache is None:
        return

    yield from _walk_point_cache(
        ctx, block_name, modifier.bfile, pointcache, cdefs.PTCACHE_EXT
    )


@mod_handler(cdefs.eModifierType_DynamicPaint)
def modifier_dynamic_paint(
    ctx: ModifierContext, modifier: blendfile.BlendFileBlock, block_name: bytes
) -> typing.Iterator[result.BlockUsage]:
    my_log = log.getChild("modifier_dynamic_paint")

    canvas_settings = modifier.get_pointer(b"canvas")
    if canvas_settings is None:
        my_log.debug(
            "Modifier %r (%r) has no canvas_settings",
            modifier[b"modifier", b"name"],
            block_name,
        )
        return

    surfaces = canvas_settings.get_pointer((b"surfaces", b"first"))

    for surface in blendfile.iterators.listbase(surfaces):
        surface_block_name = block_name + b"%s.canvas_settings.surfaces[%d]"
        point_cache = surface.get_pointer(b"pointcache")
        if point_cache is None:
            my_log.debug(
                "Surface %r (%r) has no pointcache",
                surface[b"surface", b"name"],
                surface_block_name,
            )
            continue

        yield from _walk_point_cache(
            ctx, surface_block_name, modifier.bfile, point_cache, cdefs.PTCACHE_EXT
        )
