from .web_api_base import WebApiBase
from ..lib.user_data import UserData

version = "20241125"
soft_version = "20241125"


class SarfisException(Exception):
    pass


class SarfisVersionException(Exception):
    pass


class Sarfis:
    @classmethod
    async def call(cls, user_data: UserData, endpoints):
        url = f"{user_data.farm_host}/qm/uber_api"
        headers = {}
        if user_data.qm_auth_token:
            headers["Auth-Token"] = user_data.qm_auth_token
            headers["Sarfis-Version"] = version
            headers["Sarfis-Soft-Version"] = soft_version
        return await WebApiBase.request_with_retries(
            "POST", url, json=endpoints, headers=headers
        )

    @classmethod
    def ensure_successful(cls, result_data: dict):
        status = result_data["status"]
        body = result_data["body"]
        if status != "success":
            raise SarfisException(
                f"sarfis call status was not success: {status}\n{body}"
            )
        return body

    @classmethod
    async def node_job(cls, user_data: UserData, job):
        result = await cls.call(user_data, {"node_job": job})
        data = result["node_job"]
        return cls.ensure_successful(data)

    @classmethod
    async def get_job_details(cls, user_data: UserData, job_id):
        result = await cls.call(user_data, {"job_details": {"job_id": job_id}})
        data = result["job_details"]
        return cls.ensure_successful(data)
