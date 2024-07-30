import bpy
import os
import requests
from multiprocessing.pool import ThreadPool
from dataclasses import dataclass
from traceback import format_exc
from .octa_properties import DownloadJobProperties
from .web_ui import WebUi
from .modal_operator import ModalOperator
from .util import get_all_render_passes, IMAGE_TYPE_TO_EXTENSION
from .web_api_base import WebApiBase
import time
import threading


@dataclass
class Download:
    url: str
    local_path: str
    index: int


class DownloadJobOperator(ModalOperator):
    bl_idname = "exporter.download_job"
    bl_label = "Download Job"
    bl_description = "Download Job"
    instance = None

    def __init__(self):
        super().__init__()
        DownloadJobOperator.instance = self
        self.download_count = 0
        self.completed_downloads = 0
        self.lock = threading.Lock()

    def validate_properties(self, context):
        properties = DownloadJobProperties()
        fail_validation = False

        props = context.scene.octa_properties
        job_id = props.dl_job_id
        if len(job_id) <= 0:
            self.report({"ERROR"}, "Job id is not set")
            fail_validation = True

        properties.job_id = int(job_id)

        octa_host = props.octa_host
        octa_host = octa_host.rstrip("/")
        WebUi.set_host(octa_host)
        if len(octa_host) <= 0:
            self.report({"ERROR"}, "Octa host is not set")
            fail_validation = True
        else:
            try:
                # TODO: use this in future once hooked up
                WebUi.get_version()
                # TODO: get supported plugin version instead and fail if not supported anymore
                response = requests.get(octa_host, timeout=15)
            except:
                self.report({"ERROR"}, "Octa host is not reachable")
                fail_validation = True
        properties.octa_host = octa_host

        properties.output_path = props.dl_output_path
        properties.download_threads = props.dl_threads

        if fail_validation:
            return None

        return properties

    def download_task(self, download):
        try:
            self.set_progress_name(
                f"Downloading file {download.index}/{self.download_count}"
            )
            dl_start = int(time.time() * 1000)
            response = WebApiBase.request_with_retries("GET", download.url)
            dl_end = int(time.time() * 1000)

            save_start = int(time.time() * 1000)
            with open(download.local_path, "wb") as f:
                f.write(response.data)
            save_end = int(time.time() * 1000)

            with self.lock:
                self.completed_downloads += 1
                self.set_progress(self.completed_downloads / self.download_count)

            print(
                f"Downloaded {download.url} to {download.local_path}\nDL Time {dl_end - dl_start}ms | Save Time {save_end - save_start}ms | Size {len(response.data)/1000/1000:.2f}MB"
            )
        except Exception as e:
            print(f"Failed to download {download.url}: {e}")

    def run(self, properties: DownloadJobProperties):
        self.set_progress_name("Downloading frames")
        self.set_progress(0)

        job_id = properties.job_id
        octa_host = properties.octa_host
        job = (
            requests.get(f"{octa_host}/qm/api/job_details?job_id={job_id}")
            .json()
            .get("body")
        )
        render_passes = job.get("render_passes", None)
        if render_passes is None:
            render_passes = (
                get_all_render_passes()
            )  # get from file if not present on job and hope for the best

        downloads = []

        frame_start = job["start"]
        frame_end = job["end"]
        batch_size = job.get("batch_size", None)
        if batch_size is not None and batch_size > 1:
            total_batches = frame_end - frame_start + 1
            total_frames = batch_size * total_batches
            frame_end = frame_start + total_frames - 1

        output_dir = os.path.join(properties.output_path, str(job_id))
        os.makedirs(output_dir, exist_ok=True)
        download_index = 1
        if len(render_passes) > 0:
            for render_pass_name, render_pass in render_passes.items():
                for file_name, file_ext in render_pass["files"].items():
                    os.makedirs(os.path.join(output_dir, file_name), exist_ok=True)
                    for t in range(frame_start, frame_end + 1):
                        file_full_name = f"{str(t).zfill(4)}.{file_ext}"
                        url = f"https://render-data.octa.computer/{job_id}/output/{file_name}/{file_full_name}"
                        local_path = os.path.join(output_dir, file_name, file_full_name)
                        downloads.append(Download(url, local_path, download_index))
                        download_index += 1

        os.makedirs(output_dir, exist_ok=True)
        file_ext = IMAGE_TYPE_TO_EXTENSION.get(job["render_format"], "unknown")

        for t in range(frame_start, frame_end + 1):
            file_full_name = f"{str(t).zfill(4)}.{file_ext}"
            url = f"https://render-data.octa.computer/{job_id}/output/{file_full_name}"
            local_path = os.path.join(output_dir, file_full_name)
            downloads.append(Download(url, local_path, download_index))
            download_index += 1

        self.download_count = len(downloads)
        self.completed_downloads = 0

        pool = ThreadPool(properties.download_threads)
        pool.map(self.download_task, downloads)
        pool.close()

        self.set_progress_name("Download Complete")
        self.set_progress(1.0)
