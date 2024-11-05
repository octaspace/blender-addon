from .progress import Progress
from .transfer import TRANSFER_STATUS_CREATED
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from .download import Download


class DownloadWorkOrder:
    def __init__(self, number: int, url: str, local_path: str, rel_path: str, download: "Download"):
        self.number = number
        self.url = url
        self.local_path = local_path
        self.rel_path = rel_path
        self.download = download

        self.progress = Progress()
        self.status = TRANSFER_STATUS_CREATED
        self.status_text = ""
        self.history: List[str] = []

    def small_dict(self):
        return {
            "rel_path": self.rel_path,
            "done": self.progress.done,
            "total": self.progress.total,
            "status": self.status,
            "status_history": self.history,
        }
