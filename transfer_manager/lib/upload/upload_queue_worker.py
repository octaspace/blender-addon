from ..transfer_queue_worker import TransferQueueWorker
from ..transfer import TRANSFER_STATUS_SUCCESS, TRANSFER_STATUS_FAILURE, TRANSFER_STATUS_RUNNING, TRANSFER_STATUS_CREATED
from ..progress import Progress
from .upload_work_order import UploadWorkOrder
from ...apis.r2_worker import AsyncR2Worker
from sanic.log import logger
from traceback import format_exc
import asyncio

UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1MB


class UploadQueueWorker(TransferQueueWorker):
    async def data_generator(self, _data: bytes, current_bytes: list, work_order_progress: Progress, upload_progress: Progress):
        for i in range(0, len(_data), UPLOAD_CHUNK_SIZE):
            # TODO: no idea what will happen if we stall here indefinitely, could break, maybe resort to 1B/sec upload rate?
            await self._check_pause()

            chunk = _data[i:i + UPLOAD_CHUNK_SIZE]
            yield chunk
            chunk_len = len(chunk)
            current_bytes[0] += chunk_len
            work_order_progress.increase_done(chunk_len)
            upload_progress.increase_done(chunk_len)
            self.transfer_speed.update(chunk_len)

    async def _single(self, work_order: UploadWorkOrder):
        work_order.progress.set_total(work_order.size)
        upload = work_order.upload
        upload_progress = upload.progress
        work_order_progress = work_order.progress

        file = upload.get_file()
        file.seek(0)
        data = file.read()

        while not self.ct.is_canceled():
            current_bytes = [0]  # cant pass an int by reference, so list of a single int it is
            try:
                await AsyncR2Worker.upload_single_part(
                    upload.user_data,
                    upload.url,
                    self.data_generator(data, current_bytes, work_order_progress, upload_progress)
                )
                work_order.status = TRANSFER_STATUS_SUCCESS
                break
            except:
                exc = format_exc()
                self.queue.notify_workorder_retry(self)
                logger.debug(exc)
                work_order.history.append(exc)
                upload_progress.decrease_done(current_bytes[0])
                work_order_progress.set_done(0)

    async def _multi(self, work_order: UploadWorkOrder):
        transfer_name = f"part {work_order.part_number} with offset {work_order.offset} and size {work_order.size}"
        logger.debug(f"starting upload of {transfer_name}")

        file = work_order.upload.get_file()
        file.seek(work_order.offset)
        data = file.read(work_order.size)

        upload = work_order.upload
        upload_id = await upload.get_upload_id()
        upload_progress = upload.progress

        while not self.ct.is_canceled():
            current_bytes = [0]  # cant pass an int by reference, so list of a single int it is
            try:
                logger.debug(f"uploading {transfer_name} to {upload.url}")
                result = await AsyncR2Worker.upload_multipart_part(
                    upload.user_data,
                    upload.url,
                    upload_id,
                    work_order.part_number,
                    self.data_generator(data, current_bytes, work_order.progress, upload_progress)
                )
                work_order.status = TRANSFER_STATUS_SUCCESS
                logger.debug(f"upload of {transfer_name} returned {result}")
                upload.etags.append(result)
                break
            except:
                exc = format_exc()
                self.queue.notify_workorder_retry(self)
                logger.debug(exc)
                work_order.history.append(exc)
                upload_progress.decrease_done(current_bytes[0])
                work_order.progress.set_done(0)
                await asyncio.sleep(3)

    async def _run(self):
        logger.info("upload worker starting")

        work_order: UploadWorkOrder = None
        while not self.ct.is_canceled():
            try:
                work_order = await self.queue.get_next_work_order()

                if work_order is None:
                    await asyncio.sleep(1)
                    continue

                if work_order.is_single_upload:
                    await self._single(work_order)
                else:
                    await self._multi(work_order)
                await work_order.upload.update()
                self.queue.notify_workorder_success(self)
            except Exception as ex:
                if work_order is not None:
                    work_order.history.append(format_exc())
                    work_order.status_text = f"Exception: {ex.args[0]}"
                    work_order.status = TRANSFER_STATUS_FAILURE
                    try:
                        await work_order.upload.update()
                    except:
                        work_order.history.append(format_exc())
                        logger.exception("exception when calling upload.update()")
                logger.exception("exception from within upload worker", exc_info=ex)

        if work_order is not None:
            if work_order.status == TRANSFER_STATUS_RUNNING:
                work_order.status = TRANSFER_STATUS_CREATED

        logger.info("upload worker exiting")
