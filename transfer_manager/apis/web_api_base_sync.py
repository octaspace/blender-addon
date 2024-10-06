import urllib3
import time
import random


class WebApiBaseSync:
    _urllib_pool: urllib3.PoolManager = None

    @classmethod
    def get_pool_manager(cls):
        if cls._urllib_pool is None:
            timeout = urllib3.util.Timeout(connect=15, read=15)
            cls._urllib_pool = urllib3.PoolManager(num_pools=32, timeout=timeout)
        return cls._urllib_pool

    @classmethod
    def request_with_retries(cls, method, url, fields=None, headers=None, retries=3, **kwargs) -> urllib3.HTTPResponse:
        pool = cls.get_pool_manager()
        tries = 0
        while True:
            tries += 1
            try:
                if 'body' in kwargs:
                    if hasattr(kwargs['body'], 'seek'):
                        kwargs['body'].seek(0)
                response = pool.request(method, url, fields, headers, **kwargs)
                if 200 <= response.status <= 299:
                    return response
                elif 400 <= response.status <= 499:
                    # no retries on err 4xx
                    tries = 100000
                    err = f"{method} to {url} failed with status {response.status}, content: {response.data[:1000]}"
                    print(err)
                    raise Exception(err)
                else:
                    err = f"{method} to {url} failed with status {response.status}, content: {response.data[:1000]}"
                    print(err)
                    if tries >= retries:
                        raise Exception(err)
                    time.sleep(tries + random.random())
            except:
                if tries >= retries:
                    raise
                time.sleep(tries + random.random())
