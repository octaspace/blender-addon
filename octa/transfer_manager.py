import requests
import sys
import os
import time
from .util import spawn_detached_process, UserData
from typing import TypedDict
import bpy
from bpy.props import BoolProperty

TM_HOST = "http://127.0.0.1:7780"
tm_network_status = {
    "reachable": False,
    "last_checked": 0.0,
    "process_id": None,
    "version": None,
}


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


def is_reachable() -> bool:
    """Check if the Transfer Manager is reachable via the transfer_manager_info endpoint."""
    try:
        response = requests.get(get_url("/transfer_manager_info"), timeout=0.5)
        if response.status_code == 200:
            info = response.json()
            # Update the global status with the received info
            tm_network_status["reachable"] = True
            tm_network_status["process_id"] = info.get("process_id")
            tm_network_status["version"] = info.get("version")
            return True
    except:
        pass
    # If the request failed or returned an unexpected status code
    tm_network_status["reachable"] = False
    tm_network_status["process_id"] = None
    tm_network_status["version"] = None
    return False


def ensure_running() -> bool:
    """Ensure that the Transfer Manager is running, or start it if not."""
    if is_reachable():
        print("Transfer Manager already running")
        return True
    else:
        # Start the Transfer Manager
        print("Starting Transfer Manager")
        process = spawn_detached_process(
            [sys.executable, "-m", "transfer_manager.main"],
            cwd=os.path.join(os.path.dirname(os.path.dirname(__file__))),
        )
        print(f"Detached process with PID {process.pid}")

        # Wait for it to become reachable
        for _ in range(10):  # Wait up to 5 seconds (0.5 * 10)
            if is_reachable():
                return True
            time.sleep(0.5)
        return False


def update_tm_status():
    """Periodically check Transfer Manager network reachability and update the status."""
    is_reachable()
    tm_network_status["last_checked"] = time.time()
    # Schedule to run again in 3 seconds
    return 3.0


class OCTA_OT_TransferManager(bpy.types.Operator):
    bl_idname = "octa.transfer_manager"
    bl_label = "Transfer Manager"
    bl_description = "Start or stop the Transfer Manager"

    state: BoolProperty()

    def execute(self, context):
        if self.state:
            # Start the Transfer Manager
            while not ensure_running():
                print("Failed to start Transfer Manager, retrying in 3 seconds")
                time.sleep(3)
        else:
            # Stop the Transfer Manager
            if is_reachable():
                try:
                    # Send a shutdown request to the Transfer Manager
                    response = requests.post(get_url("/shutdown"), timeout=0.5)
                    if response.status_code == 200:
                        self.report({"INFO"}, "Transfer Manager stopped")
                        tm_network_status["reachable"] = False
                        tm_network_status["process_id"] = None
                        tm_network_status["version"] = None
                    else:
                        self.report({"ERROR"}, "Failed to stop Transfer Manager")
                except Exception as e:
                    self.report({"ERROR"}, f"Failed to stop Transfer Manager: {e}")
            else:
                self.report({"INFO"}, "Transfer Manager is not running")
        return {"FINISHED"}
