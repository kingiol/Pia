from __future__ import annotations

import atexit
import multiprocessing
import threading
import time
from typing import Any, Callable

from .stage_policy import StageTimeout


_children: set[Any] = set()
_lock = threading.Lock()


def _leaf(connection, function, args, kwargs):
    try:
        connection.send(("ok", function(*args, **kwargs)))
    except BaseException as error:
        connection.send(("error", type(error).__name__))
    finally:
        connection.close()


def _stop(process) -> None:
    if process.is_alive():
        process.terminate()
    process.join(2)
    if process.is_alive():
        process.kill()
        process.join(2)


def cleanup_children() -> None:
    with _lock:
        children = list(_children)
    for process in children:
        _stop(process)


atexit.register(cleanup_children)


def isolated_call(function: Callable, args=(), kwargs=None, *, timeout=45.0, check=None):
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_leaf, args=(child, function, args, kwargs or {}), daemon=True)
    process.start()
    child.close()
    with _lock:
        _children.add(process)
    deadline = time.monotonic() + timeout
    try:
        while True:
            if check:
                check()
            if time.monotonic() >= deadline:
                raise StageTimeout("Provider call exceeded its stage deadline.")
            if parent.poll(min(0.05, max(0, deadline - time.monotonic()))):
                status, payload = parent.recv()
                if check:
                    check()
                if status == "error":
                    if payload in {"TimeoutError", "ConnectionError", "OSError"}:
                        raise ConnectionError(f"PROVIDER_CHILD_ERROR:{payload}")
                    raise RuntimeError(f"PROVIDER_CHILD_ERROR:{payload}")
                return payload
            if not process.is_alive():
                raise RuntimeError("PROVIDER_CHILD_EXITED")
    finally:
        _stop(process)
        parent.close()
        with _lock:
            _children.discard(process)


def provider_leaf(provider_id: str, credential: str | None, method: str, args: tuple, kwargs: dict, *, daily_only: bool = False):
    from .adapters import AkshareMarketProvider, TushareMarketProvider

    provider = AkshareMarketProvider() if provider_id == "akshare" else TushareMarketProvider(credential, daily_only=daily_only)
    return getattr(provider, method)(*args, **kwargs)


def isolation_health():
    import operator
    if isolated_call(operator.add, (2, 3), timeout=10) != 5:
        raise RuntimeError("ISOLATION_RESULT_INVALID")
    try:
        isolated_call(time.sleep, (30,), timeout=0.1)
    except StageTimeout:
        return {"status": "ok", "start_method": "spawn", "timeout_cleanup": True}
    raise RuntimeError("ISOLATION_TIMEOUT_NOT_ENFORCED")
