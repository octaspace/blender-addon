import webbrowser
import bpy
import time
import os
import subprocess
import shutil
import tempfile
from pathlib import Path
from bpy.types import Operator
from threading import Thread
from ..blender_asset_tracer.pack import zipped
from ..blender_asset_tracer.blendfile import close_all_cached
from .octa_properties import SubmitJobProperties
from .transfer_manager import create_upload, ensure_running
from .util import get_all_render_passes, unpack_octa_farm_config, get_preferences
import addon_utils
import json
import zipfile
import traceback
from ast import literal_eval
from contextlib import contextmanager

DEFAULT_ADDONS = [
    "io_anim_bvh",
    "bl_pkg",
    "copy_global_transform",
    "cycles",
    "io_scene_fbx",
    "io_scene_gltf2",
    "hydra_storm",
    "ui_translate",
    "node_wrangler",
    "pose_library",
    "rigify",
    "io_curve_svg",
    "io_mesh_uv_layout",
    "viewport_vr_preview",
]


@contextmanager
def rewrite_volumes_to_absolute():
    """
    Context manager that temporarily rewrites all volume filepaths to absolute paths,
    then restores them afterward.
    """
    # Store the original filepaths in a dictionary: volume -> original filepath
    original_filepaths = {}
    for vol in bpy.data.volumes:
        original_filepaths[vol] = vol.filepath

    # Convert all volume filepaths to absolute
    for vol in bpy.data.volumes:
        vol.filepath = bpy.path.abspath(vol.filepath)

    try:
        # Yield control back to the caller so they can do their operations
        yield
    finally:
        # Restore the original filepaths
        for vol, old_path in original_filepaths.items():
            vol.filepath = old_path


def subprocess_unpacker():
    current_file_path = bpy.data.filepath
    parent_dir = os.path.dirname(current_file_path)

    # Create an actual temporary directory (instead of using parent_dir)
    folder = tempfile.mkdtemp(prefix=f"{int(time.time())}_octa_")
    print(folder)
    if not os.path.exists(folder):
        print(f"creating {folder}")
        os.makedirs(folder, exist_ok=True)

    temp_blend_name = os.path.abspath(
        os.path.join(folder, os.path.basename(current_file_path))
    )

    was_autopacked = bpy.data.use_autopack

    bpy.data.use_autopack = False
    bpy.ops.wm.save_mainfile()
    with rewrite_volumes_to_absolute():
        bpy.ops.wm.save_as_mainfile(
            filepath=temp_blend_name, copy=True, compress=True, relative_remap=True
        )
    bpy.data.use_autopack = was_autopacked
    bpy.ops.wm.save_mainfile()

    blender_executable = bpy.app.binary_path

    script_path = os.path.realpath(__file__)
    dir_path = os.path.dirname(script_path)
    subprocess_unpacker_script = os.path.abspath(
        os.path.join(dir_path, "subprocess_unpacker.py")
    )

    # Determine the name of the cache folder
    base_file_name = os.path.splitext(os.path.basename(current_file_path))[0]
    cache_folder_name = f"blendcache_{base_file_name}"
    cache_folder_path = os.path.join(parent_dir, cache_folder_name)

    # Check if the cache folder exists and copy it
    if os.path.exists(cache_folder_path):
        destination_cache_folder = os.path.join(folder, cache_folder_name)
        shutil.copytree(cache_folder_path, destination_cache_folder)
        print(f"Copied cache folder to: {destination_cache_folder}")

    # command = [
    #     blender_executable,
    #     "-b",
    #     current_file_path,
    #     "--python",
    #     subprocess_unpacker_script,
    #     "--factory-startup",
    #     "--",
    #     "-save_path",
    #     temp_blend_name,
    # ]

    # result = subprocess.run(command, capture_output=True, text=True)
    # if result.returncode != 0:
    #     raise RuntimeError(
    #         f"Subprocess unpacker failed with code {result.returncode}\n"
    #         f"Stdout: {result.stdout}\nStderr: {result.stderr}"
    #     )

    return temp_blend_name, folder


def wait_for_save():
    while f"{os.path.split(bpy.data.filepath)[1]}@" in os.listdir(
        os.path.dirname(bpy.data.filepath)
    ):
        print("@ Detected, Waiting for save to finish")
        time.sleep(0.25)


# submit job operator
class SubmitJobOperator(Operator):
    bl_idname = "exporter.submit_job"
    bl_label = "Submit Job"
    bl_description = "Submit Job"

    _timer = None
    _running = False
    _progress = 0
    _progress_name = ""
    _error_message = None  # Store error messages from thread_run if any

    debug_zip: bpy.props.BoolProperty(name="Debug .zip", default=False)

    installed_addons = []

    addons_to_send = []

    def __init__(self):
        self._run_thread: Thread = None

    @classmethod
    def set_installed_addons(cls):
        cls.installed_addons = [
            mod
            for mod in addon_utils.modules()
            if addon_utils.check(mod.__name__)[1] and mod.__name__ not in DEFAULT_ADDONS
        ]

    @classmethod
    def set_addons_to_send(cls, value: str):
        cls.addons_to_send = literal_eval(value)

    @classmethod
    def poll(cls, context):
        return not cls._running

    @classmethod
    def _set_running(cls, value: bool):
        cls._running = value

    @classmethod
    def get_running(cls) -> bool:
        return cls._running

    @classmethod
    def get_progress(cls):
        return cls._progress

    @classmethod
    def set_progress(cls, value: float):
        cls._progress = value
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "PROPERTIES":
                    area.tag_redraw()

    @classmethod
    def set_progress_name(cls, value: str):
        cls._progress_name = value

    @classmethod
    def get_progress_name(cls):
        return cls._progress_name

    def modal(self, context, event):
        if event.type == "TIMER":
            if not self.get_running():  # <--- Wait until the image is marked as dirty
                self.finish(context)
                return {"FINISHED"}
        return {"PASS_THROUGH"}

    def cancel(self, context):
        # TODO: add way to cancel
        self.report({"INFO"}, "Octa render submit cancelled")

    def finish(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        self._run_thread = None
        if self._error_message:
            self.report({"ERROR"}, self._error_message)
        else:
            self.report({"INFO"}, "Octa render submit finished")

    def invoke(self, context, event):
        if self.get_running():
            self.report({"WARNING"}, "Submission is already running")
            return {"CANCELLED"}

        job_properties = self.validate_properties(context)
        if job_properties is None:
            return {"CANCELLED"}

        self._error_message = None

        try:
            temp_blend_name, temp_work_folder = subprocess_unpacker()
        except Exception as e:
            traceback.print_exc()
            self._error_message = "Failed to prepare the blend file for submission."
            self._set_running(False)
            self.finish(context)
            return {"CANCELLED"}

        wait_for_save()
        job_properties.temp_work_folder = temp_work_folder
        job_properties.temp_blend_name = temp_blend_name

        self._set_running(True)
        self._run_thread = Thread(
            target=self.thread_run, daemon=True, args=[job_properties]
        )
        self._run_thread.start()
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def zip_addons(self, zip_path):
        print("Addons to send:", self.addons_to_send)
        print("Installed addons:", self.installed_addons)
        addons_to_send = [
            mod for mod in self.installed_addons if mod.__name__ in self.addons_to_send
        ]

        enabled_addons = [
            mod.bl_info["name"]
            for mod in addon_utils.modules()
            if addon_utils.check(mod.__name__)[1]
        ]

        with zipfile.ZipFile(zip_path, "a", zipfile.ZIP_DEFLATED) as zipf:
            for addon in addons_to_send:
                addon_path = Path(addon.__file__).parent
                addon_name = addon.__name__

                for root, _, files in os.walk(addon_path):
                    archive_root = os.path.relpath(root, addon_path)
                    for file in files:
                        file_path = os.path.join(root, file)
                        addon_root = os.path.join("scripts", "addons", addon_name)
                        addon_path = os.path.join(addon_root, archive_root, file)

                        zipf.write(
                            file_path,
                            addon_path,
                        )

            zipf.writestr("enabled_addons.json", json.dumps(enabled_addons))
        print("Added addons to zip:", addons_to_send)

    def pack_blend(self, infile, zippath):
        with zipped.ZipPacker(infile, infile.parent, zippath) as packer:
            packer.strategise()
            packer.execute()

        self.zip_addons(zippath)

    def validate_properties(self, context):
        scene = context.scene
        job_properties = SubmitJobProperties()
        fail_validation = False
        if not context.blend_data.filepath:
            self.report({"ERROR"}, "You have to save the .blend before submitting")
            return None

        try:
            properties = scene.octa_properties
            job_name = properties.job_name
            if len(job_name) == 0:
                self.report({"ERROR"}, "Job name is not set")
                fail_validation = True

            job_properties.job_name = job_name

            if properties.render_type == "IMAGE":
                frame_start = frame_end = (
                    properties.frame_current
                    if not properties.match_scene
                    else scene.frame_current
                )
            else:
                if properties.match_scene:
                    frame_start = scene.frame_start
                    frame_end = scene.frame_end
                else:
                    frame_start = properties.frame_start
                    frame_end = properties.frame_end

            job_properties.frame_start = frame_start
            job_properties.frame_end = frame_end
            job_properties.frame_step = properties.frame_step

            frame_count = frame_end - frame_start + 1
            if frame_count <= 0:
                self.report({"ERROR"}, "Frame range is negative or zero")
                fail_validation = True

            if frame_count % properties.batch_size != 0:
                suggested_divisions = [i for i in range(2, 100) if frame_count % i == 0]
                suggested_divisions.sort()
                suggestion = "Choose a different frame range"
                if suggested_divisions:
                    suggestion = f"Suggested batch sizes: {', '.join(map(str, suggested_divisions[:5]))}"

                self.report(
                    {"ERROR"},
                    f"Total frame count ({frame_count}) is not divisible by batch size {properties.batch_size}. {suggestion}",
                )
                fail_validation = True

            job_properties.advanced_section_visible = (
                properties.advanced_section_visible
            )

            job_properties.generate_video = properties.generate_video
            job_properties.match_scene = properties.match_scene
            job_properties.match_scene_format = properties.match_scene_format
            job_properties.max_thumbnail_size = properties.max_thumbnail_size
            job_properties.render_format = (
                properties.render_format
                if not properties.match_scene_format
                else context.scene.render.image_settings.file_format
            )
            job_properties.render_output_path = properties.render_output_path
            job_properties.upload_threads = properties.upload_threads
            job_properties.batch_size = properties.batch_size
            job_properties.blender_version = properties.blender_version
            job_properties.octa_farm_config = get_preferences().octa_farm_config

        except Exception as e:
            traceback.print_exc()  # full traceback in console
            self.report({"ERROR"}, "An error occurred validating properties.")
            fail_validation = True

        if fail_validation:
            return None
        return job_properties

    def thread_run(self, job_properties: SubmitJobProperties):
        self.set_progress_name("Copying blend file")
        self.set_progress(0)
        try:
            temp_zip = Path(job_properties.temp_blend_name).parent / "temp.zip"
            self.set_progress_name("Packing blend file")
            self.set_progress(0.5)

            print("packing blend")
            self.pack_blend(Path(job_properties.temp_blend_name), temp_zip)

            if self.debug_zip:
                print("DEBUG: packed blend at ", temp_zip)
                # In debug mode, do not continue the submission process
                return

            self.set_progress_name("Calling Transfer Manager")
            self.set_progress(0.9)
            try:
                close_all_cached()
                try:
                    os.unlink(job_properties.temp_blend_name)
                except PermissionError:
                    print(
                        "Warning: Could not delete temp blend file - permission denied."
                    )
            except Exception as e:
                print(
                    f"Warning: Failed to close cached files or delete temp blend: {e}"
                )

            metadata = {"file_size": os.stat(temp_zip).st_size}

            print(metadata)

            while not ensure_running():
                time.sleep(3)
                print("waiting for transfer manager")

            user_data = unpack_octa_farm_config(job_properties.octa_farm_config)
            create_upload(
                str(temp_zip),
                {
                    "batch_size": job_properties.batch_size,
                    "blend_name": os.path.basename(job_properties.temp_blend_name),
                    "blender_version": job_properties.blender_version,
                    "render_passes": get_all_render_passes(),
                    "frame_end": job_properties.frame_end,
                    "frame_start": job_properties.frame_start,
                    "frame_step": job_properties.frame_step,
                    "max_thumbnail_size": job_properties.max_thumbnail_size,
                    "name": job_properties.job_name,
                    "render_engine": bpy.context.scene.render.engine,
                    "render_format": job_properties.render_format,
                },
                user_data,
                metadata,
            )

            # webbrowser.open(f"{user_data['farm_host']}/transfers/{{upload_id}}")
        except Exception:
            traceback.print_exc()
            self._error_message = "An error occurred while submitting the job."
        finally:
            self.set_progress_name("")
            self.set_progress(1)
            self._set_running(False)
