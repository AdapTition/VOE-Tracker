"""'Встановити на цей комп'ютер': copy the exe to a permanent place + desktop shortcut."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable, Mapping

APP_NAME = "VOE Explorer"


def _under(path: Path, root: str | None) -> bool:
    if not root:
        return False
    p, r = str(path).lower().rstrip("\\/"), str(Path(root)).lower().rstrip("\\/")
    return p.startswith(r + "\\") or p.startswith(r + "/")


def is_transient_location(exe: Path, env: Mapping[str, str]) -> bool:
    downloads = str(Path(env["USERPROFILE"]) / "Downloads") if env.get("USERPROFILE") else None
    return any(_under(exe, root) for root in (env.get("TEMP"), env.get("TMP"), downloads))


def install_target(env: Mapping[str, str]) -> Path:
    return Path(env["LOCALAPPDATA"]) / APP_NAME / f"{APP_NAME}.exe"


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def install_self(exe: Path, env: Mapping[str, str], run: Callable[[list[str]], None] = _run) -> Path:
    target = install_target(env)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exe, target)
    t = str(target).replace("'", "''")
    script = (
        "$d=[Environment]::GetFolderPath('Desktop');"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'VOE Explorer.lnk'));"
        f"$s.TargetPath='{t}';$s.WorkingDirectory='{str(target.parent).replace(chr(39), chr(39) * 2)}';$s.Save()"
    )
    run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script])
    return target
