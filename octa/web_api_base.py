import asyncio
import random
from traceback import format_exc
import httpx


class WebApiBase:
    timeout = 3600

    @classmethod
    async def request_with_retries(cls, method: str, url: str, **kwargs):
        retries = 3
        tries = 0
        while tries < retries:
            try:
                async with httpx.AsyncClient(timeout=cls.timeout) as client:
                    response = await client.request(method, url, **kwargs)
                    if 200 <= response.status_code <= 299:
                        return response.json()
                    else:
                        error_info = f"Status: {response.status_code}, Content: {await response.text()}"
                        raise httpx.HTTPStatusError(message=error_info, request=response.request, response=response)
            except httpx.HTTPStatusError as e:
                print(f"HTTP Error on try {tries + 1} for {url}: {str(e)}")
            except Exception as e:
                print(f"General Error on try {tries + 1} for {url}: {format_exc()}")
            finally:
                tries += 1
                if tries < retries:
                    await asyncio.sleep(tries)

        raise Exception(f"Failed after {retries} attempts: {method} {url}")
