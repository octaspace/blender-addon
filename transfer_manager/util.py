import uuid
import hashlib


def get_next_id() -> str:
    return str(uuid.uuid4())  # TODO: replace with uuid7 once it is added to python because they are sortable by timestamp


def get_file_md5(path: str) -> str:
    hasher = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(16 * 1024 * 1024), b''):  # 16 megabytes at a time
            hasher.update(chunk)
    return hasher.hexdigest()


IMAGE_TYPE_TO_EXTENSION = {
    'BMP': 'bmp',
    'IRIS': 'iris',
    'PNG': 'png',
    'JPEG': 'jpg',
    'JPEG2000': 'jp2',
    'TARGA': 'tga',
    'TARGA_RAW': 'tga',
    'CINEON': 'cin',
    'DPX': 'dpx',
    'OPEN_EXR': 'exr',
    'OPEN_EXR_MULTILAYER': 'exr',
    'HDR': 'hdr',
    'TIFF': 'tif',
    'WEBP': 'webp',
}

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