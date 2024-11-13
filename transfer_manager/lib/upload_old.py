from .transfer import Transfer, TransferException, TRANSFER_STATUS_RUNNING, TRANSFER_STATUS_PAUSED, TRANSFER_STATUS_SUCCESS, TRANSFER_STATUS_FAILURE, TRANSFER_STATUS_CREATED
from ..apis.sarfis import Sarfis
from .util import get_next_id, get_file_md5
from .sarfis_operations import get_operations
from .user_data import UserData
from typing import TypedDict, BinaryIO
from .version import version
from ..apis.r2_worker import AsyncR2Worker
from .progress import Progress
from traceback import print_exc
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
UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1MB
UPLOAD_RETRIES = 3
WORKER_COUNT = 4


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


@dataclass
class UploadWorkOrder:
    offset: int
    size: int
    part_number: int


class Upload(Transfer):
    def __init__(self, user_data: UserData, local_file_path: str, job_info: JobInformation, metadata: dict):
        super().__init__(get_next_id(), "upload", metadata)
        self.user_data = user_data
        self.local_file_path = os.path.abspath(local_file_path)
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
        self.worker_count = 0
        self.configured_worker_count = WORKER_COUNT

    async def run_init(self):
        self.file_hash = await asyncio.to_thread(get_file_md5, self.local_file_path)

    async def run_upload(self):
        with open(self.local_file_path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            self.file_size = f.tell()

        self.progress.set_total(self.file_size)

        self.url = f"{self.job_id}/input/package.zip"
        logger.info(f"uploading to {self.url}")

        if self.file_size < UPLOAD_PART_SIZE:
            # r2 does not support multipart uploads for files < 5MB, lets not use multipart for files under the part size
            await self.run_upload_single()
        else:
            await self.run_upload_multi()

    async def data_generator(self, _data, current_bytes: list, worker_progress: Progress):
        for i in range(0, len(_data), UPLOAD_CHUNK_SIZE):
            # TODO: no idea what will happen if we stall here indefinitely, could break, maybe resort to 1B/sec upload rate?
            while self.status == TRANSFER_STATUS_PAUSED:
                await asyncio.sleep(1)

            chunk = _data[i:i + UPLOAD_CHUNK_SIZE]
            yield chunk
            chunk_len = len(chunk)
            current_bytes[0] += chunk_len
            worker_progress.increase_done(chunk_len)
            self.progress.increase_done(chunk_len)

    async def run_upload_single(self):
        with open(self.local_file_path, 'rb') as f:
            data = f.read()

        self.worker_count = 1

        sub_progress = Progress()
        self.sub_progresses.append(sub_progress)

        sub_progress.set_total(len(data))
        self.progress.set_total(len(data))

        tries = 0
        while tries <= UPLOAD_RETRIES:
            tries += 1
            current_bytes = [0]  # cant pass an int by reference, so list of a single int it is
            try:
                await AsyncR2Worker.upload_single_part(self.user_data, self.url, self.data_generator(data, current_bytes, sub_progress))
                break
            except:
                sub_progress.set_done(0)
                self.progress.set_done(0)
                if tries > UPLOAD_RETRIES:
                    raise

    async def upload_worker(self, queue: asyncio.Queue):
        sub_progress = Progress()
        self.sub_progresses.append(sub_progress)
        while self.status != TRANSFER_STATUS_FAILURE:  # failure if another worker threw an exception
            work_order: UploadWorkOrder = await queue.get()
            if work_order is None:
                break

            sub_progress.set_done_total(0, work_order.size)

            while self.status == TRANSFER_STATUS_PAUSED:
                await asyncio.sleep(1)

            logger.info(f"part {work_order.part_number} with offset {work_order.offset} and size {work_order.size}")
            self.file.seek(work_order.offset)
            data = self.file.read(work_order.size)

            tries = 0
            while tries <= UPLOAD_RETRIES:
                tries += 1
                current_bytes = [0]  # cant pass an int by reference, so list of a single int it is
                try:
                    result = await AsyncR2Worker.upload_multipart_part(self.user_data, self.url, self.upload_id, work_order.part_number, self.data_generator(data, current_bytes, sub_progress))
                    self.etags.append(result)
                    break
                except:
                    sub_progress.set_done(0)
                    self.progress.decrease_done(current_bytes[0])
                    if tries > UPLOAD_RETRIES:
                        raise

    async def run_upload_multi(self):
        part_count = math.ceil(self.file_size / UPLOAD_PART_SIZE)
        self.worker_count = min(self.configured_worker_count, part_count)
        logger.info(f"part count: {part_count}, file_size: {self.file_size}, part_size: {UPLOAD_PART_SIZE}")

        data = await AsyncR2Worker.create_multipart_upload(self.user_data, self.url)
        self.upload_id = data['uploadId']

        # build queue of workOrders
        queue = asyncio.Queue()
        for i in range(part_count - 1):
            queue.put_nowait(UploadWorkOrder(i * UPLOAD_PART_SIZE, UPLOAD_PART_SIZE, i + 1))
        # add last part seperately
        last_part_offset = (part_count - 1) * UPLOAD_PART_SIZE
        queue.put_nowait(UploadWorkOrder(last_part_offset, self.file_size - last_part_offset, part_count))

        for _ in range(self.worker_count):
            queue.put_nowait(None)  # one none per worker

        try:
            with open(self.local_file_path, 'rb') as f:
                self.file = f
                workers = [asyncio.create_task(self.upload_worker(queue)) for _ in range(self.worker_count)]
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

    async def run(self):
        try:
            await self.run_init()
            await self.run_upload()
            await self.run_job_create()
            await self.run_cleanup()
            self.progress.set_value(1)
            self.status = TRANSFER_STATUS_SUCCESS
        except TransferException as ex:
            self.status = TRANSFER_STATUS_FAILURE
            self.status_text = ex.args[0]
            logger.warning(f"upload failed: {print_exc()}")
        except:
            self.status = TRANSFER_STATUS_FAILURE
            self.status_text = 'unknown exception'
            logger.warning(f"upload failed: {print_exc()}")
        finally:
            self.finished_at = time.time()

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
        d['job_info'] = self.job_info
        d['worker_count'] = self.worker_count
        d['configured_worker_count'] = self.configured_worker_count
        return d
