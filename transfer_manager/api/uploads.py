from sanic import Request
from sanic.response import json
from ..classes.upload_manager import upload_manager
from ..classes.upload import Upload, ITEM_STATUS_PAUSED, ITEM_STATUS_RUNNING, ITEM_STATUS_FAILURE
from ..util import get_next_id


async def start_upload(request: Request):
    args = request.json
    upload = Upload(get_next_id(), args['host'], args['local_file_path'])
    upload_manager.add(upload)
    upload.start()
    return json(upload.id)


async def get_all_uploads(request: Request):
    response = []
    for _, item in upload_manager.items.items():
        response.append(item.to_dict())
    return json(response)


async def get_upload(request: Request, id: str):
    if id in upload_manager.items:
        return json(upload_manager.items[id].to_dict())
    return json(None, status=404)


async def delete_upload(request: Request, id: str):
    if id in upload_manager.items:
        upload_manager.remove_by_id(id)
        return json(True)
    return json(False, status=404)


async def set_upload_status(request: Request, id: str):
    args = request.json
    status = args['status']
    upload = upload_manager.get(id)
    if upload is None:
        return json(False, status=404)
    if status == ITEM_STATUS_PAUSED:
        upload.pause()
    elif status == ITEM_STATUS_RUNNING:
        upload.start()
    elif status == ITEM_STATUS_FAILURE:
        upload.stop()
    return json(True)
