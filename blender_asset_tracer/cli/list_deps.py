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
"""List dependencies of a blend file."""

import functools
import hashlib
import json
import logging
import pathlib
import sys
import time
import typing

from .. import trace, bpathlib
from . import common

log = logging.getLogger(__name__)


def add_parser(subparsers):
    """Add argparser for this subcommand."""

    parser = subparsers.add_parser("list", help=__doc__)
    parser.set_defaults(func=cli_list)
    parser.add_argument("blendfile", type=pathlib.Path)
    common.add_flag(
        parser, "json", help="Output as JSON instead of human-readable text"
    )
    common.add_flag(
        parser,
        "sha256",
        help="Include SHA256sums in the output. Note that those may differ from the "
        "SHA256sums in a BAT-pack when paths are rewritten.",
    )
    common.add_flag(parser, "timing", help="Include timing information in the output")


def cli_list(args):
    bpath = args.blendfile
    if not bpath.exists():
        log.fatal("File %s does not exist", args.blendfile)
        return 3

    if args.json:
        if args.sha256:
            log.fatal("--sha256 can currently not be used in combination with --json")
        if args.timing:
            log.fatal("--timing can currently not be used in combination with --json")
        report_json(bpath)
    else:
        report_text(bpath, include_sha256=args.sha256, show_timing=args.timing)


def calc_sha_sum(filepath: pathlib.Path) -> typing.Tuple[str, float]:
    start = time.time()

    if filepath.is_dir():
        for subfile in filepath.rglob("*"):
            calc_sha_sum(subfile)
        duration = time.time() - start
        return "-multiple-", duration

    summer = hashlib.sha256()
    with filepath.open("rb") as infile:
        while True:
            block = infile.read(32 * 1024)
            if not block:
                break
            summer.update(block)

    digest = summer.hexdigest()
    duration = time.time() - start

    return digest, duration


def report_text(bpath, *, include_sha256: bool, show_timing: bool):
    reported_assets = set()  # type: typing.Set[pathlib.Path]
    last_reported_bfile = None
    shorten = functools.partial(common.shorten, pathlib.Path.cwd())

    time_spent_on_shasums = 0.0
    start_time = time.time()

    for usage in trace.deps(bpath):
        filepath = usage.block.bfile.filepath.absolute()
        if filepath != last_reported_bfile:
            if include_sha256:
                shasum, time_spent = calc_sha_sum(filepath)
                time_spent_on_shasums += time_spent
                print(shorten(filepath), shasum)
            else:
                print(shorten(filepath))

        last_reported_bfile = filepath

        for assetpath in usage.files():
            assetpath = bpathlib.make_absolute(assetpath)
            if assetpath in reported_assets:
                log.debug("Already reported %s", assetpath)
                continue

            if include_sha256:
                shasum, time_spent = calc_sha_sum(assetpath)
                time_spent_on_shasums += time_spent
                print("   ", shorten(assetpath), shasum)
            else:
                print("   ", shorten(assetpath))
            reported_assets.add(assetpath)

    if show_timing:
        duration = time.time() - start_time
        print("Spent %.2f seconds on producing this listing" % duration)
        if include_sha256:
            print("Spent %.2f seconds on calculating SHA sums" % time_spent_on_shasums)
            percentage = time_spent_on_shasums / duration * 100
            print("  (that is %d%% of the total time" % percentage)


class JSONSerialiser(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, pathlib.Path):
            return str(o)
        if isinstance(o, set):
            return sorted(o)
        return super().default(o)


def report_json(bpath):
    import collections

    # Mapping from blend file to its dependencies.
    report = collections.defaultdict(set)

    for usage in trace.deps(bpath):
        filepath = usage.block.bfile.filepath.absolute()
        for assetpath in usage.files():
            assetpath = assetpath.resolve()
            report[str(filepath)].add(assetpath)

    json.dump(report, sys.stdout, cls=JSONSerialiser, indent=4)
