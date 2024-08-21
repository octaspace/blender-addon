from sanic import Request


async def start_download(request: Request):
    pass


async def get_all_downloads(request: Request):
    pass


async def get_download(request: Request, id: str):
    pass


async def delete_download(request: Request, id: str):
    pass


async def set_download_status(request: Request, id: str):
    pass
