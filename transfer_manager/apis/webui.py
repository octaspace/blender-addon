from .web_api_base import WebApiBase


class WebUi(WebApiBase):
    host: str = ''
    version = "20240820"

    async def initialize(self, host):
        remote_version = await self.get_version(host=host)
        if remote_version != self.version:
            raise Exception(f"remote version {remote_version} does not match transfer manager version {self.version}")
        self.host = host

    async def get_version(self, host=None) -> str:
        return await self.request_with_retries('GET', f'{host or self.host}/api/v1/transfer_manager_version')

    async def get_job_input_multipart_upload_info_full(self, job_id, file_count: int) -> dict:
        url = f'{self.host}/api/v1/get_job_input_multipart_upload_info_full/{job_id}/{file_count}'
        return await self.request_with_retries('GET', url)

    async def complete_job_input_multipart_upload(self, key: str, bucket: str, upload_id: str, etags: dict):
        url = f'{self.host}/api/v1/complete_job_input_multipart_upload'
        return await self.request_with_retries('POST', url, json={
            'key': key,
            'bucket': bucket,
            'upload_id': upload_id,
            'etags': etags
        })

    async def abort_job_input_multipart_upload(self, key: str, bucket: str, upload_id: str):
        url = f'{self.host}/api/v1/abort_job_input_multipart_upload'
        return await self.request_with_retries('POST', url, json={
            'key': key,
            'bucket': bucket,
            'upload_id': upload_id
        })
