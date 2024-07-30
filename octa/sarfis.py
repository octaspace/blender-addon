import random
import urllib3
import json
import time


class UberApi:
    _urllib_pool: urllib3.PoolManager = None

    @classmethod
    def get_pool_manager(cls):
        if cls._urllib_pool is None:
            cls._urllib_pool = urllib3.PoolManager()
        return cls._urllib_pool

    @classmethod
    def request(cls, *args, **kwargs) -> urllib3.HTTPResponse:
        pool = cls.get_pool_manager()
        return pool.request(*args, **kwargs)

    @classmethod
    def call(cls, host, endpoints, retries=3):
        url = f'{host}/qm/uber_api'  # /qm/ is the subdir for the octa node

        tries = 0
        trying = True
        while trying:
            tries += 1
            try:
                response = cls.request('POST', url, body=json.dumps(endpoints), headers={"Content-Type": "application/json"})
                if 200 <= response.status <= 299:
                    return json.loads(response.data)
                else:
                    if tries >= retries:
                        raise Exception(f'status code: {response.status}\n content: {response.data}')
                    time.sleep(tries + random.random())
            except:
                if tries >= retries:
                    raise
                time.sleep(tries + random.random())


class Sarfis:
    @classmethod
    def node_job(cls, host, job):
        result = UberApi.call(host, {'node_job': job})
        return result['node_job']
