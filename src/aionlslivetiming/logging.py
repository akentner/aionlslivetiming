"""Logging helpers.

A trivially thin wrapper over :mod:`logging` so the parser and CLI subpackages
agree on a single helper and the logger namespace is easy to discover.
"""

from __future__ import annotations

import logging

__all__ = ["get_logger"]


def get_logger(name: str) -> logging.Logger:
    """Return a :class:`logging.Logger` for *name*.

    This is just :func:`logging.getLogger` re-exported so call sites do not need
    to import :mod:`logging` directly. The canonical subnamespaces used in the
    package are:

    - ``aionlslivetiming.parser`` — parser diagnostics (D-03)
    - ``aionlslivetiming.cli`` — live-capture / replay CLI (D-07)
    """
    return logging.getLogger(name)
