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


import pathlib


class BlendFileError(Exception):
    """Raised when there was an error reading/parsing a blend file."""

    def __init__(self, message: str, filepath: pathlib.Path) -> None:
        super().__init__(message)
        self.filepath = filepath

    def __str__(self):
        return "%s: %s" % (super().__str__(), self.filepath)


class NoDNA1Block(BlendFileError):
    """Raised when the blend file contains no DNA1 block."""


class NoReaderImplemented(NotImplementedError):
    """Raised when reading a property of a non-implemented type.

    This indicates that the property should be read using some dna.Struct.

    :type dna_name: blender_asset_tracer.blendfile.dna.Name
    :type dna_type: blender_asset_tracer.blendfile.dna.Struct
    """

    def __init__(self, message: str, dna_name, dna_type) -> None:
        super().__init__(message)
        self.dna_name = dna_name
        self.dna_type = dna_type


class NoWriterImplemented(NotImplementedError):
    """Raised when writing a property of a non-implemented type.

    :type dna_name: blender_asset_tracer.blendfile.dna.Name
    :type dna_type: blender_asset_tracer.blendfile.dna.Struct
    """

    def __init__(self, message: str, dna_name, dna_type) -> None:
        super().__init__(message)
        self.dna_name = dna_name
        self.dna_type = dna_type


class SegmentationFault(Exception):
    """Raised when a pointer to a non-existant datablock was dereferenced."""

    def __init__(self, message: str, address: int, field_path=None) -> None:
        super().__init__(message)
        self.address = address
        self.field_path = field_path
