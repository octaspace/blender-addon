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
"""Commandline entry points."""

import argparse
import datetime
import logging
import time

from . import blocks, common, pack, list_deps, version


def cli_main():
    from blender_asset_tracer import __version__

    parser = argparse.ArgumentParser(
        description="BAT: Blender Asset Tracer v%s" % __version__
    )
    common.add_flag(parser, "profile", help="Run the profiler, write to bam.prof")

    # func is set by subparsers to indicate which function to run.
    parser.set_defaults(func=None, loglevel=logging.WARNING)
    loggroup = parser.add_mutually_exclusive_group()
    loggroup.add_argument(
        "-v",
        "--verbose",
        dest="loglevel",
        action="store_const",
        const=logging.INFO,
        help="Log INFO level and higher",
    )
    loggroup.add_argument(
        "-d",
        "--debug",
        dest="loglevel",
        action="store_const",
        const=logging.DEBUG,
        help="Log everything",
    )
    loggroup.add_argument(
        "-q",
        "--quiet",
        dest="loglevel",
        action="store_const",
        const=logging.ERROR,
        help="Log at ERROR level and higher",
    )
    parser.add_argument(
        "-S",
        "--strict-pointers",
        default=False,
        action="store_true",
        help="Crash on pointers to missing data; otherwise the missing data is just ignored.",
    )

    subparsers = parser.add_subparsers(
        help="Choose a subcommand to actually make BAT do something. "
        "Global options go before the subcommand, "
        "whereas subcommand-specific options go after it. "
        "Use --help after the subcommand to get more info."
    )

    blocks.add_parser(subparsers)
    pack.add_parser(subparsers)
    list_deps.add_parser(subparsers)
    version.add_parser(subparsers)

    args = parser.parse_args()
    config_logging(args)

    from blender_asset_tracer import __version__

    log = logging.getLogger(__name__)

    # Make sure the things we log in our local logger are visible
    if args.profile and args.loglevel > logging.INFO:
        log.setLevel(logging.INFO)
    log.debug("Running BAT version %s", __version__)

    if not args.func:
        parser.error("No subcommand was given")

    set_strict_pointer_mode(args.strict_pointers)

    start_time = time.time()
    if args.profile:
        import cProfile

        prof_fname = "bam.prof"
        log.info("Running profiler")
        cProfile.runctx(
            "args.func(args)", globals=globals(), locals=locals(), filename=prof_fname
        )
        log.info("Profiler exported data to %s", prof_fname)
        log.info(
            'Run "pyprof2calltree -i %r -k" to convert and open in KCacheGrind',
            prof_fname,
        )
    else:
        retval = args.func(args)
    duration = datetime.timedelta(seconds=time.time() - start_time)
    log.info("Command took %s to complete", duration)


def config_logging(args):
    """Configures the logging system based on CLI arguments."""

    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)-15s %(levelname)8s %(name)-40s %(message)s",
    )
    # Only set the log level on our own logger. Otherwise
    # debug logging will be completely swamped.
    logging.getLogger("blender_asset_tracer").setLevel(args.loglevel)


def set_strict_pointer_mode(strict_pointers: bool) -> None:
    from blender_asset_tracer import blendfile

    blendfile.set_strict_pointer_mode(strict_pointers)
