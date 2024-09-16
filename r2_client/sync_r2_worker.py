import httpx
from httpx._types import RequestContent

from .r2_worker_shared import R2UploadedPart, R2UploadInfo, get_url, ensure_ok


class SyncR2Worker:
    def __init__(self, api_key: str):
        self.api_key = api_key
        timeout = httpx.Timeout(10.0, read=60.0)
        self.client = httpx.Client(timeout=timeout)

    def request(self, method: str, url: str, **kwargs):
        response = self.client.request(method, url, headers={
            'Authentication': self.api_key
        }, **kwargs)
        ensure_ok(response)
        return response

    def create_multipart_upload(self, path: str) -> R2UploadInfo:
        url = get_url(path)
        response = self.request('POST', url, params={
            "action": "mpu-create"
        })
        return response.json()

    def complete_multipart_upload(self, path: str, upload_id: str, parts: list[R2UploadedPart]):
        url = get_url(path)
        self.request('POST', url, params={
            "action": "mpu-complete",
            "uploadId": upload_id,
        }, json={
            "parts": parts
        })

    def upload_multipart_part(self, path: str, upload_id: str, part_number_1_based: int, body: RequestContent) -> R2UploadedPart:
        url = get_url(path)
        response = self.request('PUT', url, params={
            "action": "mpu-uploadpart",
            "uploadId": upload_id,
            "partNumber": str(part_number_1_based)
        }, content=body)
        return response.json()

    def upload_single_part(self, path: str, body: RequestContent):
        url = get_url(path)
        self.request('PUT', url, params={
            "action": "single-upload"
        }, content=body)

    def abort_multipart_upload(self, path: str, upload_id: str):
        url = get_url(path)
        self.request('DELETE', url, params={
            "action": "mpu-abort",
            "uploadId": upload_id
        })

    def delete_object(self, path: str):
        url = get_url(path)
        self.request('DELETE', url, params={
            "action": "delete"
        })

    def get_object(self, path: str) -> bytes:
        url = get_url(path)
        response = self.request('GET', url, params={
            "action": "get"
        })
        return response.content
