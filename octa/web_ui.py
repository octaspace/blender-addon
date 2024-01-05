from .web_api_base import WebApiBase
import json


class WebUi(WebApiBase):
    host: str = ''

    @classmethod
    def set_host(cls, host):
        cls.host = host

    @classmethod
    def get_version(cls):
        return 42  # TODO: to ensure we dont run an outdated plugin

    @classmethod
    def get_job_input_multipart_upload_info_full(cls, job_id, file_count: int) -> dict:
        url = f'{cls.host}/api/v1/get_job_input_multipart_upload_info_full/{job_id}/{file_count}'
        response = cls.request_with_retries('GET', url)
        text = response.data.decode()
        return json.loads(text)

    @classmethod
    def get_job_input_multipart_upload_info(cls, job_id) -> dict:
        url = f'{cls.host}/api/v1/get_job_input_multipart_upload_info/{job_id}'
        response = cls.request_with_retries('GET', url)
        text = response.data.decode()
        return json.loads(text)

    @classmethod
    def get_multipart_signed_url(cls, key: str, bucket: str, upload_id: str, part_number: int):
        response = cls.request_with_retries('POST', f'{cls.host}/api/v1/get_multipart_signed_url', body=json.dumps({
            'key': key,
            'bucket': bucket,
            'upload_id': upload_id,
            'part_number': part_number
        }).encode())
        return response.data.decode()

    @classmethod
    def complete_job_input_multipart_upload(cls, key: str, bucket: str, upload_id: str, etags: dict):
        response = cls.request_with_retries('POST', f'{cls.host}/api/v1/complete_job_input_multipart_upload', body=json.dumps({
            'key': key,
            'bucket': bucket,
            'upload_id': upload_id,
            'etags': etags
        }).encode())
        return response.data.decode()

    @classmethod
    def abort_job_input_multipart_upload(cls, key: str, bucket: str, upload_id: str):
        response = cls.request_with_retries('POST', f'{cls.host}/api/v1/abort_job_input_multipart_upload', body=json.dumps({
            'key': key,
            'bucket': bucket,
            'upload_id': upload_id
        }).encode())
        return response.data.decode()
