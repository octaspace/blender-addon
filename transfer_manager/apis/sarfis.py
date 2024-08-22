import random
import urllib3
import json
import time
import aiohttp
import asyncio
from traceback import print_exc
from .web_api_base import WebApiBase


class UberApi(WebApiBase):
    host: str = ''

    @classmethod
    async def set_host(cls, host):
        # TODO: version check not possible with sarfis yet
        cls.host = host

    @classmethod
    async def call(cls, host, endpoints):
        url = f'{host}/qm/uber_api'  # /qm/ is the subdir for the octa node

        return await cls.request_with_retries('POST', url, json=endpoints)


class Sarfis:
    @classmethod
    async def node_job(cls, host, job):
        result = await UberApi.call(host, {'node_job': job})
        return result['node_job']

    @classmethod
    async def get_job_details(cls, host, job_id):
        result = await UberApi.call(host, {'job_details': {"job_id": job_id}})
        return result['job_details']
