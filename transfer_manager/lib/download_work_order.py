from dataclasses import dataclass
from .progress import Progress
from .transfer import TRANSFER_STATUS_CREATED
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .download import Download


@dataclass
class DownloadWorkOrder:
    number: int
    url: str
    local_path: str
    rel_path: str
    progress: Progress
    download: Download
    status: str = TRANSFER_STATUS_CREATED
    status_text: str = ""

    def small_dict(self):
        return {
            "rel_path": self.rel_path,
            "done": self.progress.done,
            "total": self.progress.total,
        }
