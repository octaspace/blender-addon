from .download import Download
from .download_work_order import DownloadWorkOrder
from .download_queue_worker import DownloadQueueWorker
from .transfer import TRANSFER_STATUS_RUNNING, TRANSFER_STATUS_PAUSED, TRANSFER_STATUS_CREATED, TRANSFER_STATUS_SUCCESS
from typing import Optional


class DownloadQueue:
    def __init__(self):
        self.status = TRANSFER_STATUS_RUNNING

        self.workers = []

    def start(self):
        for _ in range(4):
            self._add_worker()

    def pause(self):
        self.status = TRANSFER_STATUS_PAUSED

    def resume(self):
        self.status = TRANSFER_STATUS_RUNNING

    def _add_worker(self):
        worker = DownloadQueueWorker(self)
        self.workers.append(worker)
        worker.start()

    async def get_next_work_order(self) -> Optional[DownloadWorkOrder]:
        from .transfer_manager import transfer_manager

        for k, v in transfer_manager.transfers.items():
            if v.type == "download":
                d: Download = v
                if d.status in [TRANSFER_STATUS_RUNNING, TRANSFER_STATUS_CREATED]:
                    for f in d.files:
                        if f.status == TRANSFER_STATUS_CREATED:
                            f.status = TRANSFER_STATUS_RUNNING
                            return f
        return None
