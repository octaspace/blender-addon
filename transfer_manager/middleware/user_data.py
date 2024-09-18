from sanic import Request
from ..classes.user_data import UserData


async def user_data(request: Request):
    request.ctx.user_data = UserData(
        request.headers.get('farm_host'),
        request.headers.get('api_token'),
        request.headers.get('qm_auth_token')
    )
