"""AIO NLS Livetiming API.

Async-first Python client for the official Nürburgring Langstrecken-Serie
livetiming service at ``livetiming.azurewebsites.net``.
"""

from aionlslivetiming.logging import get_logger
from aionlslivetiming.version import __version__

__all__ = ["__version__", "get_logger"]
