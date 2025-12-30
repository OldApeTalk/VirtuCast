"""VirtuCast auto-run hook for Unreal Editor startup.

Unreal will execute any `init_unreal.py` found on its Python paths during
startup. Using this mechanism avoids Unreal's CLI behavior where
`-ExecutePythonScript=...` auto-quits the editor right after the script
finishes.

We only run VirtuCast rendering when explicitly requested via command line:
- -VirtuCastAutoRender=1

Optional:
- -VirtuCastScript=<path-to-python-file>   (defaults to Project/Scripts/virtu_render_queue.py)

All other VirtuCast arguments (VirtuCastMap/Sequence/Out/Res/Fps) are parsed
by the render script itself.
"""

from __future__ import annotations

import os
import re
import runpy
import sys
from pathlib import Path

import unreal


_ALREADY_RAN = False


def _get_cmdline() -> str:
    try:
        return unreal.SystemLibrary.get_command_line()
    except Exception:
        return ""


def _get_arg(cmdline: str, name: str) -> str | None:
    pattern = rf"(?:^|\s)-{re.escape(name)}=(?:\"([^\"]*)\"|([^\s]+))"
    m = re.search(pattern, cmdline)
    if not m:
        return None
    return m.group(1) or m.group(2)


def _truthy(v: str | None) -> bool:
    if v is None:
        return False
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def _project_dir() -> Path:
    # project_dir() returns something like "D:/.../VirtuCast/"
    p = unreal.Paths.project_dir()
    return Path(str(p)).resolve()


def _normalize_path(p: str) -> str:
    # Unreal passes command line paths with forward slashes; keep consistent.
    return p.replace("\\", "/")


def _default_script_path() -> Path:
    return (_project_dir() / "Scripts" / "virtu_render_queue.py").resolve()


def _run_script(script_path: Path) -> None:
    script_path = script_path.resolve()
    if not script_path.exists():
        raise FileNotFoundError(f"VirtuCast script not found: {script_path}")

    # Ensure the script folder is importable for any relative imports.
    script_dir = str(script_path.parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    unreal.log(f"[VirtuCast] init_unreal.py running: {_normalize_path(str(script_path))}")
    runpy.run_path(str(script_path), run_name="__main__")


def main() -> None:
    global _ALREADY_RAN
    if _ALREADY_RAN:
        return

    cmdline = _get_cmdline()
    if not _truthy(_get_arg(cmdline, "VirtuCastAutoRender")):
        return

    _ALREADY_RAN = True

    script_arg = _get_arg(cmdline, "VirtuCastScript")
    script_path = Path(script_arg) if script_arg else _default_script_path()

    # If a relative path is provided, resolve it relative to project dir.
    if not script_path.is_absolute():
        script_path = (_project_dir() / script_path).resolve()

    try:
        _run_script(script_path)
    except Exception as exc:
        unreal.log_error(f"[VirtuCast] init_unreal.py failed: {exc}")
        # Best effort: request editor exit so automation doesn't hang.
        try:
            unreal.SystemLibrary.quit_editor()
        except Exception:
            pass


main()
