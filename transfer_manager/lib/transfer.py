from typing import List
from abc import ABC, abstractmethod
from .progress import Progress
import time

TRANSFER_STATUS_CREATED = 'created'
TRANSFER_STATUS_RUNNING = 'running'
TRANSFER_STATUS_PAUSED = 'paused'
TRANSFER_STATUS_SUCCESS = 'success'
TRANSFER_STATUS_FAILURE = 'failure'


class TransferException(Exception):
    pass


class Transfer(ABC):
    def __init__(self, transfer_id: str, transfer_type: str, metadata: dict):
        self.id = transfer_id
        self.type = transfer_type
        self.metadata = metadata

        self.progress = Progress()
        self.status = TRANSFER_STATUS_CREATED
        self.status_text = ""
        self.created = time.time()
        self.finished_at = 0
        self.work_orders = []

    @abstractmethod
    def start(self):
        pass

    @abstractmethod
    def stop(self):
        pass

    @abstractmethod
    def pause(self):
        pass

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.type,
            "progress": self.progress,
            "status": self.status,
            "status_text": self.status_text,
            "created": self.created,
            "age": time.time() - self.created,
            "finished_at": self.finished_at,
            "metadata": self.metadata,
        }
