async def index(request):
    from sanic.response import text

    return text("transfer manager")


def main():
    import os
    import tempfile
    import logging.handlers
    import sanic
    from sanic import response
    from sanic.response import empty
    from sanic.exceptions import SanicException

    logging.basicConfig(
        level=logging.INFO,
        handlers=[
            logging.handlers.RotatingFileHandler(
                os.path.join(tempfile.gettempdir(), "tm.log"),
                maxBytes=1024 * 1024 * 20,
                backupCount=2,
            )
        ],
    )

    from .middleware.user_data import user_data
    from .api.transfers import (
        create_download,
        create_upload,
        get_all_transfers,
        get_transfer,
        delete_transfer,
        set_transfer_status,
    )

    try:
        from os import system

        system("title Transfer Manager")
    except:
        pass

    app = sanic.Sanic("octa_transfer_manager")

    # Add the CORS middleware
    @app.middleware("response")
    async def add_cors_headers(request, response):
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Max-Age": "300",
        }
        response.headers.update(headers)
        if request.method == "OPTIONS":
            return empty(headers=headers)

    @app.exception(Exception)
    async def handle_exceptions(request, exception):
        if isinstance(exception, SanicException):
            status_code = exception.status_code
        else:
            status_code = 500
            print(exception)
        return response.json({"error": str(exception)}, status=status_code)

    bp_api = sanic.Blueprint("api", "api")
    bp_api.middleware(user_data, "request")

    bp_api.add_route(create_download, "/download", methods=("POST", "OPTIONS"))
    bp_api.add_route(create_upload, "/upload", methods=("POST", "OPTIONS"))
    bp_api.add_route(get_all_transfers, "/transfers", methods=("GET", "OPTIONS"))
    bp_api.add_route(get_transfer, "/transfers/<id:str>", methods=("GET",))
    bp_api.add_route(delete_transfer, "/transfers/<id:str>", methods=("DELETE",))
    bp_api.add_route(
        set_transfer_status, "/transfers/<id:str>/status", methods=("PUT",)
    )

    app.blueprint(bp_api)
    app.add_route(index, "/", methods=("GET",))
    return app


if __name__ == "__main__":
    app = main()
    app.run(host="0.0.0.0", port=7780, single_process=True, access_log=True, debug=True)
else:
    main()
