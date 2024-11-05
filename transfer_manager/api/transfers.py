from sanic import Request
from sanic.response import json
from ..lib.transfer_manager import get_transfer_manager
from ..lib.transfer import (
    TRANSFER_STATUS_PAUSED,
    TRANSFER_STATUS_FAILURE,
    TRANSFER_STATUS_RUNNING,
)
from ..lib.upload import Upload
from ..lib.download import Download
from ..lib.json_dumps import json_dumps
from ..lib.version import version
from sanic.log import logger
import filedialpy
import os


async def create_upload(request: Request):
    args = request.json
    upload = Upload(
        request.ctx.user_data,
        args["local_file_path"],
        args["job_information"],
        args["metadata"],
    )
    get_transfer_manager().add(upload)
    upload.start()
    return json(upload.id)


async def create_download(request: Request):
    args = request.json
    f = args.get('local_dir_path', None)
    if f is None:
        f = filedialpy.openDir()

    download = Download(request.ctx.user_data, f, args["job_id"], args["metadata"])
    await download.initialize()
    get_transfer_manager().add(download)
    download.start()
    return json(download.id)


async def get_all_transfers(request: Request):
    response = []
    for _, transfer in get_transfer_manager().transfers.items():
        response.append(transfer.to_dict())
    return json(response, dumps=json_dumps)


async def get_transfer(request: Request, id: str):
    transfers = get_transfer_manager().transfers
    if id in transfers:
        return json(transfers[id], dumps=json_dumps)
    return json(None, status=404)


async def delete_transfer(request: Request, id: str):
    if id in get_transfer_manager().transfers:
        get_transfer_manager().remove_by_id(id)
        return json(True)
    return json(False, status=404)


async def set_transfer_status(request: Request, id: str):
    args = request.json
    status = args["status"]
    transfer = get_transfer_manager().get(id)
    if transfer is None:
        return json(False, status=404)
    if status == TRANSFER_STATUS_PAUSED:
        transfer.pause()
    elif status == TRANSFER_STATUS_RUNNING:
        transfer.start()
    elif status == TRANSFER_STATUS_FAILURE:
        transfer.stop()
    else:
        return json(f"unsupported status {status}", status=400)
    return json(True)


async def transfer_manager_info(request):
    return json({
        "service": "transfer_manager",
        "version": version,
        "process_id": os.getpid()
    })
