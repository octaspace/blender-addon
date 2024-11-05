from ..transfer import Transfer, TransferException, TRANSFER_STATUS_RUNNING, TRANSFER_STATUS_PAUSED, TRANSFER_STATUS_SUCCESS, TRANSFER_STATUS_FAILURE, TRANSFER_STATUS_CREATED
from ...apis.sarfis import Sarfis
from ..util import get_next_id, get_file_md5
from ..sarfis_operations import get_operations
from ..user_data import UserData
from typing import TypedDict, BinaryIO
from ..version import version
from ...apis.r2_worker import AsyncR2Worker
from ..progress import Progress
from traceback import print_exc
from .upload_work_order import UploadWorkOrder
from dataclasses import dataclass
import asyncio
import os
import math
from sanic.log import logger
import sanic
import webbrowser
import shutil
import time

UPLOAD_PART_SIZE = 25 * 1024 * 1024  # 25 MB


class JobInformation(TypedDict):
    frame_start: int
    frame_end: int
    frame_step: int
    batch_size: int
    name: str
    render_passes: dict
    render_format: str
    render_engine: str
    blender_version: str
    blend_name: str
    max_thumbnail_size: int


class Upload(Transfer):
    def __init__(self, user_data: UserData, local_file_path: str, job_info: JobInformation, metadata: dict):
        super().__init__(get_next_id(), "upload", metadata)
        self.user_data = user_data
        self.local_file_path = os.path.abspath(local_file_path)
        self.job_info = job_info

        self.job_id = get_next_id()
        self.retries = 3
        self.run_task = None
        self._file: BinaryIO = None
        self.file_hash: str = None
        self.file_size = 0
        self._upload_id = None
        self.url = ""
        self.etags = []

    async def initialize(self):
        self.file_hash = await asyncio.to_thread(get_file_md5, self.local_file_path)

        with open(self.local_file_path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            self.file_size = f.tell()

        self.progress.set_total(self.file_size)

        self.url = f"{self.job_id}/input/package.zip"
        # logger.info(f"uploading to {self.url}")

        if self.file_size < UPLOAD_PART_SIZE:
            # r2 does not support multipart uploads for files < 5MB, lets not use multipart for files under the part size
            await self.init_single()
        else:
            await self.init_multi()

    def get_file(self):
        if self._file is None:
            self._file = open(self.local_file_path, 'rb')
        return self._file

    async def get_upload_id(self):
        if self._upload_id is None:
            data = await AsyncR2Worker.create_multipart_upload(self.user_data, self.url)  # TODO: actually do this lazy
            self._upload_id = data['uploadId']
        return self._upload_id

    async def init_single(self):
        self.work_orders.append(UploadWorkOrder(0, self.file_size, 1, self, True))

    async def init_multi(self):
        part_count = math.ceil(self.file_size / UPLOAD_PART_SIZE)
        logger.info(f"part count: {part_count}, file_size: {self.file_size}, part_size: {UPLOAD_PART_SIZE}")

        for i in range(part_count - 1):
            self.work_orders.append(UploadWorkOrder(i * UPLOAD_PART_SIZE, UPLOAD_PART_SIZE, i + 1, self, False))
        # add last part seperately
        last_part_offset = (part_count - 1) * UPLOAD_PART_SIZE
        self.work_orders.append(UploadWorkOrder(last_part_offset, self.file_size - last_part_offset, part_count, self, False))

    async def update(self):
        finished_files = 0
        running_or_created_files = 0
        for f in self.work_orders:
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


        # TODO: fill these 2 values by analyzing parts
        transfer_success = True
        transfer_ended = True
        if transfer_ended:
            self.get_file().close()
            self._file = None
            upload_id = await  self.get_upload_id()
            if transfer_success:
                await AsyncR2Worker.complete_multipart_upload(self.user_data, self.url, upload_id, self.etags)
                await self.run_job_create()
                await self.run_cleanup()
                self.status = TRANSFER_STATUS_SUCCESS
            else:
                await AsyncR2Worker.abort_multipart_upload(self.user_data, self.url, upload_id)
                await self.run_cleanup()
                self.status = TRANSFER_STATUS_FAILURE
                self.status_text = "Upload failed"
            self.finished_at = time.time()

    async def run_job_create(self):
        frame_end = self.job_info['frame_end']
        frame_start = self.job_info['frame_start']
        frame_step = self.job_info['frame_step']
        batch_size = self.job_info['batch_size']

        total_frames = frame_end - frame_start + 1

        if batch_size != 1:
            end = frame_start + (total_frames // batch_size) - 1
        elif frame_step > 1:
            end = (frame_end - frame_start) // frame_step
            end += frame_start
        else:
            end = frame_end

        render_format = self.job_info['render_format']
        await Sarfis.node_job(
            self.user_data,
            {
                "job_data": {
                    "id": self.job_id,
                    "name": self.job_info['name'],
                    "status": "queued",
                    "start": frame_start,
                    "batch_size": batch_size,
                    "end": end,
                    "frame_step": frame_step,
                    "render_passes": self.job_info['render_passes'],
                    "render_format": render_format,
                    "version": version,
                    "render_engine": self.job_info['render_engine'],
                    "blender_version": self.job_info['blender_version'],
                    "archive_size": self.file_size,
                },
                "operations": get_operations(
                    os.path.basename(self.job_info['blend_name']),
                    render_format,
                    self.job_info['max_thumbnail_size'],
                    self.file_hash,
                    frame_step,
                    self.user_data.api_token
                ),
            },
        )

        webbrowser.open_new(f"{self.user_data.farm_host}/project/{self.job_id}")

    async def run_cleanup(self):
        dir_to_delete = os.path.dirname(self.local_file_path)
        shutil.rmtree(dir_to_delete, ignore_errors=True)

    def to_dict(self):
        d = super().to_dict()
        d['local_file_path'] = self.local_file_path
        d['job_id'] = self.job_id
        d['job_info'] = self.job_info
        return d
