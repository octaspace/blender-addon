from sanic import Request
from sanic.response import json
from ..lib.transfer_manager import get_transfer_manager
from ..lib.transfer import (
    TRANSFER_STATUS_PAUSED,
    TRANSFER_STATUS_FAILURE,
    TRANSFER_STATUS_RUNNING,
)
from ..lib.upload.upload import Upload
from ..lib.download.download import Download
from ..lib.json_dumps import json_dumps
from ..lib.version import version
from sanic.log import logger
import filedialpy
import os
import asyncio


async def create_upload(request: Request):
    args = request.json
    local_file_path = args["local_file_path"]
    if not os.path.exists(local_file_path):
        return json("file doesnt exist", status=400)
    upload = Upload(
        request.ctx.user_data,
        local_file_path,
        args["job_information"],
        args["metadata"],
    )
    await upload.initialize()
    get_transfer_manager().add(upload)
    upload.start()
    return json(upload.id)


async def create_download(request: Request):
    args = request.json
    local_dir_path = args.get('local_dir_path', None)
    if local_dir_path is None:
        def ask_for_dir():
            return filedialpy.openDir(title="Choose Download Directory")

        local_dir_path = await asyncio.to_thread(ask_for_dir)

    download = Download(request.ctx.user_data, local_dir_path, args["job_id"], args["metadata"])
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
