from __future__ import annotations

import threading
from typing import Any


_lock = threading.RLock()
_execer: Any = None


def _get_execer(filename: str):
    global _execer

    from xonsh.built_ins import XSH
    from xonsh.execer import Execer

    if _execer is None:
        _execer = Execer(
            filename=filename,
            scriptcache=False,
            cacheall=False,
        )
    # Xonsh's parse recovery helpers consult the global session even when
    # parsing through a directly constructed Execer.
    if XSH.execer is not _execer:
        XSH.execer = _execer
    return _execer


def parse_xonsh(source: str, filename: str):
    with _lock:
        execer = _get_execer(filename)
        return execer.parse(
            source,
            ctx=set(dir(__builtins__)),
            filename=filename,
        )


def compile_xonsh(source: str, filename: str):
    with _lock:
        execer = _get_execer(filename)
        return execer.compile(
            source,
            glbs={},
            locs={},
            filename=filename,
        )
