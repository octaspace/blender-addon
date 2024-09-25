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
        self.progress = Progress()
        self.sub_progresses: List[Progress] = []
        self.status = TRANSFER_STATUS_CREATED
        self.status_text = ""
        self.type = transfer_type
        self.metadata = metadata
        self.created = time.time()

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
            "progress": self.progress.to_dict(),
            "sub_progresses": [i.to_dict() for i in self.sub_progresses],
            "status": self.status,
            "status_text": self.status_text,
            "metadata": self.metadata,
            "created": self.created,
        }
