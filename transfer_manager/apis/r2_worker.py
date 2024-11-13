import httpx
from httpx._types import RequestContent
from ..lib.user_data import UserData
from .r2_worker_shared import R2UploadedPart, R2UploadInfo, get_url, ensure_ok
from sanic.log import logger


class AsyncR2Worker:
    client = None

    @classmethod
    def get_client(cls) -> httpx.AsyncClient:
        if cls.client is None:
            cls.client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=60.0))
        return cls.client

    @classmethod
    async def request(cls, user_data: UserData, method: str, url: str, **kwargs):
        # TODO: retries here would break progress update
        client = cls.get_client()
        headers = {'authentication': user_data.api_token}
        # logger.debug(f"r2 request to {method} {url} with headers {headers} and kwargs {kwargs}")
        response = await client.request(method, url, headers=headers, **kwargs)
        return ensure_ok(response)

    @classmethod
    async def create_multipart_upload(cls, user_data: UserData, path: str) -> R2UploadInfo:
        url = get_url(path)
        response = await cls.request(user_data, 'POST', url, params={
            "action": "mpu-create"
        })
        return response.json()

    @classmethod
    async def complete_multipart_upload(cls, user_data: UserData, path: str, upload_id: str, parts: list[R2UploadedPart]):
        parts.sort(key=lambda x: x['partNumber'])
        url = get_url(path)
        await cls.request(user_data, 'POST', url, params={
            "action": "mpu-complete",
            "uploadId": upload_id,
        }, json={
            "parts": parts
        })

    @classmethod
    async def upload_multipart_part(cls, user_data: UserData, path: str, upload_id: str, part_number: int, body: RequestContent) -> R2UploadedPart:
        url = get_url(path)
        response = await cls.request(user_data, 'PUT', url, params={
            "action": "mpu-uploadpart",
            "uploadId": upload_id,
            "partNumber": str(part_number)
        }, content=body)
        return response.json()

    @classmethod
    async def upload_single_part(cls, user_data: UserData, path: str, body: RequestContent):
        url = get_url(path)
        await cls.request(user_data, 'PUT', url, params={
            "action": "single-upload"
        }, content=body)

    @classmethod
    async def abort_multipart_upload(cls, user_data: UserData, path: str, upload_id: str):
        url = get_url(path)
        await cls.request(user_data, 'DELETE', url, params={
            "action": "mpu-abort",
            "uploadId": upload_id
        })

    @classmethod
    async def delete_object(cls, user_data: UserData, path: str):
        url = get_url(path)
        await cls.request(user_data, 'DELETE', url, params={
            "action": "delete"
        })

    @classmethod
    async def get_object(cls, user_data: UserData, path: str) -> bytes:
        url = get_url(path)
        response = await cls.request(user_data, 'GET', url, params={
            "action": "get"
        })
        return response.content
