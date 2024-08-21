from abc import ABC, abstractmethod

ITEM_STATUS_CREATED = 'created'
ITEM_STATUS_RUNNING = 'running'
ITEM_STATUS_PAUSED = 'paused'
ITEM_STATUS_SUCCESS = 'success'
ITEM_STATUS_FAILURE = 'failure'


class Item(ABC):
    def __init__(self, id):
        self.id = id
        self.progress: float = 0
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
