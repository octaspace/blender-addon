import asyncio
import httpx
from typing import TYPE_CHECKING
from sanic.log import logger
from traceback import format_exception
from .transfer import TRANSFER_STATUS_RUNNING, TRANSFER_STATUS_PAUSED, TRANSFER_STATUS_CREATED, TRANSFER_STATUS_SUCCESS
from .download_work_order import DownloadWorkOrder
from .cancellation_token import CancellationToken
from .transfer_speed import TransferSpeed

if TYPE_CHECKING:
    from .download_queue import DownloadQueue

    DOWNLOAD_RETRY_INTERVAL = 5


class DownloadQueueWorker:
    def __init__(self, queue: "DownloadQueue"):
        self.queue = queue
        self.transfer_speed = TransferSpeed()
        self.ct = CancellationToken()
        self.task = None

    def start(self):
        self.task = asyncio.create_task(self._run())

    def stop(self):
        self.ct.cancel()

    async def _check_pause(self):
        while self.queue.status == TRANSFER_STATUS_PAUSED:
            await asyncio.sleep(1)

    async def _run(self):
        client = httpx.AsyncClient()
        while not self.ct.is_canceled():
            work_order: DownloadWorkOrder = await self.queue.get_next_work_order()
            if work_order is None:
                await asyncio.sleep(1)
                continue

            download = work_order.download
            transfer_name = f"file {work_order.number} of {len(download.files)} of job {download.job_id}"

            await self._check_pause()

            while True:  # never give up downloading
                try:
                    work_order.status_text = "Initiating Download"
                    logger.info(f"start downloading {transfer_name}")
                    async with client.stream("GET", work_order.url, headers={'authentication': download.user_data.api_token}) as response:
                        if not 200 <= response.status_code <= 299:
                            msg = f"download of {transfer_name} failed with response code {response.status_code}"
                            logger.warning(msg)
                            raise Exception(msg)
                        work_order.status_text = "Downloading"
                        with open(work_order.local_path, 'wb') as f:
                            file_size = int(response.headers["Content-Length"])
                            work_order.progress.set_done_total(response.num_bytes_downloaded, file_size)
                            self.transfer_speed.update(response.num_bytes_downloaded)
                            async for chunk in response.aiter_bytes():
                                f.write(chunk)
                                self.transfer_speed.update(response.num_bytes_downloaded - work_order.progress.done)
                                work_order.progress.set_done(response.num_bytes_downloaded)
                    break
                except Exception as ex:
                    msg = ex.args[0] if len(ex.args) > 0 else format_exception(ex)
                    work_order.history.append(msg)
                    work_order.status_text = msg
                    work_order.progress.set_done(0)
                    await asyncio.sleep(DOWNLOAD_RETRY_INTERVAL)

            work_order.status = TRANSFER_STATUS_SUCCESS
            download.update()
        self.queue.notify_worker_end(self)
