import bpy
import base64
import json
import hashlib
from typing import TypedDict
import aiofiles
import asyncio
import functools

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


class RenderPass(TypedDict):
    name: str
    files: dict[str, str]


def get_all_output_file_nodes():
    scene = bpy.context.scene
    output_nodes = []

    if scene.use_nodes:
        for node in scene.node_tree.nodes:
            if node.type == "OUTPUT_FILE":
                output_nodes.append(node)

    return output_nodes


def get_all_render_passes() -> dict[str, RenderPass]:
    output_nodes = get_all_output_file_nodes()
    render_passes = {}

    for node in output_nodes:
        name = node.name
        files = {}

        default_format = node.format.file_format

        for slot in node.file_slots:
            format_to_use = default_format if slot.use_node_format else slot.format.file_format
            path = slot.path
            extension = IMAGE_TYPE_TO_EXTENSION.get(format_to_use, "unknown")
            if default_format == "OPEN_EXR_MULTILAYER":
                files["MultiLayer"] = extension
                break
            else:
                files[path] = extension

        render_passes[name] = {"name": name, "files": files}

    return render_passes


def unpack_octa_farm_config(octa_farm_config: str) -> (str, str, str):
    """
    unpacks the configuration string we get from frontend
    :param octa_farm_config:
    :return: tuple of 3 strings: farm host, session cookie, queue manager auth token
    """
    lst = json.loads(base64.b64decode(octa_farm_config).decode())
    return lst[0], lst[1], lst[2]


def get_file_md5(path: str) -> str:
    hasher = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


async def get_file_md5_async(path: str) -> str:
    hasher = hashlib.md5()

    async with aiofiles.open(path, "rb") as f:
        while True:
            chunk = await f.read(4096)
            if not chunk:
                break
            hasher.update(chunk)

    return hasher.hexdigest()


async def spawn_and_wait(worker_pool, task_function, task_name, iterable, workers=4):
    iteration = 0
    active_tasks = []  # Keep track of active tasks
    while iteration < len(iterable) or any([task for task in active_tasks if not task.done()]):
        if len([task for task in active_tasks if not task.done()]) < workers and iteration < len(iterable):
            task = asyncio.create_task(task_function(iteration))
            active_tasks.append(task)
            iteration += 1
        await asyncio.sleep(0.01)  # This allows other tasks to run

    await asyncio.gather(*active_tasks)  # Ensure all tasks are completed before returning


def worker(task_name):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, iterator):
            # Increment running workers count
            task = self.workers.get(task_name, {})
            task["running"] = task.get("running", 0) + 1
            self.workers[task_name] = task

            try:
                result = await func(self, iterator)
                return result
            except Exception as e:
                # Handle exceptions and increment error count
                self.errors[task_name] = self.errors.get(task_name, 0) + 1
                raise
            finally:
                # Adjust running and finished workers count
                task["running"] = task.get("running", 0) - 1
                task["finished"] = task.get("finished", 0) + 1
                self.workers[task_name] = task

        return wrapper

    return decorator
