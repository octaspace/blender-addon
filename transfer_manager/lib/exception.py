from sanic.response import json
from sanic import SanicException
from traceback import format_exception
import logging

logger = logging.getLogger(__name__)


async def handle_exceptions(request, exception):
    exception_text = format_exception(exception, limit=None, chain=True)
    if isinstance(exception, SanicException):
        status_code = exception.status_code
    else:
        status_code = 500
        logger.warning(exception_text)
    return json({"error": exception_text}, status=status_code)
