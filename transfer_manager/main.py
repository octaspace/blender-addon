async def index(request):
    from sanic.response import text
    return text("transfer manager")


def main():
    import sanic
    import logging
    from sanic_ext import Extend
    from .middleware.user_data import user_data
    from .api.transfers import create_download, create_upload, get_all_transfers, get_transfer, delete_transfer, set_transfer_status

    logging.basicConfig(level=logging.INFO)

    app = sanic.Sanic('octa_transfer_manager')
    app.config.CORS_ORIGINS = "*"  # comma seperated list
    Extend(app)

    bp_api = sanic.Blueprint("api", "api")
    bp_api.middleware(user_data, 'request')

    bp_api.add_route(create_download, "/download", methods=('POST',))
    bp_api.add_route(create_upload, "/upload", methods=('POST',))
    bp_api.add_route(get_all_transfers, "/transfers", methods=('GET',))
    bp_api.add_route(get_transfer, "/transfers/<id:str>", methods=('GET',))
    bp_api.add_route(delete_transfer, "/transfers/<id:str>", methods=('DELETE',))
    bp_api.add_route(set_transfer_status, "/transfers/<id:str>/status", methods=('PUT',))

    app.blueprint(bp_api)

    app.add_route(index, '/', methods=('GET',))

    return app


if __name__ == '__main__':
    app = main()
    app.run(host='0.0.0.0', port=7780, single_process=True, access_log=True, debug=True)
else:
    main()
