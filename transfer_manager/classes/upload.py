from .transfer import Transfer, TransferException, TRANSFER_STATUS_RUNNING, TRANSFER_STATUS_PAUSED, TRANSFER_STATUS_SUCCESS, TRANSFER_STATUS_FAILURE, TRANSFER_STATUS_CREATED
from ..apis.webui import WebUi
from ..apis.sarfis import Sarfis
from ..util import get_next_id, get_file_md5
from .file_slice_with_callback import FileSliceWithCallback
from ..sarfis_operations import get_operations
from .user_data import UserData
from typing import TypedDict
from ..version import version
import asyncio
import os
import math
import logging
import sanic
import webbrowser

logger = logging.getLogger(__name__)

UPLOAD_PART_SIZE = 25000000  # 25 MB


class JobInformation(TypedDict):
    frame_start: int
    frame_end: int
    batch_size: int
    name: str
    render_passes: dict
    render_format: str
    render_engine: str
    blender_version: str
    blend_name: str
    max_thumbnail_size: int


class Upload(Transfer):
    def __init__(self, user_data: UserData, local_file_path: str, job_info: JobInformation):
        super().__init__(get_next_id(), "upload")
        self.user_data = user_data
        self.local_file_path = local_file_path
        self.job_info = job_info

        self.job_id = get_next_id()
        self.retries = 3
        self.run_task = None
        self.zip_hash: str = None

    async def run_init(self):
        self.zip_hash = get_file_md5(self.local_file_path)

    async def run_upload(self):
        with open(self.local_file_path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()

        part_count = math.ceil(file_size / UPLOAD_PART_SIZE)
        logger.info(f"part count: {part_count}, file_size: {file_size}, part_size: {UPLOAD_PART_SIZE}")

        etags = {}

        data = await WebUi.get_job_input_multipart_upload_info_full(self.user_data, self.job_id, part_count)
        key = data['key']
        bucket = data['bucket']
        upload_id = data['upload_id']
        links = data['links']

        with open(self.local_file_path, 'rb') as f:
            part_number = 1
            running = True
            while running and self.status != TRANSFER_STATUS_FAILURE:
                offset = f.tell()
                part_size = UPLOAD_PART_SIZE
                if offset + UPLOAD_PART_SIZE > file_size:
                    part_size = file_size - offset
                    running = False

                logger.info(f"part {part_number} with offset {offset} and size {part_size}")

                def _callback(fake_offset, fake_size):
                    self.progress.set_of_finished(offset + fake_offset, file_size)
                    self.sub_progress.set_of_finished(fake_offset, fake_size)

                file_slice = FileSliceWithCallback(f, offset, part_size, _callback)
                url = links[part_number - 1]  # WebUi.get_multipart_signed_url(key, bucket, upload_id, part_number)
                response = await WebUi.request_with_retries('PUT', url, headers={
                    'Content-Length': part_size
                }, body=file_slice, retries=self.retries)

                etags[part_number] = response.headers['ETag']

                part_number += 1
                while self.status == TRANSFER_STATUS_PAUSED:
                    await asyncio.sleep(3)
        if self.status == TRANSFER_STATUS_FAILURE:
            raise TransferException("aborted")

        if part_count == len(etags):
            await WebUi.complete_job_input_multipart_upload(self.user_data, key, bucket, upload_id, etags)
        else:
            await WebUi.abort_job_input_multipart_upload(self.user_data, key, bucket, upload_id)
            raise TransferException(f"expected etag count to be {part_count} but it was {len(etags)}")

    async def run_job_create(self):
        frame_end = self.job_info['frame_end']
        frame_start = self.job_info['frame_start']
        batch_size = self.job_info['batch_size']

        total_frames = frame_end - frame_start + 1
        if batch_size != 1:
            end = frame_start + (total_frames // batch_size) - 1
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
                    "render_passes": self.job_info['render_passes'],
                    "render_format": render_format,
                    "version": version,
                    "render_engine": self.job_info['render_engine'],
                    "blender_version": self.job_info['blender_version'],
                },
                "operations": get_operations(
                    os.path.basename(self.job_info['blend_name']),
                    render_format,
                    self.job_info['max_thumbnail_size'],
                    self.zip_hash,
                ),
            },
        )

        webbrowser.open_new(f"{self.user_data.farm_host}/project/{self.job_id}")

    async def run(self):
        try:
            await self.run_init()
            await self.run_upload()
            await self.run_job_create()
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
            self.run_task = sanic.Sanic.get_app().add_task(self.run(), name=self.id)
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
        d['local_file_path'] = self.local_file_path
        d['job_id'] = self.job_id
        return d
