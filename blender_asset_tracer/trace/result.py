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
import functools
import logging
import pathlib
import typing
from typing import Optional

from .. import blendfile, bpathlib
from ..blendfile import dna
from . import file_sequence

log = logging.getLogger(__name__)


@functools.total_ordering
class BlockUsage:
    """Represents the use of an asset by a data block.

    :ivar block_name: an identifying name for this block. Defaults to the ID
        name of the block.
    :ivar block:
    :ivar asset_path: The path of the asset, if is_sequence=False. Otherwise
        it can be either a glob pattern (must contain a * byte) or the path of
        the first file in the sequence.
    :ivar is_sequence: Indicates whether this file is alone (False), the
        first of a sequence (True, and the path points to a file), or a
        directory containing a sequence (True, and path points to a directory).
        In certain cases such files should be reported once (f.e. when
        rewriting the source field to another path), and in other cases the
        sequence should be expanded (f.e. when copying all assets to a BAT
        Pack).
    :ivar path_full_field: field containing the full path of this asset.
    :ivar path_dir_field: field containing the parent path (i.e. the
        directory) of this asset.
    :ivar path_base_field: field containing the basename of this asset.
    """

    def __init__(
        self,
        block: blendfile.BlendFileBlock,
        asset_path: bpathlib.BlendPath,
        is_sequence: bool = False,
        path_full_field: Optional[dna.Field] = None,
        path_dir_field: Optional[dna.Field] = None,
        path_base_field: Optional[dna.Field] = None,
        block_name: bytes = b"",
    ) -> None:
        if block_name:
            self.block_name = block_name
        else:
            self.block_name = self.guess_block_name(block)

        assert isinstance(block, blendfile.BlendFileBlock)
        assert isinstance(asset_path, (bytes, bpathlib.BlendPath)), (
            "asset_path should be BlendPath, not %r" % type(asset_path)
        )

        if path_full_field is None:
            assert isinstance(path_dir_field, dna.Field), (
                "path_dir_field should be dna.Field, not %r" % type(path_dir_field)
            )
            assert isinstance(path_base_field, dna.Field), (
                "path_base_field should be dna.Field, not %r" % type(path_base_field)
            )
        else:
            assert isinstance(path_full_field, dna.Field), (
                "path_full_field should be dna.Field, not %r" % type(path_full_field)
            )

        if isinstance(asset_path, bytes):
            asset_path = bpathlib.BlendPath(asset_path)

        self.block = block
        self.asset_path = asset_path
        self.is_sequence = bool(is_sequence)
        self.path_full_field = path_full_field
        self.path_dir_field = path_dir_field
        self.path_base_field = path_base_field

        # cached by __fspath__()
        self._abspath = None  # type: typing.Optional[pathlib.Path]

    @staticmethod
    def guess_block_name(block: blendfile.BlendFileBlock) -> bytes:
        try:
            return block[b"id", b"name"]
        except KeyError:
            pass
        try:
            return block[b"name"]
        except KeyError:
            pass
        return b"-unnamed-"

    def __repr__(self):
        if self.path_full_field is None:
            field_name = (
                self.path_dir_field.name.name_full.decode()
                + "/"
                + self.path_base_field.name.name_full.decode()
            )
        else:
            field_name = self.path_full_field.name.name_full.decode()
        return "<BlockUsage name=%r type=%r field=%r asset=%r%s>" % (
            self.block_name,
            self.block.dna_type_name,
            field_name,
            self.asset_path,
            " sequence" if self.is_sequence else "",
        )

    def files(self) -> typing.Iterator[pathlib.Path]:
        """Determine absolute path(s) of the asset file(s).

        A relative path is interpreted relative to the blend file referring
        to the asset. If this BlockUsage represents a sequence, the filesystem
        is inspected and the actual files in the sequence are yielded.

        It is assumed that paths are valid UTF-8.
        """

        path = self.__fspath__()
        if not self.is_sequence:
            if not path.exists():
                log.warning("Path %s does not exist for %s", path, self)
                return
            yield path
            return

        try:
            yield from file_sequence.expand_sequence(path)
        except file_sequence.DoesNotExist:
            log.warning("Path %s does not exist for %s", path, self)

    def __fspath__(self) -> pathlib.Path:
        """Determine the absolute path of the asset on the filesystem."""
        if self._abspath is None:
            bpath = self.block.bfile.abspath(self.asset_path)
            log.info(
                "Resolved %s rel to %s -> %s",
                self.asset_path,
                self.block.bfile.filepath,
                bpath,
            )

            as_path = pathlib.Path(bpath.to_path())

            # Windows cannot make a path that has a glob pattern in it absolute.
            # Since globs are generally only on the filename part, we take that off,
            # make the parent directory absolute, then put the filename back.
            try:
                abs_parent = bpathlib.make_absolute(as_path.parent)
            except FileNotFoundError:
                self._abspath = as_path
            else:
                self._abspath = abs_parent / as_path.name

            log.info(
                "Resolving %s rel to %s -> %s",
                self.asset_path,
                self.block.bfile.filepath,
                self._abspath,
            )
        else:
            log.info("Reusing abspath %s", self._abspath)
        return self._abspath

    abspath = property(__fspath__)

    def __lt__(self, other: "BlockUsage"):
        """Allow sorting for repeatable and predictable unit tests."""
        if not isinstance(other, BlockUsage):
            raise NotImplemented()
        return self.block_name < other.block_name and self.block < other.block

    def __eq__(self, other: object):
        if not isinstance(other, BlockUsage):
            return False
        return self.block_name == other.block_name and self.block == other.block

    def __hash__(self):
        return hash((self.block_name, hash(self.block)))
