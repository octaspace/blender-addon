async def cors(request, response):
    response.headers["Access-Control-Allow-Origin"] = "*"
