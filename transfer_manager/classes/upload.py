from .transfer import Transfer, TransferException, TRANSFER_STATUS_RUNNING, TRANSFER_STATUS_PAUSED, TRANSFER_STATUS_SUCCESS, TRANSFER_STATUS_FAILURE, TRANSFER_STATUS_CREATED
from ..apis.sarfis import Sarfis
from ..util import get_next_id, get_file_md5
from ..sarfis_operations import get_operations
from .user_data import UserData
from typing import TypedDict, BinaryIO
from ..version import version
from ..apis.r2_worker import AsyncR2Worker
import asyncio
import os
import math
import logging
import sanic
import webbrowser

logger = logging.getLogger(__name__)

UPLOAD_PART_SIZE = 25 * 1024 * 1024  # 25 MB
UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1MB
WORKER_COUNT = 4


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


class UploadWorkOrder:
    def __init__(self, offset, size, part_number):
        self.offset = offset
        self.size = size
        self.part_number = part_number


class Upload(Transfer):
    def __init__(self, user_data: UserData, local_file_path: str, job_info: JobInformation):
        super().__init__(get_next_id(), "upload")
        self.user_data = user_data
        self.local_file_path = local_file_path
        self.job_info = job_info

        self.job_id = get_next_id()
        self.retries = 3
        self.run_task = None
        self.file: BinaryIO = None
        self.file_hash: str = None
        self.file_size = 0
        self.upload_id = ""
        self.url = ""
        self.etags = []

    async def run_init(self):
        self.file_hash = await asyncio.to_thread(get_file_md5, self.local_file_path)

    async def run_upload(self):
        with open(self.local_file_path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            self.file_size = f.tell()

        self.progress.set_of(self.file_size)

        if self.file_size < UPLOAD_PART_SIZE:
            # r2 does not support multipart uploads for files < 5MB, lets not use multipart for files under the part size
            await self.run_upload_single()
        else:
            await self.run_upload_multi()

    async def data_generator(self, _data):
        for i in range(0, len(_data), UPLOAD_CHUNK_SIZE):
            # TODO: no idea what will happen if we stall here indefinitely, could break, maybe resort to 1B/sec upload rate?
            while self.status == TRANSFER_STATUS_PAUSED:
                await asyncio.sleep(1)

            chunk = _data[i:i + UPLOAD_CHUNK_SIZE]
            yield chunk
            self.progress.increase_finished(len(chunk))

    async def run_upload_single(self):
        with open(self.local_file_path, 'rb') as f:
            data = f.read()

        await AsyncR2Worker.upload_single_part(self.user_data, self.url, self.data_generator(data))

    async def upload_worker(self, queue: asyncio.Queue):
        while self.status != TRANSFER_STATUS_FAILURE:
            workOrder: UploadWorkOrder = await queue.get()
            if workOrder is None:
                break

            while self.status == TRANSFER_STATUS_PAUSED:
                await asyncio.sleep(1)

            logger.info(f"part {workOrder.part_number} with offset {workOrder.offset} and size {workOrder.size}")
            self.file.seek(workOrder.offset)
            data = self.file.read(workOrder.size)

            result = await AsyncR2Worker.upload_multipart_part(self.user_data, self.url, self.upload_id, workOrder.part_number, self.data_generator(data))
            self.etags.append(result)

    async def run_upload_multi(self):
        part_count = math.ceil(self.file_size / UPLOAD_PART_SIZE)
        worker_count = min(WORKER_COUNT, part_count)
        logger.info(f"part count: {part_count}, file_size: {self.file_size}, part_size: {UPLOAD_PART_SIZE}")

        self.url = f"{self.job_id}/input/package.zip"

        data = await AsyncR2Worker.create_multipart_upload(self.user_data, self.url)
        self.upload_id = data['uploadId']

        # build queue of workOrders
        queue = asyncio.Queue()
        for i in range(part_count - 1):
            queue.put_nowait(UploadWorkOrder(i * UPLOAD_PART_SIZE, UPLOAD_PART_SIZE, i + 1))
        # add last part seperately
        last_part_offset = (part_count - 1) * UPLOAD_PART_SIZE
        queue.put_nowait(UploadWorkOrder(last_part_offset, self.file_size - last_part_offset, part_count))

        for _ in range(worker_count):
            queue.put_nowait(None)  # one none per worker

        try:
            with open(self.local_file_path, 'rb') as f:
                self.file = f
                workers = [asyncio.create_task(self.upload_worker(queue)) for _ in range(worker_count)]
                await asyncio.gather(*workers)
            await AsyncR2Worker.complete_multipart_upload(self.user_data, self.url, self.upload_id, self.etags)
        except:
            await AsyncR2Worker.abort_multipart_upload(self.user_data, self.url, self.upload_id)
            raise TransferException("exception during upload")  # TODO: craft a more meaningful exception
        finally:
            self.file = None

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
                    self.file_hash,
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
