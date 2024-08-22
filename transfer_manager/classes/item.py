from abc import ABC, abstractmethod
from .progress import Progress

ITEM_STATUS_CREATED = 'created'
ITEM_STATUS_RUNNING = 'running'
ITEM_STATUS_PAUSED = 'paused'
ITEM_STATUS_SUCCESS = 'success'
ITEM_STATUS_FAILURE = 'failure'


class ItemException(Exception):
    pass


class Item(ABC):
    def __init__(self, id):
        self.id = id
        self.progress = Progress()
        self.sub_progress = Progress()
        self.status = ITEM_STATUS_CREATED
        self.status_text = ""

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
            "progress": self.progress.to_dict(),
            "sub_progress": self.sub_progress.to_dict(),
            "status": self.status,
            "status_text": self.status_text
        }
