import asyncio
import httpx
from sanic.log import logger
from traceback import format_exception
from ..transfer import TRANSFER_STATUS_SUCCESS, TRANSFER_STATUS_FAILURE
from .download_work_order import DownloadWorkOrder
from ..transfer_queue_worker import TransferQueueWorker

DOWNLOAD_RETRY_INTERVAL = 5


class DownloadQueueWorker(TransferQueueWorker):

    async def _run(self):
        logger.info("download worker starting")
        client = httpx.AsyncClient()
        while not self.ct.is_canceled():
            try:
                work_order: DownloadWorkOrder = await self.queue.get_next_work_order()
                if work_order is None:
                    await asyncio.sleep(1)
                    continue

                download = work_order.download
                transfer_name = f"file {work_order.number} of {len(download.work_orders)} of job {download.job_id}"

                await self._check_pause()

                while not self.ct.is_canceled():  # never give up downloading
                    try:
                        work_order.status_text = "Initiating Download"
                        logger.debug(f"start downloading {transfer_name}")
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
                        logger.debug(f"{transfer_name} downloaded successfully")
                        work_order.status = TRANSFER_STATUS_SUCCESS
                        break
                    except Exception as ex:
                        msg = '\n'.join(format_exception(ex))
                        logger.warning(f"download {transfer_name} had exception {msg}")
                        work_order.history.append(msg)
                        work_order.status_text = msg
                        work_order.progress.set_done(0)
                        await asyncio.sleep(DOWNLOAD_RETRY_INTERVAL)
                    finally:
                        if work_order.status != TRANSFER_STATUS_SUCCESS:
                            work_order.status = TRANSFER_STATUS_FAILURE

                download.update()
            except:
                logger.exception("exception from within download worker")
        logger.info("download worker exiting")
        self.queue.notify_worker_end(self)
