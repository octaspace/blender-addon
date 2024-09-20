import bpy
import time
import os
from pathlib import Path
from bpy.types import Operator
from threading import Thread
from ..blender_asset_tracer.pack import zipped
from ..blender_asset_tracer.blendfile import close_all_cached
from .octa_properties import SubmitJobProperties
from .transfer_manager import create_upload, ensure_running
from .util import get_all_render_passes, unpack_octa_farm_config
import subprocess
import shutil


def subprocess_unpacker():
    current_file_path = bpy.data.filepath
    parent_dir = os.path.dirname(current_file_path)
    folder = os.path.join(parent_dir, f"{int(time.time())}_octa_")
    print(folder)
    if not os.path.exists(folder):
        print(f"creating {folder}")
        os.makedirs(folder, exist_ok=True)

    temp_blend_name = os.path.abspath(os.path.join(folder, os.path.basename(current_file_path)))

    bpy.ops.wm.save_as_mainfile(filepath=temp_blend_name, copy=True, compress=True)

    blender_executable = bpy.app.binary_path

    script_path = os.path.realpath(__file__)
    dir_path = os.path.dirname(script_path)
    subprocess_unpacker_script = os.path.abspath(os.path.join(dir_path, "subprocess_unpacker.py"))

    # Determine the name of the cache folder
    base_file_name = os.path.splitext(os.path.basename(current_file_path))[0]
    cache_folder_name = f"blendcache_{base_file_name}"
    cache_folder_path = os.path.join(parent_dir, cache_folder_name)

    # Check if the cache folder exists and copy it
    if os.path.exists(cache_folder_path):
        destination_cache_folder = os.path.join(folder, cache_folder_name)
        shutil.copytree(cache_folder_path, destination_cache_folder)
        print(f"Copied cache folder to: {destination_cache_folder}")

    command = [
        blender_executable,
        "-b",
        current_file_path,
        "--python",
        subprocess_unpacker_script,
        "--",
        "-save_path",
        temp_blend_name,
    ]

    subprocess.run(command)

    return temp_blend_name, folder


def pack_blend(infile, zippath):
    # print all of the functions in blender_asset_tracer
    with zipped.ZipPacker(infile, infile.parent, zippath) as packer:
        packer.strategise()
        packer.execute()


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

    debug_zip: bpy.props.BoolProperty(name="Debug .zip", default=False)

    def __init__(self):
        self._run_thread: Thread = None

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
        self.report({"INFO"}, "Octa render submit finished")

    def invoke(self, context, event):
        if self.get_running():
            return {"CANCELLED"}

        job_properties = self.validate_properties(context)
        if job_properties is None:
            return {"CANCELLED"}

        self._set_running(True)

        temp_blend_name, temp_work_folder = subprocess_unpacker()
        wait_for_save()  # TODO: do we still need this?
        job_properties.temp_work_folder = temp_work_folder
        job_properties.temp_blend_name = temp_blend_name

        self._run_thread = Thread(
            target=self.thread_run, daemon=True, args=[job_properties]
        )
        self._run_thread.start()
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def validate_properties(self, context):
        scene = context.scene
        job_properties = SubmitJobProperties()
        fail_validation = False
        try:
            if not context.blend_data.filepath:
                self.report({"ERROR"}, "You have to save the .blend before submitting")
                fail_validation = True

            # get properties
            properties = scene.octa_properties
            job_name = properties.job_name
            if len(job_name) <= 0:
                self.report({"ERROR"}, "Job name is not set")
                fail_validation = True

            job_properties.job_name = job_name

            print("job name: " + job_name)

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

            print("frame range: " + str(frame_start) + "-" + str(frame_end))
            frame_count = frame_end - frame_start + 1
            print("frame count: " + str(frame_count))

            if frame_count <= 0:
                self.report({"ERROR"}, "Frame range is negative")
                fail_validation = True

            if frame_count % properties.batch_size != 0:
                suggested_divisions = []
                for i in range(2, 100, 1):
                    if frame_count % i == 0:
                        suggested_divisions.append(i)

                suggested_divisions.sort()
                suggestion = "Chose a different frame range"
                if len(suggested_divisions) > 0:
                    suggestion = f'Suggested batch sizes: {", ".join([str(d) for d in suggested_divisions[:5]])}'

                self.report(
                    {"ERROR"},
                    f"Total frame count ({frame_count}) is not divisible by batch size {properties.batch_size}. {suggestion}",
                )
                fail_validation = True

            job_properties.advanced_section_visible = properties.advanced_section_visible
            job_properties.generate_video = properties.generate_video
            job_properties.match_scene = properties.match_scene
            job_properties.max_thumbnail_size = properties.max_thumbnail_size
            job_properties.render_format = properties.render_format  # bpy.context.scene.render.image_settings.file_format
            job_properties.render_output_path = properties.render_output_path
            job_properties.upload_threads = properties.upload_threads
            job_properties.batch_size = properties.batch_size
            job_properties.blender_version = properties.blender_version
            job_properties.octa_farm_config = properties.octa_farm_config

        except:
            raise

        if fail_validation:
            return None

        return job_properties

    def thread_run(self, job_properties: SubmitJobProperties):
        self.set_progress_name("Copying blend file")
        self.set_progress(0)
        try:
            # temp names
            temp_zip = Path(job_properties.temp_blend_name).parent / "temp.zip"

            self.set_progress_name("Packing blend file")
            self.set_progress(0.5)  # TODO: track progress of packing

            print("packing blend")
            pack_blend(Path(Path(job_properties.temp_blend_name)), temp_zip)
            if self.debug_zip:
                print("DEBUG packed blend: ", temp_zip)
                return

            print("packed blend, deleting temp blend file")

            self.set_progress_name("Calling Transfer Manager")
            self.set_progress(0.9)
            try:
                close_all_cached()
                os.unlink(job_properties.temp_blend_name)
            except PermissionError:
                pass  # cant delete it cause the asset packer somehow still has an open handle on it. too bad

            total_frames = job_properties.frame_end - job_properties.frame_start + 1
            if job_properties.batch_size != 1:
                end = job_properties.frame_start + (total_frames // job_properties.batch_size) - 1
            elif job_properties.frame_step > 1:
                end = (job_properties.frame_end - job_properties.frame_start) // job_properties.frame_step
                end += job_properties.frame_start
            else:
                end = job_properties.frame_end

            ensure_running()
            create_upload(str(temp_zip), job_information={
                "batch_size": job_properties.batch_size,
                "blend_name": os.path.basename(job_properties.temp_blend_name),
                "blender_version": job_properties.blender_version,
                "render_passes": get_all_render_passes(),
                "frame_end": end,
                "frame_start": job_properties.frame_start,
                "frame_step": job_properties.frame_step,
                "max_thumbnail_size": job_properties.max_thumbnail_size,
                "name": job_properties.job_name,
                "render_engine": bpy.context.scene.render.engine,
                "render_format": job_properties.render_format
            }, user_data=unpack_octa_farm_config(job_properties.octa_farm_config))
        finally:
            self.set_progress_name("")
            self.set_progress(1)
            self._set_running(False)

        try:
            if not self.debug_zip:
                shutil.rmtree(job_properties.temp_work_folder)
        except:
            pass
