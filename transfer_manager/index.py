from sanic.response import text


async def index(request):
    # TODO: could add a script to redirect to private farm or so
    return text("transfer manager")
