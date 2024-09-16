from .web_api_base import WebApiBase
from ..classes.user_data import UserData
from ..version import version


class WebUiException(Exception):
    pass


class WebUi(WebApiBase):
    @classmethod
    async def web_ui_request(cls, user_data: UserData, method, sub_url, **kwargs):
        cookies = {
            "octa_farm_session": user_data.web_ui_cookie
        }
        url = f"{user_data.farm_host}{sub_url}"
        return await WebApiBase.request_with_retries(method, url, cookies=cookies, **kwargs)

    @classmethod
    async def ensure_correct_version(cls, user_data: UserData):
        remote_version = await cls.get_version(user_data)
        if remote_version != version:
            raise Exception(f"remote version {remote_version} does not match transfer manager version {version}")

    @classmethod
    async def get_version(cls, user_data: UserData) -> str:
        return await cls.web_ui_request(user_data, 'GET', '/api/v1/transfer_manager_version')

    @classmethod
    async def get_job_input_multipart_upload_info_full(cls, user_data: UserData, job_id, file_count: int) -> dict:
        url = f'/api/v1/get_job_input_multipart_upload_info_full/{job_id}/{file_count}'
        return await cls.web_ui_request(user_data, 'GET', url)

    @classmethod
    async def complete_job_input_multipart_upload(cls, user_data: UserData, key: str, bucket: str, upload_id: str, etags: dict):
        url = '/api/v1/complete_job_input_multipart_upload'
        return await cls.web_ui_request(user_data, 'POST', url, json={
            'key': key,
            'bucket': bucket,
            'upload_id': upload_id,
            'etags': etags
        })

    @classmethod
    async def abort_job_input_multipart_upload(cls, user_data: UserData, key: str, bucket: str, upload_id: str):
        url = f'/api/v1/abort_job_input_multipart_upload'
        return await cls.web_ui_request(user_data, 'POST', url, json={
            'key': key,
            'bucket': bucket,
            'upload_id': upload_id
        })
