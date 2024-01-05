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
import logging
import os
import pathlib
import struct
import typing

from . import dna_io, exceptions

log = logging.getLogger(__name__)


class BlendFileHeader:
    """
    BlendFileHeader represents the first 12 bytes of a blend file.

    It contains information about the hardware architecture, which is relevant
    to the structure of the rest of the file.
    """

    structure = struct.Struct(b"7s1s1s3s")

    def __init__(self, fileobj: typing.IO[bytes], path: pathlib.Path) -> None:
        log.debug("reading blend-file-header %s", path)
        fileobj.seek(0, os.SEEK_SET)
        header = fileobj.read(self.structure.size)
        values = self.structure.unpack(header)

        self.magic = values[0]

        pointer_size_id = values[1]
        if pointer_size_id == b"-":
            self.pointer_size = 8
        elif pointer_size_id == b"_":
            self.pointer_size = 4
        else:
            raise exceptions.BlendFileError(
                "invalid pointer size %r" % pointer_size_id, path
            )

        endian_id = values[2]
        if endian_id == b"v":
            self.endian = dna_io.LittleEndianTypes
            self.endian_str = b"<"  # indication for struct.Struct()
        elif endian_id == b"V":
            self.endian = dna_io.BigEndianTypes
            self.endian_str = b">"  # indication for struct.Struct()
        else:
            raise exceptions.BlendFileError(
                "invalid endian indicator %r" % endian_id, path
            )

        version_id = values[3]
        self.version = int(version_id)

    def create_block_header_struct(self) -> struct.Struct:
        """Create a Struct instance for parsing data block headers."""
        return struct.Struct(
            b"".join(
                (
                    self.endian_str,
                    b"4sI",
                    b"I" if self.pointer_size == 4 else b"Q",
                    b"II",
                )
            )
        )
