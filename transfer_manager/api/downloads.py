from sanic import Request
from sanic.response import json
from ..classes.download_manager import download_manager
from ..classes.download import Download, ITEM_STATUS_PAUSED, ITEM_STATUS_RUNNING, ITEM_STATUS_FAILURE
from ..util import get_next_id


async def start_download(request: Request):
    args = request.json
    download = Download(get_next_id(), args['host'], args['local_dir_path'], args['job_id'], args['download_threads'])
    download_manager.add(download)
    download.start()
    return json(download.id)


async def get_all_downloads(request: Request):
    response = []
    for _, item in download_manager.items.items():
        response.append(item.to_dict())
    return json(response)


async def get_download(request: Request, id: str):
    if id in download_manager.items:
        return json(download_manager.items[id].to_dict())
    return json(None, status=404)


async def delete_download(request: Request, id: str):
    if id in download_manager.items:
        download_manager.remove_by_id(id)
        return json(True)
    return json(False, status=404)


async def set_download_status(request: Request, id: str):
    args = request.json
    status = args['status']
    download = download_manager.get(id)
    if download is None:
        return json(False, status=404)
    if status == ITEM_STATUS_PAUSED:
        download.pause()
    elif status == ITEM_STATUS_RUNNING:
        download.start()
    elif status == ITEM_STATUS_FAILURE:
        download.stop()
    return json(True)
