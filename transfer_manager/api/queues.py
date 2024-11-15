from ..lib.transfer_manager import get_transfer_manager
from sanic.response import json


async def queues(request):
    tm = get_transfer_manager()

    download_workers = []
    for w in tm.download_queue.workers:
        download_workers.append(w.transfer_speed.value)
    upload_workers = []
    for w in tm.upload_queue.workers:
        upload_workers.append(w.transfer_speed.value)

    data = {
        "download": download_workers,
        "upload": upload_workers,
    }

    return json(data)
