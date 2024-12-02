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

import atexit
import collections
import functools
import gzip
import logging
import os
import struct
import pathlib
import shutil
import tempfile
import typing

from . import exceptions, dna, header, magic_compression
from blender_asset_tracer import bpathlib

log = logging.getLogger(__name__)

FILE_BUFFER_SIZE = 1024 * 1024
BFBList = typing.List["BlendFileBlock"]

_cached_bfiles = {}  # type: typing.Dict[pathlib.Path, BlendFile]


def open_cached(
    path: pathlib.Path, mode="rb", assert_cached: typing.Optional[bool] = None
) -> "BlendFile":
    """Open a blend file, ensuring it is only opened once."""
    my_log = log.getChild("open_cached")
    bfile_path = bpathlib.make_absolute(path)

    if assert_cached is not None:
        is_cached = bfile_path in _cached_bfiles
        if assert_cached and not is_cached:
            raise AssertionError("File %s was not cached" % bfile_path)
        elif not assert_cached and is_cached:
            raise AssertionError("File %s was cached" % bfile_path)

    try:
        bfile = _cached_bfiles[bfile_path]
    except KeyError:
        my_log.debug("Opening non-cached %s", path)
        bfile = BlendFile(path, mode=mode)
        _cached_bfiles[bfile_path] = bfile
    else:
        my_log.debug("Returning cached %s", path)

    return bfile


@atexit.register
def close_all_cached() -> None:
    if not _cached_bfiles:
        # Don't even log anything when there is nothing to close
        return

    log.debug("Closing %d cached blend files", len(_cached_bfiles))
    for bfile in list(_cached_bfiles.values()):
        bfile.close()
    _cached_bfiles.clear()


def _cache(path: pathlib.Path, bfile: "BlendFile"):
    """Add a BlendFile to the cache."""
    bfile_path = bpathlib.make_absolute(path)
    _cached_bfiles[bfile_path] = bfile


def _uncache(path: pathlib.Path):
    """Remove a BlendFile object from the cache."""
    bfile_path = bpathlib.make_absolute(path)
    _cached_bfiles.pop(bfile_path, None)


class BlendFile:
    """Representation of a blend file.

    :ivar filepath: which file this object represents.
    :ivar raw_filepath: which file is accessed; same as filepath for
        uncompressed files, but a temporary file for compressed files.
    :ivar fileobj: the file object that's being accessed.
    """

    log = log.getChild("BlendFile")

    strict_pointer_mode = True
    """Raise exceptions.SegmentationFault when dereferencing an unknown pointer.

    Set to False to disable this exception, and to return None instead.
    """

    def __init__(self, path: pathlib.Path, mode="rb") -> None:
        """Create a BlendFile instance for the blend file at the path.

        Opens the file for reading or writing pending on the access. Compressed
        blend files are uncompressed to a temporary location before opening.

        :param path: the file to open
        :param mode: see mode description of pathlib.Path.open()
        """
        self.filepath = path
        self.raw_filepath = path
        self._is_modified = False
        self.fileobj = self._open_file(path, mode)

        self.blocks = []  # type: BFBList
        """BlendFileBlocks of this file, in disk order."""

        self.code_index = collections.defaultdict(
            list
        )  # type: typing.Dict[bytes, BFBList]
        self.structs = []  # type: typing.List[dna.Struct]
        self.sdna_index_from_id = {}  # type: typing.Dict[bytes, int]
        self.block_from_addr = {}  # type: typing.Dict[int, BlendFileBlock]

        self.header = header.BlendFileHeader(self.fileobj, self.raw_filepath)
        self.block_header_struct = self.header.create_block_header_struct()
        self._load_blocks()

    def _open_file(self, path: pathlib.Path, mode: str) -> typing.IO[bytes]:
        """Open a blend file, decompressing if necessary.

        This does not parse the blend file yet, just makes sure that
        self.fileobj is opened and that self.filepath and self.raw_filepath
        are set.

        :raises exceptions.BlendFileError: when the blend file doesn't have the
            correct magic bytes.
        """

        decompressed = magic_compression.open(path, mode, FILE_BUFFER_SIZE)

        self.filepath = path
        self.is_compressed = decompressed.is_compressed
        self.raw_filepath = decompressed.path

        return decompressed.fileobj

    def _load_blocks(self) -> None:
        """Read the blend file to load its DNA structure to memory."""

        self.structs.clear()
        self.sdna_index_from_id.clear()
        while True:
            block = BlendFileBlock(self)
            if block.code == b"ENDB":
                break

            if block.code == b"DNA1":
                self.decode_structs(block)
            else:
                self.fileobj.seek(block.size, os.SEEK_CUR)

            self.blocks.append(block)
            self.code_index[block.code].append(block)
            self.block_from_addr[block.addr_old] = block

        if not self.structs:
            raise exceptions.NoDNA1Block(
                "No DNA1 block in file, not a valid .blend file", self.filepath
            )

    def __repr__(self) -> str:
        clsname = self.__class__.__qualname__
        if self.filepath == self.raw_filepath:
            return "<%s %r>" % (clsname, self.filepath)
        return "<%s %r reading from %r>" % (clsname, self.filepath, self.raw_filepath)

    def __enter__(self) -> "BlendFile":
        return self

    def __exit__(self, exctype, excvalue, traceback) -> None:
        self.close()

    def copy_and_rebind(self, path: pathlib.Path, mode="rb") -> None:
        """Change which file is bound to this BlendFile.

        This allows cloning a previously opened file, and rebinding it to reuse
        the already-loaded DNA structs and data blocks.
        """
        log.debug("Rebinding %r to %s", self, path)

        self.close()
        _uncache(self.filepath)

        self.log.debug("Copying %s to %s", self.filepath, path)
        # TODO(Sybren): remove str() calls when targeting Python 3.6+
        # dst needs to be a file and not a directory
        shutil.copyfile(str(self.filepath), str(path))

        self.fileobj = self._open_file(path, mode=mode)
        _cache(path, self)

    @property
    def is_modified(self) -> bool:
        return self._is_modified

    def mark_modified(self) -> None:
        """Recompess the file when it is closed."""
        self.log.debug("Marking %s as modified", self.raw_filepath)
        self._is_modified = True

    def find_blocks_from_code(self, code: bytes) -> typing.List["BlendFileBlock"]:
        assert isinstance(code, bytes)
        return self.code_index[code]

    def close(self) -> None:
        """Close the blend file.

        Recompresses the blend file if it was compressed and changed.
        """
        if not self.fileobj:
            return

        if self._is_modified:
            log.debug("closing blend file %s after it was modified", self.raw_filepath)

        if self._is_modified and self.is_compressed:
            log.debug("GZip-recompressing modified blend file %s", self.raw_filepath)
            self.fileobj.seek(os.SEEK_SET, 0)

            with gzip.open(str(self.filepath), "wb") as gzfile:
                while True:
                    data = self.fileobj.read(FILE_BUFFER_SIZE)
                    if not data:
                        break
                    gzfile.write(data)
            log.debug("GZip-compression to %s finished", self.filepath)

        # Close the file object after recompressing, as it may be a temporary
        # file that'll disappear as soon as we close it.
        self.fileobj.close()
        self._is_modified = False

        try:
            del _cached_bfiles[self.filepath]
        except KeyError:
            pass

    def ensure_subtype_smaller(self, sdna_index_curr, sdna_index_next) -> None:
        # never refine to a smaller type
        curr_struct = self.structs[sdna_index_curr]
        next_struct = self.structs[sdna_index_next]
        if curr_struct.size > next_struct.size:
            raise RuntimeError(
                "Can't refine to smaller type (%s -> %s)"
                % (
                    curr_struct.dna_type_id.decode("utf-8"),
                    next_struct.dna_type_id.decode("utf-8"),
                )
            )

    def decode_structs(self, block: "BlendFileBlock"):
        """
        DNACatalog is a catalog of all information in the DNA1 file-block
        """
        self.log.debug("building DNA catalog")

        # Get some names in the local scope for faster access.
        structs = self.structs
        sdna_index_from_id = self.sdna_index_from_id
        endian = self.header.endian
        shortstruct = endian.USHORT
        shortstruct2 = endian.USHORT2
        intstruct = endian.UINT
        assert intstruct.size == 4

        def pad_up_4(off: int) -> int:
            return (off + 3) & ~3

        data = self.fileobj.read(block.size)
        types = []
        typenames = []

        offset = 8
        names_len = intstruct.unpack_from(data, offset)[0]
        offset += 4

        self.log.debug("building #%d names" % names_len)
        for _ in range(names_len):
            typename = endian.read_data0_offset(data, offset)
            offset = offset + len(typename) + 1
            typenames.append(dna.Name(typename))

        offset = pad_up_4(offset)
        offset += 4
        types_len = intstruct.unpack_from(data, offset)[0]
        offset += 4
        self.log.debug("building #%d types" % types_len)
        for _ in range(types_len):
            dna_type_id = endian.read_data0_offset(data, offset)
            types.append(dna.Struct(dna_type_id))
            offset += len(dna_type_id) + 1

        offset = pad_up_4(offset)
        offset += 4
        self.log.debug("building #%d type-lengths" % types_len)
        for i in range(types_len):
            typelen = shortstruct.unpack_from(data, offset)[0]
            offset = offset + 2
            types[i].size = typelen

        offset = pad_up_4(offset)
        offset += 4

        structs_len = intstruct.unpack_from(data, offset)[0]
        offset += 4
        log.debug("building #%d structures" % structs_len)
        pointer_size = self.header.pointer_size
        for sdna_index in range(structs_len):
            struct_type_index, fields_len = shortstruct2.unpack_from(data, offset)
            offset += 4

            dna_struct = types[struct_type_index]
            sdna_index_from_id[dna_struct.dna_type_id] = sdna_index
            structs.append(dna_struct)

            dna_offset = 0

            for field_index in range(fields_len):
                field_type_index, field_name_index = shortstruct2.unpack_from(
                    data, offset
                )
                offset += 4

                dna_type = types[field_type_index]
                dna_name = typenames[field_name_index]

                if dna_name.is_pointer or dna_name.is_method_pointer:
                    dna_size = pointer_size * dna_name.array_size
                else:
                    dna_size = dna_type.size * dna_name.array_size

                field = dna.Field(dna_type, dna_name, dna_size, dna_offset)
                dna_struct.append_field(field)
                dna_offset += dna_size

    def abspath(self, relpath: bpathlib.BlendPath) -> bpathlib.BlendPath:
        """Construct an absolute path from a blendfile-relative path."""

        if relpath.is_absolute():
            return relpath

        bfile_dir = self.filepath.absolute().parent
        root = bpathlib.BlendPath(bfile_dir)
        abspath = relpath.absolute(root)

        my_log = self.log.getChild("abspath")
        my_log.debug(
            "Resolved %s relative to %s to %s", relpath, self.filepath, abspath
        )

        return abspath

    def dereference_pointer(self, address: int) -> typing.Optional["BlendFileBlock"]:
        """Return the pointed-to block, or raise SegmentationFault.

        When BlendFile.strict_pointer_mode is False, the exception will not be
        thrown, but None will be returned.
        """

        try:
            return self.block_from_addr[address]
        except KeyError:
            if self.strict_pointer_mode:
                raise exceptions.SegmentationFault(
                    "address does not exist", address
                ) from None
            log.warning(
                "Silenced SegmentationFault caused by dereferencing invalid pointer"
                " (0x%x) because strict_pointer_mode is off.",
                address,
            )
            return None

    def struct(self, name: bytes) -> dna.Struct:
        index = self.sdna_index_from_id[name]
        return self.structs[index]


@functools.total_ordering
class BlendFileBlock:
    """
    Instance of a struct.
    """

    # Due to the huge number of BlendFileBlock objects created for packing a
    # production-size blend file, using slots here actually makes the
    # dependency tracer significantly (p<0.001) faster. In my test case the
    # speed improvement was 16% for a 'bam list' command.
    __slots__ = (
        "bfile",
        "code",
        "size",
        "addr_old",
        "sdna_index",
        "count",
        "file_offset",
        "endian",
        "_id_name",
    )

    log = log.getChild("BlendFileBlock")
    old_structure = struct.Struct(b"4sI")
    """old blend files ENDB block structure"""

    def __init__(self, bfile: BlendFile) -> None:
        self.bfile = bfile

        # Defaults; actual values are set by interpreting the block header.
        self.code = b""
        self.size = 0
        self.addr_old = 0
        self.sdna_index = 0
        self.count = 0
        self.file_offset = 0
        """Offset in bytes from start of file to beginning of the data block.

        Points to the data after the block header.
        """
        self.endian = bfile.header.endian
        self._id_name = ...  # type: typing.Union[None, ellipsis, bytes]

        header_struct = bfile.block_header_struct
        data = bfile.fileobj.read(header_struct.size)
        if len(data) != header_struct.size:
            self.log.warning(
                "Blend file %s seems to be truncated, "
                "expected %d bytes but could read only %d",
                bfile.filepath,
                header_struct.size,
                len(data),
            )
            self.code = b"ENDB"
            return

        # header size can be 8, 20, or 24 bytes long
        # 8: old blend files ENDB block (exception)
        # 20: normal headers 32 bit platform
        # 24: normal headers 64 bit platform
        if len(data) <= 15:
            self.log.debug("interpreting block as old-style ENB block")
            blockheader = self.old_structure.unpack(data)
            self.code = self.endian.read_data0(blockheader[0])
            return

        blockheader = header_struct.unpack(data)
        self.code = self.endian.read_data0(blockheader[0])
        if self.code != b"ENDB":
            self.size = blockheader[1]
            self.addr_old = blockheader[2]
            self.sdna_index = blockheader[3]
            self.count = blockheader[4]
            self.file_offset = bfile.fileobj.tell()

    def __repr__(self) -> str:
        return "<%s.%s (%s), size=%d at %s>" % (
            self.__class__.__name__,
            self.dna_type_name,
            self.code.decode(),
            self.size,
            hex(self.addr_old),
        )

    def __hash__(self) -> int:
        return hash((self.code, self.addr_old, self.bfile.filepath))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BlendFileBlock):
            return False
        return (
            self.code == other.code
            and self.addr_old == other.addr_old
            and self.bfile.filepath == other.bfile.filepath
        )

    def __lt__(self, other: "BlendFileBlock") -> bool:
        """Order blocks by file path and offset within that file."""
        if not isinstance(other, BlendFileBlock):
            raise NotImplemented()
        my_key = self.bfile.filepath, self.file_offset
        other_key = other.bfile.filepath, other.file_offset
        return my_key < other_key

    def __bool__(self) -> bool:
        """Data blocks are always True."""
        return True

    @property
    def dna_type(self) -> dna.Struct:
        return self.bfile.structs[self.sdna_index]

    @property
    def dna_type_id(self) -> bytes:
        return self.dna_type.dna_type_id

    @property
    def dna_type_name(self) -> str:
        return self.dna_type_id.decode("ascii")

    @property
    def id_name(self) -> typing.Optional[bytes]:
        """Same as block[b'id', b'name']; None if there is no such field.

        Evaluated only once, so safe to call multiple times without producing
        excessive disk I/O.
        """
        if self._id_name is ...:
            try:
                self._id_name = self[b"id", b"name"]
            except KeyError:
                self._id_name = None

        # TODO(Sybren): figure out how to let mypy know self._id_name cannot
        # be ellipsis at this point.
        return self._id_name  # type: ignore

    def refine_type_from_index(self, sdna_index: int):
        """Change the DNA Struct associated with this block.

        Use to make a block type more specific, for example when you have a
        modifier but need to access it as SubSurfModifier.

        :param sdna_index: the SDNA index of the DNA type.
        """
        assert type(sdna_index) is int
        sdna_index_curr = self.sdna_index
        self.bfile.ensure_subtype_smaller(sdna_index_curr, sdna_index)
        self.sdna_index = sdna_index

    def refine_type(self, dna_type_id: bytes):
        """Change the DNA Struct associated with this block.

        Use to make a block type more specific, for example when you have a
        modifier but need to access it as SubSurfModifier.

        :param dna_type_id: the name of the DNA type.
        """
        assert isinstance(dna_type_id, bytes)
        sdna_index = self.bfile.sdna_index_from_id[dna_type_id]
        self.refine_type_from_index(sdna_index)

    def abs_offset(self, path: dna.FieldPath) -> typing.Tuple[int, int]:
        """Compute the absolute file offset of the field.

        :returns: tuple (offset in bytes, length of array in items)
        """
        field, field_offset = self.dna_type.field_from_path(
            self.bfile.header.pointer_size, path
        )
        return self.file_offset + field_offset, field.name.array_size

    def get(
        self,
        path: dna.FieldPath,
        default=...,
        null_terminated=True,
        as_str=False,
        return_field=False,
    ) -> typing.Any:
        """Read a property and return the value.

        :param path: name of the property (like `b'loc'`), tuple of names
            to read a sub-property (like `(b'id', b'name')`), or tuple of
            name and index to read one item from an array (like
            `(b'loc', 2)`)
        :param default: The value to return when the field does not exist.
            Use Ellipsis (the default value) to raise a KeyError instead.
        :param null_terminated: Only used when reading bytes or strings. When
            True, stops reading at the first zero byte; be careful with this
            when reading binary data.
        :param as_str: When True, automatically decode bytes to string
            (assumes UTF-8 encoding).
        :param return_field: When True, returns tuple (dna.Field, value).
            Otherwise just returns the value.
        """
        self.bfile.fileobj.seek(self.file_offset, os.SEEK_SET)

        dna_struct = self.bfile.structs[self.sdna_index]
        field, value = dna_struct.field_get(
            self.bfile.header,
            self.bfile.fileobj,
            path,
            default=default,
            null_terminated=null_terminated,
            as_str=as_str,
        )
        if return_field:
            return value, field
        return value

    def raw_data(self) -> bytes:
        """Read low-level raw data of this datablock."""
        self.bfile.fileobj.seek(self.file_offset, os.SEEK_SET)
        return self.bfile.fileobj.read(self.size)

    def as_string(self) -> str:
        """Interpret the bytes of this datablock as null-terminated utf8 string."""
        the_bytes = self.raw_data()
        try:
            first_null = the_bytes.index(0)
        except ValueError:
            pass
        else:
            the_bytes = the_bytes[:first_null]
        return the_bytes.decode()

    def get_recursive_iter(
        self,
        path: dna.FieldPath,
        path_root: dna.FieldPath = b"",
        default=...,
        null_terminated=True,
        as_str=True,
    ) -> typing.Iterator[typing.Tuple[dna.FieldPath, typing.Any]]:
        """Generator, yields (path, property value) tuples.

        If a property cannot be decoded, a string representing its DNA type
        name is used as its value instead, between pointy brackets.
        """
        path_full = path  # type: dna.FieldPath
        if path_root:
            if isinstance(path_root, bytes):
                path_root = (path_root,)
            if isinstance(path, bytes):
                path = (path,)
            path_full = tuple(path_root) + tuple(path)

        try:
            # Try accessing as simple property
            yield (path_full, self.get(path_full, default, null_terminated, as_str))
        except exceptions.NoReaderImplemented as ex:
            # This was not a simple property, so recurse into its DNA Struct.
            dna_type = ex.dna_type
            struct_index = self.bfile.sdna_index_from_id.get(dna_type.dna_type_id)
            if struct_index is None:
                yield (path_full, "<%s>" % dna_type.dna_type_id.decode("ascii"))
                return

            # Recurse through the fields.
            for f in dna_type.fields:
                yield from self.get_recursive_iter(
                    f.name.name_only,
                    path_full,
                    default=default,
                    null_terminated=null_terminated,
                    as_str=as_str,
                )

    def hash(self) -> int:
        """Generate a pointer-independent hash for the block.

        Generates a 'hash' that can be used instead of addr_old as block id,
        which should be 'stable' across .blend file load & save (i.e. it does
        not changes due to pointer addresses variations).
        """
        # TODO This implementation is most likely far from optimal... and CRC32
        # is not kown as the best hashing algo either. But for now does the job!
        import zlib

        dna_type = self.dna_type
        pointer_size = self.bfile.header.pointer_size

        hsh = 1
        for path, value in self.items_recursive():
            field, _ = dna_type.field_from_path(pointer_size, path)
            if field.name.is_pointer:
                continue
            hsh = zlib.adler32(str(value).encode(), hsh)
        return hsh

    def set(self, path: bytes, value):
        dna_struct = self.bfile.structs[self.sdna_index]
        self.bfile.mark_modified()
        self.bfile.fileobj.seek(self.file_offset, os.SEEK_SET)
        return dna_struct.field_set(self.bfile.header, self.bfile.fileobj, path, value)

    def get_pointer(
        self,
        path: dna.FieldPath,
        default=...,
    ) -> typing.Union[None, "BlendFileBlock"]:
        """Same as get() but dereferences a pointer.

        :raises exceptions.SegmentationFault: when there is no datablock with
            the pointed-to address.
        """
        result = self.get(path, default=default)

        # If it's not an integer, we have no pointer to follow and this may
        # actually be a non-pointer property.
        if type(result) is not int:
            return result

        if result == 0:
            return None

        try:
            return self.bfile.dereference_pointer(result)
        except exceptions.SegmentationFault as ex:
            ex.field_path = path
            raise

    def iter_array_of_pointers(
        self, path: dna.FieldPath, array_size: int
    ) -> typing.Iterator["BlendFileBlock"]:
        """Dereference pointers from an array-of-pointers field.

        Use this function when you have a field like Mesh materials:
        `Mat **mat`

        :param path: The array-of-pointers field.
        :param array_size: Number of items in the array. If None, the
            on-disk size of the DNA field is divided by the pointer size to
            obtain the array size.
        """
        if array_size == 0:
            return

        array = self.get_pointer(path)
        assert array is not None
        assert array.code == b"DATA", (
            "Array data block should have code DATA, is %r" % array.code.decode()
        )
        file_offset = array.file_offset

        endian = self.bfile.header.endian
        ps = self.bfile.header.pointer_size

        for i in range(array_size):
            fileobj = self.bfile.fileobj
            fileobj.seek(file_offset + ps * i, os.SEEK_SET)
            address = endian.read_pointer(fileobj, ps)
            if address == 0:
                continue
            dereferenced = self.bfile.dereference_pointer(address)
            if dereferenced is None:
                # This can happen when strict pointer mode is disabled.
                continue
            yield dereferenced

    def iter_fixed_array_of_pointers(
        self, path: dna.FieldPath
    ) -> typing.Iterator["BlendFileBlock"]:
        """Yield blocks from a fixed-size array field.

        Use this function when you have a field like lamp textures:
        `MTex *mtex[18]`

        The size of the array is determined automatically by the size in bytes
        of the field divided by the pointer size of the blend file.

        :param path: The array field.
        :raises KeyError: if the path does not exist.
        """

        dna_struct = self.dna_type
        ps = self.bfile.header.pointer_size
        endian = self.bfile.header.endian
        fileobj = self.bfile.fileobj

        field, offset_in_struct = dna_struct.field_from_path(ps, path)
        array_size = field.size // ps

        for i in range(array_size):
            fileobj.seek(self.file_offset + offset_in_struct + ps * i, os.SEEK_SET)
            address = endian.read_pointer(fileobj, ps)
            if not address:
                # Fixed-size arrays contain 0-pointers.
                continue

            dereferenced = self.bfile.dereference_pointer(address)
            if dereferenced is None:
                # This can happen when strict pointer mode is disabled.
                continue
            yield dereferenced

    def __getitem__(self, path: dna.FieldPath):
        return self.get(path)

    def __setitem__(self, item: bytes, value) -> None:
        self.set(item, value)

    def keys(self) -> typing.Iterator[bytes]:
        """Generator, yields all field names of this block."""
        return (f.name.name_only for f in self.dna_type.fields)

    def values(self) -> typing.Iterable[typing.Any]:
        for k in self.keys():
            try:
                yield self[k]
            except exceptions.NoReaderImplemented as ex:
                yield "<%s>" % ex.dna_type.dna_type_id.decode("ascii")

    def items(self) -> typing.Iterable[typing.Tuple[bytes, typing.Any]]:
        for k in self.keys():
            try:
                yield (k, self[k])
            except exceptions.NoReaderImplemented as ex:
                yield (k, "<%s>" % ex.dna_type.dna_type_id.decode("ascii"))

    def items_recursive(
        self,
    ) -> typing.Iterator[typing.Tuple[dna.FieldPath, typing.Any]]:
        """Generator, yields (property path, property value) recursively for all properties."""
        for k in self.keys():
            yield from self.get_recursive_iter(k, as_str=False)


def set_strict_pointer_mode(strict_pointers: bool) -> None:
    """Control behaviour when a pointer to unknown memory is dereferenced.

    Strict pointer mode raise exceptions.SegmentationFault when dereferencing an
    unknown pointer. This is the default.

    Set to False to disable this exception, and to return None instead, i.e. to
    ignore such pointers. Note that this can cause None to be returned from a
    non-nil pointer.
    """

    BlendFile.strict_pointer_mode = strict_pointers
