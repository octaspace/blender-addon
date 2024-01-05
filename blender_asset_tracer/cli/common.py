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
"""Common functionality for CLI parsers."""
import typing

import pathlib


def add_flag(argparser, flag_name: str, **kwargs):
    """Add a CLI argument for the flag.

    The flag defaults to False, and when present on the CLI stores True.
    """

    argparser.add_argument(
        "-%s" % flag_name[0],
        "--%s" % flag_name,
        default=False,
        action="store_true",
        **kwargs
    )


def shorten(cwd: pathlib.Path, somepath: pathlib.Path) -> pathlib.Path:
    """Return 'somepath' relative to CWD if possible."""
    try:
        return somepath.relative_to(cwd)
    except ValueError:
        return somepath


def humanize_bytes(size_in_bytes: int, precision: typing.Optional[int] = None):
    """Return a humanized string representation of a number of bytes.

    Source: http://code.activestate.com/recipes/577081-humanized-representation-of-a-number-of-bytes

    :param size_in_bytes: The size to humanize
    :param precision: How many digits are shown after the comma. When None,
        it defaults to 1 unless the entire number of bytes is shown, then
        it will be 0.

    >>> humanize_bytes(1)
    '1 B'
    >>> humanize_bytes(1024)
    '1.0 kB'
    >>> humanize_bytes(1024*123, 0)
    '123 kB'
    >>> humanize_bytes(1024*123)
    '123.0 kB'
    >>> humanize_bytes(1024*12342)
    '12.1 MB'
    >>> humanize_bytes(1024*12342,2)
    '12.05 MB'
    >>> humanize_bytes(1024*1234,2)
    '1.21 MB'
    >>> humanize_bytes(1024*1234*1111,2)
    '1.31 GB'
    >>> humanize_bytes(1024*1234*1111,1)
    '1.3 GB'
    """

    if precision is None:
        precision = size_in_bytes >= 1024

    abbrevs = (
        (1 << 50, "PB"),
        (1 << 40, "TB"),
        (1 << 30, "GB"),
        (1 << 20, "MB"),
        (1 << 10, "kB"),
        (1, "B"),
    )
    for factor, suffix in abbrevs:
        if size_in_bytes >= factor:
            break
    else:
        factor = 1
        suffix = "B"
    return "%.*f %s" % (precision, size_in_bytes / factor, suffix)


if __name__ == "__main__":
    import doctest

    doctest.testmod()
