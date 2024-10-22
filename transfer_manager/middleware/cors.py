from sanic.response import empty


async def cors(request, response):
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Max-Age": "300",
    }
    response.headers.update(headers)
    if request.method == "OPTIONS":
        return empty(headers=headers)
