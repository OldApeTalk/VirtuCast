"""VirtuCast UE Render Launcher

Two rendering modes are supported:

1) script (recommended): launch Unreal Editor and run a UE-side Python script
    via the project's Python startup hook `Content/Python/init_unreal.py`
    (guarded by `-VirtuCastAutoRender=1`). This avoids Unreal's auto-quit
    behavior with `-ExecutePythonScript` and is the flexible path: output
    directory, resolution, FPS, file naming, etc. can be configured by the UE
    script.

2) cli (fallback): launch Unreal in MRQ command-line mode using
    -LevelSequence and -MoviePipelineConfig. This is simple but most render
    settings (notably output directory and format) are controlled by the MRQ
    Primary Config asset.

Reads config/default_config.yaml by default.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import re
from pathlib import Path
from typing import Any

import yaml


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid YAML root in: {path}")
    return data


def _resolve_path(repo_root: Path, p: str) -> Path:
    path = Path(p)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def _to_unreal_cmd_path(path: Path) -> str:
    """Unreal generally accepts forward slashes on Windows; use them for safety."""
    return str(path).replace("\\", "/")


def _build_args(
    ue_editor: Path,
    uproject: Path,
    map_package: str,
    sequence_object: str,
    mrq_config_object: str,
    res_x: int,
    res_y: int,
) -> list[str]:
    return [
        str(ue_editor),
        str(uproject),
        # Map is a URL-like argument (non-dash) for -game startup.
        map_package,
        "-game",
        # MRQ CLI flags (UE 5.7+ Movie Render Pipeline)
        f"-LevelSequence={sequence_object}",
        f"-MoviePipelineConfig={mrq_config_object}",
        # Keep window args for stability even in unattended runs.
        "-windowed",
        f"-ResX={res_x}",
        f"-ResY={res_y}",
        "-unattended",
        "-nop4",
        "-nosplash",
        "-NoSound",
        "-log",
    ]


def _build_execute_python_args(
    ue_editor: Path,
    uproject: Path,
    ue_python_script: Path,
    map_ref: str,
    sequence_ref: str,
    out_dir: Path,
    res_x: int,
    res_y: int,
    fps: int,
) -> list[str]:
    # We use the project startup hook `Content/Python/init_unreal.py` (guarded
    # by -VirtuCastAutoRender=1) to run the render script while the editor main
    # loop continues ticking.
    return [
        str(ue_editor),
        str(uproject),
        "-VirtuCastAutoRender=1",
        f"-VirtuCastScript={_to_unreal_cmd_path(ue_python_script)}",
        f"-VirtuCastMap={map_ref}",
        f"-VirtuCastSequence={sequence_ref}",
        f"-VirtuCastOut={_to_unreal_cmd_path(out_dir)}",
        f"-VirtuCastRes={res_x}x{res_y}",
        f"-VirtuCastFps={int(fps)}",
        "-unattended",
        "-nop4",
        "-nosplash",
        "-NoSound",
        "-log",
    ]


def _extract_object_path(soft_ref: str) -> str:
    """Convert /Script/X.Y'/Game/Path.Asset' -> /Game/Path.Asset"""
    m = re.search(r"'(/Game/[^']+)'", soft_ref)
    if not m:
        return soft_ref.strip().strip('"')
    return m.group(1)


def _extract_package_path(obj_path: str) -> str:
    """Convert /Game/Maps/Test1.Test1 -> /Game/Maps/Test1"""
    if "." in obj_path:
        return obj_path.split(".", 1)[0]
    return obj_path


def _parse_resolution(resolution: str) -> tuple[int, int]:
    m = re.match(r"^(\d+)x(\d+)$", resolution.strip())
    if not m:
        return 1920, 1080
    return int(m.group(1)), int(m.group(2))


def _default_render_script(repo_root: Path) -> Path:
    return (repo_root / "ue_project" / "VirtuCast" / "Scripts" / "virtu_render_queue.py").resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="VirtuCast: launch UE and render sequence via MRQ")
    parser.add_argument(
        "--config",
        default="config/default_config.yaml",
        help="Path to YAML config (default: config/default_config.yaml)",
    )
    parser.add_argument(
        "--mode",
        choices=["script", "cli"],
        default=None,
        help="Render mode: script (flexible; init_unreal.py auto-run) or cli (MRQ CLI) (default: from config or script)",
    )
    parser.add_argument(
        "--ue-script",
        default=None,
        help="Path to UE Python render script (default: config.ue5.render_script or ue_project/VirtuCast/Scripts/virtu_render_queue.py)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Override output directory (default: config.output.directory)",
    )
    parser.add_argument(
        "--resolution",
        default=None,
        help='Override resolution like "1920x1080" (default: config.camera.resolution)',
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=None,
        help="Override fps (default: config.camera.fps)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the Unreal command line and exit without launching UE",
    )
    args = parser.parse_args()

    repo_root = _repo_root()
    cfg_path = _resolve_path(repo_root, args.config)
    cfg = _load_yaml(cfg_path)

    ue5 = cfg.get("ue5", {})
    camera = cfg.get("camera", {})
    output = cfg.get("output", {})

    editor_path = ue5.get("editor_path")
    project_path = ue5.get("project_path")
    map_asset = ue5.get("map_asset")
    sequence_asset = ue5.get("sequence_asset")
    mrq_config_asset = ue5.get("mrq_config_asset")
    cfg_render_mode = ue5.get("render_mode")
    cfg_render_script = ue5.get("render_script")

    if not editor_path or not project_path:
        raise SystemExit("Missing ue5.editor_path or ue5.project_path in config")
    if not map_asset or not sequence_asset:
        raise SystemExit("Missing ue5.map_asset or ue5.sequence_asset in config")

    # Decide render mode.
    render_mode = args.mode or (str(cfg_render_mode).strip().lower() if cfg_render_mode else None) or "script"
    if render_mode not in {"script", "cli"}:
        raise SystemExit(f"Invalid render mode: {render_mode}. Use --mode script|cli")

    if render_mode == "cli" and not mrq_config_asset:
        raise SystemExit(
            "Missing ue5.mrq_config_asset in config (required for --mode cli). Create a Movie Render Pipeline Primary "
            "Config preset asset in UE (Movie Render Queue -> Presets -> Save As Asset) and set its /Game/... reference."
        )

    ue_editor = _resolve_path(repo_root, str(editor_path))
    uproject = _resolve_path(repo_root, str(project_path))

    if not ue_editor.exists():
        raise SystemExit(f"UnrealEditor.exe not found: {ue_editor}")
    if not uproject.exists():
        raise SystemExit(f".uproject not found: {uproject}")

    if args.resolution:
        resolution = args.resolution
    else:
        res = camera.get("resolution", {})
        resolution = f"{res.get('width', 1920)}x{res.get('height', 1080)}"

    res_x, res_y = _parse_resolution(resolution)

    if args.fps is not None:
        fps = int(args.fps)
    else:
        fps = int(camera.get("fps", 30) or 30)

    map_object = _extract_object_path(str(map_asset))
    map_package = _extract_package_path(map_object)
    sequence_object = _extract_object_path(str(sequence_asset))

    out_dir_cfg = args.output_dir or output.get("directory") or "output/"
    out_dir_path = _resolve_path(repo_root, str(out_dir_cfg))

    if render_mode == "script":
        ue_script_cfg = args.ue_script or cfg_render_script
        ue_script_path = _resolve_path(repo_root, str(ue_script_cfg)) if ue_script_cfg else _default_render_script(repo_root)
        if not ue_script_path.exists():
            raise SystemExit(f"UE Python script not found: {ue_script_path}")

        cmd = _build_execute_python_args(
            ue_editor=ue_editor,
            uproject=uproject,
            ue_python_script=ue_script_path,
            map_ref=str(map_asset),
            sequence_ref=str(sequence_asset),
            out_dir=out_dir_path,
            res_x=res_x,
            res_y=res_y,
            fps=fps,
        )

        print("[VirtuCast] Launching Unreal Editor (script mode, init_unreal.py auto-run)…")
        print("[VirtuCast] UE script:", ue_script_path)
        print("[VirtuCast] Output:", out_dir_path)
    else:
        mrq_config_object = _extract_object_path(str(mrq_config_asset))
        cmd = _build_args(
            ue_editor=ue_editor,
            uproject=uproject,
            map_package=map_package,
            sequence_object=sequence_object,
            mrq_config_object=mrq_config_object,
            res_x=res_x,
            res_y=res_y,
        )

        print("[VirtuCast] Launching Unreal Editor (cli mode, MRQ CLI)…")
        print("[VirtuCast] Output (expected):", out_dir_path)
        print("[VirtuCast] NOTE: CLI output directory is controlled by the MRQ preset asset (ue5.mrq_config_asset).")

    if args.dry_run:
        print("[VirtuCast] Dry-run. Command:")
        print(" ".join(cmd))
        return 0

    env = os.environ.copy()
    # Helps avoid ANSI-related weirdness in some terminals.
    env.setdefault("PYTHONIOENCODING", "utf-8")

    completed = subprocess.run(cmd, cwd=str(repo_root), env=env)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
