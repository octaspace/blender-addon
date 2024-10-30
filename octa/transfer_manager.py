import requests
import sys
import os
import tempfile
from .util import spawn_detached_process, is_process_running, UserData
from typing import TypedDict
import signal
import bpy


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


def get_url(path: str) -> str:
    return f"{TM_HOST}/api{path}"


def create_upload(
    local_file_path: str,
    job_information: JobInformation,
    user_data: UserData,
    metadata: dict,
) -> str:
    response = requests.post(
        get_url("/upload"),
        headers=user_data,
        json={
            "local_file_path": local_file_path,
            "job_information": job_information,
            "metadata": metadata,
        },
    )
    return response.json()


def create_download(
    local_dir_path: str, job_id: str, user_data: UserData, metadata: dict
) -> str:
    response = requests.post(
        get_url("/download"),
        headers=user_data,
        json={
            "local_dir_path": local_dir_path,
            "job_id": job_id,
            "metadata": metadata,
        },
    )
    return response.json()


def is_reachable():
    try:
        requests.get(TM_HOST, timeout=5)
        return True
    except:
        return False


def get_tm_pid_path():
    return os.path.join(tempfile.gettempdir(), "tm.pid")


def ensure_running() -> bool:
    def start_tm():
        print("Starting Transfer Manager")
        process = spawn_detached_process(
            [sys.executable, "-m", "transfer_manager.main"],
            cwd=os.path.join(os.path.dirname(os.path.dirname(__file__))),
        )

        print(f"detached process with pid {process.pid}")

        with open(get_tm_pid_path(), "wt") as f:
            f.write(str(process.pid))

        return is_reachable()

    if os.path.isfile(get_tm_pid_path()):
        with open(get_tm_pid_path(), "rt") as f:
            pid = f.read()
        if len(pid) < 1 or not is_process_running(int(pid)):
            # pid file, but process not running
            return start_tm()
    else:
        # no pid file. start from scratch
        return start_tm()

    print("Transfer Manager already running")
    return is_reachable()


class OCTA_OT_TransferManager(bpy.types.Operator):
    bl_idname = "octa.transfer_manager"
    bl_label = "Transfer Manager"
    bl_description = "Start or stop the Transfer Manager"

    state: bpy.props.BoolProperty(name="State", description="State", default=True)

    def execute(self, context):
        if self.state:
            # Start the Transfer Manager
            if ensure_running():
                self.report({"INFO"}, "Transfer Manager started")
            else:
                self.report({"ERROR"}, "Failed to start Transfer Manager")
        else:
            # Stop the Transfer Manager
            pid_path = get_tm_pid_path()
            print(f"pid_path: {pid_path}")
            if os.path.isfile(pid_path):
                with open(pid_path, "rt") as f:
                    pid = f.read()
                if pid:
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                        os.remove(pid_path)
                        self.report({"INFO"}, "Transfer Manager stopped")
                    except Exception as e:
                        self.report({"ERROR"}, f"Failed to stop Transfer Manager: {e}")
            else:
                self.report({"INFO"}, "Transfer Manager is not running")
        return {"FINISHED"}
