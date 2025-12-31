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
import importlib
from pathlib import Path

import unreal


_ALREADY_RAN = False
_MENU_REGISTERED = False
_LAST_SCREEN_VIDEO: str | None = None


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


def _saved_dir() -> Path:
    try:
        return Path(str(unreal.Paths.project_saved_dir())).resolve()
    except Exception:
        return (_project_dir() / "Saved").resolve()


def _last_video_path_file() -> Path:
    return (_saved_dir() / "VirtuCast" / "last_screen_video.txt").resolve()


def _load_last_video_path() -> str | None:
    p = _last_video_path_file()
    try:
        if not p.exists():
            return None
        val = p.read_text(encoding="utf-8").strip()
        if not val:
            return None
        if os.path.exists(val):
            return val
        return None
    except Exception:
        return None


def _save_last_video_path(path: str) -> None:
    p = _last_video_path_file()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(path, encoding="utf-8")
    except Exception:
        pass


def _scene_builder_path() -> Path:
    # Repo layout: ue_project/VirtuCast (project) and ue_project/Scripts (repo-level scripts)
    # project_dir() -> .../ue_project/VirtuCast/
    return (_project_dir().parent / "Scripts" / "scene_builder.py").resolve()


def _run_scene_builder(studio_name: str = "NewsStudio_Default") -> None:
    path = _scene_builder_path()
    if not path.exists():
        raise FileNotFoundError(f"Scene builder not found: {path}")

    unreal.log(f"[VirtuCast] Running scene builder: {_normalize_path(str(path))}")
    ns = runpy.run_path(str(path))
    fn = ns.get("create_news_studio")
    if not callable(fn):
        raise RuntimeError("scene_builder.py does not define create_news_studio")
    fn(studio_name)


def _apply_screen_video_default() -> None:
    path = _scene_builder_path()
    if not path.exists():
        raise FileNotFoundError(f"Scene builder not found: {path}")

    ns = runpy.run_path(str(path))
    fn = ns.get("apply_screen_video")
    if not callable(fn):
        raise RuntimeError("scene_builder.py does not define apply_screen_video")

    global _LAST_SCREEN_VIDEO
    if _LAST_SCREEN_VIDEO is None:
        _LAST_SCREEN_VIDEO = _load_last_video_path()

    # Priority: cached selection -> cmdline external -> default Content/Movies/screen.mp4
    external = _LAST_SCREEN_VIDEO
    if not external:
        cmdline = _get_cmdline()
        external = _get_arg(cmdline, "VirtuCastScreenVideo")

    fn(external, True, True)


def _open_video_file_dialog() -> str | None:
    """Open a native file dialog (best-effort across UE builds)."""
    title = "Select screen video"
    default_path = os.path.expanduser("~")
    default_file = ""
    file_types = "Video Files (*.mp4;*.mov;*.mkv;*.avi)|*.mp4;*.mov;*.mkv;*.avi|All Files (*.*)|*.*"

    parent = None
    try:
        eul = getattr(unreal, "EditorUtilityLibrary", None)
        if eul and hasattr(eul, "get_default_parent_window_handle"):
            parent = eul.get_default_parent_window_handle()
    except Exception:
        parent = None

    # Try DesktopPlatform (preferred)
    try:
        dp = getattr(unreal, "DesktopPlatform", None)
        if dp:
            unreal.log(f"[VirtuCast] Trying DesktopPlatform file dialog... (hasattr open_file_dialog: {hasattr(dp, 'open_file_dialog')})")
            if hasattr(dp, "open_file_dialog"):
                result = dp.open_file_dialog(parent, title, default_path, default_file, file_types, False)
            elif hasattr(dp, "get") and hasattr(dp.get(), "open_file_dialog"):
                result = dp.get().open_file_dialog(parent, title, default_path, default_file, file_types, False)
            else:
                result = None

            if result:
                if isinstance(result, tuple) and result:
                    files = result[0]
                else:
                    files = result
                if isinstance(files, (list, tuple)) and files:
                    unreal.log(f"[VirtuCast] File dialog OK: {files[0]}")
                    return str(files[0])
            unreal.log_warning("[VirtuCast] DesktopPlatform returned empty")
    except Exception as e:
        unreal.log_warning(f"[VirtuCast] DesktopPlatform failed: {e}")

    # Fallback: EditorDialog if present
    try:
        ed = getattr(unreal, "EditorDialog", None)
        if ed and hasattr(ed, "open_file_dialog"):
            unreal.log("[VirtuCast] Trying EditorDialog fallback...")
            result = ed.open_file_dialog(title, default_path, default_file, file_types)
            if isinstance(result, (list, tuple)) and result:
                unreal.log(f"[VirtuCast] EditorDialog OK: {result[0]}")
                return str(result[0])
    except Exception as e:
        unreal.log_warning(f"[VirtuCast] EditorDialog failed: {e}")

    # Final fallback: pure Python tkinter (cross-platform, no UE dependency)
    unreal.log("[VirtuCast] UE dialogs unavailable, trying tkinter file dialog...")
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        root = tk.Tk()
        root.withdraw()  # Hide main window
        root.attributes('-topmost', True)  # Bring to front
        
        file_path = filedialog.askopenfilename(
            title=title,
            initialdir=default_path,
            filetypes=[
                ("Video Files", "*.mp4 *.mov *.mkv *.avi"),
                ("All Files", "*.*")
            ]
        )
        root.destroy()
        
        if file_path:
            unreal.log(f"[VirtuCast] tkinter dialog OK: {file_path}")
            return str(file_path)
        unreal.log_warning("[VirtuCast] tkinter dialog cancelled")
    except Exception as e:
        unreal.log_error(f"[VirtuCast] tkinter fallback failed: {e}")
    
    return None


def _pick_and_apply_screen_video() -> None:
    """Pick a video file and apply it to VC_Screen, caching the choice."""
    global _LAST_SCREEN_VIDEO
    picked = _open_video_file_dialog()
    if not picked:
        unreal.log_error("[VirtuCast] No file selected. Check Output Log for details or use 'Apply Screen Video' with cached/cmdline path.")
        return
    _LAST_SCREEN_VIDEO = picked
    _save_last_video_path(picked)
    unreal.log(f"[VirtuCast] Applying selected video: {picked}")
    _apply_screen_video_default()


def _apply_manual_path() -> None:
    """Fallback: manually set video path via log instruction (no GUI input available in base UE Python)."""
    unreal.log_warning(
        "[VirtuCast] Manual path entry: \n"
        "1. Copy your video file path (e.g., D:/Videos/screen.mp4)\n"
        "2. In Python console, run:\n"
        "   import init_unreal\n"
        "   init_unreal._LAST_SCREEN_VIDEO = r'YOUR_PATH_HERE'\n"
        "   init_unreal._save_last_video_path(init_unreal._LAST_SCREEN_VIDEO)\n"
        "   init_unreal._apply_screen_video_default()\n"
        "Or edit <Project>/Saved/VirtuCast/last_screen_video.txt and use 'Apply Screen Video' menu."
    )


def _register_menu() -> None:
    """Register a simple Editor menu item so users can run VirtuCast tools without copy/paste."""
    global _MENU_REGISTERED
    if _MENU_REGISTERED:
        return

    try:
        tool_menus = unreal.ToolMenus.get()
    except Exception:
        return

    # Best-effort cleanup to avoid duplicate menu items on reload.
    try:
        if hasattr(tool_menus, "unregister_owner"):
            tool_menus.unregister_owner("VirtuCast")
    except Exception:
        pass
    try:
        if hasattr(tool_menus, "remove_menu"):
            tool_menus.remove_menu("LevelEditor.MainMenu.VirtuCast")
    except Exception:
        pass

    try:
        main_menu = tool_menus.extend_menu("LevelEditor.MainMenu")
        virtucast_menu = main_menu.add_sub_menu(
            owner="VirtuCast",
            section_name="VirtuCast",
            name="LevelEditor.MainMenu.VirtuCast",
            label="VirtuCast",
            tool_tip="VirtuCast tools",
        )

        # 1. Reload Tools
        entry_reload = unreal.ToolMenuEntry(
            name="VirtuCast.ReloadTools",
            type=unreal.MultiBlockType.MENU_ENTRY,
            insert_position=unreal.ToolMenuInsert("", unreal.ToolMenuInsertType.DEFAULT),
        )
        entry_reload.set_label("Reload VirtuCast Tools")
        entry_reload.set_tool_tip("Reload init_unreal.py and re-register VirtuCast menu (no editor restart)")
        entry_reload.set_string_command(
            unreal.ToolMenuStringCommandType.PYTHON,
            "",
            "import unreal\n"
            "import importlib\n"
            "import init_unreal\n"
            "try:\n"
            "    importlib.reload(init_unreal)\n"
            "    init_unreal._register_menu()\n"
            "    unreal.log('[VirtuCast] Tools reloaded')\n"
            "except Exception as e:\n"
            "    unreal.log_error(f'[VirtuCast] Reload failed: {e}')\n",
        )
        virtucast_menu.add_menu_entry("VirtuCast", entry_reload)

        # 2. Build News Studio
        entry_build = unreal.ToolMenuEntry(
            name="VirtuCast.BuildNewsStudio",
            type=unreal.MultiBlockType.MENU_ENTRY,
            insert_position=unreal.ToolMenuInsert("", unreal.ToolMenuInsertType.DEFAULT),
        )
        entry_build.set_label("Build News Studio")
        entry_build.set_tool_tip("Generate a basic news studio set (no external assets)")
        entry_build.set_string_command(
            unreal.ToolMenuStringCommandType.PYTHON,
            "",
            "import unreal\n"
            "from init_unreal import _run_scene_builder\n"
            "try:\n"
            "    _run_scene_builder('NewsStudio_Default')\n"
            "except Exception as e:\n"
            "    unreal.log_error(f'[VirtuCast] Build failed: {e}')\n",
        )
        virtucast_menu.add_menu_entry("VirtuCast", entry_build)

        # 3. Select External Screen Video
        entry_video = unreal.ToolMenuEntry(
            name="VirtuCast.SelectAndApplyScreenVideo",
            type=unreal.MultiBlockType.MENU_ENTRY,
            insert_position=unreal.ToolMenuInsert("", unreal.ToolMenuInsertType.DEFAULT),
        )
        entry_video.set_label("Select External Screen Video…")
        entry_video.set_tool_tip("Pick a video file from disk and play it on VC_Screen")
        entry_video.set_string_command(
            unreal.ToolMenuStringCommandType.PYTHON,
            "",
            "import unreal\n"
            "from init_unreal import _pick_and_apply_screen_video\n"
            "try:\n"
            "    _pick_and_apply_screen_video()\n"
            "except Exception as e:\n"
            "    unreal.log_error(f'[VirtuCast] Select/apply failed: {e}')\n",
        )
        virtucast_menu.add_menu_entry("VirtuCast", entry_video)

        tool_menus.refresh_all_widgets()
        _MENU_REGISTERED = True
        unreal.log("[VirtuCast] Menu registered: 3 items (Reload/Build/Select Video)")
    except Exception as exc:
        unreal.log_warning(f"[VirtuCast] Failed to register menu: {exc}")


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

    # Always register the menu (no side effects unless clicked).
    _register_menu()

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
