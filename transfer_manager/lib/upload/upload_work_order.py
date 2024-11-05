from ..progress import Progress
from ..transfer import TRANSFER_STATUS_CREATED
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from .upload import Upload


class UploadWorkOrder:
    def __init__(self, offset: int, size: int, part_number: int, upload: "Upload", is_single_upload: bool):
        self.offset = offset
        self.size = size
        self.part_number = part_number
        self.upload = upload
        self.is_single_upload = is_single_upload

        self.progress = Progress()
        self.status = TRANSFER_STATUS_CREATED
        self.status_text = ""
        self.history: List[str] = []

    def small_dict(self):
        return {
            "offset": self.offset,
            "size": self.size,
            "part_number": self.part_number,
            "done": self.progress.done,
            "total": self.progress.total,
            "status": self.status,
            "status_history": self.history,
        }
