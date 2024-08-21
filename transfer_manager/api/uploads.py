from sanic import Request
from sanic.response import json
from ..classes.upload_manager import upload_manager
from ..classes.upload import Upload
from ..util import get_next_id


async def start_upload(request: Request):
    args = request.json
    upload = Upload(get_next_id(), args['local_file_path'])
    upload_manager.add(upload)
    upload.start()
    return json(upload.id)


async def get_all_uploads(request: Request):
    pass


async def get_upload(request: Request, id: str):
    pass


async def delete_upload(request: Request, id: str):
    pass


async def set_upload_status(request: Request, id: str):
    pass
