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
# (c) 2021, Blender Foundation

import collections
import enum
import gzip
import logging
import os
import pathlib
import tempfile
import typing

# Blender 3.0 replaces GZip with ZStandard compression.
# Since this is not a standard library package, be careful importing it and
# treat it as optional.
try:
    import zstandard

    has_zstandard = True
except ImportError:
    has_zstandard = False

from . import exceptions

# Magic numbers, see https://en.wikipedia.org/wiki/List_of_file_signatures
BLENDFILE_MAGIC = b"BLENDER"
GZIP_MAGIC = b"\x1f\x8b"

# ZStandard has two magic numbers, the 2nd of which doesn't use the last nibble.
# See https://tools.ietf.org/id/draft-kucherawy-dispatch-zstd-00.html#rfc.section.2.1.1
# and https://tools.ietf.org/id/draft-kucherawy-dispatch-zstd-00.html#rfc.section.2.3
ZSTD_MAGIC = b"\x28\xB5\x2F\xFD"
ZSTD_MAGIC_SKIPPABLE = b"\x50\x2A\x4D\x18"
ZSTD_MAGIC_SKIPPABLE_MASK = b"\xF0\xFF\xFF\xFF"

log = logging.getLogger(__name__)


# @dataclasses.dataclass
DecompressedFileInfo = collections.namedtuple(
    "DecompressedFileInfo", "is_compressed path fileobj"
)
# is_compressed: bool
# path: pathlib.Path
# """The path of the decompressed file, or the input path if the file is not compressed."""
# fileobj: BinaryIO


class Compression(enum.Enum):
    UNRECOGNISED = -1
    NONE = 0
    GZIP = 1
    ZSTD = 2


def open(path: pathlib.Path, mode: str, buffer_size: int) -> DecompressedFileInfo:
    """Open the file, decompressing it into a temporary file if necesssary."""
    fileobj = path.open(mode, buffering=buffer_size)  # typing.IO[bytes]
    compression = find_compression_type(fileobj)

    if compression == Compression.UNRECOGNISED:
        fileobj.close()
        raise exceptions.BlendFileError("File is not a blend file", path)

    if compression == Compression.NONE:
        return DecompressedFileInfo(
            is_compressed=False,
            path=path,
            fileobj=fileobj,
        )

    log.debug("%s-compressed blendfile detected: %s", compression.name, path)

    # Decompress to a temporary file.
    tmpfile = tempfile.NamedTemporaryFile()
    fileobj.seek(0, os.SEEK_SET)

    decompressor = _decompressor(fileobj, mode, compression)

    with decompressor as compressed_file:
        magic = compressed_file.read(len(BLENDFILE_MAGIC))
        if magic != BLENDFILE_MAGIC:
            raise exceptions.BlendFileError("Compressed file is not a blend file", path)

        data = magic
        while data:
            tmpfile.write(data)
            data = compressed_file.read(buffer_size)

    # Further interaction should be done with the uncompressed file.
    fileobj.close()
    return DecompressedFileInfo(
        is_compressed=True,
        path=pathlib.Path(tmpfile.name),
        fileobj=tmpfile,
    )


def find_compression_type(fileobj: typing.IO[bytes]) -> Compression:
    fileobj.seek(0, os.SEEK_SET)

    # This assumes that all magics are not longer than "BLENDER".
    magic = fileobj.read(len(BLENDFILE_MAGIC))
    if _matches_magic(magic, BLENDFILE_MAGIC):
        return Compression.NONE

    if _matches_magic(magic, GZIP_MAGIC):
        return Compression.GZIP

    if _matches_magic(magic, ZSTD_MAGIC):
        return Compression.ZSTD
    if _matches_magic_masked(magic, ZSTD_MAGIC_SKIPPABLE, ZSTD_MAGIC_SKIPPABLE_MASK):
        return Compression.ZSTD

    return Compression.UNRECOGNISED


def _matches_magic_masked(value: bytes, magic: bytes, mask: bytes) -> bool:
    """Returns True only if value & mask == magic & mask (ignoring trailing bytes in value)."""

    assert len(magic) == len(mask)

    int_value = int.from_bytes(value[: len(magic)], "little")
    int_magic = int.from_bytes(magic, "little")
    int_mask = int.from_bytes(mask, "little")

    return int_value & int_mask == int_magic & int_mask


def _matches_magic(value: bytes, magic: bytes) -> bool:
    """Returns True only if value == magic (ignoring trailing bytes in value)."""

    return value[: len(magic)] == magic


def _decompressor(
    fileobj: typing.IO[bytes], mode: str, compression: Compression
) -> typing.IO[bytes]:
    if compression == Compression.GZIP:
        decompressor = gzip.GzipFile(fileobj=fileobj, mode=mode)
        return typing.cast(typing.IO[bytes], decompressor)

    if compression == Compression.ZSTD:
        if not has_zstandard:
            # The required module was not loaded, raise an exception about this.
            raise EnvironmentError(
                "File is compressed with ZStandard, install the `zstandard` module to support this."
            )
        dctx = zstandard.ZstdDecompressor()
        return dctx.stream_reader(fileobj)

    raise ValueError("Unsupported compression type: %s" % compression)
