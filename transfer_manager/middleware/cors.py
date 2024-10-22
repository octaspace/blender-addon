from sanic.response import empty

headers = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Max-Age": "300",
}


async def cors_before(request):
    if request.method == "OPTIONS":
        return empty(headers=headers)


async def cors(request, response):
    response.headers.update(headers)
