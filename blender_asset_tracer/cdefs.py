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

"""Constants defined in C."""

# DNA_sequence_types.h (Sequence.type)
SEQ_TYPE_IMAGE = 0
SEQ_TYPE_META = 1
SEQ_TYPE_SCENE = 2
SEQ_TYPE_MOVIE = 3
SEQ_TYPE_SOUND_RAM = 4
SEQ_TYPE_SOUND_HD = 5
SEQ_TYPE_MOVIECLIP = 6
SEQ_TYPE_MASK = 7
SEQ_TYPE_EFFECT = 8

IMA_SRC_FILE = 1
IMA_SRC_SEQUENCE = 2
IMA_SRC_MOVIE = 3
IMA_SRC_TILED = 6  # UDIM

# DNA_modifier_types.h
eModifierType_Wave = 7
eModifierType_Displace = 14
eModifierType_UVProject = 15
eModifierType_ParticleSystem = 19
eModifierType_Cloth = 22
eModifierType_Fluidsim = 26
eModifierType_Smokesim = 31
eModifierType_WeightVGEdit = 36
eModifierType_WeightVGMix = 37
eModifierType_WeightVGProximity = 38
eModifierType_Ocean = 39
eModifierType_DynamicPaint = 40
eModifierType_MeshCache = 46
eModifierType_MeshSequenceCache = 52
eModifierType_Fluid = 56
eModifierType_Nodes = 57

# NodesModifierBakeFlag
NODES_MODIFIER_BAKE_CUSTOM_PATH = 1 << 1

# DNA_particle_types.h
PART_DRAW_OB = 7
PART_DRAW_GR = 8

# DNA_object_types.h
# Object.transflag
OB_DUPLIGROUP = 1 << 8

# DNA_object_force_types.h
PTCACHE_DISK_CACHE = 64
PTCACHE_EXTERNAL = 512

# DNA_ID_types.h
IDP_STRING = 0
IDP_INT = 1
IDP_FLOAT = 2
IDP_ARRAY = 5
IDP_GROUP = 6
IDP_ID = 7
IDP_DOUBLE = 8
IDP_IDPARRAY = 9
IDP_NUMTYPES = 10

# DNA_node_types.h
SOCK_CUSTOM = -1  # socket has no integer type
SOCK_FLOAT = 0
SOCK_VECTOR = 1
SOCK_RGBA = 2
SOCK_SHADER = 3
SOCK_BOOLEAN = 4
SOCK_MESH = 5  # deprecated
SOCK_INT = 6
SOCK_STRING = 7
SOCK_OBJECT = 8
SOCK_IMAGE = 9
SOCK_GEOMETRY = 10
SOCK_COLLECTION = 11
SOCK_TEXTURE = 12
SOCK_MATERIAL = 13

# BKE_pointcache.h
PTCACHE_FILE_PTCACHE = 0
PTCACHE_FILE_OPENVDB = 1
PTCACHE_EXT = b".bphys"
PTCACHE_EXT_VDB = b".vdb"
PTCACHE_PATH = b"blendcache_"

# BKE_node.h
SH_NODE_TEX_IMAGE = 143
CMP_NODE_R_LAYERS = 221