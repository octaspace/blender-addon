from .transfer import Transfer, TransferException, TRANSFER_STATUS_RUNNING, TRANSFER_STATUS_PAUSED, TRANSFER_STATUS_SUCCESS, TRANSFER_STATUS_FAILURE, TRANSFER_STATUS_CREATED
from ..apis.sarfis import Sarfis
from ..util import IMAGE_TYPE_TO_EXTENSION, get_next_id
from dataclasses import dataclass
from multiprocessing.pool import ThreadPool
from ..apis.web_api_base_sync import WebApiBaseSync
from traceback import print_exc
import os
import threading
import logging
import sanic
import time
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class DownloadUnit:
    url: str
    local_path: str
    index: int


class Download(Transfer):
    def __init__(self, user_data, local_dir_path, job_id, download_threads):
        super().__init__(get_next_id(), "download")
        self.user_data = user_data
        self.local_dir_path = local_dir_path
        self.job_id = job_id
        self.download_threads = download_threads

        self.retries = 3
        self.task = None
        self.lock = threading.Lock()
        self.completed_downloads = 0
        self.download_count = 0

    def download_task(self, download):
        try:
            logger.info(f"Downloading file {download.index}/{self.download_count}")
            dl_start = int(time.time() * 1000)
            response = WebApiBaseSync.request_with_retries("GET", download.url)
            dl_end = int(time.time() * 1000)

            save_start = int(time.time() * 1000)
            with open(download.local_path, "wb") as f:
                f.write(response.data)
            save_end = int(time.time() * 1000)

            with self.lock:
                self.completed_downloads += 1
                self.progress.set_of_finished(self.completed_downloads, self.download_count)

            logger.info(f"Downloaded {download.url} to {download.local_path}\n"
                        f"DL Time {dl_end - dl_start}ms | Save Time {save_end - save_start}ms\n"
                        f"Size {len(response.data) / 1000 / 1000:.2f}MB")
        except:
            logger.warning(f"Failed to download {download.url}: {print_exc()}")

    async def run_download(self):
        job = await Sarfis.get_job_details(self.user_data, self.job_id)
        render_passes = job['render_passes']

        downloads = []

        frame_start = job["start"]
        frame_end = job["end"]
        batch_size = job.get("batch_size", None)
        if batch_size is not None and batch_size > 1:
            total_batches = frame_end - frame_start + 1
            total_frames = batch_size * total_batches
            frame_end = frame_start + total_frames - 1

        output_dir = os.path.join(self.local_dir_path, str(self.job_id))
        os.makedirs(output_dir, exist_ok=True)
        download_index = 1
        if len(render_passes) > 0:
            for render_pass_name, render_pass in render_passes.items():
                for file_name, file_ext in render_pass["files"].items():
                    os.makedirs(os.path.join(output_dir, file_name), exist_ok=True)
                    for t in range(frame_start, frame_end + 1):
                        file_full_name = f"{str(t).zfill(4)}.{file_ext}"
                        url = f"https://render-data.octa.computer/{self.job_id}/output/{file_name}/{file_full_name}"
                        local_path = os.path.join(output_dir, file_name, file_full_name)
                        downloads.append(DownloadUnit(url, local_path, download_index))
                        download_index += 1

        os.makedirs(output_dir, exist_ok=True)
        file_ext = IMAGE_TYPE_TO_EXTENSION.get(job["render_format"], "unknown")

        for t in range(frame_start, frame_end + 1):
            file_full_name = f"{str(t).zfill(4)}.{file_ext}"
            url = f"https://render-data.octa.computer/{self.job_id}/output/{file_full_name}"
            local_path = os.path.join(output_dir, file_full_name)
            downloads.append(DownloadUnit(url, local_path, download_index))
            download_index += 1

        self.download_count = len(downloads)
        self.completed_downloads = 0

        pool = ThreadPool(self.download_threads)

        def do_it():
            pool.map(self.download_task, downloads)

        await asyncio.get_event_loop().run_in_executor(None, do_it)
        pool.close()

        self.progress.set_value(1)
        logger.info("Download Complete")

    async def run(self):
        try:
            await self.run_download()
            self.status = TRANSFER_STATUS_SUCCESS
        except TransferException as ex:
            self.status = TRANSFER_STATUS_FAILURE
            self.status_text = ex.args[0]
        except:
            self.status = TRANSFER_STATUS_FAILURE
            self.status_text = 'unknown exception'

    def start(self):
        if self.status == TRANSFER_STATUS_CREATED:
            self.status = TRANSFER_STATUS_RUNNING
            self.task = sanic.Sanic.get_app().add_task(self.run(), name=self.id)
        elif self.status == TRANSFER_STATUS_PAUSED:
            self.status = TRANSFER_STATUS_RUNNING

    def stop(self):
        if self.status != TRANSFER_STATUS_CREATED:
            self.status = TRANSFER_STATUS_FAILURE

    def pause(self):
        if self.status == TRANSFER_STATUS_RUNNING:
            self.status = TRANSFER_STATUS_PAUSED

    def to_dict(self):
        d = super().to_dict()
        d['local_dir_path'] = self.local_dir_path
        d['job_id'] = self.job_id
        return d
