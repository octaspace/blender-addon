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
import collections
import enum
import functools
import logging
import pathlib
import tempfile
import threading
import typing

from .. import trace, bpathlib, blendfile
from ..trace import file_sequence, result

from . import filesystem, transfer, progress

log = logging.getLogger(__name__)


class PathAction(enum.Enum):
    KEEP_PATH = 1
    FIND_NEW_LOCATION = 2


class AssetAction:
    """All the info required to rewrite blend files and copy assets."""

    def __init__(self) -> None:
        self.path_action = PathAction.KEEP_PATH
        self.usages = []  # type: typing.List[result.BlockUsage]
        """BlockUsage objects referring to this asset.

        Those BlockUsage objects could refer to data blocks in this blend file
        (if the asset is a blend file) or in another blend file.
        """

        self.new_path = None  # type: typing.Optional[pathlib.PurePath]
        """Absolute path to the asset in the BAT Pack.

        This path may not exist on the local file system at all, for example
        when uploading files to remote S3-compatible storage.
        """

        self.read_from = None  # type: typing.Optional[pathlib.Path]
        """Optional path from which to read the asset.

        This is used when blend files have been rewritten. It is assumed that
        when this property is set, the file can be moved instead of copied.
        """

        self.rewrites = []  # type: typing.List[result.BlockUsage]
        """BlockUsage objects in this asset that may require rewriting.

        Empty list if this AssetAction is not for a blend file.
        """


class Aborted(RuntimeError):
    """Raised by Packer to abort the packing process.

    See the Packer.abort() function.
    """


class Packer:
    """Takes a blend file and bundle it with its dependencies.

    The process is separated into two functions:

        - strategise() finds all the dependencies and determines what to do
          with them.
        - execute() performs the actual packing operation, by rewriting blend
          files to ensure the paths to moved files are correct and
          transferring the files.

    The file transfer is performed in a separate thread by a FileTransferer
    instance.
    """

    def __init__(
        self,
        bfile: pathlib.Path,
        project: pathlib.Path,
        target: str,
        *,
        noop=False,
        compress=False,
        relative_only=False,
    ) -> None:
        self.blendfile = bfile
        self.project = project
        self.target = target
        self._target_path = self._make_target_path(target)
        self.noop = noop
        self.compress = compress
        self.relative_only = relative_only
        self._aborted = threading.Event()
        self._abort_lock = threading.RLock()
        self._abort_reason = ""

        # Set this to a custom Callback() subclass instance before calling
        # strategise() to receive progress reports.
        self._progress_cb = progress.Callback()
        self._tscb = progress.ThreadSafeCallback(self._progress_cb)

        self._exclude_globs = set()  # type: typing.Set[str]

        self._shorten = functools.partial(shorten_path, self.project)

        if noop:
            log.warning("Running in no-op mode, only showing what will be done.")

        # Filled by strategise()
        self._actions = collections.defaultdict(
            AssetAction
        )  # type: typing.DefaultDict[pathlib.Path, AssetAction]
        self.missing_files = set()  # type: typing.Set[pathlib.Path]
        self._new_location_paths = set()  # type: typing.Set[pathlib.Path]
        self._output_path = None  # type: typing.Optional[pathlib.PurePath]

        # Filled by execute()
        self._file_transferer = None  # type: typing.Optional[transfer.FileTransferer]

        # Number of files we would copy, if not for --noop
        self._file_count = 0

        self._tmpdir = tempfile.TemporaryDirectory(prefix="bat-", suffix="-batpack")
        self._rewrite_in = pathlib.Path(self._tmpdir.name)

    def _make_target_path(self, target: str) -> pathlib.PurePath:
        """Return a Path for the given target.

        This can be the target directory itself, but can also be a non-existent
        directory if the target doesn't support direct file access. It should
        only be used to perform path operations, and never for file operations.
        """
        return pathlib.Path(target).absolute()

    def close(self) -> None:
        """Clean up any temporary files."""
        self._tscb.flush()
        self._tmpdir.cleanup()

    def __enter__(self) -> "Packer":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    @property
    def output_path(self) -> pathlib.PurePath:
        """The path of the packed blend file in the target directory."""
        assert self._output_path is not None
        return self._output_path

    @property
    def progress_cb(self) -> progress.Callback:
        return self._progress_cb

    @progress_cb.setter
    def progress_cb(self, new_progress_cb: progress.Callback):
        self._tscb.flush()
        self._progress_cb = new_progress_cb
        self._tscb = progress.ThreadSafeCallback(self._progress_cb)

    def abort(self, reason="") -> None:
        """Aborts the current packing process.

        Can be called from any thread. Aborts as soon as the running strategise
        or execute function gets control over the execution flow, by raising
        an Aborted exception.
        """
        with self._abort_lock:
            self._abort_reason = reason
            if self._file_transferer:
                self._file_transferer.abort()
            self._aborted.set()

    def _check_aborted(self) -> None:
        """Raises an Aborted exception when abort() was called."""

        with self._abort_lock:
            reason = self._abort_reason
            if self._file_transferer is not None and self._file_transferer.has_error:
                log.error("A transfer error occurred")
                reason = self._file_transferer.error_message()
            elif not self._aborted.is_set():
                return

            log.warning("Aborting")
            self._tscb.flush()
            self._progress_cb.pack_aborted(reason)
            raise Aborted(reason)

    def exclude(self, *globs: str):
        """Register glob-compatible patterns of files that should be ignored.

        Must be called before calling strategise().
        """
        if self._actions:
            raise RuntimeError(
                "%s.exclude() must be called before strategise()"
                % self.__class__.__qualname__
            )
        self._exclude_globs.update(globs)

    def strategise(self) -> None:
        """Determine what to do with the assets.

        Places an asset into one of these categories:
            - Can be copied as-is, nothing smart required.
            - Blend files referring to this asset need to be rewritten.

        This function does *not* expand globs. Globs are seen as single
        assets, and are only evaluated when performing the actual transfer
        in the execute() function.
        """

        # The blendfile that we pack is generally not its own dependency, so
        # we have to explicitly add it to the _packed_paths.
        bfile_path = bpathlib.make_absolute(self.blendfile)

        # Both paths have to be resolved first, because this also translates
        # network shares mapped to Windows drive letters back to their UNC
        # notation. Only resolving one but not the other (which can happen
        # with the abosolute() call above) can cause errors.
        bfile_pp = self._target_path / bfile_path.relative_to(
            bpathlib.make_absolute(self.project)
        )
        self._output_path = bfile_pp

        self._progress_cb.pack_start()

        act = self._actions[bfile_path]
        act.path_action = PathAction.KEEP_PATH
        act.new_path = bfile_pp

        self._check_aborted()
        self._new_location_paths = set()
        for usage in trace.deps(self.blendfile, self._progress_cb):
            self._check_aborted()
            asset_path = usage.abspath
            if any(asset_path.match(glob) for glob in self._exclude_globs):
                log.info("Excluding file: %s", asset_path)
                continue

            if self.relative_only and not usage.asset_path.startswith(b"//"):
                log.info("Skipping absolute path: %s", usage.asset_path)
                continue

            if usage.is_sequence:
                self._visit_sequence(asset_path, usage)
            else:
                self._visit_asset(asset_path, usage)

        self._find_new_paths()
        self._group_rewrites()

    def _visit_sequence(self, asset_path: pathlib.Path, usage: result.BlockUsage):
        assert usage.is_sequence

        def handle_missing_file():
            log.warning("Missing file: %s", asset_path)
            self.missing_files.add(asset_path)
            self._progress_cb.missing_file(asset_path)

        try:
            for file_path in file_sequence.expand_sequence(asset_path):
                if file_path.exists():
                    break
            else:
                # At least some file of a sequence must exist.
                handle_missing_file()
                return
        except file_sequence.DoesNotExist:
            # The asset path should point to something existing.
            handle_missing_file()
            return

        # Handle this sequence as an asset.
        self._visit_asset(asset_path, usage)

    def _visit_asset(self, asset_path: pathlib.Path, usage: result.BlockUsage):
        """Determine what to do with this asset.

        Determines where this asset will be packed, whether it needs rewriting,
        and records the blend file data block referring to it.
        """

        # Sequences are allowed to not exist at this point.
        if not usage.is_sequence and not asset_path.exists():
            log.warning("Missing file: %s", asset_path)
            self.missing_files.add(asset_path)
            self._progress_cb.missing_file(asset_path)
            return

        bfile_path = usage.block.bfile.filepath.absolute()
        self._progress_cb.trace_asset(asset_path)

        # Needing rewriting is not a per-asset thing, but a per-asset-per-
        # blendfile thing, since different blendfiles can refer to it in
        # different ways (for example with relative and absolute paths).
        if usage.is_sequence:
            first_path = next(file_sequence.expand_sequence(asset_path))
        else:
            first_path = asset_path
        path_in_project = self._path_in_project(first_path)
        use_as_is = usage.asset_path.is_blendfile_relative() and path_in_project
        needs_rewriting = not use_as_is

        act = self._actions[asset_path]
        assert isinstance(act, AssetAction)
        act.usages.append(usage)

        if needs_rewriting:
            log.info("%s needs rewritten path to %s", bfile_path, usage.asset_path)
            act.path_action = PathAction.FIND_NEW_LOCATION
            self._new_location_paths.add(asset_path)
        else:
            log.debug("%s can keep using %s", bfile_path, usage.asset_path)
            asset_pp = self._target_path / asset_path.relative_to(self.project)
            act.new_path = asset_pp

    def _find_new_paths(self):
        """Find new locations in the BAT Pack for the given assets."""

        for path in self._new_location_paths:
            act = self._actions[path]
            assert isinstance(act, AssetAction)

            relpath = bpathlib.strip_root(path)
            act.new_path = pathlib.Path(self._target_path, "_outside_project", relpath)

    def _group_rewrites(self) -> None:
        """For each blend file, collect which fields need rewriting.

        This ensures that the execute() step has to visit each blend file
        only once.
        """

        # Take a copy so we can modify self._actions in the loop.
        actions = set(self._actions.values())

        while actions:
            action = actions.pop()

            if action.path_action != PathAction.FIND_NEW_LOCATION:
                # This asset doesn't require a new location, so no rewriting necessary.
                continue

            for usage in action.usages:
                bfile_path = bpathlib.make_absolute(usage.block.bfile.filepath)
                insert_new_action = bfile_path not in self._actions

                self._actions[bfile_path].rewrites.append(usage)

                if insert_new_action:
                    actions.add(self._actions[bfile_path])

    def _path_in_project(self, path: pathlib.Path) -> bool:
        abs_path = bpathlib.make_absolute(path)
        abs_project = bpathlib.make_absolute(self.project)
        try:
            abs_path.relative_to(abs_project)
        except ValueError:
            return False
        return True

    def execute(self) -> None:
        """Execute the strategy."""
        assert self._actions, "Run strategise() first"

        if not self.noop:
            self._rewrite_paths()

        self._start_file_transferrer()
        self._perform_file_transfer()
        self._progress_cb.pack_done(self.output_path, self.missing_files)

    def _perform_file_transfer(self):
        """Use file transferrer to do the actual file transfer.

        This is performed in a separate function, so that subclasses can
        override this function to queue up copy/move actions first, and
        then call this function.
        """
        self._write_info_file()
        self._copy_files_to_target()

    def _create_file_transferer(self) -> transfer.FileTransferer:
        """Create a FileCopier(), can be overridden in a subclass."""

        if self.compress:
            return filesystem.CompressedFileCopier()
        return filesystem.FileCopier()

    def _start_file_transferrer(self):
        """Starts the file transferrer thread."""
        self._file_transferer = self._create_file_transferer()
        self._file_transferer.progress_cb = self._tscb
        if not self.noop:
            self._file_transferer.start()

    def _copy_files_to_target(self) -> None:
        """Copy all assets to the target directoy.

        This creates the BAT Pack but does not yet do any path rewriting.
        """
        log.debug("Executing %d copy actions", len(self._actions))

        assert self._file_transferer is not None

        try:
            for asset_path, action in self._actions.items():
                self._check_aborted()
                self._copy_asset_and_deps(asset_path, action)

            if self.noop:
                log.info("Would copy %d files to %s", self._file_count, self.target)
                return
            self._file_transferer.done_and_join()
            self._on_file_transfer_finished(file_transfer_completed=True)
        except KeyboardInterrupt:
            log.info("File transfer interrupted with Ctrl+C, aborting.")
            self._file_transferer.abort_and_join()
            self._on_file_transfer_finished(file_transfer_completed=False)
            raise
        finally:
            self._tscb.flush()
            self._check_aborted()

            # Make sure that the file transferer is no longer usable, for
            # example to avoid it being involved in any following call to
            # self.abort().
            self._file_transferer = None

    def _on_file_transfer_finished(self, *, file_transfer_completed: bool) -> None:
        """Called when the file transfer is finished.

        This can be used in subclasses to perform cleanup on the file transferer,
        or to obtain information from it before we destroy it.
        """

    def _rewrite_paths(self) -> None:
        """Rewrite paths to the new location of the assets.

        Writes the rewritten blend files to a temporary location.
        """

        for bfile_path, action in self._actions.items():
            if not action.rewrites:
                continue
            self._check_aborted()

            assert isinstance(bfile_path, pathlib.Path)
            # bfile_pp is the final path of this blend file in the BAT pack.
            # It is used to determine relative paths to other blend files.
            # It is *not* used for any disk I/O, since the file may not even
            # exist on the local filesystem.
            bfile_pp = action.new_path
            assert (
                bfile_pp is not None
            ), f"Action {action.path_action.name} on {bfile_path} has no final path set, unable to process"

            # Use tempfile to create a unique name in our temporary directoy.
            # The file should be deleted when self.close() is called, and not
            # when the bfile_tp object is GC'd.
            bfile_tmp = tempfile.NamedTemporaryFile(
                dir=str(self._rewrite_in),
                prefix="bat-",
                suffix="-" + bfile_path.name,
                delete=False,
            )
            bfile_tp = pathlib.Path(bfile_tmp.name)
            action.read_from = bfile_tp
            log.info("Rewriting %s to %s", bfile_path, bfile_tp)

            # The original blend file will have been cached, so we can use it
            # to avoid re-parsing all data blocks in the to-be-rewritten file.
            bfile = blendfile.open_cached(bfile_path, assert_cached=True)
            bfile.copy_and_rebind(bfile_tp, mode="rb+")

            for usage in action.rewrites:
                self._check_aborted()
                assert isinstance(usage, result.BlockUsage)
                asset_pp = self._actions[usage.abspath].new_path
                assert isinstance(asset_pp, pathlib.Path)

                log.debug("   - %s is packed at %s", usage.asset_path, asset_pp)
                relpath = bpathlib.BlendPath.mkrelative(asset_pp, bfile_pp)
                if relpath == usage.asset_path:
                    log.info("   - %s remained at %s", usage.asset_path, relpath)
                    continue

                log.info("   - %s moved to %s", usage.asset_path, relpath)

                # Find the same block in the newly copied file.
                block = bfile.dereference_pointer(usage.block.addr_old)

                # Pointers can point to a non-existing data block, in which case
                # either a SegmentationFault exception is thrown, or None is
                # returned, based on the strict pointer mode set on the
                # BlendFile class. Since this block was already meant to be
                # rewritten, it was found before.
                assert block is not None

                if usage.path_full_field is None:
                    dir_field = usage.path_dir_field
                    assert dir_field is not None
                    log.debug(
                        "   - updating field %s of block %s",
                        dir_field.name.name_only,
                        block,
                    )
                    reldir = bpathlib.BlendPath.mkrelative(asset_pp.parent, bfile_pp)
                    written = block.set(dir_field.name.name_only, reldir)
                    log.debug("   - written %d bytes", written)

                    # BIG FAT ASSUMPTION that the filename (e.g. basename
                    # without path) does not change. This makes things much
                    # easier, as in the sequence editor the directory and
                    # filename fields are in different blocks. See the
                    # blocks2assets.scene() function for the implementation.
                else:
                    log.debug(
                        "   - updating field %s of block %s",
                        usage.path_full_field.name.name_only,
                        block,
                    )
                    written = block.set(usage.path_full_field.name.name_only, relpath)
                    log.debug("   - written %d bytes", written)

            # Make sure we close the file, otherwise changes may not be
            # flushed before it gets copied.
            if bfile.is_modified:
                self._progress_cb.rewrite_blendfile(bfile_path)
            bfile.close()

    def _copy_asset_and_deps(self, asset_path: pathlib.Path, action: AssetAction):
        asset_path_is_dir = asset_path.is_dir()

        # Copy the asset itself, but only if it's not a sequence (sequences are
        # handled below in the for-loop).
        if (
            "*" not in str(asset_path)
            and "<UDIM>" not in asset_path.name
            and not asset_path_is_dir
        ):
            packed_path = action.new_path
            assert packed_path is not None
            read_path = action.read_from or asset_path
            self._send_to_target(
                read_path, packed_path, may_move=action.read_from is not None
            )

        if asset_path_is_dir:  # like 'some/directory':
            asset_base_path = asset_path
        else:  # like 'some/directory/prefix_*.bphys':
            asset_base_path = asset_path.parent

        # Copy its sequence dependencies.
        for usage in action.usages:
            if not usage.is_sequence:
                continue

            first_pp = self._actions[usage.abspath].new_path
            assert first_pp is not None
            log.info(f"first_pp = {first_pp}")

            # In case of globbing, we only support globbing by filename,
            # and not by directory.
            assert "*" not in str(first_pp) or "*" in first_pp.name

            if asset_path_is_dir:
                packed_base_dir = first_pp
            else:
                packed_base_dir = first_pp.parent

            for file_path in usage.files():
                # Compute the relative path, to support cases where asset_path
                # is `some/directory` and the to-be-copied file is in
                # `some/directory/subdir/filename.txt`.
                relpath = file_path.relative_to(asset_base_path)
                packed_path = packed_base_dir / relpath

                # Assumption: assets in a sequence are never blend files.
                self._send_to_target(file_path, packed_path)

            # Assumption: all data blocks using this asset use it the same way.
            break

    def _send_to_target(
        self, asset_path: pathlib.Path, target: pathlib.PurePath, may_move=False
    ):
        if self.noop:
            print("%s -> %s" % (asset_path, target))
            self._file_count += 1
            return

        verb = "move" if may_move else "copy"
        log.debug("Queueing %s of %s", verb, asset_path)

        self._tscb.flush()

        assert self._file_transferer is not None
        if may_move:
            self._file_transferer.queue_move(asset_path, target)
        else:
            self._file_transferer.queue_copy(asset_path, target)

    def _write_info_file(self):
        """Write a little text file with info at the top of the pack."""

        infoname = "pack-info.txt"
        infopath = self._rewrite_in / infoname
        log.debug("Writing info to %s", infopath)
        with infopath.open("wt", encoding="utf8") as infofile:
            print("This is a Blender Asset Tracer pack.", file=infofile)
            print("Start by opening the following blend file:", file=infofile)
            print(
                "    %s" % self._output_path.relative_to(self._target_path).as_posix(),
                file=infofile,
            )

        self._file_transferer.queue_move(infopath, self._target_path / infoname)


def shorten_path(cwd: pathlib.Path, somepath: pathlib.Path) -> pathlib.Path:
    """Return 'somepath' relative to CWD if possible."""
    try:
        return somepath.relative_to(cwd)
    except ValueError:
        return somepath
