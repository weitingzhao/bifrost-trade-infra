"""Put this directory on the path so tests import the recorder modules.

Bytecode is left off, and any cache directory is removed when the run
ends, so a second look at this directory sees no leftover files.
"""

from __future__ import annotations

import atexit
import os
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


def _drop_cache() -> None:
    cache = _HERE / "__pycache__"
    if cache.is_dir():
        shutil.rmtree(cache, ignore_errors=True)


atexit.register(_drop_cache)


def pytest_collection_modifyitems(items):
    """During a mutant run, fail the new checks before the older suite."""
    if os.environ.get("RECORDER_MUTANT_ORDER") != "1":
        return

    def rank(item):
        path = str(getattr(item, "path", getattr(item, "fspath", "")))
        name = path.rsplit("/", 1)[-1]
        if name.startswith("test_round8"):
            group = 0
        elif name == "test_review113.py":
            group = 1
        else:
            group = 2
        return (group, name)

    items.sort(key=rank)
