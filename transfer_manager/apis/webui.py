import json
import aiohttp
import asyncio
import random
from traceback import print_exc


class WebUi():
    host: str = ''
    session = None
    version = "20240820"

    @classmethod
    async def set_host(cls, host):
        remote_version = await cls.get_version(host=host)
        if remote_version != cls.version:
            raise Exception(f"remote version {remote_version} does not match transfer manager version {cls.version}")
        cls.host = host

    @classmethod
    def get_session(cls) -> aiohttp.ClientSession:
        if cls.session is None:
            timeout = aiohttp.ClientTimeout(total=3)
            cls.session = aiohttp.ClientSession(timeout=timeout)
        return cls.session

    @classmethod
    async def request_with_retries(cls, method: str, url: str, **kwargs):
        session = cls.get_session()
        tries = 0
        while True:
            error_info = ''
            try:
                async with session.request(method, url, **kwargs) as response:
                    if 200 <= response.status <= 299:
                        return await response.json()
                    else:
                        error_info = f"status: {response.status}, {response.content}"
            except:
                error_info = print_exc()
            finally:
                tries += 1
                if tries >= 3:
                    raise Exception(f'{method} {url}: too many tries\n{error_info}')
                await asyncio.sleep(tries + random.random())

    @classmethod
    async def get_version(cls, host=None) -> str:
        return await cls.request_with_retries('GET', f'{host or cls.host}/api/v1/transfer_manager_version')

    @classmethod
    async def get_job_input_multipart_upload_info_full(cls, job_id, file_count: int) -> dict:
        url = f'{cls.host}/api/v1/get_job_input_multipart_upload_info_full/{job_id}/{file_count}'
        return await cls.request_with_retries('GET', url)

    @classmethod
    async def complete_job_input_multipart_upload(cls, key: str, bucket: str, upload_id: str, etags: dict):
        url = f'{cls.host}/api/v1/complete_job_input_multipart_upload'
        return await cls.request_with_retries('POST', url, json={
            'key': key,
            'bucket': bucket,
            'upload_id': upload_id,
            'etags': etags
        })

    @classmethod
    async def abort_job_input_multipart_upload(cls, key: str, bucket: str, upload_id: str):
        url = f'{cls.host}/api/v1/abort_job_input_multipart_upload'
        return await cls.request_with_retries('POST', url, json={
            'key': key,
            'bucket': bucket,
            'upload_id': upload_id
        })
