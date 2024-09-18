from typing import TypedDict

from httpx import Response

R2_WORKER_ENDPOINT = "https://r2-worker.artem-teslenko.workers.dev"


def sanitize_path(path: str):
    # make sure path begins with slash
    if not path.startswith('/'):
        return '/' + path
    return path


def get_url(path: str):
    return f"{R2_WORKER_ENDPOINT}{sanitize_path(path)}"


class R2UploadedPart(TypedDict):
    partNumber: int
    etag: str


class R2UploadParts(TypedDict):
    parts: list[R2UploadedPart]


class R2UploadInfo(TypedDict):
    uploadId: str


def ensure_ok(response: Response):
    if response.status_code < 200 or response.status_code > 299:
        raise Exception(f"response had non OK status code {response.status_code}: {response.content}")
    return response
