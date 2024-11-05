from ..transfer import Transfer, TRANSFER_STATUS_RUNNING, TRANSFER_STATUS_PAUSED, TRANSFER_STATUS_SUCCESS, TRANSFER_STATUS_FAILURE, TRANSFER_STATUS_CREATED
from ...apis.sarfis import Sarfis
from ..util import IMAGE_TYPE_TO_EXTENSION, get_next_id
from .download_work_order import DownloadWorkOrder
from ...apis.r2_worker_shared import R2_WORKER_ENDPOINT
from ..user_data import UserData
from typing import List
import os
import time


class Download(Transfer):
    def __init__(self, user_data: UserData, local_dir_path: str, job_id: str, metadata: dict):
        super().__init__(get_next_id(), "download", metadata)
        self.user_data = user_data
        self.local_dir_path = os.path.abspath(local_dir_path)
        self.job_id = job_id

        self.files: List[DownloadWorkOrder] = []

    async def initialize(self):
        job = await Sarfis.get_job_details(self.user_data, self.job_id)
        render_passes = job['render_passes']

        frame_start = job["start"]
        frame_end = job["end"]
        batch_size = job.get("batch_size", None)
        if batch_size is not None and batch_size > 1:
            total_batches = frame_end - frame_start + 1
            total_frames = batch_size * total_batches
            frame_end = frame_start + total_frames - 1

        number = 0

        def add_work_order(_url, _local_path, _rel_path):
            nonlocal number
            self.files.append(DownloadWorkOrder(number, _url, _local_path, _rel_path, self))
            number += 1

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

        file_ext = IMAGE_TYPE_TO_EXTENSION.get(job["render_format"], "unknown")

        for t in range(frame_start, frame_end + 1):
            file_full_name = f"{str(t).zfill(4)}.{file_ext}"
            url = f"{R2_WORKER_ENDPOINT}/{self.job_id}/output/{file_full_name}"
            local_path = os.path.join(output_dir, file_full_name)
            add_work_order(url, local_path, file_full_name)

        self.progress.set_total(len(self.files))

    def update(self):
        finished_files = 0
        running_or_created_files = 0
        for f in self.files:
            if f.status == TRANSFER_STATUS_SUCCESS:
                finished_files += 1
            elif f.status in [TRANSFER_STATUS_RUNNING, TRANSFER_STATUS_CREATED]:
                running_or_created_files += 1
        self.progress.set_done(finished_files)

        if self.progress.done >= self.progress.total:
            self.status = TRANSFER_STATUS_SUCCESS
            self.finished_at = time.time()
        elif running_or_created_files == 0:  # if not all done, but no running or created files left, download is finished and gets status failed
            self.status = TRANSFER_STATUS_FAILURE
            self.finished_at = time.time()
            self.status_text = "Some files could not be downloaded"

    def start(self):
        if self.status in [TRANSFER_STATUS_CREATED, TRANSFER_STATUS_PAUSED]:
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
        return d
