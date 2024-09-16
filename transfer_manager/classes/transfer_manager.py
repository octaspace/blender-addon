from .transfer import Transfer
from typing import Dict


class TransferManager():
    def __init__(self):
        self.transfers: Dict[str, Transfer] = {}

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


transfer_manager = TransferManager()
