from .transfer import Transfer, TransferException, TRANSFER_STATUS_RUNNING, TRANSFER_STATUS_PAUSED, TRANSFER_STATUS_SUCCESS, TRANSFER_STATUS_FAILURE, TRANSFER_STATUS_CREATED
from ..apis.sarfis import Sarfis
from ..util import IMAGE_TYPE_TO_EXTENSION, get_next_id
from dataclasses import dataclass
from ..apis.r2_worker_shared import R2_WORKER_ENDPOINT
from .progress import Progress
import os
import threading
import logging
import sanic
import asyncio
import httpx

logger = logging.getLogger(__name__)

DOWNLOAD_RETRIES = 3
WORKER_COUNT = 4


@dataclass
class DownloadWorkOrder:
    url: str
    local_path: str
    download_number: int


class Download(Transfer):
    def __init__(self, user_data, local_dir_path, job_id):
        super().__init__(get_next_id(), "download")
        self.user_data = user_data
        self.local_dir_path = local_dir_path
        self.job_id = job_id

        self.retries = 3
        self.task = None
        self.lock = threading.Lock()

    async def download_worker(self, queue: asyncio.Queue):
        sub_progress = Progress()
        self.sub_progresses.append(sub_progress)
        while self.status != TRANSFER_STATUS_FAILURE:  # failure if another worker threw an exception
            work_order: DownloadWorkOrder = await queue.get()
            if work_order is None:
                break

            while self.status == TRANSFER_STATUS_PAUSED:
                await asyncio.sleep(1)

            tries = 0
            while tries <= DOWNLOAD_RETRIES:
                tries += 1
                try:
                    with open(work_order.local_path, 'wb') as f:
                        with httpx.stream("GET", work_order.url, params={"action": "get"}, headers={'authentication': self.user_data.api_token}) as response:
                            file_size = int(response.headers["Content-Length"])
                            sub_progress.set_of(file_size)
                            sub_progress.set_finished(response.num_bytes_downloaded)
                            for chunk in response.iter_bytes():
                                f.write(chunk)
                                sub_progress.set_finished(response.num_bytes_downloaded)
                    break
                except:
                    sub_progress.set_finished(0)
                    if tries > DOWNLOAD_RETRIES:
                        raise
            self.progress.increase_finished(1)

    async def run_download(self):
        job = await Sarfis.get_job_details(self.user_data, self.job_id)
        render_passes = job['render_passes']

        downloads = asyncio.Queue()

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
                        url = f"{R2_WORKER_ENDPOINT}/{self.job_id}/output/{file_name}/{file_full_name}"
                        local_path = os.path.join(output_dir, file_name, file_full_name)
                        downloads.put_nowait(DownloadWorkOrder(url, local_path, download_index))
                        download_index += 1

        os.makedirs(output_dir, exist_ok=True)
        file_ext = IMAGE_TYPE_TO_EXTENSION.get(job["render_format"], "unknown")

        for t in range(frame_start, frame_end + 1):
            file_full_name = f"{str(t).zfill(4)}.{file_ext}"
            url = f"{R2_WORKER_ENDPOINT}/{self.job_id}/output/{file_full_name}"
            local_path = os.path.join(output_dir, file_full_name)
            downloads.put_nowait(DownloadWorkOrder(url, local_path, download_index))
            download_index += 1

        self.progress.set_of(downloads.qsize())

        worker_count = min(WORKER_COUNT, downloads.qsize())
        for _ in range(worker_count):
            downloads.put_nowait(None)  # one none per worker

        workers = [asyncio.create_task(self.download_worker(downloads)) for _ in range(worker_count)]
        await asyncio.gather(*workers)

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
