import requests
import sys
import os
import time
from .util import spawn_detached_process, is_process_running, UserData
from typing import TypedDict

TM_HOST = "http://127.0.0.1:7780"


class JobInformation(TypedDict):
    frame_start: int
    frame_end: int
    frame_step: int
    batch_size: int
    name: str
    render_passes: dict
    render_format: str
    render_engine: str
    blender_version: str
    blend_name: str
    max_thumbnail_size: int


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


def ensure_running():
    # TODO: call api instead to check if running?
    def start_tm():
        print("Starting Transfer Manager")
        process = spawn_detached_process([
            sys.executable,
            '-m',
            'transfer_manager.main'
        ], cwd=os.path.join(os.path.dirname(os.path.dirname(__file__))))

        with open('tm.pid', 'wt') as f:
            f.write(str(process.pid))

        time.sleep(5) # give tm time to startup TODO: ping api instead?

    if os.path.isfile('tm.pid'):
        with open('tm.pid', 'rt') as f:
            pid = f.read()
        if len(pid) < 1 or not is_process_running(int(pid)):
            return start_tm()
    else:
        return start_tm()

    print("Transfer Manager already running")