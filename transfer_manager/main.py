def main():
    import sanic

    from .middleware.user_data import user_data
    from .middleware.cors import cors, cors_before
    from .middleware.ensure_version import ensure_version
    from .lib.exception import handle_exceptions
    from .lib.index import index
    from .api.transfers import (
        create_download,
        create_upload,
        get_all_transfers,
        get_transfer,
        delete_transfer,
        set_transfer_status,
    )
    from .api.other import logs, transfer_manager_info
    from .api.queues import queues

    try:
        # change title of console window in windows
        from os import system

        system("title Transfer Manager")
    except:
        pass

    app = sanic.Sanic("octa_transfer_manager")
    app.middleware(cors, "response")
    app.middleware(cors_before, "request")
    app.middleware(ensure_version, "request")
    app.error_handler.add(Exception, handle_exceptions)

    bp_api = sanic.Blueprint("api", "api")
    bp_api.middleware(user_data, "request")

    bp_api.add_route(create_download, "/download", methods=("POST", "OPTIONS"))
    bp_api.add_route(create_upload, "/upload", methods=("POST", "OPTIONS"))
    bp_api.add_route(get_all_transfers, "/transfers", methods=("GET", "OPTIONS"))
    bp_api.add_route(get_transfer, "/transfers/<id:str>", methods=("GET",))
    bp_api.add_route(delete_transfer, "/transfers/<id:str>", methods=("DELETE",))
    bp_api.add_route(set_transfer_status, "/transfers/<id:str>/status", methods=("PUT",))
    bp_api.add_route(transfer_manager_info, "/transfer_manager_info", methods=("GET",))
    bp_api.add_route(logs, "/logs", methods=("GET",))
    bp_api.add_route(queues, "/queues", methods=("GET",))

    app.blueprint(bp_api)
    app.add_route(index, "/", methods=("GET",))
    return app


if __name__ == "__main__":
    app = main()
    debug = True  # TODO: get from config somewhere
    app.run(host="127.0.0.1", port=7780, single_process=True, access_log=False, debug=debug)
else:
    main()
