from .transfer import Transfer
from .transfer_queue import TransferQueue
from .download.download_queue_worker import DownloadQueueWorker
from .download.download_work_order import DownloadWorkOrder

from typing import Dict


class TransferManager:
    def __init__(self):
        self.transfers: Dict[str, Transfer] = {}
        self.download_queue = TransferQueue[DownloadWorkOrder]("download", DownloadQueueWorker)
        self.download_queue.start()

    def add(self, transfer: Transfer):
        self.transfers[transfer.id] = transfer

    def get(self, id: str):
        return self.transfers.get(id)

    def remove(self, transfer: Transfer):
        if transfer.id in self.transfers:
            transfer.stop()
            self.transfers.pop(transfer.id)

    def remove_by_id(self, id: str):
        if id in self.transfers:
            self.remove(self.transfers[id])


_transfer_manager: TransferManager = None


def get_transfer_manager() -> TransferManager:
    global _transfer_manager
    if _transfer_manager is None:
        _transfer_manager = TransferManager()
    return _transfer_manager
