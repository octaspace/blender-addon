from .item import Item
from typing import Dict, TypeVar, Generic
from abc import ABC, abstractmethod

T = TypeVar('T', bound=Item)


class ItemManager(ABC, Generic[T]):
    def __init__(self):
        self.items: Dict[str, T] = {}

    def add(self, item: T):
        self.items[item.id] = item

    def get(self, id: str):
        return self.items.get(id)

    def remove(self, item: T):
        if item.id in self.items:
            item.stop()
            self.items.pop(item.id)

    def remove_by_id(self, id: str):
        if id in self.items:
            self.remove(self.items[id])
