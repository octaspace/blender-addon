import bpy
import time
import requests
import os
from pathlib import Path
from tempfile import mktemp
from .cloudflare import FileUpload
from .sarfis import Sarfis
from .sarfis_operations import get_operations
from bpy.types import Operator
from threading import Thread
from ..blender_asset_tracer.pack import zipped
from ..blender_asset_tracer.blendfile import close_all_cached
from .octa_properties import SubmitJobProperties
from .web_ui import WebUi
from .util import get_all_render_passes
import webbrowser


def pack_blend(infile, zippath):
    # print all of the functions in blender_asset_tracer
    with zipped.ZipPacker(infile, infile.parent, zippath) as packer:
        packer.strategise()
        packer.execute()


# submit job operator
class SubmitJobOperator(Operator):
    bl_idname = "exporter.submit_job"
    bl_label = "Submit Job"
    bl_description = "Submit Job"

    _timer = None
    _running = False
    _progress = 0
    _progress_name = ""

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
                if area.type == 'PROPERTIES':
                    area.tag_redraw()

    @classmethod
    def set_progress_name(cls, value: str):
        cls._progress_name = value

    @classmethod
    def get_progress_name(cls):
        return cls._progress_name

    def modal(self, context, event):
        # if event.type in {'ESC'}:
        #    self.cancel(context)
        #    return {'CANCELLED'}

        if event.type == 'TIMER':
            if not self.get_running():  # <--- Wait until the image is marked as dirty
                self.finish(context)
                return {'FINISHED'}

        return {'PASS_THROUGH'}

    def cancel(self, context):
        # TODO: add way to cancel
        self.report({'INFO'}, "Octa render submit cancelled")

    def finish(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        self._run_thread = None
        self.report({'INFO'}, "Octa render submit finished")

    def invoke(self, context, event):
        if self.get_running():
            return {"CANCELLED"}

        job_properties = self.validate_properties(context)
        if job_properties is None:
            return {"CANCELLED"}

        self._set_running(True)
        temp_blend_name = os.path.join(os.path.dirname(bpy.data.filepath), 'octa_' + os.path.basename(bpy.data.filepath))
        bpy.ops.wm.save_as_mainfile(filepath=temp_blend_name, copy=True, compress=True)
        job_properties.temp_blend_name = temp_blend_name

        while f'{os.path.split(bpy.data.filepath)[1]}@' in os.listdir(os.path.dirname(bpy.data.filepath)):
            print("@ Detected")
            time.sleep(0.1)

        self._run_thread = Thread(target=self.thread_run, daemon=True, args=[job_properties])
        self._run_thread.start()
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def validate_properties(self, context):
        job_properties = SubmitJobProperties()
        fail_validation = False
        try:
            if not context.blend_data.filepath:
                self.report({'ERROR'}, "You have to save the .blend before submitting")
                fail_validation = True

            # get properties
            properties = context.scene.octa_properties
            job_name = properties.job_name
            if len(job_name) <= 0:
                self.report({'ERROR'}, 'Job name is not set')
                fail_validation = True

            job_properties.job_name = job_name

            print("job name: " + job_name)

            if properties.match_scene:
                scene = context.scene
                frame_start = scene.frame_start
                frame_end = scene.frame_end
            else:
                frame_start = properties.frame_start
                frame_end = properties.frame_end

            job_properties.frame_start = frame_start
            job_properties.frame_end = frame_end

            print("frame range: " + str(frame_start) + "-" + str(frame_end))
            frame_count = frame_end - frame_start + 1
            print("frame count: " + str(frame_count))

            if frame_count <= 0:
                self.report({'ERROR'}, 'Frame range is negative')
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

                self.report({'ERROR'}, f'Total frame count ({frame_count}) is not divisible by batch size {properties.batch_size}. {suggestion}')
                fail_validation = True

            octa_host = properties.octa_host
            octa_host = octa_host.rstrip('/')
            WebUi.set_host(octa_host)
            if len(octa_host) <= 0:
                self.report({'ERROR'}, 'Octa host is not set')
                fail_validation = True
            else:
                try:
                    # TODO: use this in future once hooked up
                    WebUi.get_version()
                    # TODO: get supported plugin version instead and fail if not supported anymore
                    response = requests.get(octa_host, timeout=15)
                except:
                    self.report({'ERROR'}, 'Octa host is not reachable')
                    fail_validation = True

            job_properties.advanced_section_visible = properties.advanced_section_visible
            job_properties.generate_video = properties.generate_video
            job_properties.match_scene = properties.match_scene
            job_properties.max_thumbnail_size = properties.max_thumbnail_size
            job_properties.render_format = properties.render_format  # bpy.context.scene.render.image_settings.file_format
            job_properties.render_output_path = properties.render_output_path
            job_properties.octa_host = octa_host
            job_properties.upload_threads = properties.upload_threads
            job_properties.batch_size = properties.batch_size
            job_properties.blender_version = properties.blender_version
            
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
            temp_zip_name = mktemp('.zip')

            self.set_progress_name("Packing blend file")
            self.set_progress(0.2)

            print("packing blend")
            pack_blend(Path(Path(job_properties.temp_blend_name)), Path(temp_zip_name))
            print("packed blend, deleting temp blend file")

            self.set_progress_name("Uploading")
            self.set_progress(0.5)
            try:
                close_all_cached()
                os.unlink(job_properties.temp_blend_name)
            except PermissionError:
                pass  # cant delete it cause the asset packer somehow still has an open handle on it. too bad

            job_id = int(time.time())

            set_thread_count = job_properties.upload_threads

            # zip_size = os.stat(temp_zip_name).st_size
            # min_chunk_size = 1024 * 1024
            # max_chunk_size = 1024 * 1024 * 20
            # chunk_size = max(min_chunk_size, min(max_chunk_size, (zip_size // set_thread_count) + 1))
            # thread_count = max(1, (zip_size // chunk_size) + 1)

            upload = FileUpload(temp_zip_name, str(job_id), thread_count=set_thread_count, progress_callback=self.set_progress)
            upload.start()
            upload.join()
            if not upload.success:
                raise Exception(f"upload failed: {upload.reason}")

            self.set_progress_name("Creating Job")
            self.set_progress(0.9)

            total_frames = job_properties.frame_end - job_properties.frame_start + 1
            if job_properties.batch_size != 1:
                end = job_properties.frame_start + (total_frames // job_properties.batch_size) - 1
            else:
                end = job_properties.frame_end
            Sarfis.node_job(job_properties.octa_host, {
                "job_data": {
                    'id': job_id,
                    'name': job_properties.job_name,
                    'status': 'queued',
                    'start': job_properties.frame_start,
                    'batch_size': job_properties.batch_size,
                    'end': end,
                    'render_passes': get_all_render_passes(),
                    'render_format': job_properties.render_format,
                    'version': '1712359928',
                    'render_engine': bpy.context.scene.render.engine,
                    'blender_version': job_properties.blender_version
                },
                "operations": get_operations(os.path.basename(job_properties.temp_blend_name), job_properties.render_format, job_properties.max_thumbnail_size)
            })

            bpy.context.scene.octa_properties.dl_job_id = str(job_id)

            webbrowser.open_new(f"{job_properties.octa_host}/project/{job_id}")
        finally:
            self.set_progress_name("")
            self.set_progress(1)
            self._set_running(False)

            try:
                os.unlink(temp_zip_name)
            except:
                pass
