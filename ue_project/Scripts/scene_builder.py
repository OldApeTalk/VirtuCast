"""
UE5 Scene Builder
Automates creation of virtual news studio environments
"""

import math
import os
from typing import Any

try:
    import unreal
except ImportError:
    print("Warning: This script must be run within Unreal Engine Python environment")
    unreal = None


_STUDIO_TAG = "VirtuCastStudio"


def _v(x: float, y: float, z: float):
    return unreal.Vector(x, y, z)


def _r(pitch: float, yaw: float, roll: float):
    return unreal.Rotator(pitch, yaw, roll)


def _load_asset_best_effort(object_path: str):
    # Accepts either /Package/Asset or /Package/Asset.Asset
    try:
        asset = unreal.load_asset(object_path)
        if asset:
            return asset
    except Exception:
        pass

    try:
        return unreal.load_object(None, object_path)
    except Exception:
        return None


def _mat(path: str) -> object | None:
    return _load_asset_best_effort(path)


def _first_existing(paths: list[str]) -> str | None:
    for p in paths:
        if _load_asset_best_effort(p):
            return p
    return None


def _make_mid(parent_mat, outer, color: Any | None = None, roughness: float | None = None, metallic: float | None = None) -> object | None:
    if not parent_mat:
        return None
    try:
        mid = unreal.MaterialInstanceDynamic.create(parent_mat, outer)
    except Exception:
        return None

    if color is not None:
        # Best-effort: common parameter names across template materials.
        for param in ("Color", "BaseColor", "Tint", "Albedo"):
            try:
                mid.set_vector_parameter_value(param, color)
                break
            except Exception:
                continue
    
    # Set physical material parameters for wood-like appearance
    if roughness is not None:
        for param in ("Roughness", "roughness"):
            try:
                mid.set_scalar_parameter_value(param, roughness)
                break
            except Exception:
                continue
    
    if metallic is not None:
        for param in ("Metallic", "metallic"):
            try:
                mid.set_scalar_parameter_value(param, metallic)
                break
            except Exception:
                continue
    
    return mid


def _apply_material(actor, slot: int, parent_paths: list[str], color: Any | None = None, roughness: float | None = None, metallic: float | None = None) -> None:
    """Apply a material to the actor's static mesh component.

    Tries a list of possible parent material paths (project-first, then engine).
    If possible, uses a dynamic instance and sets a color parameter.
    """
    parent_path = _first_existing(parent_paths)
    if not parent_path:
        return
    parent = _mat(parent_path)
    if not parent:
        return

    try:
        smc = actor.static_mesh_component
    except Exception:
        smc = None
    if not smc:
        return

    mid = _make_mid(parent, smc, color=color, roughness=roughness, metallic=metallic)
    try:
        smc.set_material(slot, mid or parent)
    except Exception:
        pass


def _engine_basicshape(name: str) -> str:
    # UE commonly exposes basic shapes under /Engine/BasicShapes
    # Use the fully qualified object path for best compatibility.
    return f"/Engine/BasicShapes/{name}.{name}"


def _try_set(obj, prop: str, value) -> None:
    try:
        obj.set_editor_property(prop, value)
    except Exception:
        try:
            setattr(obj, prop, value)
        except Exception:
            pass


def _tag_actor(actor) -> None:
    try:
        tags = list(getattr(actor, "tags", []) or [])
        if _STUDIO_TAG not in [str(t) for t in tags]:
            tags.append(_STUDIO_TAG)
        actor.tags = tags
    except Exception:
        pass


def _yaw_towards(src, dst) -> float:
    # Yaw is rotation around Z axis in UE.
    dx = float(dst.x) - float(src.x)
    dy = float(dst.y) - float(src.y)
    return math.degrees(math.atan2(dy, dx))


def _label_actor(actor, label: str) -> None:
    for fn in ("set_actor_label", "set_editor_property"):
        try:
            if fn == "set_actor_label":
                actor.set_actor_label(label)
                return
        except Exception:
            continue
    try:
        actor.set_editor_property("actor_label", label)
    except Exception:
        pass


def _project_content_dir() -> str:
    try:
        return str(unreal.Paths.project_content_dir())
    except Exception:
        return ""


def _ensure_asset_dir(package_path: str) -> None:
    try:
        if unreal.EditorAssetLibrary.does_directory_exist(package_path):
            return
        unreal.EditorAssetLibrary.make_directory(package_path)
    except Exception:
        pass


def _load_or_create_asset(asset_name: str, package_path: str, asset_class, factory) -> object | None:
    asset_path = f"{package_path}/{asset_name}"
    if not asset_path.startswith("/"):
        asset_path = "/" + asset_path
    if not asset_path.startswith("/Game/"):
        # Expecting /Game/...
        pass

    try:
        if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
            return unreal.load_asset(asset_path)
    except Exception:
        pass

    try:
        tools = unreal.AssetToolsHelpers.get_asset_tools()
        return tools.create_asset(asset_name, package_path, asset_class, factory)
    except Exception as exc:
        unreal.log_warning(f"[SceneBuilder] Failed to create asset {asset_path}: {exc}")
        return None


def _build_screen_video_material(material_name: str, package_path: str, media_texture) -> object | None:
    """Create/reuse a simple unlit material that outputs the MediaTexture to Emissive."""
    _ensure_asset_dir(package_path)
    material = _load_or_create_asset(
        material_name,
        package_path,
        unreal.Material,
        unreal.MaterialFactoryNew(),
    )
    if not material:
        return None

    # Best-effort set to unlit
    try:
        material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    except Exception:
        pass

    # Clear graph and rebuild
    try:
        for expr in unreal.MaterialEditingLibrary.get_material_expressions(material) or []:
            unreal.MaterialEditingLibrary.delete_material_expression(material, expr)
    except Exception:
        pass

    try:
        tex_node = unreal.MaterialEditingLibrary.create_material_expression(
            material,
            unreal.MaterialExpressionTextureSample,
            -400,
            0,
        )
        _try_set(tex_node, "texture", media_texture)
        # Hook RGB to EmissiveColor for an emissive screen.
        unreal.MaterialEditingLibrary.connect_material_property(
            tex_node,
            "RGB",
            unreal.MaterialProperty.MP_EMISSIVE_COLOR,
        )
    except Exception as exc:
        unreal.log_warning(f"[SceneBuilder] Failed to build material graph: {exc}")

    try:
        unreal.MaterialEditingLibrary.recompile_material(material)
    except Exception:
        pass

    try:
        unreal.EditorAssetLibrary.save_asset(material.get_path_name())
    except Exception:
        pass

    return material


def _find_actor_by_label(label: str) -> object | None:
    try:
        actors = unreal.EditorLevelLibrary.get_all_level_actors() or []
    except Exception:
        actors = []
    for a in actors:
        try:
            if a.get_actor_label() == label:
                return a
        except Exception:
            continue
    return None


def apply_screen_video(video_path: str | None = None, autoplay: bool = True, loop: bool = True) -> None:
    """Apply a local video file to the generated VC_Screen actor.

    This creates/reuses Media Framework assets under /Game/VirtuCast/Media:
    - VC_ScreenMediaSource (FileMediaSource)
    - VC_ScreenMediaPlayer (MediaPlayer)
    - VC_ScreenMediaTexture (MediaTexture)
    - M_VC_ScreenVideo (Material)

    Default video path: <Project>/Content/Movies/screen.mp4
    """
    if not unreal:
        return

    if not video_path:
        content_dir = _project_content_dir()
        video_path = os.path.join(content_dir, "Movies", "screen.mp4")

    video_path = os.path.normpath(video_path)
    if not os.path.exists(video_path):
        unreal.log_error(f"[SceneBuilder] Video not found: {video_path}")
        unreal.log("[SceneBuilder] Put a file at Content/Movies/screen.mp4 or pass an explicit path.")
        return

    package_path = "/Game/VirtuCast/Media"
    _ensure_asset_dir(package_path)

    media_source = _load_or_create_asset(
        "VC_ScreenMediaSource",
        package_path,
        unreal.FileMediaSource,
        unreal.FileMediaSourceFactoryNew(),
    )
    media_player = _load_or_create_asset(
        "VC_ScreenMediaPlayer",
        package_path,
        unreal.MediaPlayer,
        unreal.MediaPlayerFactoryNew(),
    )
    media_texture = _load_or_create_asset(
        "VC_ScreenMediaTexture",
        package_path,
        unreal.MediaTexture,
        unreal.MediaTextureFactoryNew(),
    )

    if not (media_source and media_player and media_texture):
        unreal.log_error("[SceneBuilder] Failed to create/load Media Framework assets")
        return

    # Point media source to the file
    _try_set(media_source, "file_path", video_path)
    try:
        unreal.EditorAssetLibrary.save_asset(media_source.get_path_name())
    except Exception:
        pass

    # Bind texture to player
    _try_set(media_texture, "media_player", media_player)
    try:
        unreal.EditorAssetLibrary.save_asset(media_texture.get_path_name())
    except Exception:
        pass

    material = _build_screen_video_material("M_VC_ScreenVideo", package_path, media_texture)
    if not material:
        unreal.log_error("[SceneBuilder] Failed to create screen video material")
        return

    # Apply to VC_Screen
    screen_actor = _find_actor_by_label("VC_Screen")
    if not screen_actor:
        unreal.log_error("[SceneBuilder] VC_Screen actor not found. Run create_news_studio first.")
        return

    smc = None
    try:
        smc = screen_actor.static_mesh_component
    except Exception:
        pass
    if not smc:
        unreal.log_error("[SceneBuilder] VC_Screen has no static mesh component")
        return

    try:
        smc.set_material(0, material)
    except Exception as exc:
        unreal.log_warning(f"[SceneBuilder] Failed to set material on screen: {exc}")

    # Start playback
    try:
        if hasattr(media_player, "set_looping"):
            media_player.set_looping(bool(loop))
        ok = media_player.open_source(media_source)
        unreal.log(f"[SceneBuilder] Media open_source={ok}")
        if autoplay:
            media_player.play()
    except Exception as exc:
        unreal.log_warning(f"[SceneBuilder] Failed to play media: {exc}")


class NewsStudioBuilder:
    """Automated news studio scene builder"""
    
    def __init__(self):
        if unreal:
            self.editor_util = unreal.EditorLevelLibrary()
            self.editor_asset_lib = unreal.EditorAssetLibrary()

    def _delete_previous(self) -> None:
        """Delete actors created by previous runs."""
        actors = []
        try:
            actors = unreal.EditorLevelLibrary.get_all_level_actors()
        except Exception:
            pass
        to_delete = []
        for a in actors or []:
            try:
                tags = getattr(a, "tags", []) or []
                if _STUDIO_TAG in [str(t) for t in tags]:
                    to_delete.append(a)
            except Exception:
                continue
        if to_delete:
            try:
                unreal.EditorLevelLibrary.destroy_actor(to_delete)
            except Exception:
                try:
                    unreal.EditorLevelLibrary.destroy_actor(to_delete[0])
                    for extra in to_delete[1:]:
                        unreal.EditorLevelLibrary.destroy_actor(extra)
                except Exception:
                    pass

    def _spawn_static_mesh(self, label: str, mesh_path: str, location, rotation, scale) -> object | None:
        mesh = _load_asset_best_effort(mesh_path)
        if not mesh:
            unreal.log_warning(f"[SceneBuilder] Missing mesh: {mesh_path}")
            return None

        try:
            actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.StaticMeshActor, location, rotation)
        except Exception:
            unreal.log_warning("[SceneBuilder] Failed to spawn StaticMeshActor")
            return None

        _label_actor(actor, label)
        _tag_actor(actor)

        try:
            smc = actor.static_mesh_component
        except Exception:
            smc = None
            try:
                smc = actor.get_component_by_class(unreal.StaticMeshComponent)
            except Exception:
                pass
        if smc:
            try:
                smc.set_static_mesh(mesh)
            except Exception:
                _try_set(smc, "static_mesh", mesh)
            try:
                smc.set_world_scale3d(scale)
            except Exception:
                _try_set(smc, "world_scale3d", scale)
        else:
            try:
                actor.set_actor_scale3d(scale)
            except Exception:
                pass

        return actor

    def _spawn_camera(self, label: str, location, rotation) -> object | None:
        cam_class = getattr(unreal, "CineCameraActor", None) or getattr(unreal, "CameraActor", None)
        if not cam_class:
            unreal.log_warning("[SceneBuilder] CineCameraActor not available")
            return None
        try:
            actor = unreal.EditorLevelLibrary.spawn_actor_from_class(cam_class, location, rotation)
        except Exception:
            unreal.log_warning("[SceneBuilder] Failed to spawn camera")
            return None
        _label_actor(actor, label)
        _tag_actor(actor)
        return actor

    def _spawn_light(self, label: str, preferred_classes: list[str], location, rotation) -> object | None:
        light_class = None
        for cls_name in preferred_classes:
            light_class = getattr(unreal, cls_name, None)
            if light_class:
                break
        if not light_class:
            unreal.log_warning(f"[SceneBuilder] Light classes missing: {preferred_classes}")
            return None
        try:
            actor = unreal.EditorLevelLibrary.spawn_actor_from_class(light_class, location, rotation)
        except Exception:
            unreal.log_warning(f"[SceneBuilder] Failed to spawn light: {preferred_classes[0]}")
            return None
        _label_actor(actor, label)
        _tag_actor(actor)
        return actor
    
    def create_basic_studio(self, studio_name: str = "NewsStudio_Default"):
        """
        Create a basic news studio setup
        
        Args:
            studio_name: Name for the studio level
        """
        if not unreal:
            print("Must run in UE5 environment")
            return
        
        print(f"[SceneBuilder] Creating studio: {studio_name}")

        # Minimal approach (no external assets required):
        # - Build on the currently loaded level
        # - Spawn only Engine basic shapes, lights, and cameras
        self._delete_previous()

        # Add basic components
        self._add_floor()
        self._add_desk()
        self._add_backdrop_and_screen()
        self._add_metahuman()
        self._add_lighting()
        self._add_cameras()
        
        print(f"[SceneBuilder] ✓ Studio created")
    
    def _add_floor(self):
        """Add floor plane (sized for real studio: 10m x 8m)"""
        print("[SceneBuilder] Adding floor...")

        actor = self._spawn_static_mesh(
            label="VC_Floor",
            mesh_path=_engine_basicshape("Plane"),
            location=_v(0, 0, 0),
            rotation=_r(0, 0, 0),
            scale=_v(100, 80, 1),  # 10m x 8m studio floor
        )
        if actor:
            _apply_material(
                actor,
                slot=0,
                parent_paths=[
                    "/Game/BungeeMan/Materials/Mat_BungeeMan_Rubber.Mat_BungeeMan_Rubber",
                    "/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial",
                    "/Engine/EngineMaterials/DefaultMaterial.DefaultMaterial",
                ],
                color=unreal.LinearColor(0.04, 0.05, 0.08, 1.0),
            )
    
    def _add_desk(self):
        """Add news desk (real dimensions: 180cm W x 80cm D x 75cm H)"""
        print("[SceneBuilder] Adding news desk...")

        # Real news desk: width 180cm, depth 80cm, height 75cm (standard desk height)
        # Position: X=80 (right of center), Y=180 (front area), Z=75 (top at waist level)
        desk_center = _v(80, 180, 37.5)  # Center of desk base

        # Desktop (2cm thick)
        top = self._spawn_static_mesh(
            label="VC_DeskTop",
            mesh_path=_engine_basicshape("Cube"),
            location=_v(80, 180, 75),  # Top surface at 75cm height
            rotation=_r(0, 0, 0),
            scale=_v(1.8, 0.8, 0.02),  # 180cm x 80cm x 2cm
        )
        
        # Desk base/cabinet (70cm tall)
        base = self._spawn_static_mesh(
            label="VC_DeskBase",
            mesh_path=_engine_basicshape("Cube"),
            location=_v(80, 180, 35),
            rotation=_r(0, 0, 0),
            scale=_v(1.6, 0.75, 0.7),  # 160cm x 75cm x 70cm
        )

        # Curved front panel (modern news desk style)
        front = self._spawn_static_mesh(
            label="VC_DeskFront",
            mesh_path=_engine_basicshape("Cylinder"),
            location=_v(80, 140, 35),  # Front edge
            rotation=_r(0, 90, 0),
            scale=_v(0.7, 0.75, 0.7),  # Curved accent
        )

        # Tablet prop (25cm x 18cm)
        tablet = self._spawn_static_mesh(
            label="VC_Desk_Tablet",
            mesh_path=_engine_basicshape("Cube"),
            location=_v(60, 165, 76),  # On desk surface
            rotation=_r(0, -15, 0),
            scale=_v(0.25, 0.18, 0.008),
        )

        # Apply wood-like material properties to desk parts
        # Wood has higher roughness (0.6-0.8) and no metallic (0.0)
        for actor, col, rough in (
            (top, unreal.LinearColor(0.42, 0.28, 0.18, 1.0), 0.7),    # Oak wood color
            (base, unreal.LinearColor(0.38, 0.25, 0.16, 1.0), 0.75),   # Walnut wood color
            (front, unreal.LinearColor(0.35, 0.23, 0.15, 1.0), 0.8),  # Dark wood accent
            (tablet, unreal.LinearColor(0.02, 0.02, 0.02, 1.0), 0.2),  # Glossy tablet
        ):
            if actor:
                _apply_material(
                    actor,
                    slot=0,
                    parent_paths=[
                        "/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial",
                        "/Engine/EngineMaterials/DefaultMaterial.DefaultMaterial",
                    ],
                    color=col,
                    roughness=rough,
                    metallic=0.0 if actor != tablet else 0.1,
                )
    
    def _add_lighting(self):
        """Setup studio lighting (3-point lighting for 170cm subject)"""
        print("[SceneBuilder] Setting up lighting...")

        # 3-point lighting positioned for MetaHuman at (100, 210, 0) + 160cm height
        # Key light: front-left, 45° angle, height ~220cm
        key = self._spawn_light(
            label="VC_KeyLight",
            preferred_classes=["RectLight", "SpotLight", "PointLight"],
            location=_v(-100, 80, 220),  # Front-left of subject
            rotation=_r(-30, 25, 0),
        )
        # Fill light: front-right, softer, height ~200cm
        fill = self._spawn_light(
            label="VC_FillLight",
            preferred_classes=["RectLight", "SpotLight", "PointLight"],
            location=_v(-80, 320, 200),  # Front-right
            rotation=_r(-25, -15, 0),
        )
        # Rim/back light: behind subject, height ~200cm
        rim = self._spawn_light(
            label="VC_RimLight",
            preferred_classes=["SpotLight", "PointLight"],
            location=_v(180, 320, 200),  # Behind and above
            rotation=_r(-20, -120, 0),
        )

        # Best-effort tuning (property names vary by class/version).
        for actor, intensity in ((key, 5500.0), (fill, 2400.0), (rim, 1600.0)):
            if not actor:
                continue
            _try_set(actor, "intensity", intensity)
            _try_set(actor, "use_temperature", True)
            _try_set(actor, "temperature", 5200.0)
    
    def _add_metahuman(self):
        """Spawn MetaHuman anchor behind the desk"""
        print("[SceneBuilder] Adding MetaHuman anchor...")
        
        # MetaHuman BP path (user specified: /Game/MetaHumans/Vivian)
        bp_path = "/Game/MetaHumans/Vivian/BP_Vivian.BP_Vivian"
        bp_asset = _load_asset_best_effort(bp_path)
        
        if not bp_asset:
            unreal.log_warning(f"[SceneBuilder] MetaHuman BP not found: {bp_path}")
            return
        
        # Get the generated class from Blueprint
        try:
            bp_class = bp_asset.generated_class()
        except Exception as e:
            unreal.log_error(f"[SceneBuilder] Failed to get generated class: {e}")
            return
        
        if not bp_class:
            unreal.log_error("[SceneBuilder] Blueprint has no generated class")
            return
        
        # Position: behind desk, standing position (MetaHuman height ~170cm)
        # Desk center at (80, 180), put anchor slightly right at Y=200 (behind desk)
        # X=100 (right of center for classic news layout with screen on left)
        spawn_loc = _v(100, 200, 0)  # Z=0 feet on ground
        spawn_rot = _r(0, 0, 90)  # User manually corrected
        
        actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
            bp_class, spawn_loc, spawn_rot
        )
        
        if actor:
            _tag_actor(actor)
            actor.set_actor_label("VC_Anchor_Vivian")
            print(f"[SceneBuilder]   ✓ MetaHuman spawned at {spawn_loc}")
        else:
            unreal.log_error("[SceneBuilder] Failed to spawn MetaHuman")
    
    def _add_cameras(self):
        """Add camera actors"""
        print("[SceneBuilder] Adding cameras...")

        # Composition goal: Classic news layout
        # - Anchor on right side (~40% of frame)
        # - Screen visible on left in background (~25% of frame)
        # - Camera positioned front-left to frame both anchor and screen

        # Camera positions: front of studio, slightly left to see both elements
        # Wide shot: full scene (anchor + screen + desk)
        wide_pos = _v(-550, -100, 155)  # Front left, eye level
        # Medium shot: upper body + screen visible
        med_pos = _v(-420, -50, 150)    # Closer, slight left
        # Close shot: head and shoulders
        close_pos = _v(-320, 0, 145)    # Close, more centered

        # Camera targets: aim between screen and anchor for balanced composition
        # Anchor at (100, 200, 0), head height ~160cm
        # Screen at (650, -250, 170)
        wide_tgt = _v(250, 0, 155)      # Between screen and anchor
        med_tgt = _v(150, 100, 150)     # Closer to anchor
        close_tgt = _v(100, 200, 150)   # Anchor face

        wide_yaw = _yaw_towards(wide_pos, wide_tgt)
        med_yaw = _yaw_towards(med_pos, med_tgt)
        close_yaw = _yaw_towards(close_pos, close_tgt)

        self._spawn_camera(
            label="VC_Cam_Wide",
            location=wide_pos,
            rotation=_r(-2, wide_yaw, 0),
        )
        self._spawn_camera(
            label="VC_Cam_Medium",
            location=med_pos,
            rotation=_r(-2, med_yaw, 0),
        )
        self._spawn_camera(
            label="VC_Cam_Close",
            location=close_pos,
            rotation=_r(-1, close_yaw, 0),
        )

    def _add_backdrop_and_screen(self):
        """Add a simple background wall and a 'screen' plane."""
        print("[SceneBuilder] Adding backdrop + screen...")

        # Flat backdrop wall (blue), plus a simple grid overlay to mimic studio panels.
        wall = self._spawn_static_mesh(
            label="VC_BackWall",
            mesh_path=_engine_basicshape("Cube"),
            location=_v(720, 0, 235),
            rotation=_r(0, 0, 0),
            scale=_v(0.15, 18.0, 5.2),
        )
        if wall:
            _apply_material(
                wall,
                slot=0,
                parent_paths=[
                    "/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial",
                    "/Engine/EngineMaterials/DefaultMaterial.DefaultMaterial",
                ],
                color=unreal.LinearColor(0.02, 0.07, 0.18, 1.0),
            )

        # Grid lines (thin cubes slightly in front of wall)
        grid_color = unreal.LinearColor(0.10, 0.18, 0.35, 1.0)
        grid_x = 705
        grid_z_center = 240
        grid_y_half = 900
        grid_z_half = 250

        # Vertical lines
        for i in range(-4, 5):
            y = i * 200
            bar = self._spawn_static_mesh(
                label=f"VC_BackGrid_V_{i:+d}",
                mesh_path=_engine_basicshape("Cube"),
                location=_v(grid_x, y, grid_z_center),
                rotation=_r(0, 0, 0),
                scale=_v(0.02, 0.05, 5.0),
            )
            if bar:
                _apply_material(
                    bar,
                    slot=0,
                    parent_paths=[
                        "/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial",
                        "/Engine/EngineMaterials/DefaultMaterial.DefaultMaterial",
                    ],
                    color=grid_color,
                )

        # Horizontal lines
        for i in range(-2, 4):
            z = grid_z_center + i * 120
            bar = self._spawn_static_mesh(
                label=f"VC_BackGrid_H_{i:+d}",
                mesh_path=_engine_basicshape("Cube"),
                location=_v(grid_x, 0, z),
                rotation=_r(0, 0, 0),
                scale=_v(0.02, 18.0, 0.05),
            )
            if bar:
                _apply_material(
                    bar,
                    slot=0,
                    parent_paths=[
                        "/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial",
                        "/Engine/EngineMaterials/DefaultMaterial.DefaultMaterial",
                    ],
                    color=grid_color,
                )

        # Studio screen: 16:9 ratio, 250cm W x 140cm H
        screen = self._spawn_static_mesh(
            label="VC_Screen",
            mesh_path=_engine_basicshape("Plane"),
            location=_v(650, -250, 170),  # Back wall, left side, eye level
            rotation=_r(90, 0, 90),  # Pitch 90° (Y-axis) + Roll 90° (X-axis)
            scale=_v(2.5, 1.4, 1.0),  # 250cm x 140cm
        )

        # Screen: gray neutral color (like a modern display panel)
        if screen:
            _apply_material(
                screen,
                slot=0,
                parent_paths=[
                    "/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial",
                    "/Engine/EngineMaterials/DefaultMaterial.DefaultMaterial",
                ],
                color=unreal.LinearColor(0.35, 0.35, 0.35, 1.0),  # Neutral gray
            )

            # Add simple "X" markers using thin cubes (purely visual).
            for idx, (sy, sz, s) in enumerate(((-250, 170, 1.0), (-375, 240, 0.45), (-125, 100, 0.45))):
                cross_a = self._spawn_static_mesh(
                    label=f"VC_Screen_XA_{idx}",
                    mesh_path=_engine_basicshape("Cube"),
                    location=_v(648, sy, sz),
                    rotation=_r(0, 90, 45),
                    scale=_v(0.02, 1.4 * s, 0.02),
                )
                cross_b = self._spawn_static_mesh(
                    label=f"VC_Screen_XB_{idx}",
                    mesh_path=_engine_basicshape("Cube"),
                    location=_v(648, sy, sz),
                    rotation=_r(0, 90, -45),
                    scale=_v(0.02, 1.4 * s, 0.02),
                )
                for a in (cross_a, cross_b):
                    if a:
                        _apply_material(
                            a,
                            slot=0,
                            parent_paths=[
                                "/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial",
                                "/Engine/EngineMaterials/DefaultMaterial.DefaultMaterial",
                            ],
                            color=unreal.LinearColor(0.72, 0.86, 0.72, 0.55),
                        )

    def _add_ceiling_rig(self):
        """Add a simple ceiling truss/rig so the set doesn't feel empty."""
        print("[SceneBuilder] Adding ceiling rig...")

        z = 460
        # Two cross beams
        beams = [
            self._spawn_static_mesh(
                label="VC_Rig_Beam_A",
                mesh_path=_engine_basicshape("Cube"),
                location=_v(-50, 0, z),
                rotation=_r(0, 0, 0),
                scale=_v(14.0, 0.12, 0.12),
            ),
            self._spawn_static_mesh(
                label="VC_Rig_Beam_B",
                mesh_path=_engine_basicshape("Cube"),
                location=_v(250, 0, z),
                rotation=_r(0, 0, 0),
                scale=_v(14.0, 0.12, 0.12),
            ),
            self._spawn_static_mesh(
                label="VC_Rig_Beam_C",
                mesh_path=_engine_basicshape("Cube"),
                location=_v(100, -350, z),
                rotation=_r(0, 90, 0),
                scale=_v(8.5, 0.12, 0.12),
            ),
            self._spawn_static_mesh(
                label="VC_Rig_Beam_D",
                mesh_path=_engine_basicshape("Cube"),
                location=_v(100, 350, z),
                rotation=_r(0, 90, 0),
                scale=_v(8.5, 0.12, 0.12),
            ),
        ]
        for b in beams:
            if b:
                _apply_material(
                    b,
                    slot=0,
                    parent_paths=[
                        "/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial",
                        "/Engine/EngineMaterials/DefaultMaterial.DefaultMaterial",
                    ],
                    color=unreal.LinearColor(0.03, 0.03, 0.035, 1.0),
                )

        # Simple "light panel" planes (visual only; real lights are separate)
        panels = [
            self._spawn_static_mesh(
                label="VC_LightPanel_Key",
                mesh_path=_engine_basicshape("Plane"),
                location=_v(40, -320, 430),
                rotation=_r(-55, 0, 0),
                scale=_v(2.8, 1.8, 1.0),
            ),
            self._spawn_static_mesh(
                label="VC_LightPanel_Fill",
                mesh_path=_engine_basicshape("Plane"),
                location=_v(40, 320, 420),
                rotation=_r(-50, 0, 0),
                scale=_v(2.6, 1.6, 1.0),
            ),
        ]
        for p in panels:
            if p:
                _apply_material(
                    p,
                    slot=0,
                    parent_paths=[
                        "/Engine/EngineMaterials/EmissiveMeshMaterial.EmissiveMeshMaterial",
                        "/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial",
                        "/Engine/EngineMaterials/DefaultMaterial.DefaultMaterial",
                    ],
                    color=unreal.LinearColor(0.35, 0.35, 0.33, 1.0),
                )
    
    def setup_metahuman(self, metahuman_name: str, position: tuple = (0, 0, 100)):
        """
        Place MetaHuman in scene
        
        Args:
            metahuman_name: Name of MetaHuman asset
            position: (X, Y, Z) position
        """
        print(f"[SceneBuilder] Placing MetaHuman: {metahuman_name}")
        # TODO: Spawn MetaHuman actor at position
        pass


# Utility functions for external calls
def create_news_studio(studio_name: str = "NewsStudio_Default"):
    """Create a news studio (callable from external Python)"""
    builder = NewsStudioBuilder()
    builder.create_basic_studio(studio_name)


if __name__ == "__main__":
    # Example usage when run in UE5
    create_news_studio()
