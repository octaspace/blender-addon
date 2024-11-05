from .transfer import TRANSFER_STATUS_RUNNING, TRANSFER_STATUS_PAUSED, TRANSFER_STATUS_CREATED
from .transfer_queue_worker import TransferQueueWorker
from typing import Optional, TypeVar, Generic, List

T_WorkOrder = TypeVar("T_WorkOrder")


class TransferQueue(Generic[T_WorkOrder]):
    def __init__(self, transfer_type: str, worker_class: type):
        self.transfer_type = transfer_type
        self.worker_class = worker_class

        self.status = TRANSFER_STATUS_RUNNING
        self.workers: List[TransferQueueWorker] = []

    def start(self):
        for _ in range(4):
            self._add_worker()

    def pause(self):
        self.status = TRANSFER_STATUS_PAUSED

    def resume(self):
        self.status = TRANSFER_STATUS_RUNNING

    def _add_worker(self):
        worker = self.worker_class(self)
        self.workers.append(worker)
        worker.start()

    async def get_next_work_order(self) -> Optional[T_WorkOrder]:
        if self.status == TRANSFER_STATUS_PAUSED:
            return None

        from .transfer_manager import get_transfer_manager

        for k, v in get_transfer_manager().transfers.items():
            if v.type == self.transfer_type:
                if v.status == TRANSFER_STATUS_RUNNING:
                    for wo in v.work_orders:
                        if wo.status == TRANSFER_STATUS_CREATED:
                            wo.status = TRANSFER_STATUS_RUNNING
                            return wo
        return None

    def notify_worker_end(self, worker: TransferQueueWorker):
        self.workers.remove(worker)
