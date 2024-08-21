import asyncio

from .item import Item, ITEM_STATUS_RUNNING, ITEM_STATUS_PAUSED, ITEM_STATUS_SUCCESS, ITEM_STATUS_FAILURE, ITEM_STATUS_CREATED
from ..apis.webui import WebUi
from ..util import get_next_id
from .file_slice_with_callback import FileSliceWithCallback
import os
import math
import logging
import sanic

logger = logging.getLogger(__name__)

UPLOAD_PART_SIZE = 25000000  # 25 MB


class Upload(Item):
    def __init__(self, id, local_file_path):
        self.local_file_path = local_file_path
        self.job_id = get_next_id()
        self.retries = 3
        self.task = None
        super().__init__(id)

    async def run(self):
        with open(self.local_file_path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()

        part_count = math.ceil(file_size / UPLOAD_PART_SIZE)
        logger.info(f"part count: {part_count}, file_size: {file_size}, part_size: {UPLOAD_PART_SIZE}")

        etags = {}

        data = await WebUi.get_job_input_multipart_upload_info_full(self.job_id, part_count)
        key = data['key']
        bucket = data['bucket']
        upload_id = data['upload_id']
        links = data['links']

        with open(self.local_file_path, 'rb') as f:
            part_number = 1
            running = True
            while running and self.status != ITEM_STATUS_FAILURE:
                offset = f.tell()
                part_size = UPLOAD_PART_SIZE
                if offset + UPLOAD_PART_SIZE > file_size:
                    part_size = file_size - offset
                    running = False

                logger.info(f"part {part_number} with offset {offset} and size {part_size}")

                def _callback(fake_offset, fake_size):
                    progress = (offset + fake_offset) / file_size
                    self.progress = progress

                file_slice = FileSliceWithCallback(f, offset, part_size, _callback)
                url = links[part_number - 1]  # WebUi.get_multipart_signed_url(key, bucket, upload_id, part_number)
                response = await WebUi.request_with_retries('PUT', url, headers={
                    'Content-Length': part_size
                }, body=file_slice, retries=self.retries)

                etags[part_number] = response.headers['ETag']

                part_number += 1
                while self.status == ITEM_STATUS_PAUSED:
                    await asyncio.sleep(3)

        if part_count == len(etags):
            await WebUi.complete_job_input_multipart_upload(key, bucket, upload_id, etags)
            self.status = ITEM_STATUS_SUCCESS
        else:
            await WebUi.abort_job_input_multipart_upload(key, bucket, upload_id)
            self.status = ITEM_STATUS_FAILURE
            self.status_text = f"expected etag count to be {part_count} but it was {len(etags)}"

    def start(self):
        if self.status == ITEM_STATUS_CREATED:
            self.status = ITEM_STATUS_RUNNING
            self.task = sanic.Sanic.get_app().add_task(self.run(), name=self.id)
        elif self.status == ITEM_STATUS_PAUSED:
            self.status = ITEM_STATUS_RUNNING

    def stop(self):
        if self.status != ITEM_STATUS_CREATED:
            self.status = ITEM_STATUS_FAILURE

    def pause(self):
        if self.status == ITEM_STATUS_RUNNING:
            self.status = ITEM_STATUS_PAUSED
