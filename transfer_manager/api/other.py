import tempfile
import os
from sanic.response import text, json
from ..lib.version import version


async def logs(_):
    log_file_path = os.path.join(tempfile.gettempdir(), "tm.log")
    if os.path.exists(log_file_path) and os.path.isfile(log_file_path):
        with open(log_file_path, 'rt') as f:
            data = f.read()
    else:
        data = ""
    return text(data)


async def transfer_manager_info(request):
    return json({
        "service": "transfer_manager",
        "version": version,
        "process_id": os.getpid()
    })
