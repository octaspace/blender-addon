from sanic.response import empty


async def options(request, path):
    return empty()
