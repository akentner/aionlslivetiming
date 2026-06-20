"""Package version constant.

Kept in a separate module so ``__version__`` is importable from anywhere in
the package without triggering the top-level ``__init__`` import chain
(useful for ``pip show`` and debugging).
"""

__version__: str = "0.1.0"
