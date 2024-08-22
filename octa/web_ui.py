from .web_api_base import WebApiBase


class WebUi(WebApiBase):
    host: str = ""
    version = "20240820"

    @classmethod
    async def initialize(cls, host):
        remote_version = await cls.get_version(host=host)
        if remote_version != cls.version:
            raise Exception(f"remote version {remote_version} does not match transfer manager version {cls.version}")
        cls.host = host

    @classmethod
    async def get_version(cls, host=None) -> str:
        response = await cls.request_with_retries("GET", f"{host or cls.host}/api/v1/transfer_manager_version")
        return response

    @classmethod
    async def get_job_input_multipart_upload_info_full(cls, job_id, file_count: int) -> dict:
        url = f"{cls.host}/api/v1/get_job_input_multipart_upload_info_full/{job_id}/{file_count}"
        response = await cls.request_with_retries("GET", url)
        return response

    @classmethod
    async def complete_job_input_multipart_upload(cls, key: str, bucket: str, upload_id: str, etags: dict):
        url = f"{cls.host}/api/v1/complete_job_input_multipart_upload"
        response = await cls.request_with_retries("POST", url, json={"key": key, "bucket": bucket, "upload_id": upload_id, "etags": etags})
        return response

    @classmethod
    async def abort_job_input_multipart_upload(cls, key: str, bucket: str, upload_id: str):
        url = f"{cls.host}/api/v1/abort_job_input_multipart_upload"
        response = await cls.request_with_retries("POST", url, json={"key": key, "bucket": bucket, "upload_id": upload_id})
        return response
