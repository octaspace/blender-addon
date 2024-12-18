from sanic import Request
from ..lib.user_data import UserData
from sanic.log import logger


async def user_data(request: Request):
    farm_host = request.headers.get('farm_host')
    if farm_host is not None:
        farm_host = farm_host.rstrip('/')
    request.ctx.user_data = UserData(
        farm_host,
        request.headers.get('api_token'),
        request.headers.get('qm_auth_token')
    )
