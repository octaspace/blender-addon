from sanic.response import text
from sanic import Request
from ..lib.version import version


async def ensure_version(request: Request):
    tm_version_header = request.headers.get("Transfer-Manager-Version", None)
    if tm_version_header:
        if tm_version_header != version:
            return text(f"you requested version {tm_version_header} but this is version {version}", status=412)
