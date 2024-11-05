import asyncio
import httpx
from typing import TYPE_CHECKING
from sanic.log import logger
from traceback import format_exception
from .transfer import TRANSFER_STATUS_PAUSED, TRANSFER_STATUS_SUCCESS
from .cancellation_token import CancellationToken
from .transfer_speed import TransferSpeed
from abc import ABC,abstractmethod

if TYPE_CHECKING:
    from .transfer_queue import TransferQueue

    DOWNLOAD_RETRY_INTERVAL = 5

class TransferQueueWorker:
    def __init__(self, queue: "TransferQueue"):
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

    @abstractmethod
    async def _run(self):
       pass