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
"""Blender path support.

Does not use pathlib, because we may have to handle POSIX paths on Windows
or vice versa.
"""

import os.path
import pathlib
import platform
import string
import sys


class BlendPath(bytes):
    """A path within Blender is always stored as bytes."""

    def __new__(cls, path):
        if isinstance(path, pathlib.PurePath):
            path = str(path).encode("utf-8")
        if not isinstance(path, bytes):
            raise TypeError("path must be bytes or pathlib.Path, but is %r" % path)

        return super().__new__(cls, path.replace(b"\\", b"/"))

    @classmethod
    def mkrelative(
        cls, asset_path: pathlib.PurePath, bfile_path: pathlib.PurePath
    ) -> "BlendPath":
        """Construct a BlendPath to the asset relative to the blend file.

        Assumes that bfile_path is absolute.

        Note that this can return an absolute path on Windows when 'asset_path'
        and 'bfile_path' are on different drives.
        """
        from collections import deque

        # Only compare absolute paths.
        assert bfile_path.is_absolute(), (
            "BlendPath().mkrelative(bfile_path=%r) should get absolute bfile_path"
            % bfile_path
        )
        assert asset_path.is_absolute(), (
            "BlendPath().mkrelative(asset_path=%r) should get absolute asset_path"
            % asset_path
        )

        # There is no way to construct a relative path between drives.
        if bfile_path.drive != asset_path.drive:
            return cls(asset_path)

        bdir_parts = deque(bfile_path.parent.parts)
        asset_path = make_absolute(asset_path)
        asset_parts = deque(asset_path.parts)

        # Remove matching initial parts. What is left in bdir_parts represents
        # the number of '..' we need. What is left in asset_parts represents
        # what we need after the '../../../'.
        while bdir_parts:
            if bdir_parts[0] != asset_parts[0]:
                break
            bdir_parts.popleft()
            asset_parts.popleft()

        rel_asset = pathlib.PurePath(*asset_parts)
        # TODO(Sybren): should we use sys.getfilesystemencoding() instead?
        rel_bytes = str(rel_asset).encode("utf-8")
        as_bytes = b"//" + len(bdir_parts) * b"../" + rel_bytes
        return cls(as_bytes)

    def __str__(self) -> str:
        """Decodes the path as UTF-8, replacing undecodable bytes.

        Undecodable bytes are ignored so this function can be safely used
        for reporting.
        """
        return self.decode("utf8", errors="replace")

    def __repr__(self) -> str:
        return "BlendPath(%s)" % super().__repr__()

    def __truediv__(self, subpath: bytes):
        """Slash notation like pathlib.Path."""
        sub = BlendPath(subpath)
        if sub.is_absolute():
            raise ValueError("'a / b' only works when 'b' is a relative path")
        return BlendPath(self.rstrip(b"/") + b"/" + sub)

    def __rtruediv__(self, parentpath: bytes):
        """Slash notation like pathlib.Path."""
        if self.is_absolute():
            raise ValueError("'a / b' only works when 'b' is a relative path")
        return BlendPath(parentpath.rstrip(b"/") + b"/" + self)

    def to_path(self) -> pathlib.PurePath:
        """Convert this path to a pathlib.PurePath.

        This path MUST NOT be a blendfile-relative path (e.g. it may not start
        with `//`). For such paths, first use `.absolute()` to resolve the path.

        Interprets the path as UTF-8, and if that fails falls back to the local
        filesystem encoding.

        The exact type returned is determined by the current platform.
        """
        # TODO(Sybren): once we target Python 3.6, implement __fspath__().
        try:
            decoded = self.decode("utf8")
        except UnicodeDecodeError:
            decoded = self.decode(sys.getfilesystemencoding())
        if self.is_blendfile_relative():
            raise ValueError("to_path() cannot be used on blendfile-relative paths")
        return pathlib.PurePath(decoded)

    def is_blendfile_relative(self) -> bool:
        return self[:2] == b"//"

    def is_absolute(self) -> bool:
        if self.is_blendfile_relative():
            return False
        if self[0:1] == b"/":
            return True

        # Windows style path starting with drive letter.
        if (
            len(self) >= 3
            and (self.decode("utf8"))[0] in string.ascii_letters
            and self[1:2] == b":"
            and self[2:3] in {b"\\", b"/"}
        ):
            return True

        return False

    def absolute(self, root: bytes = b"") -> "BlendPath":
        """Determine absolute path.

        :param root: root directory to compute paths relative to.
            For blendfile-relative paths, root should be the directory
            containing the blendfile. If not given, blendfile-relative
            paths cause a ValueError but filesystem-relative paths are
            resolved based on the current working directory.
        """
        if self.is_absolute():
            return self

        if self.is_blendfile_relative():
            my_relpath = self[2:]  # strip off leading //
        else:
            my_relpath = self
        return BlendPath(os.path.join(root, my_relpath))


def make_absolute(path: pathlib.PurePath) -> pathlib.Path:
    """Make the path absolute without resolving symlinks or drive letters.

    This function is an alternative to `Path.resolve()`. It make the path absolute,
    and resolves `../../`, but contrary to `Path.resolve()` does NOT perform these
    changes:
        - Symlinks are NOT followed.
        - Windows Network shares that are mapped to a drive letter are NOT resolved
          to their UNC notation.

    The type of the returned path is determined by the current platform.
    """
    str_path = path.as_posix()
    if len(str_path) >= 2 and str_path[0].isalpha() and str_path[1] == ":":
        # This is an absolute Windows path. It must be handled with care on non-Windows platforms.
        if platform.system() != "Windows":
            # Normalize the POSIX-like part of the path, but leave out the drive letter.
            non_drive_path = str_path[2:]
            normalized = os.path.normpath(non_drive_path)
            # Stick the drive letter back on the normalized path.
            return pathlib.Path(str_path[:2] + normalized)

    return pathlib.Path(os.path.abspath(str_path))


def strip_root(path: pathlib.PurePath) -> pathlib.PurePosixPath:
    """Turn the path into a relative path by stripping the root.

    This also turns any drive letter into a normal path component.

    This changes "C:/Program Files/Blender" to "C/Program Files/Blender",
    and "/absolute/path.txt" to "absolute/path.txt", making it possible to
    treat it as a relative path.
    """

    if path.drive:
        return pathlib.PurePosixPath(path.drive[0], *path.parts[1:])
    if isinstance(path, pathlib.PurePosixPath):
        # This happens when running on POSIX but still handling paths
        # originating from a Windows machine.
        parts = path.parts
        if (
            parts
            and len(parts[0]) == 2
            and parts[0][0].isalpha()
            and parts[0][1] == ":"
        ):
            # The first part is a drive letter.
            return pathlib.PurePosixPath(parts[0][0], *path.parts[1:])

    if path.is_absolute():
        return pathlib.PurePosixPath(*path.parts[1:])
    return pathlib.PurePosixPath(path)
