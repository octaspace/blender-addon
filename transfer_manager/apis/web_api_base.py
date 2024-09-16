import httpx
import asyncio
import random
from traceback import print_exc


class WebApiBase:
    client = None

    @classmethod
    def get_client(cls) -> httpx.AsyncClient:
        if cls.client is None:
            cls.client = httpx.Client(timeout=5)
        return cls.client

    @classmethod
    async def request_with_retries(cls, method: str, url: str, **kwargs):
        client = cls.get_client()
        retries = 3
        tries = 0
        while True:
            error_info = ''
            try:
                response = await client.request(method, url, **kwargs)
                if 200 <= response.status_code <= 299:
                    return response.json()
                else:
                    error_info = f"status: {response.status_code}\n{response.content}"
            except:
                error_info = print_exc()
            finally:
                tries += 1
                if tries >= retries:
                    raise Exception(f'{method} {url}: too many tries\n{error_info}')
                await asyncio.sleep(tries + random.random())
