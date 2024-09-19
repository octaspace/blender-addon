import requests
from typing import TypedDict

TM_HOST = "http://127.0.0.1:7780"


class JobInformation(TypedDict):
    frame_start: int
    frame_end: int
    batch_size: int
    name: str
    render_passes: dict
    render_format: str
    render_engine: str
    blender_version: str
    blend_name: str
    max_thumbnail_size: int


class UserData(TypedDict):
    farm_host: str
    api_token: str
    qm_auth_token: str


def get_url(path):
    return f"{TM_HOST}/api{path}"


def create_upload(local_file_path: str, job_information: JobInformation, user_data: UserData) -> str:
    response = requests.post(get_url('/upload'), headers=user_data, json={
        'local_file_path': local_file_path,
        'job_information': job_information
    })
    return response.json()


def create_download(local_dir_path: str, job_id: str, user_data: UserData):
    response = requests.post(get_url('/download'), headers=user_data, json={
        'local_dir_path': local_dir_path,
        'job_id': job_id
    })
    return response.json()
