from .web_api_base import WebApiBase
import json


class WebUi(WebApiBase):
    host: str = ''
    cookie: str = ''

    @classmethod
    def set_config(cls, host, cookie):
        cls.host = host
        cls.cookie = cookie

    @classmethod
    def get_version(cls):
        # TODO: to ensure we dont run an outdated plugin
        url = f'{cls.host}/api/v1/blender_plugin_version'
        response = cls.request_with_retries('GET', url)
        return int(response.text)

    @classmethod
    def get_job_input_multipart_upload_info_full(cls, job_id, file_count: int) -> dict:
        url = f'{cls.host}/api/v1/get_job_input_multipart_upload_info_full/{job_id}/{file_count}'
        response = cls.request_with_retries('GET', url)
        return response.json()

    @classmethod
    def get_multipart_signed_url(cls, key: str, bucket: str, upload_id: str, part_number: int):
        response = cls.request_with_retries('POST', f'{cls.host}/api/v1/get_multipart_signed_url', json={
            'key': key,
            'bucket': bucket,
            'upload_id': upload_id,
            'part_number': part_number
        })
        return response.text

    @classmethod
    def complete_job_input_multipart_upload(cls, key: str, bucket: str, upload_id: str, etags: dict):
        response = cls.request_with_retries('POST', f'{cls.host}/api/v1/complete_job_input_multipart_upload', json={
            'key': key,
            'bucket': bucket,
            'upload_id': upload_id,
            'etags': etags
        })
        return response.text

    @classmethod
    def abort_job_input_multipart_upload(cls, key: str, bucket: str, upload_id: str):
        response = cls.request_with_retries('POST', f'{cls.host}/api/v1/abort_job_input_multipart_upload', json={
            'key': key,
            'bucket': bucket,
            'upload_id': upload_id
        })
        return response.text
