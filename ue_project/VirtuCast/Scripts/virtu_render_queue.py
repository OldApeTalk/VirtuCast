"""UE-side MRQ renderer for VirtuCast.

Executed inside Unreal Editor via -ExecutePythonScript.

Reads parameters from the editor command line:
- -VirtuCastMap=/Script/Engine.World'/Game/Maps/Test1.Test1'
- -VirtuCastSequence=/Script/LevelSequence.LevelSequence'/Game/Cinematics/Seq.Seq'
- -VirtuCastOut=D:/.../output
- -VirtuCastRes=1920x1080
- -VirtuCastFps=30

Renders a PNG sequence using Movie Render Queue, then quits the editor.
"""

from __future__ import annotations

import os
import re
import time

import unreal


# Keep strong references to UE objects/callbacks created by this script.
# Without this, Python GC may collect the executor/callbacks after `main()`
# returns, which can end PIE early and produce no output frames.
_KEEPALIVE: dict[str, object] = {}


def _get_cmdline() -> str:
    try:
        return unreal.SystemLibrary.get_command_line()
    except Exception:
        return ""


def _get_arg(cmdline: str, name: str) -> str | None:
    # Matches -Name=value or -Name="value"
    pattern = rf"(?:^|\s)-{re.escape(name)}=(?:\"([^\"]*)\"|([^\s]+))"
    m = re.search(pattern, cmdline)
    if not m:
        return None
    return m.group(1) or m.group(2)


def _extract_object_path(soft_ref: str) -> str:
    # Converts /Script/X.Y'/Game/Path.Asset' -> /Game/Path.Asset
    m = re.search(r"'(/Game/[^']+)'", soft_ref)
    if not m:
        # Already looks like /Game/...
        return soft_ref.strip().strip('"')
    return m.group(1)


def _extract_package_path(obj_path: str) -> str:
    # /Game/Maps/Test1.Test1 -> /Game/Maps/Test1
    if "." in obj_path:
        return obj_path.split(".", 1)[0]
    return obj_path


def _parse_resolution(res: str) -> tuple[int, int]:
    m = re.match(r"^(\d+)x(\d+)$", res.strip())
    if not m:
        return 1920, 1080
    return int(m.group(1)), int(m.group(2))


def _load_map(map_obj_path: str) -> None:
    pkg = _extract_package_path(map_obj_path)

    if hasattr(unreal, "EditorLoadingAndSavingUtils"):
        try:
            unreal.EditorLoadingAndSavingUtils.load_map(pkg)
            return
        except Exception:
            pass

    if hasattr(unreal, "EditorLevelLibrary"):
        try:
            unreal.EditorLevelLibrary.load_level(pkg)
            return
        except Exception:
            pass

    unreal.log_warning(f"[VirtuCast] Could not load map via API. Package: {pkg}")


def _ensure_png_output(job: unreal.MoviePipelineExecutorJob, out_dir: str, width: int, height: int, fps: int) -> None:
    config = job.get_configuration()

    output_setting = config.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)

    # Output directory: use explicit field assignment for best compatibility.
    try:
        output_setting.output_directory = unreal.DirectoryPath(path=out_dir)
    except Exception:
        output_setting.output_directory = unreal.DirectoryPath(out_dir)

    output_setting.output_resolution = unreal.IntPoint(width, height)
    output_setting.file_name_format = "{sequence_name}.{frame_number}"
    output_setting.override_existing_output = True

    # FPS override (API differs across UE versions)
    frame_rate = unreal.FrameRate(fps, 1)
    if hasattr(output_setting, "use_custom_frame_rate"):
        try:
            output_setting.use_custom_frame_rate = True
        except Exception:
            pass
    if hasattr(output_setting, "custom_frame_rate"):
        try:
            output_setting.custom_frame_rate = frame_rate
        except Exception:
            pass
    elif hasattr(output_setting, "output_frame_rate"):
        try:
            output_setting.output_frame_rate = frame_rate
        except Exception:
            pass

    # Ensure we actually have a render pass (otherwise MRQ may finish with no outputs).
    if hasattr(unreal, "MoviePipelineDeferredPassBase"):
        config.find_or_add_setting_by_class(unreal.MoviePipelineDeferredPassBase)
    elif hasattr(unreal, "MoviePipelineDeferredPass"):
        config.find_or_add_setting_by_class(unreal.MoviePipelineDeferredPass)

    # Force PNG sequence output
    config.find_or_add_setting_by_class(unreal.MoviePipelineImageSequenceOutput_PNG)

    try:
        unreal.log(f"[VirtuCast] MRQ output_directory.path={output_setting.output_directory.path}")
    except Exception:
        pass


def main() -> None:
    cmdline = _get_cmdline()

    map_ref = _get_arg(cmdline, "VirtuCastMap")
    seq_ref = _get_arg(cmdline, "VirtuCastSequence")
    out_dir = _get_arg(cmdline, "VirtuCastOut")
    res = _get_arg(cmdline, "VirtuCastRes") or "1920x1080"
    fps_str = _get_arg(cmdline, "VirtuCastFps") or "30"

    if not map_ref or not seq_ref or not out_dir:
        raise RuntimeError("Missing required args. Need -VirtuCastMap, -VirtuCastSequence, -VirtuCastOut")

    map_obj = _extract_object_path(map_ref)
    seq_obj = _extract_object_path(seq_ref)

    width, height = _parse_resolution(res)
    try:
        fps = int(fps_str)
    except ValueError:
        fps = 30

    os.makedirs(out_dir, exist_ok=True)

    unreal.log(f"[VirtuCast] Map: {map_obj}")
    unreal.log(f"[VirtuCast] Sequence: {seq_obj}")
    unreal.log(f"[VirtuCast] Output: {out_dir}")
    unreal.log(f"[VirtuCast] Res/FPS: {width}x{height} @ {fps}")

    _load_map(map_obj)

    queue_subsystem = unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem)
    queue = queue_subsystem.get_queue()
    queue.delete_all_jobs()

    job = queue.allocate_new_job(unreal.MoviePipelineExecutorJob)
    job.map = unreal.SoftObjectPath(map_obj)
    job.sequence = unreal.SoftObjectPath(seq_obj)

    _ensure_png_output(job, out_dir=out_dir, width=width, height=height, fps=fps)

    done = {"finished": False, "success": False}

    def _on_finished(executor_obj, success: bool):
        done["finished"] = True
        done["success"] = bool(success)
        unreal.log(f"[VirtuCast] MRQ finished. success={success}")

    # Prefer PIE executor for reliability when running from -ExecutePythonScript.
    # LocalExecutor can stall depending on headless/editor tick state.
    executor = unreal.MoviePipelinePIEExecutor()

    executor.on_executor_finished_delegate.add_callable_unique(_on_finished)

    # Keep refs alive for the lifetime of the editor session.
    _KEEPALIVE["queue_subsystem"] = queue_subsystem
    _KEEPALIVE["queue"] = queue
    _KEEPALIVE["job"] = job
    _KEEPALIVE["executor"] = executor
    _KEEPALIVE["on_finished"] = _on_finished

    unreal.log("[VirtuCast] Starting MRQ render…")
    queue_subsystem.render_queue_with_executor_instance(executor)

    # IMPORTANT:
    # Do NOT busy-wait in Python here.
    # Python execution runs on the editor/game thread; a blocking while-loop
    # can starve engine ticking and prevent MRQ from progressing.
    #
    # Instead, register a tick callback and return. The editor keeps running,
    # MRQ can tick normally, and we quit the editor when MRQ finishes.
    start_time = time.time()
    last_heartbeat = {"t": start_time}
    timeout_seconds = 60 * 60

    def _quit_editor():
        try:
            unreal.SystemLibrary.quit_editor()
            return
        except Exception:
            pass
        try:
            world = unreal.EditorLevelLibrary.get_editor_world()
            unreal.SystemLibrary.execute_console_command(world, "QUIT_EDITOR")
        except Exception:
            pass

    def _unregister_tick():
        handle = _KEEPALIVE.get("tick_handle")
        if handle is None:
            return
        try:
            if hasattr(unreal, "unregister_slate_post_tick_callback"):
                unreal.unregister_slate_post_tick_callback(handle)
        except Exception:
            pass

    def _tick_callback(*_args):
        now = time.time()

        if done["finished"]:
            unreal.log(f"[VirtuCast] Render complete (success={done['success']}); quitting editor.")
            _unregister_tick()
            _quit_editor()
            return

        if (now - start_time) > timeout_seconds:
            unreal.log_warning("[VirtuCast] Render timeout; quitting editor.")
            _unregister_tick()
            _quit_editor()
            return

        if (now - last_heartbeat["t"]) >= 10.0:
            elapsed = int(now - start_time)
            unreal.log(f"[VirtuCast] MRQ still running… elapsed={elapsed}s")
            last_heartbeat["t"] = now

    if not hasattr(unreal, "register_slate_post_tick_callback"):
        unreal.log_warning("[VirtuCast] Slate tick callback API not available; MRQ may stall under -ExecutePythonScript.")
        return

    unreal.log("[VirtuCast] Waiting for MRQ completion (tick callback)…")
    tick_handle = unreal.register_slate_post_tick_callback(_tick_callback)

    # Keep tick callback + handle alive.
    _KEEPALIVE["tick_handle"] = tick_handle
    _KEEPALIVE["tick_callback"] = _tick_callback


if __name__ == "__main__":
    main()
