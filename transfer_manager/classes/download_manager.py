from .item_manager import ItemManager
from .upload import Upload


class DownloadManager(ItemManager[Upload]):
    def __init__(self):
        super().__init__()


download_manager = DownloadManager()
