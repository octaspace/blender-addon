import requests
import sys
import os
import threading
import time
import signal
import bpy
from .util import (
    spawn_detached_process,
    UserData,
    unpack_octa_farm_config,
    get_preferences,
)
from typing import TypedDict
from bpy.props import BoolProperty
from bpy.types import PropertyGroup
import webbrowser
from .install_dependencies import InstallDependenciesOperator

TM_HOST = "http://127.0.0.1:7780"

TRANSFER_MANAGER_IS_RUNNING = False  # Global variable for service status


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


def verify_key(user_data: UserData) -> bool:
    api_token = user_data["api_token"]
    headers = {
        "Authorization": api_token,
        "Content-Type": "application/json",
    }
    response = requests.get(
        "https://api.octa.computer/accounts/balance", headers=headers
    )
    print(response.json())
    return response.status_code == 200


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


# Background thread function to check service status
def background_is_reachable():
    global TRANSFER_MANAGER_IS_RUNNING
    while True:
        try:
            response = requests.get(get_url("/transfer_manager_info"), timeout=5)
            TRANSFER_MANAGER_IS_RUNNING = response.status_code == 200
        except Exception as e:
            TRANSFER_MANAGER_IS_RUNNING = False
            # print(f"Error checking Transfer Manager status: {e}")
        time.sleep(3)  # Check every 3 seconds


# Start the background thread
threading.Thread(target=background_is_reachable, daemon=True).start()


def is_reachable():
    global TRANSFER_MANAGER_IS_RUNNING
    return TRANSFER_MANAGER_IS_RUNNING


def ensure_running() -> bool:
    if is_reachable():
        print("Transfer Manager already running")
        return True
    else:
        # Start the Transfer Manager
        print("Starting Transfer Manager Buffer")
        process = spawn_detached_process(
            [sys.executable, "-m", "transfer_manager.buffer_main"],
            cwd=os.path.join(os.path.dirname(os.path.dirname(__file__))),
        )
        print(f"Started Transfer Manager Buffer with PID {process.pid}")

        # Wait for the service to become reachable
        for _ in range(10):  # Try for up to 30 seconds
            if is_reachable():
                print("Transfer Manager is now reachable")
                return True
            print("Waiting for Transfer Manager to start")
            time.sleep(3)

        print("Failed to start Transfer Manager")
        return False


class TransferManagerStatus(PropertyGroup):
    is_running: BoolProperty(name="Is Transfer Manager Running", default=False)


class OCTA_OT_TransferManager(bpy.types.Operator):
    bl_idname = "octa.transfer_manager"
    bl_label = "Transfer Manager"
    bl_description = "Start or Stop the Transfer Manager"

    state: bpy.props.BoolProperty()

    _timer = None
    _run_thread = None
    _running = False
    _messages = []
    _current_action = None  # Added to track current action ('starting' or 'stopping')

    @classmethod
    def _set_running(cls, value: bool):
        cls._running = value

    @classmethod
    def get_running(cls) -> bool:
        return cls._running

    @classmethod
    def poll(cls, context):
        return not cls.get_running()

    def modal(self, context, event):
        if event.type == "TIMER":
            if not self.get_running():
                context.window_manager.event_timer_remove(self._timer)
                # Report messages collected from the thread
                for level, msg in self._messages:
                    self.report({level}, msg)
                self._messages.clear()
                self._run_thread = None
                self.__class__._current_action = None  # Reset current action
                return {"FINISHED"}
        return {"PASS_THROUGH"}

    def execute(self, context):
        self._set_running(True)
        self.__class__._current_action = (
            "starting" if self.state else "stopping"
        )  # Set current action
        self._messages = []
        self._run_thread = threading.Thread(target=self.thread_run)
        self._run_thread.start()
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def thread_run(self):
        global TRANSFER_MANAGER_IS_RUNNING
        if self.state:
            # Start the Transfer Manager
            if ensure_running():
                # Collect messages to report later
                self._messages.append(("INFO", "Transfer Manager started."))
                TRANSFER_MANAGER_IS_RUNNING = True
            else:
                self._messages.append(("ERROR", "Failed to start Transfer Manager."))
                TRANSFER_MANAGER_IS_RUNNING = False
        else:
            # Stop the Transfer Manager via shutdown endpoint
            try:
                response = requests.get(get_url("/transfer_manager_info"), timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    ppid = data.get("process_id", None)
                    if ppid:
                        os.kill(ppid, signal.SIGTERM)
                        self._messages.append(
                            ("INFO", f"Transfer Manager (PID {ppid}) stopped.")
                        )
                        TRANSFER_MANAGER_IS_RUNNING = False
                    else:
                        self._messages.append(("ERROR", "Parent process ID not found."))
                else:
                    self._messages.append(
                        ("ERROR", "Failed to retrieve Transfer Manager process info.")
                    )
            except Exception as e:
                self._messages.append(
                    ("ERROR", f"Failed to stop Transfer Manager: {e}")
                )
            # Optionally, wait a moment for the service to shut down
            time.sleep(1)  # Adjust as needed
        self._set_running(False)
        # Reset current action after operation completes
        self.__class__._current_action = None


class OCTA_OT_OpenTransferManager(bpy.types.Operator):
    bl_idname = "octa.open_transfer_manager"
    bl_label = "Open Transfer Manager"
    bl_description = "Open the Transfer Manager in a web browser"

    def execute(self, context):
        properties = context.scene.octa_properties
        farm_config = unpack_octa_farm_config(get_preferences().octa_farm_config)
        farm_host = farm_config.get("farm_host", "")
        transfer_manager_url = f"{farm_host}/transfers"
        webbrowser.open(transfer_manager_url)
        return {"FINISHED"}


def transfer_manager_section(layout, properties):
    installed_correctly, missing_or_incorrect = (
        InstallDependenciesOperator.check_dependencies_installed()
    )
    dependencies_installed = not missing_or_incorrect

    box = layout.box()
    if box is not None:
        row = box.row()
        if not dependencies_installed:
            row.label(text="Install dependencies in addon preferences", icon="ERROR")

        col = box.column()

        col.enabled = dependencies_installed

        is_running = is_reachable()

        col.label(
            text=f"Transfer Manager {'Running' if is_running else 'Stopped'}",
            icon="KEYTYPE_JITTER_VEC" if is_running else "KEYTYPE_EXTREME_VEC",
        )

        row = col.row()
        row_left = row.row()
        row_right = row.row()
        row_right.alignment = "RIGHT"

        if not OCTA_OT_TransferManager._running:
            if is_running:
                op = row_left.operator(
                    "octa.transfer_manager", icon="X", text="Stop Transfer Manager"
                )
                op.state = False
            else:
                op = row_left.operator(
                    "octa.transfer_manager", icon="PLAY", text="Start Transfer Manager"
                )
                op.state = True
        else:
            current_action = OCTA_OT_TransferManager._current_action
            if current_action == "starting":
                text = "Starting Transfer Manager"
            elif current_action == "stopping":
                text = "Stopping Transfer Manager"
            else:
                text = "Processing..."

            row_left.operator(
                "octa.transfer_manager",
                icon="FILE_REFRESH",
                text=text,
            )

        row_right.operator(
            "octa.open_transfer_manager",
            icon="URL",
            text="",
        )
