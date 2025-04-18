import bpy
import base64
import json
import sys
import os
import subprocess
from typing import TypedDict

IMAGE_TYPE_TO_EXTENSION = {
    "BMP": "bmp",
    "IRIS": "iris",
    "PNG": "png",
    "JPEG": "jpg",
    "JPEG2000": "jp2",
    "TARGA": "tga",
    "TARGA_RAW": "tga",
    "CINEON": "cin",
    "DPX": "dpx",
    "OPEN_EXR": "exr",
    "OPEN_EXR_MULTILAYER": "exr",
    "HDR": "hdr",
    "TIFF": "tif",
    "WEBP": "webp",
}


class UserData(TypedDict):
    farm_host: str
    api_token: str
    qm_auth_token: str


class RenderPass(TypedDict):
    name: str
    files: dict[str, str]


def get_addon_name():
    current_package = __package__
    if current_package.startswith("bl_ext."):
        parts = current_package.split(".")
        root_package = ".".join(parts[:3])
        return root_package

    root_package = (
        current_package.split(".")[0] if "." in current_package else current_package
    )
    return root_package


def get_preferences():
    root_package = get_addon_name()
    preferences = bpy.context.preferences.addons[root_package].preferences
    return preferences


def get_all_output_file_nodes():
    scene = bpy.context.scene
    output_nodes = []

    if scene.use_nodes and scene.node_tree:
        for node in scene.node_tree.nodes:
            # Check for type
            if node.type == "OUTPUT_FILE":
                # Skip if no inputs are connected
                if not node.inputs or not any(inp.is_linked for inp in node.inputs):
                    continue
                output_nodes.append(node)

    return output_nodes


def get_all_render_passes():
    output_nodes = get_all_output_file_nodes()
    render_passes = {}

    for node in output_nodes:
        name = node.name
        files = {}

        default_format = node.format.file_format

        for slot in node.file_slots:
            # Use the node's default format unless the slot specifically
            # overrides it
            format_to_use = (
                default_format if slot.use_node_format else slot.format.file_format
            )
            extension = IMAGE_TYPE_TO_EXTENSION.get(format_to_use, "unknown")

            # If the format is EXR Multilayer, there's only one file
            if default_format == "OPEN_EXR_MULTILAYER":
                files["MultiLayer"] = extension
                break
            else:
                files[slot.path] = extension

        render_passes[name] = {
            "name": name,
            "files": files,
        }

    return render_passes


def unpack_octa_farm_config(octa_farm_config: str) -> UserData:
    """
    unpacks the configuration string we get from frontend
    :param octa_farm_config:
    :return: tuple of 3 strings: farm host, api token, queue manager auth token
    """

    if not octa_farm_config:
        return {
            "farm_host": "http://34.147.146.4/",
            "api_token": "thisisatestkey",
            "qm_auth_token": "",
        }

    lst = json.loads(base64.b64decode(octa_farm_config).decode())
    return {"farm_host": lst[0], "api_token": lst[1], "qm_auth_token": lst[2]}


def section(layout, properties, toggle_name, title):
    box = layout.box()
    visible = getattr(properties, toggle_name)
    box.prop(
        properties,
        toggle_name,
        text=title,
        icon="DOWNARROW_HLT" if visible else "RIGHTARROW",
        emboss=False,
    )
    if visible:
        return box
    return None


def spawn_detached_process(command, **kwargs):
    print(f"spawning detached process {command} {kwargs}")
    if sys.platform.startswith("win"):
        # Windows
        # create new console
        CREATE_NEW_CONSOLE = 0x00000010
        # hide console
        DETACHED_PROCESS = 0x00000008
        return subprocess.Popen(
            command, creationflags=DETACHED_PROCESS, close_fds=True, **kwargs
        )
        # return subprocess.Popen(command, stdout=sys.stdout, stderr=sys.stderr, **kwargs) # for debugging
    else:
        # Unix-like systems (Linux, macOS)
        return subprocess.Popen(command, preexec_fn=os.setsid, close_fds=True, **kwargs)


def is_process_running(pid: int):
    if sys.platform.startswith("win"):
        # Windows
        try:
            # Use tasklist command to check if the process is running
            output = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {pid}"],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            output = output.decode(errors="ignore")
            if f"{pid}" in output:
                return True
        except subprocess.CalledProcessError:
            pass
    else:
        # Unix-like systems (Linux, macOS)
        try:
            if sys.platform.startswith("linux"):
                # Linux
                os.kill(pid, 0)  # os.kill with signal 0 only checks for existence
                return True
            else:
                # macOS
                output = subprocess.check_output(["ps", "-p", str(pid)])
                output = output.decode()
                if f"{pid}" in output:
                    return True
        except (OSError, subprocess.CalledProcessError):
            pass

    return False
