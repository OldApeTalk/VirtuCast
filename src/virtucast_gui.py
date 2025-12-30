"""VirtuCast GUI (MVP)

Requested UX:
- VS Code-like app shell.
- Menu bar: File -> New Project (create a workspace root directory).
- Main view shows current render-related info (key fields from YAML).

Run:
    python src/virtucast_gui.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tkinter import filedialog

import yaml

try:
    import ttkbootstrap as tb  # type: ignore[import-not-found]
    from ttkbootstrap.dialogs import Messagebox, Querybox  # type: ignore[import-not-found]
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "Missing optional UI dependency 'ttkbootstrap'. Install it with: pip install ttkbootstrap\n"
        f"Original import error: {exc}"
    )


MARKER_FILENAME = ".virtucast_workspace.json"
DEFAULT_WORKSPACE_CONFIG_NAME = "virtucast.yaml"


@dataclass(frozen=True)
class WorkspaceSpec:
    path: Path
    config_path: Path

    def marker_path(self) -> Path:
        return self.path / MARKER_FILENAME


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=False)


def _write_marker(spec: WorkspaceSpec) -> None:
    payload = {
        "schema": "virtucast.workspace.v1",
        "created_at": _now_iso_utc(),
        "workspace_root": str(spec.path),
        "config_path": str(spec.config_path),
    }
    spec.marker_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _sanitize_project_name(name: str) -> str:
    name = name.strip()
    if not name:
        return ""
    # Keep it simple: reject path separators and reserved characters.
    forbidden = set('\\/:*?"<>|')
    if any(ch in forbidden for ch in name):
        return ""
    return name


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _default_repo_config_path() -> Path:
    return (_repo_root() / "config" / "default_config.yaml").resolve()


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _dump_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _set_nested(data: dict[str, Any], keys: list[str], value: Any) -> None:
    cur: dict[str, Any] = data
    for k in keys[:-1]:
        nxt = cur.get(k)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[k] = nxt
        cur = nxt
    cur[keys[-1]] = value


def _get_nested(data: dict[str, Any], keys: list[str]) -> Any:
    cur: Any = data
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _normalize_ws_path(p: Path) -> str:
    return str(p).replace("\\", "/")


def _python_exe() -> str:
    return sys.executable


def _ue_render_entry() -> Path:
    return (_repo_root() / "src" / "ue_render.py").resolve()


def _extract_key_render_fields(cfg: dict[str, Any]) -> list[tuple[str, str]]:
    fields: list[tuple[str, list[str]]] = [
        ("ue5.editor_path", ["ue5", "editor_path"]),
        ("ue5.project_path", ["ue5", "project_path"]),
        ("ue5.render_mode", ["ue5", "render_mode"]),
        ("ue5.render_script", ["ue5", "render_script"]),
        ("ue5.map_asset", ["ue5", "map_asset"]),
        ("ue5.sequence_asset", ["ue5", "sequence_asset"]),
        ("output.directory", ["output", "directory"]),
        ("camera.resolution", ["camera", "resolution"]),
        ("camera.fps", ["camera", "fps"]),
    ]

    rows: list[tuple[str, str]] = []
    for label, path in fields:
        v = _get_nested(cfg, path)
        if isinstance(v, dict) and label == "camera.resolution":
            w = v.get("width")
            h = v.get("height")
            rows.append((label, f"{w}x{h}" if w and h else json.dumps(v, ensure_ascii=False)))
        elif v is None:
            rows.append((label, ""))
        else:
            rows.append((label, str(v)))
    return rows


class VirtuCastGUI(tb.Window):
    def __init__(self) -> None:
        super().__init__(themename="darkly")
        self.title("VirtuCast")
        self.geometry("980x620")
        self.minsize(860, 520)

        self.current_workspace: WorkspaceSpec | None = None
        self.current_config_path: Path | None = None
        self.current_config: dict[str, Any] = {}
        self.status_var = tb.StringVar(value="")
        self._render_thread: threading.Thread | None = None

        self._build_menu()
        self._build_layout()
        self._set_project_loaded(False)

    def _build_menu(self) -> None:
        menubar = tb.Menu(self)

        file_menu = tb.Menu(menubar, tearoff=False)
        file_menu.add_command(label="New Project…", command=self._menu_new_project)
        file_menu.add_command(label="Open Project…", command=self._menu_open_project)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        self.config(menu=menubar)

    def _build_layout(self) -> None:
        root = tb.Frame(self)
        root.pack(fill="both", expand=True)

        # Blank state: no project loaded
        self.blank = tb.Frame(root)
        self.blank.pack(fill="both", expand=True)

        # Loaded state: show workspace/config/render controls
        self.loaded = tb.Frame(root)

        paned = tb.Panedwindow(self.loaded, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = tb.Frame(paned, padding=12)
        paned.add(left, weight=1)

        tb.Label(left, text="Workspace", font=("", 12, "bold")).pack(anchor="w")
        self.workspace_path_var = tb.StringVar(value="")
        tb.Label(left, textvariable=self.workspace_path_var, wraplength=260).pack(anchor="w", pady=(6, 0))

        tb.Separator(left).pack(fill="x", pady=12)

        tb.Label(left, text="Config", font=("", 12, "bold")).pack(anchor="w")
        self.config_path_var = tb.StringVar(value="")
        tb.Label(left, textvariable=self.config_path_var, wraplength=260).pack(anchor="w", pady=(6, 0))

        tb.Separator(left).pack(fill="x", pady=12)

        self.btn_set_output = tb.Button(left, text="Set Output…", command=self._edit_output_dir, state="disabled")
        self.btn_set_output.pack(fill="x")
        self.btn_render = tb.Button(left, text="Render", bootstyle="success", command=self._render, state="disabled")
        self.btn_render.pack(fill="x", pady=(8, 0))

        right = tb.Frame(paned, padding=12)
        paned.add(right, weight=3)

        header = tb.Frame(right)
        header.pack(fill="x")
        tb.Label(header, text="Current Render Settings", font=("", 14, "bold")).pack(side="left")

        self.table = tb.Treeview(right, columns=("key", "value"), show="headings", height=18)
        self.table.heading("key", text="Key")
        self.table.heading("value", text="Value")
        self.table.column("key", width=260, stretch=False)
        self.table.column("value", width=660, stretch=True)
        self.table.pack(fill="both", expand=True, pady=(12, 0))

        # Status bar
        status = tb.Frame(root, padding=(10, 6))
        status.pack(fill="x")
        tb.Label(status, textvariable=self.status_var).pack(side="left")

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _set_project_loaded(self, loaded: bool) -> None:
        if loaded:
            self.blank.pack_forget()
            self.loaded.pack(fill="both", expand=True)
        else:
            self.loaded.pack_forget()
            self.blank.pack(fill="both", expand=True)
            self.workspace_path_var.set("")
            self.config_path_var.set("")
            self.current_config = {}
            for item in self.table.get_children() if hasattr(self, "table") else []:
                self.table.delete(item)
            if hasattr(self, "btn_set_output"):
                self.btn_set_output.configure(state="disabled")
            if hasattr(self, "btn_render"):
                self.btn_render.configure(state="disabled")
            self._set_status("")

    def _load_config(self, config_path: Path) -> None:
        if not config_path.exists():
            Messagebox.show_error(f"Config not found:\n{config_path}", title="VirtuCast")
            return

        self.current_config_path = config_path
        self.config_path_var.set(str(config_path))
        try:
            self.current_config = _load_yaml(config_path)
        except Exception as e:
            Messagebox.show_error(f"Failed to read YAML:\n{e}", title="VirtuCast")
            return

        self._refresh_table()
        self._set_status("Loaded config")
        self.btn_set_output.configure(state="normal")
        self.btn_render.configure(state="normal")

    def _refresh_table(self) -> None:
        for item in self.table.get_children():
            self.table.delete(item)

        for k, v in _extract_key_render_fields(self.current_config):
            self.table.insert("", "end", values=(k, v))

    def _menu_open_project(self) -> None:
        folder = filedialog.askdirectory(title="Open project folder")
        if not folder:
            return

        root = Path(folder).resolve()
        config_path = (root / DEFAULT_WORKSPACE_CONFIG_NAME).resolve()
        if not config_path.exists():
            Messagebox.show_error(
                f"Not a VirtuCast project (missing {DEFAULT_WORKSPACE_CONFIG_NAME}):\n{root}",
                title="VirtuCast",
            )
            return

        self.current_workspace = WorkspaceSpec(path=root, config_path=config_path)
        self.workspace_path_var.set(str(root))
        self._set_project_loaded(True)
        self._load_config(config_path)

    def _menu_new_project(self) -> None:
        parent_dir = filedialog.askdirectory(title="Choose parent directory")
        if not parent_dir:
            return

        name = Querybox.get_string(
            title="New Project",
            prompt="Project name (this will be the workspace root folder name):",
            parent=self,
        )
        if name is None:
            return

        project_name = _sanitize_project_name(name)
        if not project_name:
            Messagebox.show_error(
                "Invalid project name. Avoid characters: \\ / : * ? \" < > |",
                title="VirtuCast",
            )
            return

        workspace_root = (Path(parent_dir) / project_name).resolve()
        workspace_config = (workspace_root / DEFAULT_WORKSPACE_CONFIG_NAME).resolve()

        try:
            _safe_mkdir(workspace_root)
        except FileExistsError:
            Messagebox.show_error(f"Folder already exists:\n{workspace_root}", title="VirtuCast")
            return
        except Exception as e:
            Messagebox.show_error(str(e), title="VirtuCast")
            return

        # Create per-project config by copying the repo default config into the project.
        try:
            base_cfg = _load_yaml(_default_repo_config_path())
            # Default output directory is inside the project root; user can change later.
            _set_nested(base_cfg, ["output", "directory"], _normalize_ws_path(workspace_root / "output"))
            _dump_yaml(workspace_config, base_cfg)

            spec = WorkspaceSpec(path=workspace_root, config_path=workspace_config)
            _write_marker(spec)
        except Exception as e:
            Messagebox.show_error(f"Failed to initialize project:\n{e}", title="VirtuCast")
            return

        self.current_workspace = WorkspaceSpec(path=workspace_root, config_path=workspace_config)
        self.workspace_path_var.set(str(workspace_root))
        self._set_project_loaded(True)
        self._load_config(workspace_config)
        self._set_status(f"Created project: {workspace_root}")


    def _edit_output_dir(self) -> None:
        if not self.current_config_path:
            return
        chosen = filedialog.askdirectory(title="Choose output directory")
        if not chosen:
            return

        out_dir = _normalize_ws_path(Path(chosen).resolve())
        try:
            cfg = dict(self.current_config)
            _set_nested(cfg, ["output", "directory"], out_dir)
            _dump_yaml(self.current_config_path, cfg)
            self.current_config = cfg
        except Exception as e:
            Messagebox.show_error(f"Failed to update config:\n{e}", title="VirtuCast")
            return

        self._refresh_table()
        self._set_status("Updated output directory")

    def _render(self) -> None:
        if not self.current_config_path:
            return
        if self._render_thread and self._render_thread.is_alive():
            Messagebox.show_info("Render is already running.", title="VirtuCast")
            return

        cfg_path = self.current_config_path
        self.btn_render.configure(state="disabled")
        self._set_status("Rendering…")

        def _run() -> None:
            try:
                cmd = [
                    _python_exe(),
                    str(_ue_render_entry()),
                    "--config",
                    str(cfg_path),
                ]
                subprocess.run(cmd, cwd=str(_repo_root()))
            finally:
                self.after(0, lambda: self.btn_render.configure(state="normal"))
                self.after(0, lambda: self._set_status("Render finished"))

        self._render_thread = threading.Thread(target=_run, daemon=True)
        self._render_thread.start()


def main() -> None:
    try:
        os.chdir(_repo_root())
    except Exception:
        pass

    app = VirtuCastGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
