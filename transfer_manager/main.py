def main():
    import sanic
    from sanic_ext import Extend
    from .middleware.ensure_user import ensure_user
    from .api.downloads import start_download, get_all_downloads, get_download, delete_download, set_download_status
    from .api.uploads import start_upload, get_all_uploads, get_upload, delete_upload, set_upload_status

    app = sanic.Sanic('octa_farm_manager')
    app.config.CORS_ORIGINS = "*"  # comma seperated list
    Extend(app)

    bp_api = sanic.Blueprint("api", "api/v1")
    bp_api.middleware(ensure_user, 'request')

    bp_api.add_route(start_download, "/downloads", methods=('POST',))
    bp_api.add_route(get_all_downloads, "/downloads", methods=('GET',))
    bp_api.add_route(get_download, "/downloads/<id:str>", methods=('GET',))
    bp_api.add_route(delete_download, "/downloads/<id:str>", methods=('DELETE',))
    bp_api.add_route(set_download_status, "/downloads/<id:str>/status", methods=('PUT',))

    bp_api.add_route(start_upload, "/uploads", methods=('POST',))
    bp_api.add_route(get_all_uploads, "/uploads", methods=('GET',))
    bp_api.add_route(get_upload, "/uploads/<id:str>", methods=('GET',))
    bp_api.add_route(delete_upload, "/uploads/<id:str>", methods=('DELETE',))
    bp_api.add_route(set_upload_status, "/uploads/<id:str>/status", methods=('PUT',))

    app.blueprint(bp_api)

    return app


if __name__ == '__main__':
    app = main()
    app.run(host='0.0.0.0', port=7780)
else:
    main()
