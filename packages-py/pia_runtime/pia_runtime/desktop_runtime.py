from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path


PROFILE_FILE = "desktop-profile"


class DesktopDataError(RuntimeError):
    pass


@contextmanager
def lock_desktop_data(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "desktop.lock").open("a+b") as lock:
        try:
            if os.name == "nt":
                import msvcrt

                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise DesktopDataError("此数据目录正在使用。请退出占用它的 Pia 进程后重试。") from error
        yield


def claim_desktop_profile(directory: Path, profile: str) -> None:
    marker = directory / PROFILE_FILE
    if marker.exists():
        if marker.read_text(encoding="utf-8").strip() != profile:
            raise DesktopDataError("当前应用与数据目录的环境不一致。请检查桌面端数据目录配置。")
        return
    marker.write_text(f"{profile}\n", encoding="utf-8")
