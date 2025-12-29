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

from dataclasses import dataclass
import logging
import os
import pathlib
import struct
import typing

from . import dna_io, exceptions

log = logging.getLogger(__name__)


@dataclass
class BHead4:
    code: bytes
    len: int
    old: int
    SDNAnr: int
    nr: int

@dataclass
class SmallBHead8:
    code: bytes
    len: int
    old: int
    SDNAnr: int
    nr: int

@dataclass
class LargeBHead8:
    code: bytes
    SDNAnr: int
    old: int
    len: int
    nr: int

class BlendFileHeader:
    """
    BlendFileHeader represents the first 12-17 bytes of a blend file.

    It contains information about the hardware architecture, which is relevant
    to the structure of the rest of the file.
    """

    magic: bytes
    file_format_version: int
    pointer_size: int
    is_little_endian: bool
    endian: typing.Type[dna_io.EndianIO]
    endian_str: bytes

    def __init__(self, fileobj: typing.IO[bytes], path: pathlib.Path) -> None:
        log.debug("reading blend-file-header %s", path)
        fileobj.seek(0, os.SEEK_SET)

        bytes_0_6 = fileobj.read(7)
        if bytes_0_6 != b'BLENDER':
            raise exceptions.BlendFileError("invalid first bytes %r" % bytes_0_6, path)
        self.magic = bytes_0_6

        byte_7 = fileobj.read(1)
        is_legacy_header = byte_7 in (b'_', b'-')
        if is_legacy_header:
            self.file_format_version = 0
            if byte_7 == b'_':
                self.pointer_size = 4
            elif byte_7 == b'-':
                self.pointer_size = 8
            else:
                raise exceptions.BlendFileError("invalid pointer size %r" % byte_7, path)
            byte_8 = fileobj.read(1)
            if byte_8 == b'v':
                self.is_little_endian = True
            elif byte_8 == b'V':
                self.is_little_endian = False
            else:
                raise exceptions.BlendFileError("invalid endian indicator %r" % byte_8, path)
            bytes_9_11 = fileobj.read(3)
            self.version = int(bytes_9_11)
        else:
            byte_8 = fileobj.read(1)
            header_size = int(byte_7 + byte_8)
            if header_size != 17:
                raise exceptions.BlendFileError("unknown file header size %d" % header_size, path)
            byte_9 = fileobj.read(1)
            if byte_9 != b'-':
                raise exceptions.BlendFileError("invalid file header", path)
            self.pointer_size = 8
            byte_10_11 = fileobj.read(2)
            self.file_format_version = int(byte_10_11)
            if self.file_format_version != 1:
                raise exceptions.BlendFileError("unsupported file format version %r" % self.file_format_version, path)
            byte_12 = fileobj.read(1)
            if byte_12 != b'v':
                raise exceptions.BlendFileError("invalid file header", path)
            self.is_little_endian = True
            byte_13_16 = fileobj.read(4)
            self.version = int(byte_13_16)

        if self.is_little_endian:
            self.endian_str = b'<'
            self.endian = dna_io.LittleEndianTypes
        else:
            self.endian_str = b'>'
            self.endian = dna_io.BigEndianTypes

    def create_block_header_struct(self) -> typing.Tuple[struct.Struct, typing.Type[typing.Union[BHead4, SmallBHead8, LargeBHead8]]]:
        """
        Returns a Struct instance for parsing data block headers and a corresponding
        Python class for accessing the right members. Ddepending on the .blend file,
        the order of the data members in the block header may be different.
        """
        assert self.file_format_version in (0, 1)
        if self.file_format_version == 1:
            header_struct = struct.Struct(b''.join((
                self.endian_str,
                # LargeBHead8.code
                b'4s',
                # LargeBHead8.SDNAnr
                b'i',
                # LargeBHead8.old
                b'Q',
                # LargeBHead8.len
                b'q',
                # LargeBHead8.nr
                b'q',
            )))
            return header_struct, LargeBHead8

        if self.pointer_size == 4:
            header_struct = struct.Struct(b''.join((
                self.endian_str,
                # BHead4.code
                b'4s',
                # BHead4.len
                b'i',
                # BHead4.old
                b'I',
                # BHead4.SDNAnr
                b'i',
                # BHead4.nr
                b'i',
            )))
            return header_struct, BHead4

        assert self.pointer_size == 8
        header_struct = struct.Struct(b''.join((
            self.endian_str,
            # SmallBHead8.code
            b'4s',
            # SmallBHead8.len
            b'i',
            # SmallBHead8.old
            b'Q',
            # SmallBHead8.SDNAnr
            b'i',
            # SmallBHead8.nr
            b'i',
        )))
        return header_struct, SmallBHead8
