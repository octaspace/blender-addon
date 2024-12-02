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
"""Read-write utility functions."""

import struct
import typing


class EndianIO:
    # TODO(Sybren): note as UCHAR: struct.Struct = None and move actual structs to LittleEndianTypes
    UCHAR = struct.Struct(b"<B")
    SINT8 = struct.Struct(b"<b")
    USHORT = struct.Struct(b"<H")
    USHORT2 = struct.Struct(b"<HH")  # two shorts in a row
    SSHORT = struct.Struct(b"<h")
    UINT = struct.Struct(b"<I")
    SINT = struct.Struct(b"<i")
    FLOAT = struct.Struct(b"<f")
    ULONG = struct.Struct(b"<Q")

    @classmethod
    def _read(cls, fileobj: typing.IO[bytes], typestruct: struct.Struct):
        data = fileobj.read(typestruct.size)
        try:
            return typestruct.unpack(data)[0]
        except struct.error as ex:
            raise struct.error("%s (read %d bytes)" % (ex, len(data))) from None

    @classmethod
    def _write(
        cls, fileobj: typing.IO[bytes], typestruct: struct.Struct, value: typing.Any
    ):
        try:
            data = typestruct.pack(value)
        except struct.error as ex:
            raise struct.error(f"{ex} (write '{value}')")
        return fileobj.write(data)

    @classmethod
    def read_char(cls, fileobj: typing.IO[bytes]):
        return cls._read(fileobj, cls.UCHAR)

    @classmethod
    def write_char(cls, fileobj: typing.IO[bytes], value: int):
        return cls._write(fileobj, cls.UCHAR, value)

    @classmethod
    def read_int8(cls, fileobj: typing.IO[bytes]):
        return cls._read(fileobj, cls.SINT8)

    @classmethod
    def write_int8(cls, fileobj: typing.IO[bytes], value: int):
        return cls._write(fileobj, cls.SINT8, value)

    @classmethod
    def read_ushort(cls, fileobj: typing.IO[bytes]):
        return cls._read(fileobj, cls.USHORT)

    @classmethod
    def write_ushort(cls, fileobj: typing.IO[bytes], value: int):
        return cls._write(fileobj, cls.USHORT, value)

    @classmethod
    def read_short(cls, fileobj: typing.IO[bytes]):
        return cls._read(fileobj, cls.SSHORT)

    @classmethod
    def write_short(cls, fileobj: typing.IO[bytes], value: int):
        return cls._write(fileobj, cls.SSHORT, value)

    @classmethod
    def read_uint(cls, fileobj: typing.IO[bytes]):
        return cls._read(fileobj, cls.UINT)

    @classmethod
    def write_uint(cls, fileobj: typing.IO[bytes], value: int):
        return cls._write(fileobj, cls.UINT, value)

    @classmethod
    def read_int(cls, fileobj: typing.IO[bytes]):
        return cls._read(fileobj, cls.SINT)

    @classmethod
    def write_int(cls, fileobj: typing.IO[bytes], value: int):
        return cls._write(fileobj, cls.SINT, value)

    @classmethod
    def read_float(cls, fileobj: typing.IO[bytes]):
        return cls._read(fileobj, cls.FLOAT)

    @classmethod
    def write_float(cls, fileobj: typing.IO[bytes], value: float):
        return cls._write(fileobj, cls.FLOAT, value)

    @classmethod
    def read_ulong(cls, fileobj: typing.IO[bytes]):
        return cls._read(fileobj, cls.ULONG)

    @classmethod
    def write_ulong(cls, fileobj: typing.IO[bytes], value: int):
        return cls._write(fileobj, cls.ULONG, value)

    @classmethod
    def read_pointer(cls, fileobj: typing.IO[bytes], pointer_size: int):
        """Read a pointer from a file."""

        if pointer_size == 4:
            return cls.read_uint(fileobj)
        if pointer_size == 8:
            return cls.read_ulong(fileobj)
        raise ValueError("unsupported pointer size %d" % pointer_size)

    @classmethod
    def write_pointer(cls, fileobj: typing.IO[bytes], pointer_size: int, value: int):
        """Write a pointer to a file."""

        if pointer_size == 4:
            return cls.write_uint(fileobj, value)
        if pointer_size == 8:
            return cls.write_ulong(fileobj, value)
        raise ValueError("unsupported pointer size %d" % pointer_size)

    @classmethod
    def write_string(
        cls, fileobj: typing.IO[bytes], astring: str, fieldlen: int
    ) -> int:
        """Write a (truncated) string as UTF-8.

        The string will always be written 0-terminated.

        :param fileobj: the file to write to.
        :param astring: the string to write.
        :param fieldlen: the field length in bytes.
        :returns: the number of bytes written.
        """
        assert isinstance(astring, str)
        encoded = astring.encode("utf-8")

        # Take into account we also need space for a trailing 0-byte.
        maxlen = fieldlen - 1

        if len(encoded) >= maxlen:
            encoded = encoded[:maxlen]

            # Keep stripping off the last byte until the string
            # is valid UTF-8 again.
            while True:
                try:
                    encoded.decode("utf8")
                except UnicodeDecodeError:
                    encoded = encoded[:-1]
                else:
                    break

        return fileobj.write(encoded + b"\0")

    @classmethod
    def write_bytes(cls, fileobj: typing.IO[bytes], data: bytes, fieldlen: int) -> int:
        """Write (truncated) bytes.

        When len(data) < fieldlen, a terminating b'\0' will be appended.

        :returns: the number of bytes written.
        """
        assert isinstance(data, (bytes, bytearray))
        if len(data) >= fieldlen:
            to_write = data[0:fieldlen]
        else:
            to_write = data + b"\0"

        return fileobj.write(to_write)

    @classmethod
    def read_bytes0(cls, fileobj, length):
        data = fileobj.read(length)
        return cls.read_data0(data)

    @classmethod
    def read_data0_offset(cls, data, offset):
        add = data.find(b"\0", offset) - offset
        return data[offset : offset + add]

    @classmethod
    def read_data0(cls, data):
        add = data.find(b"\0")
        if add < 0:
            return data
        return data[:add]

    @classmethod
    def accepted_types(cls):
        """Return a mapping from type name to writer function.

        This is mostly to make it easier to get the correct number write
        function, given that Python's `int` and `float` can map to a whole range
        of C types.
        """
        return {
            b"char": cls.write_char,
            b"int8": cls.write_int8,
            b"ushort": cls.write_ushort,
            b"short": cls.write_short,
            b"uint": cls.write_uint,
            b"int": cls.write_int,
            b"ulong": cls.write_ulong,
            b"float": cls.write_float,
        }


class LittleEndianTypes(EndianIO):
    pass


class BigEndianTypes(LittleEndianTypes):
    UCHAR = struct.Struct(b">B")
    SINT8 = struct.Struct(b">b")
    USHORT = struct.Struct(b">H")
    USHORT2 = struct.Struct(b">HH")  # two shorts in a row
    SSHORT = struct.Struct(b">h")
    UINT = struct.Struct(b">I")
    SINT = struct.Struct(b">i")
    FLOAT = struct.Struct(b">f")
    ULONG = struct.Struct(b">Q")
