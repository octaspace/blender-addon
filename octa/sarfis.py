import random
import requests
import json
import time


class UberApi:
    session: requests.Session = None

    @classmethod
    def get_session(cls):
        if cls.session is None:
            cls.session = requests.Session()
        return cls.session

    @classmethod
    def request(cls, *args, **kwargs) -> requests.Response:
        session = cls.get_session()
        return session.request(*args, **kwargs)

    @classmethod
    def call(cls, host, auth_token, endpoints, retries=3):
        url = f'{host}/qm/uber_api'  # /qm/ is the subdir for the octa node

        tries = 0
        trying = True
        while trying:
            tries += 1
            try:
                response = cls.request('POST', url, json=endpoints, headers={'Auth-Token': auth_token})
                if 200 <= response.status_code <= 299:
                    return response.json()
                else:
                    if tries >= retries:
                        raise Exception(f'status code: {response.status_code}\n content: {response.content}')
                    time.sleep(tries + random.random())
            except:
                if tries >= retries:
                    raise
                time.sleep(tries + random.random())


class Sarfis:
    @classmethod
    def node_job(cls, host, auth_token, job):
        result = UberApi.call(host, auth_token, {'node_job': job})
        return result['node_job']

    @classmethod
    def get_job_details(cls, host, auth_token, job_id):
        result = UberApi.call(host, auth_token, {"job_details": {'job_id': job_id}})
        return result['job_details']
