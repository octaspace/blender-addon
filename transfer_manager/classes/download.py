from .transfer import Transfer, TransferException, TRANSFER_STATUS_RUNNING, TRANSFER_STATUS_PAUSED, TRANSFER_STATUS_SUCCESS, TRANSFER_STATUS_FAILURE, TRANSFER_STATUS_CREATED
from ..apis.sarfis import Sarfis
from ..util import IMAGE_TYPE_TO_EXTENSION, get_next_id
from dataclasses import dataclass
from ..apis.r2_worker_shared import R2_WORKER_ENDPOINT
from .progress import Progress
from .user_data import UserData
import os
import logging
import sanic
import asyncio
import httpx
import time

logger = logging.getLogger(__name__)

DOWNLOAD_RETRY_INTERVAL = 5
WORKER_COUNT = 4


@dataclass
class DownloadWorkOrder:
    url: str
    local_path: str
    rel_path: str
    progress: Progress
    status_text: str = ""

    def small_dict(self):
        return {
            "rel_path": self.rel_path,
            "done": self.progress.done,
            "total": self.progress.total,
        }


class Download(Transfer):
    def __init__(self, user_data: UserData, local_dir_path: str, job_id: str, metadata: dict):
        super().__init__(get_next_id(), "download", metadata)
        self.user_data = user_data
        self.local_dir_path = os.path.abspath(local_dir_path)
        self.job_id = job_id

        self.retries = 3
        self.task = None
        self.files = []
        self.configured_worker_count = WORKER_COUNT
        self.worker_count = 0

        self.total_bytes_downloaded = 0

    async def _check_pause(self):
        while self.status == TRANSFER_STATUS_PAUSED:
            await asyncio.sleep(1)

    async def download_worker(self, queue: asyncio.Queue):
        sub_progress = Progress()
        self.sub_progresses.append(sub_progress)
        client = httpx.AsyncClient()
        while self.status != TRANSFER_STATUS_FAILURE:  # failure if canceled
            work_order: DownloadWorkOrder = await queue.get()
            if work_order is None:
                break

            await self._check_pause()

            while True:  # never give up downloading
                try:
                    work_order.status_text = "Initiating Download"
                    async with client.stream("GET", work_order.url, headers={'authentication': self.user_data.api_token}) as response:
                        if not 200 <= response.status_code <= 299:
                            raise Exception(f"Request {work_order.rel_path} returned status {response.status_code}")
                        work_order.status_text = "Downloading"
                        with open(work_order.local_path, 'wb') as f:
                            file_size = int(response.headers["Content-Length"])
                            sub_progress.set_done_total(response.num_bytes_downloaded, file_size)
                            work_order.progress.set_done_total(response.num_bytes_downloaded, file_size)
                            self.total_bytes_downloaded += response.num_bytes_downloaded
                            async for chunk in response.aiter_bytes():
                                f.write(chunk)
                                self.total_bytes_downloaded += response.num_bytes_downloaded - sub_progress.done
                                sub_progress.set_done(response.num_bytes_downloaded)
                                work_order.progress.set_done(response.num_bytes_downloaded)
                    break
                except Exception as ex:
                    work_order.status_text = ex.args[0] if len(ex.args) > 0 else str(ex)
                    sub_progress.set_done(0)
                    await asyncio.sleep(DOWNLOAD_RETRY_INTERVAL)
            self.progress.increase_done(1)

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

        def add_work_order(_url, _local_path, _rel_path):
            work_order = DownloadWorkOrder(_url, _local_path, _rel_path, Progress())
            self.files.append(work_order)
            downloads.put_nowait(work_order)

        output_dir = os.path.join(self.local_dir_path, str(self.job_id))
        os.makedirs(output_dir, exist_ok=True)
        if len(render_passes) > 0:
            for render_pass_name, render_pass in render_passes.items():
                for render_pass_output_name, file_ext in render_pass["files"].items():
                    os.makedirs(os.path.join(output_dir, render_pass_output_name), exist_ok=True)
                    for t in range(frame_start, frame_end + 1):
                        file_full_name = f"{str(t).zfill(4)}.{file_ext}"
                        url = f"{R2_WORKER_ENDPOINT}/{self.job_id}/output/{render_pass_output_name}/{file_full_name}"
                        local_path = os.path.join(output_dir, render_pass_output_name, file_full_name)
                        add_work_order(url, local_path, f"{render_pass_output_name}/{file_full_name}")

        os.makedirs(output_dir, exist_ok=True)
        file_ext = IMAGE_TYPE_TO_EXTENSION.get(job["render_format"], "unknown")

        for t in range(frame_start, frame_end + 1):
            file_full_name = f"{str(t).zfill(4)}.{file_ext}"
            url = f"{R2_WORKER_ENDPOINT}/{self.job_id}/output/{file_full_name}"
            local_path = os.path.join(output_dir, file_full_name)
            add_work_order(url, local_path, file_full_name)

        self.progress.set_total(downloads.qsize())

        self.worker_count = min(self.configured_worker_count, downloads.qsize())
        for _ in range(self.worker_count):
            downloads.put_nowait(None)  # one none per worker

        workers = [asyncio.create_task(self.download_worker(downloads)) for _ in range(self.worker_count)]
        await asyncio.gather(*workers)

        self.progress.set_value(1)
        self.finished_at = time.time()
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
            logger.exception("exception during download")

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
        d['files'] = [i.small_dict() for i in self.files]
        d['total_bytes_downloaded'] = self.total_bytes_downloaded
        d['worker_count'] = self.worker_count
        d['configured_worker_count'] = self.configured_worker_count
        return d
