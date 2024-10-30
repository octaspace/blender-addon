from sanic import Request
from sanic.response import json, empty
from ..classes.transfer_manager import transfer_manager
from ..classes.transfer import (
    TRANSFER_STATUS_PAUSED,
    TRANSFER_STATUS_CREATED,
    TRANSFER_STATUS_FAILURE,
    TRANSFER_STATUS_RUNNING,
    TRANSFER_STATUS_SUCCESS,
)
from ..classes.upload import Upload
from ..classes.download import Download
from ..json_dumps import json_dumps
from ..version import version
import logging
import filedialpy
import os

logger = logging.getLogger(__name__)


async def create_upload(request: Request):
    args = request.json
    upload = Upload(
        request.ctx.user_data,
        args["local_file_path"],
        args["job_information"],
        args["metadata"],
    )
    transfer_manager.add(upload)
    upload.start()
    return json(upload.id)


async def create_download(request: Request):
    args = request.json
    f = args.get('local_dir_path', None)
    if f is None:
        f = filedialpy.openDir()
    logger.info("Download Path: ", f)

    download = Download(request.ctx.user_data, f, args["job_id"], args["metadata"])
    transfer_manager.add(download)
    download.start()
    logger.info("DOWNLOAD STARTED")
    return json(download.id)


async def get_all_transfers(request: Request):
    response = []
    for _, transfer in transfer_manager.transfers.items():
        response.append(transfer.to_dict())
    return json(response, dumps=json_dumps)


async def get_transfer(request: Request, id: str):
    if id in transfer_manager.transfers:
        return json(transfer_manager.transfers[id], dumps=json_dumps)
    return json(None, status=404)


async def delete_transfer(request: Request, id: str):
    if id in transfer_manager.transfers:
        transfer_manager.remove_by_id(id)
        return json(True)
    return json(False, status=404)


async def set_transfer_status(request: Request, id: str):
    args = request.json
    status = args["status"]
    transfer = transfer_manager.get(id)
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
