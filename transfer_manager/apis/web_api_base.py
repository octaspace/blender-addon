import aiohttp
import asyncio
import random
from traceback import print_exc


class WebApiBase:
    session = None

    @classmethod
    def get_session(cls) -> aiohttp.ClientSession:
        if cls.session is None:
            timeout = aiohttp.ClientTimeout(total=3)
            cls.session = aiohttp.ClientSession(timeout=timeout)
        return cls.session

    @classmethod
    async def request_with_retries(cls, method: str, url: str, **kwargs):
        session = cls.get_session()
        retries = 3
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
                if tries >= retries:
                    raise Exception(f'{method} {url}: too many tries\n{error_info}')
                await asyncio.sleep(tries + random.random())
