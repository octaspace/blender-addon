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
import logging
import pathlib
import typing

log = logging.getLogger(__name__)


class DoesNotExist(OSError):
    """Indicates a path does not exist on the filesystem."""

    def __init__(self, path: pathlib.Path) -> None:
        super().__init__(path)
        self.path = path


def expand_sequence(path: pathlib.Path) -> typing.Iterator[pathlib.Path]:
    """Expand a file sequence path into the actual file paths.

    :param path: can be either a glob pattern (must contain a * character)
        or the path of the first file in the sequence.
    """

    if "<UDIM>" in path.name:  # UDIM tiles
        # Change <UDIM> marker to a glob pattern, then let the glob case handle it.
        # This assumes that all files that match the glob are actually UDIM
        # tiles; this could cause some false-positives.
        path = path.with_name(path.name.replace("<UDIM>", "*"))

    if "*" in str(path):  # assume it is a glob
        import glob

        log.debug("expanding glob %s", path)
        for fname in sorted(glob.glob(str(path), recursive=True)):
            yield pathlib.Path(fname)
        return
    if not path.exists():
        raise DoesNotExist(path)

    if path.is_dir():
        # Explode directory paths into separate files.
        for subpath in path.rglob("*"):
            if subpath.is_file():
                yield subpath
        return

    log.debug("expanding file sequence %s", path)

    import string

    stem_no_digits = path.stem.rstrip(string.digits)
    if stem_no_digits == path.stem:
        # Just a single file, no digits here.
        yield path
        return

    # Return everything start starts with 'stem_no_digits' and ends with the
    # same suffix as the first file. This may result in more files than used
    # by Blender, but at least it shouldn't miss any.
    pattern = "%s*%s" % (stem_no_digits, path.suffix)
    yield from sorted(path.parent.glob(pattern))
