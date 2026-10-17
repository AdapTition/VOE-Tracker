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


def _ps_quote(text: str) -> str:
    """Body of a PowerShell single-quoted string: it also ends on ‘ ’ ‚ ‛, doubling escapes each."""
    return "".join(c * 2 if c in "'\u2018\u2019\u201a\u201b" else c for c in text)


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def install_self(exe: Path, env: Mapping[str, str], run: Callable[[list[str]], None] = _run) -> Path:
    target = install_target(env)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exe, target)
    script = (
        "$d=[Environment]::GetFolderPath('Desktop');"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'VOE Explorer.lnk'));"
        f"$s.TargetPath='{_ps_quote(str(target))}';$s.WorkingDirectory='{_ps_quote(str(target.parent))}';$s.Save()"
    )
    run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script])
    return target
