from .item_manager import ItemManager
from .upload import Upload


class UploadManager(ItemManager[Upload]):
    def __init__(self):
        super().__init__()


upload_manager = UploadManager()
