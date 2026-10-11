"""Put this directory on the path so tests import the recorder modules.

Bytecode is left off, and any cache directory is removed when the run
ends, so a second look at this directory sees no leftover files.
"""

from __future__ import annotations

import atexit
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
