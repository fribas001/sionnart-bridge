import bpy
import bmesh
import csv
import hashlib
import html
import importlib.util
import json
import math
import os
import re
import subprocess
import shutil
import sys
import traceback
import time
import tempfile
import statistics
import textwrap
import uuid
import webbrowser
import xml.etree.ElementTree as ET

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import Operator, Panel, PropertyGroup
from bpy.app.handlers import persistent
from mathutils import Matrix


_ADDON_VERSION = "1.8.1"

_ENV_COLLECTION = "sionna_env"
_SCENE_COLLECTION = "scene"
_PROCEDURAL_COLLECTION = "procedural_geometry"
_DEVICES_COLLECTION = "devices"
_TX_COLLECTION = "txs"
_RX_COLLECTION = "rxs"
_MOTION_TEMPLATES_COLLECTION = "motion_templates"
_DEVICE_REPRESENTATION_COLLECTION = "devices_representation"
_DEVICE_REPRESENTATION_TX_COLLECTION = "tx"
_DEVICE_REPRESENTATION_RX_COLLECTION = "rx"
_DEVICE_REPRESENTATION_MATERIALS = {
    "TX": ("Sionna_Device_TX_Representation", (1.0, 0.02, 0.02, 1.0)),
    "RX": ("Sionna_Device_RX_Representation", (0.02, 0.12, 1.0, 1.0)),
}
_DEVICE_REPRESENTATION_SPHERE_MESH = "Sionna_Device_Representation_UVSphere"
_DEVICE_REPRESENTATION_ARROW_MESH = "Sionna_Device_Representation_Arrow"
_DEVICE_REPRESENTATION_TAG = "sionna_device_representation"
_DEVICE_ID_PROPERTY = "sionna_device_id"
_PATHS_COLLECTION = "simulated_paths"
_RADIO_MAPS_COLLECTION = "radio_maps"
_RADIO_MAPS_3D_COLLECTION = "radio_maps_3d"
_LEGACY_RESULT_COLLECTION = "Sionna Results"
_RESULT_COLLECTION = _PATHS_COLLECTION
_DEFAULT_GEOMETRY_NODES_GROUP = "Sionna_Paths"
_RADIO_MAP_MODE_DEFINITIONS = {
    "path_gain": {
        "label": "Path Gain",
        "name_token": "PathGain",
        "node_group": "Sionna_radio_map_pathgain_node",
        "linear_attribute": "path_gain",
        "db_attribute": "path_gain_db",
        "unit": "dB",
    },
    "rss": {
        "label": "RSS",
        "name_token": "RSS",
        "node_group": "Sionna_radio_map_rss_node",
        "linear_attribute": "rss",
        "db_attribute": "rss_dbm",
        "unit": "dBm",
    },
    "sinr": {
        "label": "SINR",
        "name_token": "SINR",
        "node_group": "Sionna_radio_map_sinr_node",
        "linear_attribute": "sinr",
        "db_attribute": "sinr_db",
        "unit": "dB",
    },
}
_RADIO_MAP_PROJECTED_MODE_DEFINITIONS = {
    "path_gain": {
        "label": "Projected Path Gain",
        "name_token": "Projected_PathGain",
        "node_group": "Sionna_radio_map_projected_pathgain_node",
        "linear_attribute": "path_gain",
        "db_attribute": "path_gain_db",
        "unit": "dB",
    },
}
_DEFAULT_RADIO_MAP_GEOMETRY_NODES_GROUP = (
    _RADIO_MAP_MODE_DEFINITIONS["path_gain"]["node_group"]
)
_RADIO_MAP_3D_MODE_DEFINITIONS = {
    "path_gain": {
        "label": "Path Gain",
        "name_token": "PathGain",
        "node_group": "Sionna_radio_map_3d_pathgain_node",
        "linear_attribute": "path_gain",
        "db_attribute": "path_gain_db",
        "unit": "dB",
    },
    "rss": {
        "label": "RSS",
        "name_token": "RSS",
        "node_group": "Sionna_radio_map_3d_rss_node",
        "linear_attribute": "rss",
        "db_attribute": "rss_dbm",
        "unit": "dBm",
    },
    "sinr": {
        "label": "SINR",
        "name_token": "SINR",
        "node_group": "Sionna_radio_map_3d_sinr_node",
        "linear_attribute": "sinr",
        "db_attribute": "sinr_db",
        "unit": "dB",
    },
}
_DEFAULT_RADIO_MAP_3D_GEOMETRY_NODES_GROUP = (
    _RADIO_MAP_3D_MODE_DEFINITIONS["path_gain"]["node_group"]
)

# Bundled Geometry Nodes library. The extension ships a native Blender .blend
# asset containing all SionnaRT node groups. Missing groups are appended
# automatically after extension registration and whenever another .blend file
# is loaded, so users never need to use File > Append manually.
_BUNDLED_NODE_LIBRARY = "sionnart_geometry_nodes.blend"
_BUNDLED_NODE_LIBRARY_DIR = "assets"
_BUNDLED_NODE_LIBRARY_TAG = "sionnart_bridge_bundled_node_library"
_BUNDLED_NODE_LIBRARY_VERSION = _ADDON_VERSION


def _bundled_node_library_path():
    return Path(__file__).resolve().parent / _BUNDLED_NODE_LIBRARY_DIR / _BUNDLED_NODE_LIBRARY


def _ensure_bundled_geometry_nodes(*, verbose=True):
    """Append every missing node group from the bundled Blender library.

    Existing node groups are intentionally preserved. This prevents duplicate
    ``.001`` groups and, importantly, does not overwrite user edits made to a
    node group inside the current project. Nested node-group dependencies are
    resolved by Blender's native library loader.
    """
    node_groups = getattr(bpy.data, "node_groups", None)
    if node_groups is None:
        return {"status": "DEFERRED", "available": 0, "loaded": 0, "missing": []}

    library_path = _bundled_node_library_path()
    if not library_path.is_file():
        if verbose:
            print(f"[SionnaRT-Bridge] Bundled Geometry Nodes library not found: {library_path}")
        return {"status": "MISSING_LIBRARY", "available": 0, "loaded": 0, "missing": []}

    try:
        with bpy.data.libraries.load(str(library_path), link=False) as (data_from, data_to):
            available_names = [str(name) for name in data_from.node_groups if str(name)]
            missing_names = [name for name in available_names if node_groups.get(name) is None]
            data_to.node_groups = missing_names

        loaded_groups = [group for group in data_to.node_groups if group is not None]
        for group in loaded_groups:
            try:
                group[_BUNDLED_NODE_LIBRARY_TAG] = _BUNDLED_NODE_LIBRARY
                group["sionnart_bridge_bundled_version"] = _BUNDLED_NODE_LIBRARY_VERSION
            except Exception:
                pass

        if verbose:
            if loaded_groups:
                names = ", ".join(group.name for group in loaded_groups)
                print(
                    f"[SionnaRT-Bridge] Loaded {len(loaded_groups)} bundled Geometry Nodes "
                    f"group(s): {names}"
                )
            else:
                print(
                    f"[SionnaRT-Bridge] Bundled Geometry Nodes ready "
                    f"({len(available_names)} group(s) already present)."
                )
        return {
            "status": "OK",
            "available": len(available_names),
            "loaded": len(loaded_groups),
            "missing": missing_names,
        }
    except Exception as exc:
        if verbose:
            print(f"[SionnaRT-Bridge] Could not load bundled Geometry Nodes: {exc}")
            traceback.print_exc()
        return {"status": "ERROR", "available": 0, "loaded": 0, "missing": [], "error": str(exc)}


@persistent
def _bundled_geometry_nodes_load_post(_dummy):
    # load_post runs after the new BlendData is available. Append only groups
    # that are missing from the newly opened project.
    _ensure_bundled_geometry_nodes(verbose=True)


# ITU-R P.2040 material identifiers supported by Sionna RT. The colors are
# Blender viewport approximations only; electromagnetic properties are supplied
# by Sionna at the evaluated scene frequency.
_ITU_MATERIAL_DEFINITIONS = {
    "vacuum": ("Vacuum", (0.82, 0.90, 1.00, 0.25)),
    "concrete": ("Concrete", (0.48, 0.48, 0.46, 1.00)),
    "brick": ("Brick", (0.55, 0.16, 0.10, 1.00)),
    "plasterboard": ("Plasterboard", (0.82, 0.78, 0.67, 1.00)),
    "wood": ("Wood", (0.40, 0.20, 0.07, 1.00)),
    "glass": ("Glass", (0.32, 0.68, 0.82, 0.35)),
    "ceiling_board": ("Ceiling board", (0.88, 0.86, 0.74, 1.00)),
    "chipboard": ("Chipboard", (0.47, 0.29, 0.12, 1.00)),
    "plywood": ("Plywood", (0.58, 0.36, 0.15, 1.00)),
    "marble": ("Marble", (0.78, 0.80, 0.82, 1.00)),
    "floorboard": ("Floorboard", (0.48, 0.28, 0.10, 1.00)),
    "metal": ("Metal", (0.35, 0.38, 0.42, 1.00)),
    "very_dry_ground": ("Very dry ground", (0.57, 0.43, 0.25, 1.00)),
    "medium_dry_ground": ("Medium dry ground", (0.38, 0.28, 0.16, 1.00)),
    "wet_ground": ("Wet ground", (0.20, 0.16, 0.10, 1.00)),
}
_ITU_MATERIAL_ITEMS = tuple(
    (key, label, f"ITU-R P.2040 {label.lower()} model")
    for key, (label, _color) in _ITU_MATERIAL_DEFINITIONS.items()
)


_ANTENNA_PATTERNS = ("iso", "dipole", "hw_dipole", "tr38901")
_ANTENNA_POLARIZATIONS = ("V", "H", "VH", "cross")
_ANTENNA_POLARIZATION_MODELS = ("tr38901_1", "tr38901_2")
_DEFAULT_ANTENNA_PROFILE = {
    "pattern": "iso",
    "num_rows": 1,
    "num_cols": 1,
    "vertical_spacing": 0.5,
    "horizontal_spacing": 0.5,
    "polarization": "V",
    "polarization_model": "tr38901_2",
}


def _compact_float(value):
    value = float(value)
    text = f"{value:.6g}"
    return "0" if text == "-0" else text


def _device_base_name(name, role=None):
    """Return the stable TX/RX identifier before encoded antenna tokens."""
    raw = str(name or "").strip()
    if "__" in raw:
        raw = raw.split("__", 1)[0]
    match = re.match(r"^(TX|RX)[_-]?(\d+)", raw, re.IGNORECASE)
    if match:
        return f"{match.group(1).upper()}_{int(match.group(2)):03d}"
    if role in {"TX", "RX"}:
        return _sanitize_name(raw) or f"{role}_001"
    return raw or "DEVICE"


def _default_device_name_config(name, role=None):
    return {
        "base_name": _device_base_name(name, role),
        "antenna": dict(_DEFAULT_ANTENNA_PROFILE),
        "orientation_mode": "BLENDER",
        "fixed_orientation_deg": [0.0, 0.0, 0.0],
        "look_at_target": "",
    }


def _parse_triplet(text):
    values = [part.strip() for part in re.split(r"[,;]", str(text))]
    if len(values) != 3:
        raise ValueError("Expected three comma-separated angles")
    return [float(value) for value in values]


def _parse_device_name(name, role=None):
    """Parse antenna, array, and orientation metadata encoded in a device name.

    Canonical examples::

        TX_001__pat-tr38901__arr-4x4__sp-0.5x0.5__pol-VH__ori-blender
        TX_001__pat-tr38901__arr-4x4__sp-0.5x0.5__pol-VH__look-(RX_001)
        RX_001__pat-dipole__arr-1x1__pol-cross__ori-90,0,0

    A compact legacy style such as ``TX_001_iso_4x4_orientation_RX_001``
    is also recognized.
    """
    result = _default_device_name_config(name, role)
    raw = str(name or "")
    suffix = raw.split("__", 1)[1] if "__" in raw else ""
    tokens = [token.strip() for token in suffix.split("__") if token.strip()]

    def apply_token(token):
        lower = token.lower()
        antenna = result["antenna"]
        compact = re.fullmatch(
            r"(iso|dipole|hw_dipole|tr38901)-(\d+)[xX](\d+)-(V|H|VH|cross)",
            token,
            re.IGNORECASE,
        )
        if compact:
            antenna["pattern"] = compact.group(1).lower()
            antenna["num_rows"] = max(1, int(compact.group(2)))
            antenna["num_cols"] = max(1, int(compact.group(3)))
            polarization_map = {item.lower(): item for item in _ANTENNA_POLARIZATIONS}
            antenna["polarization"] = polarization_map[compact.group(4).lower()]
            return
        if lower in {"obj", "blender", "object"}:
            result["orientation_mode"] = "BLENDER"
            return
        if lower.startswith("rot-"):
            try:
                result["fixed_orientation_deg"] = _parse_triplet(token[4:])
                result["orientation_mode"] = "FIXED"
            except Exception:
                pass
            return
        if lower.startswith("pat-"):
            candidate = token[4:].lower()
            if candidate in _ANTENNA_PATTERNS:
                antenna["pattern"] = candidate
            return
        if lower in _ANTENNA_PATTERNS:
            antenna["pattern"] = lower
            return
        match = re.fullmatch(r"(?:arr-)?(\d+)[xX](\d+)", token)
        if match:
            antenna["num_rows"] = max(1, int(match.group(1)))
            antenna["num_cols"] = max(1, int(match.group(2)))
            return
        match = re.fullmatch(r"(?:sp-|spacing-)([-+0-9.eE]+)[xX]([-+0-9.eE]+)", token)
        if match:
            antenna["vertical_spacing"] = max(1e-6, float(match.group(1)))
            antenna["horizontal_spacing"] = max(1e-6, float(match.group(2)))
            return
        if lower.startswith("pol-"):
            candidate = token[4:]
            mapping = {item.lower(): item for item in _ANTENNA_POLARIZATIONS}
            if candidate.lower() in mapping:
                antenna["polarization"] = mapping[candidate.lower()]
            return
        if lower.startswith("pmod-"):
            candidate = token[5:].lower()
            if candidate in _ANTENNA_POLARIZATION_MODELS:
                antenna["polarization_model"] = candidate
            return
        if lower in {"ori-blender", "ori-object", "orientation", "orientation-blender", "normal"}:
            result["orientation_mode"] = "BLENDER"
            return
        if lower.startswith("ori-"):
            payload = token[4:]
            if payload.lower() in {"blender", "object", "normal"}:
                result["orientation_mode"] = "BLENDER"
                return
            try:
                result["fixed_orientation_deg"] = _parse_triplet(payload)
                result["orientation_mode"] = "FIXED"
            except Exception:
                pass
            return
        if lower.startswith(("look-", "lookat-", "target-")):
            payload = token.split("-", 1)[1].strip()
            if payload.startswith("(") and payload.endswith(")"):
                payload = payload[1:-1].strip()
            if payload:
                result["look_at_target"] = payload
                result["orientation_mode"] = "LOOK_AT"
            return

    for token in tokens:
        apply_token(token)

    if not tokens:
        lower = raw.lower()
        # Compact name parser retained for names such as
        # TX_001_iso_4X4_orientation_RX_001.
        for pattern in sorted(_ANTENNA_PATTERNS, key=len, reverse=True):
            if re.search(rf"(?:^|_){re.escape(pattern)}(?:_|$)", lower):
                result["antenna"]["pattern"] = pattern
                break
        match = re.search(r"(?:^|_)(\d+)[xX](\d+)(?:_|$)", raw)
        if match:
            result["antenna"]["num_rows"] = max(1, int(match.group(1)))
            result["antenna"]["num_cols"] = max(1, int(match.group(2)))
        target_match = re.search(
            r"(?:look(?:at)?|target|orientation)[-_]?\(?((?:TX|RX)[_-]\d+)\)?",
            raw,
            re.IGNORECASE,
        )
        if target_match:
            result["look_at_target"] = _device_base_name(target_match.group(1))
            result["orientation_mode"] = "LOOK_AT"

    antenna = result["antenna"]
    antenna["num_rows"] = max(1, int(antenna["num_rows"]))
    antenna["num_cols"] = max(1, int(antenna["num_cols"]))
    antenna["vertical_spacing"] = max(1e-6, float(antenna["vertical_spacing"]))
    antenna["horizontal_spacing"] = max(1e-6, float(antenna["horizontal_spacing"]))
    return result


def _canonical_device_name(base_name, antenna, orientation_mode="BLENDER", fixed_deg=None, target_name=""):
    """Build a compact human-readable device name.

    Runtime array settings are role-wide (one TX array and one RX array in
    Sionna RT). The name mirrors the active role profile and stores the
    per-device orientation target or Euler orientation.
    """
    base = _device_base_name(base_name)
    fixed_deg = list(fixed_deg or (0.0, 0.0, 0.0))
    summary = (
        f"{antenna['pattern']}-{int(antenna['num_rows'])}x{int(antenna['num_cols'])}-"
        f"{antenna['polarization']}"
    )
    tokens = [summary]
    if orientation_mode == "LOOK_AT" and target_name:
        tokens.append(f"look-{target_name}")
    elif orientation_mode == "FIXED":
        tokens.append("rot-" + ",".join(_compact_float(value) for value in fixed_deg))
    else:
        tokens.append("obj")
    return base + "__" + "__".join(tokens)


def _find_named_target(target_name):
    target_name = str(target_name or "").strip()
    if not target_name:
        return None
    exact = bpy.data.objects.get(target_name)
    if exact is not None:
        return exact
    target_lower = target_name.lower()
    for candidate in bpy.data.objects:
        if candidate.name.lower() == target_lower:
            return candidate
        if _device_base_name(candidate.name).lower() == target_lower:
            return candidate
    return None


def _antenna_signature(profile):
    return (
        str(profile["pattern"]),
        int(profile["num_rows"]),
        int(profile["num_cols"]),
        round(float(profile["vertical_spacing"]), 9),
        round(float(profile["horizontal_spacing"]), 9),
        str(profile["polarization"]),
        str(profile.get("polarization_model", "tr38901_2")),
    )


def _validate_device_base_names(devices, role):
    seen = {}
    for obj in devices:
        base = _device_base_name(obj.name, role)
        if base in seen:
            raise RuntimeError(
                f"Duplicate {role} base identifier '{base}' in {seen[base]} and {obj.name}. "
                "Use unique names such as TX_001, TX_002 or RX_001, RX_002."
            )
        seen[base] = obj.name


def _role_antenna_profile(settings, role):
    """Return the scene-wide Sionna array profile for one device role."""
    prefix = "tx" if str(role).upper() == "TX" else "rx"
    return {
        "pattern": getattr(settings, f"{prefix}_antenna_pattern"),
        "num_rows": int(getattr(settings, f"{prefix}_array_rows")),
        "num_cols": int(getattr(settings, f"{prefix}_array_cols")),
        "vertical_spacing": float(getattr(settings, f"{prefix}_vertical_spacing")),
        "horizontal_spacing": float(getattr(settings, f"{prefix}_horizontal_spacing")),
        "polarization": getattr(settings, f"{prefix}_polarization"),
        "polarization_model": getattr(settings, f"{prefix}_polarization_model"),
    }


def _set_role_antenna_profile(settings, role, profile):
    prefix = "tx" if str(role).upper() == "TX" else "rx"
    setattr(settings, f"{prefix}_antenna_pattern", str(profile.get("pattern", "iso")))
    setattr(settings, f"{prefix}_array_rows", max(1, int(profile.get("num_rows", 1))))
    setattr(settings, f"{prefix}_array_cols", max(1, int(profile.get("num_cols", 1))))
    setattr(settings, f"{prefix}_vertical_spacing", max(1e-6, float(profile.get("vertical_spacing", 0.5))))
    setattr(settings, f"{prefix}_horizontal_spacing", max(1e-6, float(profile.get("horizontal_spacing", 0.5))))
    setattr(settings, f"{prefix}_polarization", str(profile.get("polarization", "V")))
    setattr(settings, f"{prefix}_polarization_model", str(profile.get("polarization_model", "tr38901_2")))


def _antenna_config(settings, transmitters, receivers=()):
    """Build independent TX/RX array profiles.

    Sionna RT exposes one scene.tx_array shared by all transmitters and one
    scene.rx_array shared by all receivers. TX and RX profiles may differ,
    but devices of the same role cannot use different arrays in one run.
    """
    _validate_device_base_names(transmitters, "TX")
    _validate_device_base_names(receivers, "RX")
    return {
        "tx": _role_antenna_profile(settings, "TX"),
        "rx": _role_antenna_profile(settings, "RX"),
    }


def _object_orientation_state(obj, role=None):
    """Return per-object UI orientation, falling back to encoded name data."""
    parsed = _parse_device_name(obj.name, role)
    config = getattr(obj, "sionna_device_config", None)
    if config is not None and bool(config.configured):
        target = config.look_at_target
        target_name = ""
        if target is not None:
            target_role = str(target.get("sionna_role", "")).upper()
            target_name = (
                _device_base_name(target.name, target_role)
                if target_role in {"TX", "RX"}
                else target.name
            )
        return {
            "orientation_mode": config.orientation_mode,
            "fixed_orientation_deg": [
                math.degrees(float(config.fixed_alpha)),
                math.degrees(float(config.fixed_beta)),
                math.degrees(float(config.fixed_gamma)),
            ],
            "look_at_target": target_name,
            "look_at_target_object": target,
        }
    parsed["look_at_target_object"] = _find_named_target(parsed["look_at_target"])
    return parsed


def _sync_device_name(obj, settings, role=None):
    role = (role or str(obj.get("sionna_role", ""))).upper()
    if role not in {"TX", "RX"}:
        return obj.name
    state = _object_orientation_state(obj, role)
    profile = _role_antenna_profile(settings, role)
    obj.name = _canonical_device_name(
        _device_base_name(obj.name, role),
        profile,
        state["orientation_mode"],
        state["fixed_orientation_deg"],
        state["look_at_target"],
    )
    return obj.name


def _sync_role_device_names(scene, settings, role):
    count = 0
    for obj in _device_objects(scene, role):
        _sync_device_name(obj, settings, role)
        count += 1
    return count

# Process state is intentionally not stored in the .blend file.
_RUN_STATE = {
    "process": None,
    "log_handle": None,
    "scene_name": "",
    "run_dir": "",
    "results_json": "",
    "results_csv": "",
    "frame_count": 0,
    "config_path": "",
    "started_ns": 0,
    "object_name": "",
    "pid": 0,
    "lock_path": "",
    "auto_triggered": False,
}

_RADIO_MAP_STATE = {
    "process": None,
    "log_handle": None,
    "scene_name": "",
    "run_dir": "",
    "results_json": "",
    "results_csv": "",
    "expected_frequency_ghz": None,
    "frame": 0,
    "frame_count": 0,
    "config_path": "",
    "started_ns": 0,
    "object_name": "",
    "pid": 0,
    "lock_path": "",
    "auto_triggered": False,
}

_RADIO_MAP_3D_STATE = {
    "process": None,
    "log_handle": None,
    "scene_name": "",
    "run_dir": "",
    "results_json": "",
    "results_csv": "",
    "frame_count": 0,
    "config_path": "",
    "started_ns": 0,
    "pid": 0,
    "lock_path": "",
    "auto_triggered": False,
}

# Coordinates the single Run Simulation button. When multiple outputs are enabled,
# propagation paths run first, then the 2D map, then the 3D map.
_BATCH_STATE = {
    "active": False,
    "scene_name": "",
    "scene_source": None,
    "paths_requested": False,
    "radio_map_requested": False,
    "radio_map_3d_requested": False,
    "pending_radio_map": False,
    "pending_radio_map_3d": False,
    "path_status": "",
    "radio_map_status": "",
    "auto_triggered": False,
    "force_current_frame": False,
    "auto_anchor_tx_name": "",
    "export_bundle": {},
}

# Debounced, latest-state-wins recomputation driven by TX/RX transforms.
# This is runtime-only state: nothing here is persisted in the .blend file.
_AUTO_PATH_STATE = {
    "pending": False,
    "scene_name": "",
    "device_name": "",
    "device_role": "",
    "anchor_device_name": "",
    "deadline": 0.0,
    "suppress": 0,
    "transform_signatures": {},
}


def _reset_batch_state():
    _BATCH_STATE.update({
        "active": False,
        "scene_name": "",
        "scene_source": None,
        "paths_requested": False,
        "radio_map_requested": False,
        "radio_map_3d_requested": False,
        "pending_radio_map": False,
        "pending_radio_map_3d": False,
        "path_status": "",
        "radio_map_status": "",
        "auto_triggered": False,
        "force_current_frame": False,
        "auto_anchor_tx_name": "",
        "export_bundle": {},
    })


def _processes_idle():
    path_process = _RUN_STATE.get("process")
    map_process = _RADIO_MAP_STATE.get("process")
    map_3d_process = _RADIO_MAP_3D_STATE.get("process")
    return (
        (path_process is None or path_process.poll() is not None)
        and (map_process is None or map_process.poll() is not None)
        and (map_3d_process is None or map_3d_process.poll() is not None)
    )


def _addon_dir():
    return Path(__file__).resolve().parent


def _worker_script():
    return _addon_dir() / "sionna_worker.py"


def _radio_map_worker_script():
    return _addon_dir() / "radio_map_worker.py"


def _radio_map_3d_worker_script():
    return _addon_dir() / "radio_map_3d_worker.py"


def _result_export_worker_script():
    return _addon_dir() / "result_export_worker.py"


def _now_utc():
    return datetime.now(timezone.utc).isoformat()


def _sanitize_name(value):
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip())
    cleaned = cleaned.strip("_")
    return cleaned or "device"


def _absolute_path(value):
    return Path(bpy.path.abspath(value)).expanduser().resolve()


def _collection_child(parent, name):
    """Return a direct child collection by name, or None."""
    try:
        return parent.children.get(name)
    except Exception:
        return None


def _ensure_collection_datablock(name):
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
    if getattr(collection, "library", None) is not None:
        raise RuntimeError(
            f"Collection '{name}' is linked from another blend file and cannot be managed"
        )
    return collection


def _link_collection(parent, child):
    if _collection_child(parent, child.name) is None:
        parent.children.link(child)


def _unlink_collection(parent, child):
    if _collection_child(parent, child.name) is not None:
        parent.children.unlink(child)


def _move_object_to_collection(obj, target):
    """Move an object exclusively into one workflow collection."""
    if target.objects.get(obj.name) is None:
        target.objects.link(obj)
    for collection in list(obj.users_collection):
        if collection != target:
            try:
                collection.objects.unlink(obj)
            except RuntimeError:
                pass


def _collection_objects_recursive(collection):
    objects = []
    seen_objects = set()
    seen_collections = set()

    def visit(current):
        pointer = current.as_pointer()
        if pointer in seen_collections:
            return
        seen_collections.add(pointer)
        for obj in current.objects:
            obj_pointer = obj.as_pointer()
            if obj_pointer not in seen_objects:
                seen_objects.add(obj_pointer)
                objects.append(obj)
        for child in current.children:
            visit(child)

    visit(collection)
    return objects



_DEVICE_REPRESENTATION_SYNC_PENDING = False
_DEVICE_REPRESENTATION_SYNC_GUARD = False


def _collection_child_by_role(parent, name, role):
    collection = _collection_child(parent, name)
    if collection is not None:
        return collection
    for child in parent.children:
        if child.get("sionna_collection_role") == role:
            return child
    return None


def _ensure_child_collection(parent, name, role):
    collection = _collection_child_by_role(parent, name, role)
    if collection is None:
        for candidate in bpy.data.collections:
            if candidate.get("sionna_collection_role") == role:
                collection = candidate
                break
    if collection is None:
        collection = bpy.data.collections.new(name)
    if getattr(collection, "library", None) is not None:
        raise RuntimeError(
            f"Collection '{collection.name}' is linked from another blend file and cannot be managed"
        )
    _link_collection(parent, collection)
    collection["sionna_collection_role"] = role
    return collection


def _ensure_device_representation_materials():
    """Create Blender-only TX/RX display materials and keep them out of Sionna export."""
    created = 0
    materials = {}
    for role, (name, color) in _DEVICE_REPRESENTATION_MATERIALS.items():
        material = bpy.data.materials.get(name)
        if material is None:
            material = bpy.data.materials.new(name=name)
            created += 1
        signature = f"{role}:v1"
        if material.get("sionna_representation_material_signature") != signature:
            _set_material_preview_color(material, color)
            material["sionna_blender_only"] = True
            material["sionna_device_representation"] = role
            material["sionna_representation_material_signature"] = signature
        config = getattr(material, "sionna_radio", None)
        if config is not None:
            if config.enabled:
                config.enabled = False
            if config.configured:
                config.configured = False
        materials[role] = material
    return materials, created


def _ensure_device_representation_meshes():
    sphere = bpy.data.meshes.get(_DEVICE_REPRESENTATION_SPHERE_MESH)
    if sphere is None:
        sphere = bpy.data.meshes.new(_DEVICE_REPRESENTATION_SPHERE_MESH)
        bm = bmesh.new()
        try:
            bmesh.ops.create_uvsphere(
                bm,
                u_segments=24,
                v_segments=16,
                radius=0.2,
            )
            bm.to_mesh(sphere)
        finally:
            bm.free()
        for polygon in sphere.polygons:
            polygon.use_smooth = True
        sphere.update()
        sphere["sionna_blender_only"] = True

    arrow = bpy.data.meshes.get(_DEVICE_REPRESENTATION_ARROW_MESH)
    if arrow is None:
        arrow = bpy.data.meshes.new(_DEVICE_REPRESENTATION_ARROW_MESH)
        bm = bmesh.new()
        try:
            rotate_to_x = Matrix.Rotation(math.radians(90.0), 4, "Y")
            shaft_matrix = Matrix.Translation((0.58, 0.0, 0.0)) @ rotate_to_x
            head_matrix = Matrix.Translation((1.05, 0.0, 0.0)) @ rotate_to_x
            bmesh.ops.create_cone(
                bm,
                cap_ends=True,
                cap_tris=False,
                segments=16,
                radius1=0.035,
                radius2=0.035,
                depth=0.72,
                matrix=shaft_matrix,
            )
            bmesh.ops.create_cone(
                bm,
                cap_ends=True,
                cap_tris=False,
                segments=16,
                radius1=0.10,
                radius2=0.0,
                depth=0.30,
                matrix=head_matrix,
            )
            bm.to_mesh(arrow)
        finally:
            bm.free()
        arrow.update()
        arrow["sionna_blender_only"] = True
    return sphere, arrow


def _device_representation_id(device, used_ids=None):
    value = str(device.get(_DEVICE_ID_PROPERTY, "")).strip()
    if not value or (used_ids is not None and value in used_ids):
        value = uuid.uuid4().hex
        try:
            device[_DEVICE_ID_PROPERTY] = value
        except Exception:
            value = f"name-{_sanitize_name(device.name)}-{device.as_pointer()}"
    if used_ids is not None:
        used_ids.add(value)
    return value


def _representation_object_name(device, role, part):
    base = _sanitize_name(_device_base_name(device.name, role))
    return f"{base}_{role}_{part}_representation"


def _assign_single_material(obj, material):
    slots = getattr(getattr(obj, "data", None), "materials", None)
    if slots is None:
        return
    if len(slots) == 0:
        slots.append(material)
    object_slots = getattr(obj, "material_slots", None)
    if object_slots and len(object_slots) > 0:
        slot = object_slots[0]
        if slot.link != "OBJECT":
            slot.link = "OBJECT"
        if slot.material != material:
            slot.material = material
    color = tuple(float(value) for value in material.diffuse_color)
    if tuple(float(value) for value in obj.color) != color:
        obj.color = color


def _clear_representation_constraints(obj):
    for constraint in list(obj.constraints):
        if constraint.name.startswith("Sionna Representation"):
            obj.constraints.remove(constraint)


def _add_copy_location_constraint(obj, source):
    constraint = obj.constraints.new("COPY_LOCATION")
    constraint.name = "Sionna Representation Location"
    constraint.target = source
    constraint.target_space = "WORLD"
    constraint.owner_space = "WORLD"
    return constraint


def _configure_representation_arrow(arrow, source, role):
    parsed = _parse_device_name(source.name, role)
    mode = parsed["orientation_mode"]
    fixed = tuple(float(value) for value in parsed["fixed_orientation_deg"])
    target = _find_named_target(parsed["look_at_target"]) if mode == "LOOK_AT" else None
    target_name = target.name if target is not None else ""
    signature = json.dumps(
        [source.name, mode, [round(value, 8) for value in fixed], target_name],
        separators=(",", ":"),
    )
    if arrow.get("sionna_representation_signature") == signature:
        return

    _clear_representation_constraints(arrow)
    _add_copy_location_constraint(arrow, source)
    arrow.rotation_mode = "XYZ"
    arrow.rotation_euler = (0.0, 0.0, 0.0)
    arrow["sionna_orientation_mode"] = mode
    arrow["sionna_look_at_target"] = parsed["look_at_target"]
    arrow["sionna_representation_warning"] = ""

    if mode == "LOOK_AT" and target is not None and target is not source:
        constraint = arrow.constraints.new("DAMPED_TRACK")
        constraint.name = "Sionna Representation Look At"
        constraint.target = target
        constraint.track_axis = "TRACK_X"
    elif mode == "FIXED":
        alpha, beta, gamma = (math.radians(value) for value in fixed)
        # Sionna (alpha, beta, gamma) rotates around Z, Y, X. Blender XYZ
        # stores the equivalent world Euler as (gamma, beta, alpha).
        arrow.rotation_euler = (gamma, beta, alpha)
    else:
        constraint = arrow.constraints.new("COPY_ROTATION")
        constraint.name = "Sionna Representation Rotation"
        constraint.target = source
        constraint.target_space = "WORLD"
        constraint.owner_space = "WORLD"
        constraint.mix_mode = "REPLACE"
        if mode == "LOOK_AT":
            arrow["sionna_representation_warning"] = (
                f"Look-at target '{parsed['look_at_target']}' was not found; using object rotation"
            )

    arrow["sionna_representation_signature"] = signature


def _set_representation_property(obj, name, value):
    if obj.get(name) != value:
        obj[name] = value


def _create_representation_object(name, mesh, collection, material, device_id, source_name, role, part):
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj[_DEVICE_REPRESENTATION_TAG] = True
    obj["sionna_source_device_id"] = device_id
    obj["sionna_source_device_name"] = source_name
    obj["sionna_source_role"] = role
    obj["sionna_representation_part"] = part
    obj["sionna_blender_only"] = True
    obj.show_in_front = True
    obj.hide_select = True
    obj.display_type = "SOLID"
    _assign_single_material(obj, material)
    return obj


def _ensure_device_representation_object(
    device,
    device_id,
    role,
    part,
    mesh,
    collection,
    material,
    existing,
):
    key = (device_id, part)
    candidates = existing.pop(key, [])
    obj = candidates.pop(0) if candidates else None
    for duplicate in candidates:
        bpy.data.objects.remove(duplicate, do_unlink=True)
    if obj is None:
        obj = _create_representation_object(
            _representation_object_name(device, role, part),
            mesh,
            collection,
            material,
            device_id,
            device.name,
            role,
            part,
        )
    else:
        if obj.data != mesh:
            obj.data = mesh
        _move_object_to_collection(obj, collection)
        _assign_single_material(obj, material)
        _set_representation_property(obj, _DEVICE_REPRESENTATION_TAG, True)
        _set_representation_property(obj, "sionna_source_device_id", device_id)
        _set_representation_property(obj, "sionna_source_device_name", device.name)
        _set_representation_property(obj, "sionna_source_role", role)
        _set_representation_property(obj, "sionna_representation_part", part)
        _set_representation_property(obj, "sionna_blender_only", True)
        if not obj.show_in_front:
            obj.show_in_front = True
        if not obj.hide_select:
            obj.hide_select = True
    expected_name = _representation_object_name(device, role, part)
    if obj.name != expected_name:
        obj.name = expected_name
    return obj


def _sync_device_representations(scene):
    """Create, update, and remove live Blender-only device representations."""
    global _DEVICE_REPRESENTATION_SYNC_GUARD
    if _DEVICE_REPRESENTATION_SYNC_GUARD:
        return 0
    workflow = _find_environment(scene)
    if workflow is None:
        return 0
    _DEVICE_REPRESENTATION_SYNC_GUARD = True
    try:
        representation_root = workflow.get("device_representations")
        representation_txs = workflow.get("representation_txs")
        representation_rxs = workflow.get("representation_rxs")
        if not all((representation_root, representation_txs, representation_rxs)):
            workflow = _ensure_environment(scene, migrate=False)
            representation_root = workflow["device_representations"]
            representation_txs = workflow["representation_txs"]
            representation_rxs = workflow["representation_rxs"]

        materials, _created = _ensure_device_representation_materials()
        sphere_mesh, arrow_mesh = _ensure_device_representation_meshes()
        existing = {}
        for collection in (representation_txs, representation_rxs):
            for obj in list(collection.objects):
                if not obj.get(_DEVICE_REPRESENTATION_TAG):
                    continue
                key = (
                    str(obj.get("sionna_source_device_id", "")),
                    str(obj.get("sionna_representation_part", "")),
                )
                existing.setdefault(key, []).append(obj)

        used_ids = set()
        active_keys = set()
        count = 0
        for role, collection in (("TX", representation_txs), ("RX", representation_rxs)):
            for device in _device_objects(scene, role):
                device_id = _device_representation_id(device, used_ids)
                for part, mesh in (("sphere", sphere_mesh), ("arrow", arrow_mesh)):
                    obj = _ensure_device_representation_object(
                        device,
                        device_id,
                        role,
                        part,
                        mesh,
                        collection,
                        materials[role],
                        existing,
                    )
                    active_keys.add((device_id, part))
                    if part == "sphere":
                        source_name = str(obj.get("sionna_representation_source_name", ""))
                        if source_name != device.name or not obj.constraints:
                            _clear_representation_constraints(obj)
                            _add_copy_location_constraint(obj, device)
                            obj["sionna_representation_source_name"] = device.name
                    else:
                        _configure_representation_arrow(obj, device, role)
                    count += 1

        for key, objects in existing.items():
            if key in active_keys:
                continue
            for obj in objects:
                bpy.data.objects.remove(obj, do_unlink=True)
        return count
    finally:
        _DEVICE_REPRESENTATION_SYNC_GUARD = False


def _device_representation_sync_timer():
    global _DEVICE_REPRESENTATION_SYNC_PENDING
    _DEVICE_REPRESENTATION_SYNC_PENDING = False
    for scene in list(bpy.data.scenes):
        try:
            if _find_environment(scene) is not None:
                _sync_device_representations(scene)
        except ReferenceError:
            # A scene refresh can remove an RNA object between depsgraph evaluation
            # and this deferred timer. The next relevant update will resync it.
            continue
        except Exception:
            traceback.print_exc()
    return None


def _schedule_device_representation_sync():
    global _DEVICE_REPRESENTATION_SYNC_PENDING
    if _DEVICE_REPRESENTATION_SYNC_PENDING:
        return
    _DEVICE_REPRESENTATION_SYNC_PENDING = True
    if not bpy.app.timers.is_registered(_device_representation_sync_timer):
        bpy.app.timers.register(
            _device_representation_sync_timer,
            first_interval=0.05,
            persistent=False,
        )


@persistent
def _device_representation_depsgraph_update(scene, _depsgraph):
    # Device representations use constraints for ordinary transforms, so there is
    # no reason to keep a depsgraph listener alive while Dynamic Mode is disabled.
    settings = getattr(scene, "sionna_bridge", None)
    if settings is None or not _dynamic_mode_enabled(settings):
        return
    _schedule_device_representation_sync()


@persistent
def _device_representation_load_post(_dummy):
    _schedule_device_representation_sync()


def _auto_path_transform_signature(obj, depsgraph=None):
    evaluated = obj.evaluated_get(depsgraph) if depsgraph is not None else obj
    matrix = evaluated.matrix_world
    return tuple(float(matrix[row][column]) for row in range(4) for column in range(4))


def _auto_path_signature_changed(previous, current, tolerance=1e-7):
    if previous is None or len(previous) != len(current):
        return False
    return any(abs(float(a) - float(b)) > tolerance for a, b in zip(previous, current))


def _dynamic_mode_enabled(settings):
    """Return whether movement-driven background work is explicitly enabled."""
    return bool(settings is not None and getattr(settings, "dynamic_mode", False))


def _auto_move_enabled(settings):
    # Dynamic Mode is the single master switch for every depsgraph-driven Sionna
    # recomputation. Output-specific toggles decide what a move recomputes.
    return bool(
        _dynamic_mode_enabled(settings)
        and (
            getattr(settings, "auto_compute_paths_on_tx_move", False)
            or getattr(settings, "auto_compute_radio_map_on_device_move", False)
            or getattr(settings, "auto_compute_radio_map_3d_on_device_move", False)
        )
    )


def _auto_move_requested_outputs(settings, device_role):
    role = str(device_role or "").upper()
    return {
        # Propagation paths depend on both endpoint transforms, so either TX or RX
        # movement can invalidate the current path solution.
        "paths": bool(
            role in {"TX", "RX"}
            and getattr(settings, "simulate_paths", False)
            and getattr(settings, "auto_compute_paths_on_tx_move", False)
        ),
        # Sionna coverage maps are generated from transmitters over a measurement
        # region. RX empties are not inputs to these solvers, so RX-only movement
        # deliberately does not waste a coverage-map recomputation.
        "radio_map": bool(
            role == "TX"
            and getattr(settings, "simulate_radio_map", False)
            and getattr(settings, "auto_compute_radio_map_on_device_move", False)
        ),
        "radio_map_3d": bool(
            role == "TX"
            and getattr(settings, "simulate_radio_map_3d", False)
            and getattr(settings, "auto_compute_radio_map_3d_on_device_move", False)
        ),
    }


def _clear_auto_path_scene_state(scene_name=None):
    if scene_name is None or _AUTO_PATH_STATE.get("scene_name") == scene_name:
        _AUTO_PATH_STATE["pending"] = False
        _AUTO_PATH_STATE["scene_name"] = ""
        _AUTO_PATH_STATE["device_name"] = ""
        _AUTO_PATH_STATE["device_role"] = ""
        _AUTO_PATH_STATE["anchor_device_name"] = ""
        _AUTO_PATH_STATE["deadline"] = 0.0
    signatures = _AUTO_PATH_STATE.setdefault("transform_signatures", {})
    if scene_name is None:
        signatures.clear()
    else:
        prefix = str(scene_name) + ":"
        for key in [key for key in signatures if str(key).startswith(prefix)]:
            signatures.pop(key, None)


def _prime_auto_path_transform_signatures(scene, depsgraph=None):
    signatures = _AUTO_PATH_STATE.setdefault("transform_signatures", {})
    prefix = str(scene.name) + ":"
    for key in [key for key in signatures if str(key).startswith(prefix)]:
        signatures.pop(key, None)
    for role in ("TX", "RX"):
        for device in _device_objects(scene, role):
            try:
                signatures[f"{scene.name}:{device.as_pointer()}"] = _auto_path_transform_signature(
                    device, depsgraph
                )
            except (ReferenceError, RuntimeError):
                pass


def _schedule_auto_path_compute(
    scene, device_name, device_role, *, anchor_device_name=""
):
    settings = getattr(scene, "sionna_bridge", None)
    if settings is None:
        return
    delay = max(0.05, float(getattr(settings, "auto_compute_paths_delay", 0.35)))
    _AUTO_PATH_STATE.update({
        "pending": True,
        "scene_name": scene.name,
        "device_name": str(device_name or device_role or "device"),
        "device_role": str(device_role or "").upper(),
        "anchor_device_name": str(anchor_device_name or ""),
        "deadline": time.monotonic() + delay,
    })
    if not bpy.app.timers.is_registered(_auto_path_compute_timer):
        bpy.app.timers.register(
            _auto_path_compute_timer, first_interval=delay, persistent=False
        )


def _auto_path_runtime_idle():
    # Do not treat a process that merely *exited* as available yet. The poll
    # timer must first consume/import its outputs and clear the batch state.
    return (
        _RUN_STATE.get("process") is None
        and _RADIO_MAP_STATE.get("process") is None
        and _RADIO_MAP_3D_STATE.get("process") is None
        and not _BATCH_STATE.get("active")
    )


def _auto_path_scene_source(context):
    scene = context.scene
    settings = scene.sionna_bridge
    settings.procedural_export_report_json = ""
    settings.procedural_export_report_path = ""
    if _procedural_scene_active(scene):
        # Interactive recomputation deliberately exports only the visible frame.
        return _export_procedural_scene_frames(context, [int(scene.frame_current)])
    if settings.refresh_scene_before_run:
        scene_source, _, _ = _export_scene_cache(context)
        return scene_source
    try:
        return _cached_scene_xml(settings)
    except Exception:
        scene_source, _, _ = _export_scene_cache(context)
        return scene_source


def _auto_center_tx_object(scene, tx_name):
    """Resolve the transmitter that anchors an automatic coverage recompute."""
    tx_name = str(tx_name or "")
    if not tx_name:
        return None
    candidate = scene.objects.get(tx_name)
    if candidate is None or str(candidate.get("sionna_role", "")).upper() != "TX":
        return None
    return candidate


def _auto_path_compute_timer():
    if not _AUTO_PATH_STATE.get("pending"):
        return None

    scene_name = str(_AUTO_PATH_STATE.get("scene_name", ""))
    scene = bpy.data.scenes.get(scene_name)
    if scene is None:
        _clear_auto_path_scene_state(scene_name)
        return None

    settings = getattr(scene, "sionna_bridge", None)
    if settings is None or not _auto_move_enabled(settings):
        _clear_auto_path_scene_state(scene_name)
        return None

    remaining = float(_AUTO_PATH_STATE.get("deadline", 0.0)) - time.monotonic()
    if remaining > 0.0:
        return max(0.05, min(remaining, 0.25))

    device_name = str(_AUTO_PATH_STATE.get("device_name", "device"))
    device_role = str(_AUTO_PATH_STATE.get("device_role", "")).upper()
    anchor_device_name = str(_AUTO_PATH_STATE.get("anchor_device_name", ""))
    requested = _auto_move_requested_outputs(settings, device_role)
    transmitters = _device_objects(scene, "TX")
    receivers = _device_objects(scene, "RX")
    skipped = []

    if requested["paths"] and not transmitters:
        requested["paths"] = False
        skipped.append("paths need a TX")
    if requested["paths"] and not receivers:
        requested["paths"] = False
        skipped.append("paths need an RX")
    if (requested["radio_map"] or requested["radio_map_3d"]) and not transmitters:
        requested["radio_map"] = False
        requested["radio_map_3d"] = False
        skipped.append("coverage maps need a TX")

    if not any(requested.values()):
        _AUTO_PATH_STATE["pending"] = False
        if skipped:
            settings.last_status = "Auto simulation skipped: " + "; ".join(skipped)
        elif device_role == "RX":
            settings.last_status = (
                f"Auto simulation: {device_name} moved. RX movement affects propagation "
                "paths only; coverage maps were not recomputed."
            )
        return None

    if not _auto_path_runtime_idle():
        # Keep only the newest requested transform and launch as soon as the
        # current worker/batch has been fully consumed.
        return 0.20

    context = bpy.context
    if getattr(context, "scene", None) != scene:
        # A timer has no safe context override for a non-active scene. Wait
        # until this scene is active instead of running against the wrong one.
        return 0.25

    _AUTO_PATH_STATE["pending"] = False
    _AUTO_PATH_STATE["suppress"] = int(_AUTO_PATH_STATE.get("suppress", 0)) + 1
    try:
        _ensure_environment(scene, migrate=True)
        scene_source = _auto_path_scene_source(context)
        export_bundle = _prepare_export_bundle(settings)
        _BATCH_STATE.update({
            "active": True,
            "scene_name": scene.name,
            "scene_source": scene_source,
            "paths_requested": bool(requested["paths"]),
            "radio_map_requested": bool(requested["radio_map"]),
            "radio_map_3d_requested": bool(requested["radio_map_3d"]),
            "pending_radio_map": bool(requested["paths"] and requested["radio_map"]),
            "pending_radio_map_3d": bool(
                requested["radio_map_3d"]
                and (requested["paths"] or requested["radio_map"])
            ),
            "path_status": "",
            "radio_map_status": "",
            "auto_triggered": True,
            "force_current_frame": True,
            "auto_anchor_tx_name": (
                anchor_device_name if device_role == "TX" else ""
            ),
            "export_bundle": export_bundle,
        })

        output_names = []
        if requested["paths"]:
            output_names.append("paths")
        if requested["radio_map"]:
            output_names.append("2D coverage")
        if requested["radio_map_3d"]:
            output_names.append("3D coverage")

        if requested["paths"]:
            _start_sionna_process(
                context, scene_source, force_current_frame=True, auto_triggered=True
            )
        elif requested["radio_map"]:
            _start_radio_map_process(
                context, scene_source, force_current_frame=True, auto_triggered=True,
                auto_anchor_tx_name=(anchor_device_name if device_role == "TX" else ""),
            )
        else:
            _start_radio_map_3d_process(
                context, scene_source, force_current_frame=True, auto_triggered=True,
                auto_anchor_tx_name=(anchor_device_name if device_role == "TX" else ""),
            )

        settings.last_status = (
            f"Auto simulation: {device_name} ({device_role}) moved; running "
            f"{', '.join(output_names)} for current frame"
            + (f"; skipped {', '.join(skipped)}" if skipped else "")
        )
    except Exception as exc:
        _reset_batch_state()
        _set_status(
            settings,
            f"Auto simulation failed: {exc}",
            traceback.format_exc(),
            run_dir=settings.last_status_run_dir,
            log_path=settings.last_status_log_path,
        )
        traceback.print_exc()
    finally:
        _AUTO_PATH_STATE["suppress"] = max(
            0, int(_AUTO_PATH_STATE.get("suppress", 1)) - 1
        )
    return None


@persistent
def _auto_path_depsgraph_update(scene, depsgraph):
    if int(_AUTO_PATH_STATE.get("suppress", 0)) > 0:
        return
    settings = getattr(scene, "sionna_bridge", None)
    if settings is None or not _auto_move_enabled(settings):
        return

    signatures = _AUTO_PATH_STATE.setdefault("transform_signatures", {})
    moved = []
    for update in depsgraph.updates:
        obj = getattr(update, "id", None)
        if not isinstance(obj, bpy.types.Object):
            continue
        if not bool(getattr(update, "is_updated_transform", False)):
            continue
        # Moving a generated grid/anchor is equivalent to moving its associated
        # radio device. Handle helpers explicitly because Blender may report only
        # the constraint target in a depsgraph update on some viewport operations.
        if bool(obj.get("sionna_motion_template", False)) or bool(obj.get("sionna_motion_anchor", False)):
            device_name = str(obj.get("sionna_motion_device", "") or "")
            device = scene.objects.get(device_name) if device_name else None
            helper_role = str(device.get("sionna_role", "")).upper() if device is not None else ""
            if helper_role in {"TX", "RX"}:
                moved.append((helper_role, device.name))
            continue

        role = str(obj.get("sionna_role", "")).upper()
        if role not in {"TX", "RX"}:
            continue
        key = f"{scene.name}:{obj.as_pointer()}"
        try:
            current = _auto_path_transform_signature(obj, depsgraph)
        except (ReferenceError, RuntimeError):
            continue
        previous = signatures.get(key)
        signatures[key] = current
        # A missing baseline is initialization, not a user movement.
        if previous is not None and _auto_path_signature_changed(previous, current):
            moved.append((role, obj.name))

    if moved:
        # A constrained device, its hidden anchor, and the visible grid can all
        # appear in one depsgraph pass. Keep one trigger per associated device.
        moved = list(dict.fromkeys(moved))
        # If a TX and RX are both updated in the same depsgraph pass, the TX
        # trigger is the superset: it refreshes paths plus any enabled maps.
        anchor_device_name = ""
        if any(role == "TX" for role, _name in moved):
            role = "TX"
            names = [name for moved_role, name in moved if moved_role == "TX"]
            active = getattr(getattr(bpy.context, "view_layer", None), "objects", None)
            active_obj = getattr(active, "active", None) if active is not None else None
            if active_obj is not None and active_obj.name in names:
                anchor_device_name = active_obj.name
            elif names:
                anchor_device_name = names[0]
        else:
            role = "RX"
            names = [name for _moved_role, name in moved]
        if any(_auto_move_requested_outputs(settings, role).values()):
            label = ", ".join(names[:3])
            if len(names) > 3:
                label += f" +{len(names) - 3} more"
            _schedule_auto_path_compute(
                scene, label or role, role, anchor_device_name=anchor_device_name
            )


@persistent
def _auto_path_load_post(_dummy):
    _clear_auto_path_scene_state()
    _stop_legacy_live_update_timer()
    _sync_dynamic_mode_handlers()
    _sync_pointcloud_motion_handler()
    for scene in bpy.data.scenes:
        settings = getattr(scene, "sionna_bridge", None)
        if settings is not None and _auto_move_enabled(settings):
            try:
                _prime_auto_path_transform_signatures(scene)
            except Exception:
                pass


def _stop_legacy_live_update_timer():
    """Remove the one-off live timer used by the early Blender/Sionna prototype.

    That experimental script stored a timer in ``bpy.app.driver_namespace`` under
    this well-known key. If its TX object is later rebuilt by the add-on it keeps
    referencing removed RNA and can spam ``StructRNA ... has been removed``.
    Version 1.3 cleans it up automatically; the add-on's Dynamic Mode replaces it.
    """
    key = "_sionna_blender_live_timer"
    timer = bpy.app.driver_namespace.pop(key, None)
    if timer is None:
        return False
    try:
        if bpy.app.timers.is_registered(timer):
            bpy.app.timers.unregister(timer)
    except Exception:
        pass
    return True


def _any_dynamic_mode_enabled():
    # During extension registration Blender temporarily exposes ``bpy.data`` as
    # ``_RestrictData``. Accessing ``bpy.data.scenes`` in that phase raises an
    # AttributeError. Treat that short registration window as "not ready yet";
    # _post_register_init_timer() will retry once normal BlendData is available.
    scenes = getattr(bpy.data, "scenes", None)
    if scenes is None:
        return False
    try:
        scene_iter = list(scenes)
    except (AttributeError, ReferenceError, RuntimeError):
        return False
    for scene in scene_iter:
        settings = getattr(scene, "sionna_bridge", None)
        if settings is not None and _dynamic_mode_enabled(settings):
            return True
    return False


def _sync_dynamic_mode_handlers():
    """Register movement listeners only while at least one scene uses Dynamic Mode."""
    enabled = _any_dynamic_mode_enabled()
    handlers = bpy.app.handlers.depsgraph_update_post
    dynamic_handlers = (
        _device_representation_depsgraph_update,
        _auto_path_depsgraph_update,
    )
    if enabled:
        for handler in dynamic_handlers:
            if handler not in handlers:
                handlers.append(handler)
    else:
        for handler in dynamic_handlers:
            if handler in handlers:
                handlers.remove(handler)
        _clear_auto_path_scene_state()
        try:
            if bpy.app.timers.is_registered(_auto_path_compute_timer):
                bpy.app.timers.unregister(_auto_path_compute_timer)
        except Exception:
            pass
    return enabled


def _find_environment(scene):
    env = _collection_child(scene.collection, _ENV_COLLECTION)
    if env is None:
        return None
    scene_collection = _collection_child(env, _SCENE_COLLECTION)
    procedural_geometry = _collection_child(scene_collection, _PROCEDURAL_COLLECTION) if scene_collection else None
    devices = _collection_child(env, _DEVICES_COLLECTION)
    device_representations = _collection_child_by_role(
        env, _DEVICE_REPRESENTATION_COLLECTION, "device_representations"
    )
    representation_txs = (
        _collection_child_by_role(
            device_representations,
            _DEVICE_REPRESENTATION_TX_COLLECTION,
            "device_representation_transmitters",
        )
        if device_representations else None
    )
    representation_rxs = (
        _collection_child_by_role(
            device_representations,
            _DEVICE_REPRESENTATION_RX_COLLECTION,
            "device_representation_receivers",
        )
        if device_representations else None
    )
    simulated_paths = _collection_child(env, _PATHS_COLLECTION)
    radio_maps = _collection_child(env, _RADIO_MAPS_COLLECTION)
    radio_maps_3d = _collection_child(env, _RADIO_MAPS_3D_COLLECTION)
    txs = _collection_child(devices, _TX_COLLECTION) if devices else None
    rxs = _collection_child(devices, _RX_COLLECTION) if devices else None
    if not all((scene_collection, procedural_geometry, devices, simulated_paths, radio_maps, radio_maps_3d, txs, rxs)):
        return None
    return {
        "env": env,
        "scene": scene_collection,
        "procedural_geometry": procedural_geometry,
        "devices": devices,
        "txs": txs,
        "rxs": rxs,
        "device_representations": device_representations,
        "representation_txs": representation_txs,
        "representation_rxs": representation_rxs,
        "simulated_paths": simulated_paths,
        "radio_maps": radio_maps,
        "radio_maps_3d": radio_maps_3d,
    }


def _ensure_environment(scene, migrate=True):
    """Create and repair the Sionna workflow collection hierarchy."""
    env = _ensure_collection_datablock(_ENV_COLLECTION)
    scene_collection = _ensure_collection_datablock(_SCENE_COLLECTION)
    procedural_geometry = _ensure_collection_datablock(_PROCEDURAL_COLLECTION)
    devices = _ensure_collection_datablock(_DEVICES_COLLECTION)
    txs = _ensure_collection_datablock(_TX_COLLECTION)
    rxs = _ensure_collection_datablock(_RX_COLLECTION)
    device_representations = _ensure_child_collection(
        env, _DEVICE_REPRESENTATION_COLLECTION, "device_representations"
    )
    representation_txs = _ensure_child_collection(
        device_representations,
        _DEVICE_REPRESENTATION_TX_COLLECTION,
        "device_representation_transmitters",
    )
    representation_rxs = _ensure_child_collection(
        device_representations,
        _DEVICE_REPRESENTATION_RX_COLLECTION,
        "device_representation_receivers",
    )
    simulated_paths = _ensure_collection_datablock(_PATHS_COLLECTION)
    radio_maps = _ensure_collection_datablock(_RADIO_MAPS_COLLECTION)
    radio_maps_3d = _ensure_collection_datablock(_RADIO_MAPS_3D_COLLECTION)

    _link_collection(scene.collection, env)
    _link_collection(env, scene_collection)
    _link_collection(scene_collection, procedural_geometry)
    _link_collection(env, devices)
    _link_collection(env, device_representations)
    _link_collection(device_representations, representation_txs)
    _link_collection(device_representations, representation_rxs)
    _link_collection(env, simulated_paths)
    _link_collection(env, radio_maps)
    _link_collection(env, radio_maps_3d)
    _link_collection(devices, txs)
    _link_collection(devices, rxs)

    # Keep the workflow hierarchy unambiguous in the active scene.
    for child in (scene_collection, procedural_geometry, devices, device_representations, representation_txs, representation_rxs, simulated_paths, radio_maps, radio_maps_3d, txs, rxs):
        _unlink_collection(scene.collection, child)
    for child in (procedural_geometry, txs, rxs, representation_txs, representation_rxs):
        _unlink_collection(env, child)
    _unlink_collection(devices, device_representations)

    env["sionna_collection_role"] = "environment"
    scene_collection["sionna_collection_role"] = "scene"
    procedural_geometry["sionna_collection_role"] = "procedural_geometry"
    devices["sionna_collection_role"] = "devices"
    txs["sionna_collection_role"] = "transmitters"
    rxs["sionna_collection_role"] = "receivers"
    device_representations["sionna_collection_role"] = "device_representations"
    representation_txs["sionna_collection_role"] = "device_representation_transmitters"
    representation_rxs["sionna_collection_role"] = "device_representation_receivers"
    device_representations.hide_render = True
    representation_txs.hide_render = True
    representation_rxs.hide_render = True
    simulated_paths["sionna_collection_role"] = "simulated_paths"
    radio_maps["sionna_collection_role"] = "radio_maps"
    radio_maps_3d["sionna_collection_role"] = "radio_maps_3d"

    if migrate:
        # Existing tagged devices are automatically organized when upgrading.
        for obj in list(scene.objects):
            role = str(obj.get("sionna_role", "")).upper()
            if role == "TX":
                _move_object_to_collection(obj, txs)
            elif role == "RX":
                _move_object_to_collection(obj, rxs)

        # Migrate legacy imported path curves from bridge 0.4 and earlier.
        legacy = bpy.data.collections.get(_LEGACY_RESULT_COLLECTION)
        if legacy is not None and legacy != simulated_paths:
            for obj in list(legacy.objects):
                _move_object_to_collection(obj, simulated_paths)

    return {
        "env": env,
        "scene": scene_collection,
        "procedural_geometry": procedural_geometry,
        "devices": devices,
        "txs": txs,
        "rxs": rxs,
        "device_representations": device_representations,
        "representation_txs": representation_txs,
        "representation_rxs": representation_rxs,
        "simulated_paths": simulated_paths,
        "radio_maps": radio_maps,
        "radio_maps_3d": radio_maps_3d,
    }


def _scene_export_objects(scene):
    workflow = _find_environment(scene)
    if workflow is None:
        raise RuntimeError("Create the Sionna environment first using Create Env")
    objects = [
        obj for obj in _collection_objects_recursive(workflow["scene"])
        if not obj.get("sionna_blender_only", False)
    ]
    if not objects:
        raise RuntimeError(
            "The sionna_env/scene collection is empty. Move the environment objects "
            "to that collection before exporting."
        )
    return objects


def _procedural_scene_objects(scene):
    workflow = _find_environment(scene)
    if workflow is None:
        return []
    return _collection_objects_recursive(workflow["procedural_geometry"])


def _procedural_scene_active(scene):
    settings = scene.sionna_bridge
    return bool(settings.procedural_geometry_enabled and _procedural_scene_objects(scene))


def _evaluated_procedural_geometry_stats(context, depsgraph=None):
    """Return compact frame-level descriptors of evaluated procedural meshes.

    Values are stored once per frame as result-object metadata, not duplicated
    on every simulation point. Surface area and volume use world coordinates.
    Volume is most reliable for closed, consistently oriented meshes.
    """
    objects = _procedural_scene_objects(context.scene)
    if depsgraph is None:
        depsgraph = context.evaluated_depsgraph_get()
    totals = {
        "object_count": len(objects),
        "mesh_object_count": 0,
        "vertex_count": 0,
        "edge_count": 0,
        "face_count": 0,
        "surface_area_m2": 0.0,
        "volume_m3": 0.0,
    }
    minimum = [math.inf, math.inf, math.inf]
    maximum = [-math.inf, -math.inf, -math.inf]
    sampled_vertices = 0
    signature = hashlib.sha256()

    for source_obj in objects:
        try:
            obj = source_obj.evaluated_get(depsgraph)
        except Exception:
            obj = source_obj
        if getattr(obj, "type", "") != "MESH":
            continue
        mesh = None
        try:
            mesh = obj.to_mesh(preserve_all_data_layers=False, depsgraph=depsgraph)
            if mesh is None:
                continue
            totals["mesh_object_count"] += 1
            totals["vertex_count"] += len(mesh.vertices)
            totals["edge_count"] += len(mesh.edges)
            totals["face_count"] += len(mesh.polygons)
            matrix = obj.matrix_world
            coordinates = [matrix @ vertex.co for vertex in mesh.vertices]
            sampled_vertices += len(coordinates)
            signature.update(str(source_obj.name).encode("utf-8", errors="replace"))
            signature.update(
                f"|{len(mesh.vertices)}|{len(mesh.edges)}|{len(mesh.polygons)}|".encode("ascii")
            )
            sample_step = max(1, len(coordinates) // 4096)
            for co in coordinates[::sample_step]:
                signature.update(
                    f"{float(co.x):.6g},{float(co.y):.6g},{float(co.z):.6g};".encode("ascii")
                )
            for co in coordinates:
                minimum[0] = min(minimum[0], float(co.x))
                minimum[1] = min(minimum[1], float(co.y))
                minimum[2] = min(minimum[2], float(co.z))
                maximum[0] = max(maximum[0], float(co.x))
                maximum[1] = max(maximum[1], float(co.y))
                maximum[2] = max(maximum[2], float(co.z))

            mesh.calc_loop_triangles()
            signed_volume = 0.0
            surface_area = 0.0
            for triangle in mesh.loop_triangles:
                i0, i1, i2 = triangle.vertices
                a, b, c = coordinates[i0], coordinates[i1], coordinates[i2]
                surface_area += 0.5 * (b - a).cross(c - a).length
                signed_volume += a.dot(b.cross(c)) / 6.0
            totals["surface_area_m2"] += float(surface_area)
            totals["volume_m3"] += abs(float(signed_volume))
        except Exception:
            # Diagnostic statistics must never block scene export or simulation.
            continue
        finally:
            if mesh is not None:
                try:
                    obj.to_mesh_clear()
                except Exception:
                    pass

    if sampled_vertices:
        size = [maximum[i] - minimum[i] for i in range(3)]
        center = [(maximum[i] + minimum[i]) * 0.5 for i in range(3)]
    else:
        minimum = [0.0, 0.0, 0.0]
        maximum = [0.0, 0.0, 0.0]
        size = [0.0, 0.0, 0.0]
        center = [0.0, 0.0, 0.0]
    totals.update({
        "bbox_min_x": minimum[0], "bbox_min_y": minimum[1], "bbox_min_z": minimum[2],
        "bbox_max_x": maximum[0], "bbox_max_y": maximum[1], "bbox_max_z": maximum[2],
        "bbox_center_x": center[0], "bbox_center_y": center[1], "bbox_center_z": center[2],
        "bbox_size_x": size[0], "bbox_size_y": size[1], "bbox_size_z": size[2],
        "bbox_volume_m3": size[0] * size[1] * size[2],
        "geometry_signature": signature.hexdigest()[:16],
    })
    return totals


def _procedural_stats_for_payload(context, depsgraph):
    settings = context.scene.sionna_bridge
    if not (
        settings.procedural_capture_analytics
        and _procedural_scene_active(context.scene)
    ):
        return None
    return _evaluated_procedural_geometry_stats(context, depsgraph)


def _procedural_scene_frames(context):
    settings = context.scene.sionna_bridge
    if settings.timeline_mode == "CURRENT":
        return [int(context.scene.frame_current)]
    return _frame_range(context.scene, settings.timeline_step)


def _scene_xml_for_frame(scene_source, frame):
    if isinstance(scene_source, dict):
        value = scene_source.get(int(frame))
        if value is None:
            value = scene_source.get(str(int(frame)))
        if value is None:
            raise RuntimeError(f"No successful procedural scene export exists for frame {int(frame)}")
        return Path(value)
    return Path(scene_source)


def _attach_scene_sources(frame_payloads, scene_source):
    """Attach exact scene files and drop frames whose procedural export failed.

    A procedural scene mapping only contains frames that exported successfully.
    Never substitute another frame's geometry, because doing so would silently
    associate RF results with the wrong procedural state.
    """
    if isinstance(scene_source, dict):
        available = {int(key) for key in scene_source.keys()}
        frame_payloads[:] = [
            payload for payload in frame_payloads
            if int(payload.get("frame", -1)) in available
        ]
        if not frame_payloads:
            raise RuntimeError(
                "No simulation frames remain after filtering failed procedural scene exports"
            )

    for payload in frame_payloads:
        path = _scene_xml_for_frame(scene_source, payload["frame"])
        if not path.is_file():
            raise RuntimeError(f"Scene XML is missing for frame {payload['frame']}: {path}")
        payload["scene_xml"] = str(path)
        payload["scene_xml_sha256"] = _sha256(path)
    return frame_payloads


@contextmanager
def _temporary_export_selection(context, objects):
    """Select only the scene-collection objects, then restore user selection."""
    view_layer = context.view_layer
    view_objects = {obj.as_pointer(): obj for obj in view_layer.objects}
    unavailable = [obj.name for obj in objects if obj.as_pointer() not in view_objects]
    if unavailable:
        preview = ", ".join(unavailable[:5])
        suffix = "..." if len(unavailable) > 5 else ""
        raise RuntimeError(
            "Some objects in sionna_env/scene are excluded from the active View Layer: "
            f"{preview}{suffix}. Enable the collection before export."
        )

    selected_before = [obj for obj in view_layer.objects if obj.select_get()]
    active_before = view_layer.objects.active
    hide_select_before = {obj.as_pointer(): bool(obj.hide_select) for obj in objects}

    try:
        for obj in view_layer.objects:
            if obj.select_get():
                obj.select_set(False)
        for obj in objects:
            obj.hide_select = False
            obj.select_set(True)
        view_layer.objects.active = objects[0]
        yield
    finally:
        for obj in objects:
            try:
                obj.select_set(False)
                obj.hide_select = hide_select_before.get(obj.as_pointer(), obj.hide_select)
            except (ReferenceError, RuntimeError):
                pass
        for obj in selected_before:
            try:
                obj.select_set(True)
            except (ReferenceError, RuntimeError):
                pass
        try:
            view_layer.objects.active = active_before
        except (ReferenceError, RuntimeError):
            pass


def _workspace(settings):
    """Return a writable workspace path for Sionna run/cache files.

    Blender's ``//`` prefix means "relative to the current .blend file".
    When a file has not been saved yet, ``bpy.path.abspath("//...")`` may
    resolve relative to Blender's process working directory. On Windows that
    is commonly the protected ``Program Files/Blender Foundation/...``
    directory, which produces WinError 5 when the bridge tries to create its
    cache. For an unsaved file, resolve ``//`` paths relative to the user's
    home directory instead. Once the .blend is saved, normal Blender-relative
    path semantics are preserved.
    """
    raw = settings.workspace_dir.strip()
    if raw:
        if raw.startswith("//") and not bpy.data.filepath:
            relative = raw[2:].lstrip("/\\")
            return (Path.home() / (relative or "sionna_runs")).resolve()
        return _absolute_path(raw)
    if bpy.data.filepath:
        return Path(bpy.data.filepath).resolve().parent / "sionna_runs"
    return Path.home() / "sionna_runs"


def _python_path_candidates(path):
    """Yield likely Python executables for a file, environment, or project path."""
    if path.is_file():
        yield path
        return

    if not path.is_dir():
        return

    # Conda environments commonly place python.exe in the environment root.
    # Standard venvs use Scripts/python.exe on Windows and bin/python elsewhere.
    relative_candidates = (
        "python.exe",
        "python3.exe",
        "Scripts/python.exe",
        "Scripts/python3.exe",
        "bin/python",
        "bin/python3",
        ".venv/Scripts/python.exe",
        ".venv/bin/python",
        "venv/Scripts/python.exe",
        "venv/bin/python",
        "env/Scripts/python.exe",
        "env/bin/python",
    )
    for relative in relative_candidates:
        yield path / relative


def _runtime_mode(settings):
    """Return the configured Sionna execution runtime.

    BLENDER is the Blender 5.2 default: simulations are still executed in
    isolated worker processes so the UI stays responsive, but those workers
    use Blender's bundled Python instead of requiring a second Python install.
    EXTERNAL preserves the legacy Blender 5.0 workflow.
    """
    mode = str(getattr(settings, "runtime_mode", "BLENDER") or "BLENDER").upper()
    return mode if mode in {"BLENDER", "EXTERNAL"} else "BLENDER"


def _blender_python_candidates():
    """Yield likely standalone Python executables for this Blender build."""
    seen = set()

    def emit(value):
        if not value:
            return
        try:
            candidate = Path(value).expanduser()
            key = os.path.normcase(os.path.abspath(str(candidate)))
        except Exception:
            return
        if key in seen:
            return
        seen.add(key)
        yield candidate

    yield from emit(sys.executable)

    for prefix in (getattr(sys, "prefix", ""), getattr(sys, "base_prefix", "")):
        if not prefix:
            continue
        root = Path(prefix)
        for relative in (
            "python.exe",
            "python3.exe",
            "Scripts/python.exe",
            "Scripts/python3.exe",
            "bin/python",
            "bin/python3",
        ):
            yield from emit(root / relative)

    # Blender 5.x normally reports the bundled interpreter through
    # sys.executable. This final fallback covers layouts where only the Blender
    # binary location is available.
    blender_binary = str(getattr(bpy.app, "binary_path", "") or "")
    if blender_binary:
        blender_root = Path(blender_binary).resolve().parent
        version_string = f"{bpy.app.version[0]}.{bpy.app.version[1]}"
        for relative in (
            f"{version_string}/python/bin/python.exe",
            f"{version_string}/python/bin/python3.exe",
            f"{version_string}/python/bin/python",
            f"{version_string}/python/bin/python3",
        ):
            yield from emit(blender_root / relative)


def _resolve_blender_python_executable():
    for candidate in _blender_python_candidates():
        try:
            if not candidate.is_file():
                continue
        except OSError:
            continue
        name = candidate.name.lower()
        if os.name == "nt" and name not in {"python.exe", "python3.exe"}:
            continue
        if os.name != "nt" and not os.access(candidate, os.X_OK):
            continue
        return candidate.resolve(), ""
    return None, (
        "Could not locate Blender's bundled Python interpreter. "
        "Expected Blender 5.2 to expose python through sys.executable."
    )


def _site_packages_candidates(path):
    """Yield site-packages directories from a site path or virtualenv root."""
    if not path:
        return
    try:
        root = Path(path).expanduser()
    except Exception:
        return
    if root.is_file():
        root = root.parent
    candidates = [root, root / "Lib" / "site-packages"]
    try:
        candidates.extend(sorted((root / "lib").glob("python*/site-packages")))
    except Exception:
        pass
    seen = set()
    for candidate in candidates:
        try:
            key = os.path.normcase(os.path.abspath(str(candidate)))
        except Exception:
            continue
        if key in seen:
            continue
        seen.add(key)
        yield candidate


def _sionna_site_packages_candidates(settings):
    """Yield locations that may contain the already-installed Sionna package."""
    configured = str(getattr(settings, "sionna_site_packages", "") or "").strip()
    if configured:
        try:
            yield from _site_packages_candidates(_absolute_path(configured))
        except Exception:
            yield from _site_packages_candidates(configured)

    env_path = os.environ.get("SIONNA_SITE_PACKAGES", "").strip()
    if env_path:
        yield from _site_packages_candidates(env_path)

    # If Sionna is already importable in Blender, reuse the site-packages root
    # that provided it. find_spec avoids importing the CUDA stack just to probe.
    try:
        spec = importlib.util.find_spec("sionna")
    except Exception:
        spec = None
    if spec is not None:
        locations = list(spec.submodule_search_locations or [])
        if spec.origin:
            locations.append(str(Path(spec.origin).parent))
        for location in locations:
            package_dir = Path(location)
            yield package_dir.parent

    for entry in sys.path:
        if not entry:
            continue
        try:
            candidate = Path(entry)
            if (candidate / "sionna" / "__init__.py").is_file():
                yield candidate
        except Exception:
            pass

    # Migration convenience for the Blender 5.2 setup used by the bridge's
    # installation guide: Blender's Python creates a dedicated Sionna venv in
    # the user's home directory, and Blender only borrows its site-packages.
    home = Path.home()
    conventional_roots = (
        home / "blender52-sionna",
        home / "blender5-sionna",
        home / "sionna",
    )
    for root in conventional_roots:
        yield from _site_packages_candidates(root)


def _resolve_sionna_site_packages(settings):
    seen = set()
    for candidate in _sionna_site_packages_candidates(settings):
        try:
            candidate = candidate.resolve()
            key = os.path.normcase(str(candidate))
            if key in seen:
                continue
            seen.add(key)
            if (candidate / "sionna" / "__init__.py").is_file():
                return candidate
        except (OSError, RuntimeError):
            continue
    return None


def _resolve_python_executable(settings):
    """Resolve the Python used by simulation workers.

    Blender 5.2 mode uses Blender's bundled Python automatically and only needs
    access to the site-packages directory where Sionna is installed. Legacy
    external-Python mode retains the original Blender 5.0 behavior.
    """
    if _runtime_mode(settings) == "BLENDER":
        executable, error = _resolve_blender_python_executable()
        if executable is None:
            return None, error
        if _resolve_sionna_site_packages(settings) is None:
            return None, (
                "Sionna is not discoverable for Blender Python. Install Sionna "
                "for Blender 5.2 or select its site-packages/virtualenv folder "
                "in Sionna Runtime."
            )
        return executable, ""

    value = str(getattr(settings, "sionna_python", "") or "").strip()
    if not value:
        return None, "Select the external Sionna environment's python.exe"

    configured = _absolute_path(value)
    for candidate in _python_path_candidates(configured):
        try:
            if not candidate.is_file():
                continue
        except OSError:
            continue

        name = candidate.name.lower()
        if name in {"blender.exe", "blender-launcher.exe"}:
            return None, "Select the Sionna environment's python.exe, not Blender's executable"
        if os.name == "nt" and name not in {"python.exe", "python3.exe"}:
            continue
        if os.name != "nt" and not os.access(candidate, os.X_OK):
            continue
        return candidate.resolve(), ""

    if configured.is_dir():
        return None, (
            f"No Python executable found in '{configured}'. Select the environment folder "
            "or its python.exe (for a Windows venv: Scripts\\python.exe)."
        )
    if configured.exists():
        return None, f"'{configured}' is not a supported Python executable"
    return None, f"Configured Python path does not exist: {configured}"

def _python_executable(settings):
    executable, _ = _resolve_python_executable(settings)
    return executable


def _drjit_libllvm_candidates(settings, python_executable=None):
    """Yield likely LLVM-C.dll locations for Dr.Jit's Windows CPU backend."""
    seen = set()

    def emit(path):
        if not path:
            return
        try:
            candidate = Path(path).expanduser()
            if candidate.is_dir():
                candidate = candidate / "LLVM-C.dll"
            key = os.path.normcase(os.path.abspath(str(candidate)))
        except Exception:
            return
        if key in seen:
            return
        seen.add(key)
        yield candidate

    configured = str(getattr(settings, "drjit_libllvm_path", "") or "").strip()
    if configured:
        try:
            yield from emit(_absolute_path(configured))
        except Exception:
            yield from emit(configured)

    yield from emit(os.environ.get("DRJIT_LIBLLVM_PATH", ""))
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if entry.strip():
            yield from emit(Path(entry) / "LLVM-C.dll")

    executable = Path(python_executable) if python_executable else None
    if executable:
        try:
            executable = executable.resolve()
            env_root = executable.parent.parent if executable.parent.name.lower() == "scripts" else executable.parent
            for relative in (
                "LLVM-C.dll",
                "bin/LLVM-C.dll",
                "Library/bin/LLVM-C.dll",
                "Lib/site-packages/LLVM-C.dll",
            ):
                yield from emit(env_root / relative)
        except Exception:
            pass

    if os.name == "nt":
        for root in (
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramW6432"),
            os.environ.get("ProgramFiles(x86)"),
        ):
            if root:
                yield from emit(Path(root) / "LLVM" / "bin" / "LLVM-C.dll")
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            yield from emit(Path(local_app_data) / "Programs" / "LLVM" / "bin" / "LLVM-C.dll")
        user_profile = os.environ.get("USERPROFILE")
        if user_profile:
            yield from emit(Path(user_profile) / "scoop" / "apps" / "llvm" / "current" / "bin" / "LLVM-C.dll")


def _resolve_drjit_libllvm(settings, python_executable=None):
    for candidate in _drjit_libllvm_candidates(settings, python_executable):
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            continue
    return None


def _sionna_worker_environment(settings, python_executable=None):
    """Build the worker environment for Blender-Python or legacy runtimes.

    In Blender 5.2 mode the simulation worker uses Blender's bundled Python.
    When Sionna lives in a dedicated venv, its site-packages directory is
    prepended through PYTHONPATH so the worker sees the same Sionna stack
    without requiring the user to select that venv's python.exe.
    """
    env = os.environ.copy()

    if _runtime_mode(settings) == "BLENDER":
        site_packages = _resolve_sionna_site_packages(settings)
        if site_packages is not None:
            site_text = str(site_packages)
            existing = [entry for entry in env.get("PYTHONPATH", "").split(os.pathsep) if entry]
            normalized = {os.path.normcase(os.path.abspath(entry)) for entry in existing}
            if os.path.normcase(os.path.abspath(site_text)) not in normalized:
                env["PYTHONPATH"] = site_text + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    libllvm = _resolve_drjit_libllvm(settings, python_executable)
    if libllvm is not None:
        env["DRJIT_LIBLLVM_PATH"] = str(libllvm)
        llvm_dir = str(libllvm.parent)
        path_entries = [entry for entry in env.get("PATH", "").split(os.pathsep) if entry]
        normalized = {os.path.normcase(os.path.abspath(entry)) for entry in path_entries}
        if os.path.normcase(os.path.abspath(llvm_dir)) not in normalized:
            env["PATH"] = llvm_dir + (os.pathsep + env["PATH"] if env.get("PATH") else "")
    return env, libllvm



def _pid_is_running(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # The process exists but belongs to another security context.
        return True
    except OSError:
        return False
    return True


def _active_run_lock_path(settings):
    return _workspace(settings) / ".sionna_rt_bridge_active_run.json"


def _check_stale_or_active_lock(settings):
    lock_path = _active_run_lock_path(settings)
    payload = _load_json_file(lock_path, attempts=2)
    pid = int(payload.get("pid", 0) or 0) if payload else 0
    if pid and _pid_is_running(pid):
        run_type = payload.get("run_type", "Sionna")
        run_dir = payload.get("run_dir", "")
        raise RuntimeError(
            f"A {run_type} worker is already running (PID {pid}). "
            f"Wait for it to finish before starting another run. Run folder: {run_dir}"
        )
    if lock_path.exists():
        try:
            lock_path.unlink()
        except OSError:
            pass
    return lock_path


def _write_active_run_lock(settings, process, run_type, run_dir):
    lock_path = _active_run_lock_path(settings)
    payload = {
        "pid": int(process.pid),
        "run_type": str(run_type),
        "run_dir": str(run_dir),
        "created_utc": _now_utc(),
    }
    temporary = lock_path.with_name(lock_path.name + f".{os.getpid()}.tmp")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError:
            pass
    last_error = None
    for attempt in range(10):
        try:
            os.replace(temporary, lock_path)
            return lock_path
        except (PermissionError, OSError) as exc:
            last_error = exc
            time.sleep(0.05 * (attempt + 1))
    try:
        process.terminate()
        process.wait(timeout=5)
    except Exception:
        pass
    try:
        temporary.unlink(missing_ok=True)
    except Exception:
        pass
    raise RuntimeError(f"Could not create the active-run lock: {last_error}")


def _release_active_run_lock(lock_path, pid=0):
    if not lock_path:
        return
    path = Path(lock_path)
    try:
        payload = _load_json_file(path, attempts=2)
        lock_pid = int(payload.get("pid", 0) or 0) if payload else 0
        if int(pid or 0) and lock_pid and int(pid) != lock_pid:
            return
        path.unlink(missing_ok=True)
    except Exception:
        pass


def _popen_with_retries(command, *, cwd, stdout, creationflags, env=None, attempts=4):
    last_error = None
    for attempt in range(max(1, int(attempts))):
        try:
            return subprocess.Popen(
                command,
                cwd=str(cwd),
                stdout=stdout,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=creationflags,
                env=env,
            )
        except PermissionError as exc:
            last_error = exc
            if attempt + 1 >= attempts:
                break
            time.sleep(0.15 * (attempt + 1))
    if last_error is not None:
        raise last_error
    raise RuntimeError("Could not launch the Sionna simulation worker")


def _tail_text(path, max_lines=30, max_chars=12000):
    path = Path(path)
    if not path.is_file():
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
    except Exception as exc:
        return f"Could not read log: {exc}"
    text = "".join(lines[-max(1, int(max_lines)):]).strip()
    if len(text) > max_chars:
        text = text[-max_chars:]
    return text


def _failure_details(label, return_code, status_payload, run_dir, log_name):
    run_dir = Path(run_dir)
    parts = [
        f"Output: {label}",
        f"Worker exit code: {return_code}",
        f"Worker state: {status_payload.get('state', 'missing')}",
        f"Run folder: {run_dir}",
        f"Status file: {run_dir / 'status.json'}",
        f"Log file: {run_dir / log_name}",
    ]
    error = str(status_payload.get("error", "") or "").strip()
    if error:
        parts.append("Error: " + error)
    tb = str(status_payload.get("traceback", "") or "").strip()
    if tb:
        parts.append("Traceback:\n" + tb)
    tail = _tail_text(run_dir / log_name)
    if tail:
        parts.append("Log tail:\n" + tail)
    return "\n".join(parts)


def _set_status(settings, summary, details="", *, run_dir="", log_path=""):
    settings.last_status = str(summary)
    settings.last_status_details = str(details or "")
    if run_dir:
        settings.last_status_run_dir = str(run_dir)
    if log_path:
        settings.last_status_log_path = str(log_path)


def _subprocess_creationflags():
    # Keep the simulation worker silent on Windows; all output is written to its log.
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        return subprocess.CREATE_NO_WINDOW
    return 0


def _device_objects(scene, role):
    return sorted(
        [
            obj for obj in scene.objects
            if obj.get("sionna_role", "") == role
        ],
        key=lambda obj: obj.name,
    )


def _poll_motion_template_device(_settings, obj):
    """Only marked TX/RX objects can be associated with a motion template."""
    try:
        return str(obj.get("sionna_role", "")).upper() in {"TX", "RX"}
    except Exception:
        return False


def _poll_motion_template_pointcloud(_settings, obj):
    """Only Blender PointCloud objects can be used as index-driven motion paths."""
    try:
        return obj is not None and obj.type == "POINTCLOUD" and obj.data is not None
    except Exception:
        return False


def _motion_template_collection(scene):
    """Return/create the Blender-only helper collection for sweep templates."""
    workflow = _ensure_environment(scene, migrate=True)
    collection = _ensure_child_collection(
        workflow["devices"], _MOTION_TEMPLATES_COLLECTION, "motion_templates"
    )
    collection.hide_render = True
    collection["sionna_blender_only"] = True
    return collection


def _sweep_template_object(device):
    name = str(device.get("sionna_sweep_template", "") or "")
    obj = bpy.data.objects.get(name) if name else None
    if obj is not None and bool(obj.get("sionna_motion_template", False)):
        return obj
    return None


def _sweep_anchor_object(device):
    name = str(device.get("sionna_sweep_anchor", "") or "")
    obj = bpy.data.objects.get(name) if name else None
    if obj is not None and bool(obj.get("sionna_motion_anchor", False)):
        return obj
    return None


def _sweep_source_object(device):
    """Return the external source object used by a motion template, if any."""
    if device is None:
        return None
    name = str(device.get("sionna_sweep_source", "") or "")
    return bpy.data.objects.get(name) if name else None


def _sweep_constraint(device):
    for constraint in device.constraints:
        if constraint.name == "Sionna Motion Template":
            return constraint
    return None


def _remove_motion_template_for_device(device, preserve_world_position=True):
    """Disconnect and remove only helper data created by this add-on."""
    if device is None:
        return False
    world_matrix = None
    if preserve_world_position:
        try:
            world_matrix = device.matrix_world.copy()
        except Exception:
            world_matrix = None

    constraint = _sweep_constraint(device)
    if constraint is not None:
        try:
            device.constraints.remove(constraint)
        except Exception:
            pass

    anchor = _sweep_anchor_object(device)
    template = _sweep_template_object(device)
    for obj in (anchor, template):
        if obj is None:
            continue
        data = getattr(obj, "data", None)
        try:
            bpy.data.objects.remove(obj, do_unlink=True)
        except Exception:
            continue
        if isinstance(data, bpy.types.Mesh) and getattr(data, "users", 1) == 0:
            try:
                bpy.data.meshes.remove(data)
            except Exception:
                pass

    for key in (
        "sionna_sweep_template",
        "sionna_sweep_anchor",
        "sionna_sweep_source",
        "sionna_sweep_style",
        "sionna_sweep_start_frame",
        "sionna_sweep_end_frame",
        "sionna_sweep_point_count",
    ):
        if key in device:
            try:
                del device[key]
            except Exception:
                pass

    if world_matrix is not None:
        try:
            device.matrix_world = world_matrix
        except Exception:
            pass
    try:
        _sync_pointcloud_motion_handler()
    except NameError:
        pass
    return constraint is not None or anchor is not None or template is not None


def _grid_sweep_points(rows, columns, row_spacing, column_spacing):
    """Create centered XY grid samples in a serpentine frame order."""
    rows = max(1, int(rows))
    columns = max(1, int(columns))
    row_spacing = float(row_spacing)
    column_spacing = float(column_spacing)
    x0 = -0.5 * (columns - 1) * column_spacing
    y0 = -0.5 * (rows - 1) * row_spacing
    result = []
    for row in range(rows):
        column_indices = range(columns) if row % 2 == 0 else range(columns - 1, -1, -1)
        for column in column_indices:
            result.append((
                (x0 + column * column_spacing, y0 + row * row_spacing, 0.0),
                row,
                column,
            ))
    return result


def _set_grid_point_attributes(mesh, samples, start_frame):
    """Attach frame/row/column metadata when the Blender mesh API supports it."""
    try:
        for attr_name, values in (
            ("sionna_frame", [int(start_frame) + i for i in range(len(samples))]),
            ("sionna_row", [int(item[1]) for item in samples]),
            ("sionna_column", [int(item[2]) for item in samples]),
        ):
            existing = mesh.attributes.get(attr_name)
            if existing is not None:
                mesh.attributes.remove(existing)
            attr = mesh.attributes.new(name=attr_name, type="INT", domain="POINT")
            for index, value in enumerate(values):
                attr.data[index].value = int(value)
    except Exception:
        # Attributes are useful metadata, not required for motion.
        pass


def _create_grid_motion_template(context, device, settings):
    """Create a movable grid helper and constrain a TX/RX to its frame samples."""
    if device is None:
        raise RuntimeError("Choose a TX or RX to associate with the grid")
    role = str(device.get("sionna_role", "")).upper()
    if role not in {"TX", "RX"}:
        raise RuntimeError("The associated object must be marked as a TX or RX")

    rows = max(1, int(settings.motion_template_grid_rows))
    columns = max(1, int(settings.motion_template_grid_columns))
    row_spacing = max(1e-6, float(settings.motion_template_grid_row_spacing))
    column_spacing = max(1e-6, float(settings.motion_template_grid_column_spacing))
    start_frame = int(settings.motion_template_start_frame)
    samples = _grid_sweep_points(rows, columns, row_spacing, column_spacing)
    end_frame = start_frame + len(samples) - 1

    # Rebuilding an existing template uses the device's current evaluated position
    # as the center of the replacement grid.
    try:
        depsgraph = context.evaluated_depsgraph_get()
        center = device.evaluated_get(depsgraph).matrix_world.translation.copy()
    except Exception:
        center = device.matrix_world.translation.copy()
    _remove_motion_template_for_device(device, preserve_world_position=True)

    collection = _motion_template_collection(context.scene)
    base = _sanitize_name(_device_base_name(device.name, role))
    mesh = bpy.data.meshes.new(f"Sionna_Grid_{base}_Mesh")
    mesh.from_pydata([item[0] for item in samples], [], [])
    mesh.update()
    _set_grid_point_attributes(mesh, samples, start_frame)

    grid = bpy.data.objects.new(f"Sionna_Grid_{base}", mesh)
    collection.objects.link(grid)
    grid.location = center
    grid.show_in_front = True
    grid.display_type = "WIRE"
    grid.color = (1.0, 0.45, 0.05, 1.0)
    grid["sionna_blender_only"] = True
    grid["sionna_motion_template"] = True
    grid["sionna_motion_style"] = "GRID"
    grid["sionna_motion_device"] = device.name
    grid["sionna_motion_device_role"] = role
    grid["sionna_motion_rows"] = rows
    grid["sionna_motion_columns"] = columns
    grid["sionna_motion_row_spacing"] = row_spacing
    grid["sionna_motion_column_spacing"] = column_spacing
    grid["sionna_motion_start_frame"] = start_frame
    grid["sionna_motion_end_frame"] = end_frame
    grid["sionna_motion_point_count"] = len(samples)

    anchor = bpy.data.objects.new(f"Sionna_GridAnchor_{base}", None)
    collection.objects.link(anchor)
    anchor.empty_display_type = "PLAIN_AXES"
    anchor.empty_display_size = max(0.05, min(row_spacing, column_spacing) * 0.12)
    anchor.parent = grid
    anchor.matrix_parent_inverse = Matrix.Identity(4)
    anchor["sionna_blender_only"] = True
    anchor["sionna_motion_anchor"] = True
    anchor["sionna_motion_device"] = device.name
    anchor["sionna_motion_device_role"] = role
    anchor["sionna_motion_template"] = grid.name
    try:
        anchor.hide_set(True)
    except Exception:
        pass

    for index, sample in enumerate(samples):
        anchor.location = sample[0]
        anchor.keyframe_insert(
            data_path="location",
            frame=start_frame + index,
            group="Sionna Grid Sweep",
        )

    constraint = device.constraints.new(type="COPY_LOCATION")
    constraint.name = "Sionna Motion Template"
    constraint.target = anchor
    constraint.owner_space = "WORLD"
    constraint.target_space = "WORLD"

    device["sionna_sweep_template"] = grid.name
    device["sionna_sweep_anchor"] = anchor.name
    device["sionna_sweep_style"] = "GRID"
    device["sionna_sweep_start_frame"] = start_frame
    device["sionna_sweep_end_frame"] = end_frame
    device["sionna_sweep_point_count"] = len(samples)

    if bool(settings.motion_template_set_scene_range):
        context.scene.frame_start = start_frame
        context.scene.frame_end = end_frame
    else:
        context.scene.frame_start = min(int(context.scene.frame_start), start_frame)
        context.scene.frame_end = max(int(context.scene.frame_end), end_frame)

    try:
        for obj in context.selected_objects:
            obj.select_set(False)
        grid.select_set(True)
        context.view_layer.objects.active = grid
    except Exception:
        pass
    return grid, start_frame, end_frame, len(samples)


def _pointcloud_motion_devices(scene):
    """Return marked devices that use the live PointCloud index follower."""
    result = []
    try:
        objects = list(scene.objects)
    except (AttributeError, ReferenceError):
        return result
    for obj in objects:
        try:
            if str(obj.get("sionna_sweep_style", "")) != "POINT_CLOUD":
                continue
            if str(obj.get("sionna_role", "")).upper() not in {"TX", "RX"}:
                continue
            if not str(obj.get("sionna_sweep_source", "") or ""):
                continue
            result.append(obj)
        except (ReferenceError, AttributeError):
            continue
    return result


def _pointcloud_source_point_world(source, point_index, depsgraph=None):
    """Return one PointCloud sample in evaluated Blender-world coordinates."""
    source_eval = source
    try:
        if depsgraph is not None:
            candidate = source.evaluated_get(depsgraph)
            if candidate is not None and candidate.type == "POINTCLOUD" and candidate.data is not None:
                source_eval = candidate
    except Exception:
        source_eval = source

    points = source_eval.data.points
    if not points:
        raise RuntimeError(f"PointCloud {source.name} contains no points")
    point_index = max(0, min(int(point_index), len(points) - 1))
    point = points[point_index]
    return source_eval.matrix_world @ point.co, len(points)


def _set_object_world_translation(obj, world_co):
    """Set only an object's Blender-world translation, preserving rotation/scale."""
    matrix = obj.matrix_world.copy()
    matrix.translation = world_co
    obj.matrix_world = matrix
    try:
        obj.update_tag(refresh={"OBJECT"})
    except Exception:
        pass


def _apply_pointcloud_motion_for_device(scene, device, depsgraph=None):
    """Map the current scene frame to one PointCloud index and place the device."""
    source_name = str(device.get("sionna_sweep_source", "") or "")
    source = bpy.data.objects.get(source_name) if source_name else None
    if source is None or source.type != "POINTCLOUD" or source.data is None:
        return False

    start_frame = int(device.get("sionna_sweep_start_frame", 1))
    requested_index = int(scene.frame_current) - start_frame
    world_co, current_count = _pointcloud_source_point_world(
        source, requested_index, depsgraph=depsgraph
    )
    point_index = max(0, min(requested_index, current_count - 1))
    _set_object_world_translation(device, world_co)

    # Runtime diagnostics are intentionally tiny and numeric. They are useful
    # when verifying that the visible PointCloud and the TX/RX use the same
    # evaluated sample and coordinate space.
    device["sionna_sweep_current_index"] = int(point_index)
    device["sionna_sweep_current_world"] = [
        float(world_co.x), float(world_co.y), float(world_co.z)
    ]
    return True


@persistent
def _pointcloud_motion_frame_change(scene, depsgraph=None):
    """Live frame -> PointCloud index follower. Runs only on frame changes."""
    if scene is None:
        return
    for device in _pointcloud_motion_devices(scene):
        try:
            _apply_pointcloud_motion_for_device(scene, device, depsgraph=depsgraph)
        except (ReferenceError, AttributeError):
            continue
        except Exception:
            # Frame handlers must never make timeline playback unusable.
            traceback.print_exc()


def _sync_pointcloud_motion_handler():
    """Register the lightweight frame handler only while a PointCloud path exists."""
    handlers = bpy.app.handlers.frame_change_post
    need_handler = False
    scenes = getattr(bpy.data, "scenes", None)
    if scenes is not None:
        try:
            need_handler = any(_pointcloud_motion_devices(scene) for scene in scenes)
        except (AttributeError, ReferenceError):
            need_handler = False

    if need_handler:
        if _pointcloud_motion_frame_change not in handlers:
            handlers.append(_pointcloud_motion_frame_change)
    else:
        while _pointcloud_motion_frame_change in handlers:
            handlers.remove(_pointcloud_motion_frame_change)


def _create_pointcloud_motion_template(context, device, settings):
    """Drive a TX/RX live by PointCloud index: point i maps to start_frame + i."""
    if device is None:
        raise RuntimeError("Choose a TX or RX to associate with the PointCloud path")
    role = str(device.get("sionna_role", "")).upper()
    if role not in {"TX", "RX"}:
        raise RuntimeError("The associated object must be marked as a TX or RX")

    source = settings.motion_template_pointcloud
    if source is None:
        raise RuntimeError("Choose a PointCloud path with the eyedropper")
    if source.type != "POINTCLOUD" or source.data is None:
        raise RuntimeError("The path source must be a Blender PointCloud object")

    point_count = len(source.data.points)
    if point_count < 1:
        raise RuntimeError(f"PointCloud {source.name} contains no points")

    start_frame = int(settings.motion_template_start_frame)
    end_frame = start_frame + point_count - 1

    # Remove the old baked-anchor/constraint implementation if this device was
    # connected by an earlier add-on version. Preserve its current world pose.
    _remove_motion_template_for_device(device, preserve_world_position=True)
    collection = _motion_template_collection(context.scene)
    base = _sanitize_name(_device_base_name(device.name, role))

    # Keep one tiny metadata helper so the existing UI can detect/select/remove
    # a connected motion template. It has no transform role and no animation.
    helper = bpy.data.objects.new(f"Sionna_PointCloudPath_{base}", None)
    collection.objects.link(helper)
    helper.empty_display_type = "PLAIN_AXES"
    helper.empty_display_size = 0.1
    helper["sionna_blender_only"] = True
    helper["sionna_motion_template"] = True
    helper["sionna_motion_style"] = "POINT_CLOUD"
    helper["sionna_motion_device"] = device.name
    helper["sionna_motion_device_role"] = role
    helper["sionna_motion_source"] = source.name
    helper["sionna_motion_start_frame"] = start_frame
    helper["sionna_motion_end_frame"] = end_frame
    helper["sionna_motion_point_count"] = point_count
    helper["sionna_motion_mapping"] = "frame = start_frame + point_index"
    helper["sionna_motion_coordinate_space"] = "EVALUATED_WORLD"
    helper["sionna_motion_drive_mode"] = "LIVE_FRAME_INDEX"
    try:
        helper.hide_set(True)
    except Exception:
        pass

    device["sionna_sweep_template"] = helper.name
    # No anchor/Copy Location constraint is used for PointCloud mode in 1.7.2.
    device["sionna_sweep_anchor"] = ""
    device["sionna_sweep_source"] = source.name
    device["sionna_sweep_style"] = "POINT_CLOUD"
    device["sionna_sweep_start_frame"] = start_frame
    device["sionna_sweep_end_frame"] = end_frame
    device["sionna_sweep_point_count"] = point_count
    device["sionna_sweep_mapping"] = "frame = start_frame + point_index"
    device["sionna_sweep_drive_mode"] = "LIVE_FRAME_INDEX"

    if bool(settings.motion_template_set_scene_range):
        context.scene.frame_start = start_frame
        context.scene.frame_end = end_frame
    else:
        context.scene.frame_start = min(int(context.scene.frame_start), start_frame)
        context.scene.frame_end = max(int(context.scene.frame_end), end_frame)

    _sync_pointcloud_motion_handler()

    # Snap immediately to the point corresponding to the current frame; when
    # outside the path range this intentionally clamps to the first/last point.
    try:
        depsgraph = context.evaluated_depsgraph_get()
    except Exception:
        depsgraph = None
    _apply_pointcloud_motion_for_device(context.scene, device, depsgraph=depsgraph)

    try:
        for obj in context.selected_objects:
            obj.select_set(False)
        source.hide_set(False)
        source.select_set(True)
        context.view_layer.objects.active = source
    except Exception:
        pass

    return source, start_frame, end_frame, point_count


def _device_payload(obj, depsgraph=None):
    evaluated = obj.evaluated_get(depsgraph) if depsgraph is not None else obj
    location = evaluated.matrix_world.translation
    rotation = evaluated.matrix_world.to_euler("XYZ")
    role = str(obj.get("sionna_role", "")) or None
    parsed = _parse_device_name(obj.name, role)
    # The encoded name is the runtime source for per-device orientation. The
    # object PropertyGroup only provides independent UI state and writes this
    # compact name through Apply to Name.
    mode = parsed["orientation_mode"]
    # Blender XYZ Euler matrices are Rz(z) @ Ry(y) @ Rx(x), matching Sionna's
    # (alpha, beta, gamma) rotations about (z, y, x).
    orientation = [float(rotation.z), float(rotation.y), float(rotation.x)]
    target_position = None
    target_sionna_name = ""
    if mode == "FIXED":
        orientation = [math.radians(float(value)) for value in parsed["fixed_orientation_deg"]]
    elif mode == "LOOK_AT":
        target_obj = _find_named_target(parsed["look_at_target"])
        if target_obj is None:
            raise RuntimeError(
                f"{obj.name} looks at '{parsed['look_at_target']}', but no Blender object with that name or device base name exists"
            )
        if target_obj == obj:
            raise RuntimeError(f"{_device_base_name(obj.name, role)} cannot look at itself")
        target_eval = target_obj.evaluated_get(depsgraph) if depsgraph is not None else target_obj
        target_location = target_eval.matrix_world.translation
        delta = target_location - location
        if float(delta.length_squared) <= 1e-12:
            raise RuntimeError(
                f"{_device_base_name(obj.name, role)} and its look-at target occupy the same position"
            )
        target_position = [float(target_location.x), float(target_location.y), float(target_location.z)]
        target_role = str(target_obj.get("sionna_role", "")) or None
        target_sionna_name = _sanitize_name(_parse_device_name(target_obj.name, target_role)["base_name"])
    payload = {
        "name": _sanitize_name(parsed["base_name"]),
        "base_name": parsed["base_name"],
        "blender_name": obj.name,
        "position": [float(location.x), float(location.y), float(location.z)],
        "orientation_mode": mode,
        "orientation_sionna_rad": orientation,
        "blender_rotation_euler_xyz_rad": [
            float(rotation.x), float(rotation.y), float(rotation.z)
        ],
        "look_at_target": parsed["look_at_target"],
        "look_at_target_name": target_sionna_name,
        "look_at_target_position": target_position,
    }
    if role == "TX":
        config = getattr(obj, "sionna_device_config", None)
        payload["power_dbm"] = float(getattr(config, "tx_power_dbm", 44.0))
    return payload


def _integrated_exporter_module():
    """Return the bundled Blender-native Mitsuba XML/PLY exporter.

    The exporter is part of SionnaRT-Bridge and does not require Mitsuba-Blender
    or a Mitsuba installation inside Blender. Mitsuba remains a dependency of
    the configured Sionna runtime used by the simulation workers to load and simulate scenes.
    """
    from . import integrated_mitsuba_exporter
    return integrated_mitsuba_exporter


def _material_slug(value):
    value = str(value or "material").strip().lower()
    if value.startswith("itu_"):
        value = value[4:]
    value = re.sub(r"[^a-z0-9_]+", "_", value).strip("_") or "material"
    return value[:48]


def _material_source_name(material_or_name):
    """Stable generic Sionna material name used in the exported XML.

    A generic placeholder preserves one identity per Blender material. The
    simulation worker replaces it with either an ITURadioMaterial or a custom
    RadioMaterial using the frame-evaluated Blender properties.
    """
    name = material_or_name.name if hasattr(material_or_name, "name") else str(material_or_name)
    slug = _material_slug(name)
    suffix = hashlib.sha1(str(name).encode("utf-8")).hexdigest()[:6]
    return f"sb_{slug}_{suffix}"


def _material_runtime_name(material_or_name):
    name = material_or_name.name if hasattr(material_or_name, "name") else str(material_or_name)
    return "sbr_" + _material_source_name(name)[3:]


def _material_itu_type_from_name(name):
    slug = _material_slug(name)
    if slug in _ITU_MATERIAL_DEFINITIONS:
        return slug
    # Names such as itu_brick_wall are treated as custom unless configured.
    return "concrete"


def _set_material_preview_color(material, color):
    color = tuple(float(v) for v in color)
    material.diffuse_color = color
    material.use_nodes = True
    node_tree = material.node_tree
    if node_tree is None:
        return
    principled = next(
        (node for node in node_tree.nodes if node.type == "BSDF_PRINCIPLED"),
        None,
    )
    if principled is None:
        return
    base = principled.inputs.get("Base Color")
    if base is not None:
        base.default_value = color
    roughness = principled.inputs.get("Roughness")
    if roughness is not None:
        roughness.default_value = 0.45
    alpha = principled.inputs.get("Alpha")
    if alpha is not None:
        alpha.default_value = color[3]
    if color[3] < 0.999 and hasattr(material, "surface_render_method"):
        try:
            material.surface_render_method = "DITHERED"
        except Exception:
            pass


def _configure_material_defaults(material, itu_type, *, force=False):
    config = getattr(material, "sionna_radio", None)
    if config is None:
        return
    if force or not config.configured:
        config.enabled = True
        config.configured = True
        config.model = "ITU"
        config.itu_type = itu_type
        config.thickness = 0.1
        config.scattering_coefficient = 0.0
        config.xpd_coefficient = 0.0
        config.scattering_pattern = "lambertian"
        config.directive_alpha_r = 1
        config.backscatter_alpha_r = 1
        config.backscatter_alpha_i = 1
        config.backscatter_lambda = 1.0


def _ensure_default_sionna_materials():
    """Create built-in radio materials and Blender-only device display materials."""
    created = 0
    configured = 0
    for itu_type, (_label, color) in _ITU_MATERIAL_DEFINITIONS.items():
        name = f"itu_{itu_type}"
        material = bpy.data.materials.get(name)
        if material is None:
            material = bpy.data.materials.new(name=name)
            created += 1
            _set_material_preview_color(material, color)
        config = getattr(material, "sionna_radio", None)
        if config is not None and not config.configured:
            _configure_material_defaults(material, itu_type)
            configured += 1
    _representation_materials, representation_created = _ensure_device_representation_materials()
    return created + representation_created, configured


def _material_is_sionna(material):
    if material is None:
        return False
    config = getattr(material, "sionna_radio", None)
    return bool((config and config.enabled) or material.name.lower().startswith("itu_"))


def _configured_material_from_export_id(value):
    """Resolve a Mitsuba-exported BSDF id back to a Blender material."""
    normalized = str(value or "").strip().lower().replace(" ", "_")
    normalized = re.sub(r"[^a-z0-9_-]+", "_", normalized)
    candidates = []
    for material in bpy.data.materials:
        if not _material_is_sionna(material):
            continue
        mat_name = material.name.lower().replace(" ", "_")
        mat_name = re.sub(r"[^a-z0-9_-]+", "_", mat_name)
        if mat_name and mat_name in normalized:
            candidates.append((len(mat_name), material))
    return max(candidates, default=(0, None), key=lambda item: item[0])[1]


def _used_sionna_materials(scene):
    workflow = _find_environment(scene)
    if not workflow:
        return []
    result = []
    seen = set()
    for obj in _collection_objects_recursive(workflow["scene"]):
        data = getattr(obj, "data", None)
        materials = getattr(data, "materials", None)
        if materials is None:
            continue
        for material in materials:
            if material is None or not _material_is_sionna(material):
                continue
            pointer = material.as_pointer()
            if pointer not in seen:
                seen.add(pointer)
                result.append(material)
    return sorted(result, key=lambda item: item.name.lower())


def _material_payload(material):
    config = getattr(material, "sionna_radio", None)
    inferred_itu = _material_slug(material.name)
    if inferred_itu not in _ITU_MATERIAL_DEFINITIONS:
        inferred_itu = "concrete"
    if config is None or not config.configured:
        model = "ITU" if _material_slug(material.name) in _ITU_MATERIAL_DEFINITIONS else "CUSTOM"
        return {
            "blender_name": material.name,
            "source_name": _material_source_name(material),
            "runtime_name": _material_runtime_name(material),
            "model": model,
            "itu_type": inferred_itu,
            "thickness": 0.1,
            "relative_permittivity": 5.24,
            "conductivity": 0.0462,
            "scattering_coefficient": 0.0,
            "xpd_coefficient": 0.0,
            "scattering_pattern": "lambertian",
            "directive_alpha_r": 1,
            "backscatter_alpha_r": 1,
            "backscatter_alpha_i": 1,
            "backscatter_lambda": 1.0,
            "color": [float(v) for v in material.diffuse_color[:3]],
        }
    return {
        "blender_name": material.name,
        "source_name": _material_source_name(material),
        "runtime_name": _material_runtime_name(material),
        "model": str(config.model),
        "itu_type": str(config.itu_type),
        "thickness": float(config.thickness),
        "relative_permittivity": float(config.relative_permittivity),
        "conductivity": float(config.conductivity),
        "scattering_coefficient": float(config.scattering_coefficient),
        "xpd_coefficient": float(config.xpd_coefficient),
        "scattering_pattern": str(config.scattering_pattern),
        "directive_alpha_r": int(config.directive_alpha_r),
        "backscatter_alpha_r": int(config.backscatter_alpha_r),
        "backscatter_alpha_i": int(config.backscatter_alpha_i),
        "backscatter_lambda": float(config.backscatter_lambda),
        "color": [float(v) for v in material.diffuse_color[:3]],
    }


def _material_payloads(scene):
    return [_material_payload(material) for material in _used_sionna_materials(scene)]


def _material_parameter_signature(scene):
    signature = []
    for payload in _material_payloads(scene):
        signature.extend((
            payload["blender_name"], payload["model"], payload["itu_type"],
            payload["thickness"], payload["relative_permittivity"],
            payload["conductivity"], payload["scattering_coefficient"],
            payload["xpd_coefficient"], payload["scattering_pattern"],
            payload["directive_alpha_r"], payload["backscatter_alpha_r"],
            payload["backscatter_alpha_i"], payload["backscatter_lambda"],
        ))
    return tuple(signature)


def _canonical_itu_material_id(value):
    """Return a known Sionna ITU material ID or ``None``."""
    value = str(value or "").strip().lower().replace(" ", "_")
    value = re.sub(r"[^a-z0-9_-]+", "_", value)
    marker = value.find("itu_")
    if marker < 0:
        return None
    itu_type = value[marker + 4:]
    if itu_type not in _ITU_MATERIAL_DEFINITIONS:
        return None
    return "mat-itu_" + itu_type


def _radio_material_xml_element(material_id, configured=None):
    """Build a Sionna-native Mitsuba BSDF declaration.

    Configured Blender materials are deliberately exported as generic
    ``radio-material`` placeholders. The simulation worker updates this existing
    material instance in place for every frame. This avoids replacing a BSDF on
    an already-loaded Mitsuba mesh, which is unreliable after shape merging and
    caused the v0.17.1 ``No object found with name`` failure.
    """
    material_id = str(material_id)

    if configured is not None:
        payload = _material_payload(configured)
        color = payload.get("color", (0.5, 0.5, 0.5))
        element = ET.Element(
            "bsdf",
            {"type": "radio-material", "id": material_id},
        )
        # These are safe loading values. The worker applies the evaluated
        # CUSTOM values or frequency-dependent ITU values before each solve.
        ET.SubElement(
            element,
            "float",
            {
                "name": "relative_permittivity",
                "value": f'{max(1.0, float(payload.get("relative_permittivity", 5.24))):.12g}',
            },
        )
        ET.SubElement(
            element,
            "float",
            {
                "name": "conductivity",
                "value": f'{max(0.0, float(payload.get("conductivity", 0.0462))):.12g}',
            },
        )
        ET.SubElement(
            element,
            "float",
            {
                "name": "thickness",
                "value": f'{max(0.0, float(payload.get("thickness", 0.1))):.12g}',
            },
        )
        ET.SubElement(
            element,
            "float",
            {
                "name": "scattering_coefficient",
                "value": f'{min(1.0, max(0.0, float(payload.get("scattering_coefficient", 0.0)))):.12g}',
            },
        )
        ET.SubElement(
            element,
            "float",
            {
                "name": "xpd_coefficient",
                "value": f'{min(1.0, max(0.0, float(payload.get("xpd_coefficient", 0.0)))):.12g}',
            },
        )
        ET.SubElement(
            element,
            "rgb",
            {
                "name": "color",
                "value": " ".join(f"{min(1.0, max(0.0, float(v))):.6g}" for v in color[:3]),
            },
        )
        return element

    itu_id = _canonical_itu_material_id(material_id) or "mat-itu_concrete"
    itu_type = itu_id.split("mat-itu_", 1)[-1]
    element = ET.Element(
        "bsdf",
        {"type": "itu-radio-material", "id": itu_id},
    )
    ET.SubElement(element, "string", {"name": "type", "value": itu_type})
    ET.SubElement(element, "float", {"name": "thickness", "value": "0.1"})
    return element

def _patch_xml_to_radio_materials(xml_path):
    """Replace optical exporter BSDFs with valid Sionna radio materials.

    Configured Blender materials receive unique, Sionna-native placeholder
    BSDFs. Their frame-evaluated parameters are still applied by the external
    worker before every solve. Unconfigured geometry uses ITU concrete, while
    already recognized ``itu_*`` names retain their ITU type.
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    fallback_id = "mat-itu_concrete"

    old_to_radio = {}
    material_by_id = {}
    top_level_bsdfs = [child for child in list(root) if child.tag == "bsdf"]
    for child in top_level_bsdfs:
        old_id = child.attrib.get("id") or child.attrib.get("name") or ""
        configured = _configured_material_from_export_id(old_id)
        if configured is not None:
            # Keep the exact source name so the worker can locate all scene
            # objects that currently use this placeholder material.
            radio_id = _material_source_name(configured)
            material_by_id[radio_id] = configured
        else:
            radio_id = _canonical_itu_material_id(old_id) or fallback_id
        if old_id:
            old_to_radio[old_id] = radio_id
        root.remove(child)

    shape_materials = []
    shape_count = 0
    for shape in root.iter("shape"):
        shape_count += 1
        radio_id = None
        for child in list(shape):
            is_bsdf = child.tag == "bsdf"
            is_bsdf_ref = child.tag == "ref" and child.attrib.get("name") == "bsdf"
            if not (is_bsdf or is_bsdf_ref):
                continue
            old_id = child.attrib.get("id") or child.attrib.get("name") or ""
            configured = _configured_material_from_export_id(old_id)
            if configured is not None:
                configured_id = _material_source_name(configured)
                material_by_id[configured_id] = configured
            else:
                configured_id = None
            radio_id = (
                old_to_radio.get(old_id)
                or configured_id
                or _canonical_itu_material_id(old_id)
            )
            shape.remove(child)
        radio_id = radio_id or fallback_id
        shape_materials.append(radio_id)
        ET.SubElement(shape, "ref", {"id": radio_id, "name": "bsdf"})

    material_ids = sorted(set(shape_materials) or {fallback_id})
    insert_at = next(
        (index for index, child in enumerate(list(root)) if child.tag == "shape"),
        len(root),
    )
    for offset, material_id in enumerate(material_ids):
        root.insert(
            insert_at + offset,
            _radio_material_xml_element(
                material_id,
                configured=material_by_id.get(material_id),
            ),
        )

    # Regression guard: a configured placeholder must never be an optical BSDF.
    for child in root.findall("bsdf"):
        material_id = child.attrib.get("id", "")
        if material_id.startswith("sb_") and child.attrib.get("type") != "radio-material":
            raise RuntimeError(
                f"Invalid Sionna material placeholder '{material_id}': "
                f"BSDF type is '{child.attrib.get('type')}'."
            )

    try:
        ET.indent(tree, space="    ")
    except AttributeError:
        pass
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)
    return shape_count, material_ids

def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _frame_token(frame):
    frame = int(frame)
    return f"{frame:04d}"


def _scene_cache_dir(settings):
    blend_stem = Path(bpy.data.filepath).stem if bpy.data.filepath else "untitled"
    return _workspace(settings) / "_scene_cache" / _sanitize_name(blend_stem)


def _new_versioned_cache_dir(base_dir, *, kind="cache"):
    """Return a new immutable cache directory beside *base_dir*.

    Mitsuba simulation workers may keep PLY files open. On Windows, deleting a
    live cache can partially remove ``meshes/`` before ``shutil.rmtree`` raises
    WinError 5. A refresh therefore publishes a new directory and leaves the
    previous package untouched for any worker that still references it.
    """
    base_dir = Path(base_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    token = uuid.uuid4().hex[:8]
    stem = f"{base_dir.name}__{_sanitize_name(kind)}_{timestamp}_{token}"
    candidate = base_dir.parent / stem
    suffix = 1
    while candidate.exists():
        candidate = base_dir.parent / f"{stem}_{suffix:02d}"
        suffix += 1
    return candidate



_TILE_SPATIAL_DATASET_OBJECT = "Tile_spacial_dataset"


def _idprop_json_safe(value):
    """Convert Blender ID-property values to ordinary JSON-compatible data."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _idprop_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_idprop_json_safe(item) for item in value]
    if hasattr(value, "to_list"):
        try:
            return [_idprop_json_safe(item) for item in value.to_list()]
        except Exception:
            pass
    if hasattr(value, "items"):
        try:
            return {str(key): _idprop_json_safe(item) for key, item in value.items()}
        except Exception:
            pass
    try:
        return float(value)
    except Exception:
        return str(value)


def _find_tile_spatial_dataset():
    """Return the Tile_dataset master PointCloud when it is present."""
    obj = bpy.data.objects.get(_TILE_SPATIAL_DATASET_OBJECT)
    if obj is not None and getattr(obj, "type", "") == "POINTCLOUD":
        return obj
    for candidate in bpy.data.objects:
        if getattr(candidate, "type", "") != "POINTCLOUD":
            continue
        try:
            if bool(candidate.get("tile_spacial_dataset", False)):
                return candidate
        except Exception:
            continue
    return None


def _pointcloud_attribute_array(attribute, point_count, np):
    """Read one numeric POINT-domain Blender attribute as a NumPy array."""
    try:
        if str(attribute.domain) != "POINT":
            return None
    except Exception:
        pass
    data_type = str(getattr(attribute, "data_type", "") or "")
    spec = {
        "FLOAT": ("value", 1, np.float32),
        "INT": ("value", 1, np.int64),
        "BOOLEAN": ("value", 1, np.bool_),
        "FLOAT_VECTOR": ("vector", 3, np.float32),
        "FLOAT2": ("vector", 2, np.float32),
        "FLOAT_COLOR": ("color", 4, np.float32),
        "BYTE_COLOR": ("color", 4, np.float32),
    }.get(data_type)
    if spec is None:
        return None
    prop, components, dtype = spec
    if components == 1:
        arr = np.empty(point_count, dtype=dtype)
    else:
        arr = np.empty((point_count, components), dtype=dtype)
    try:
        attribute.data.foreach_get(prop, arr.reshape(-1))
        return arr
    except Exception:
        pass
    try:
        rows = []
        for item in attribute.data:
            value = getattr(item, prop)
            if components == 1:
                rows.append(value)
            else:
                rows.append(tuple(value)[:components])
        return np.asarray(rows, dtype=dtype)
    except Exception:
        return None


def _snapshot_tile_spatial_dataset(run_dir, settings):
    """Snapshot Tile_spacial_dataset for HDF5 workers.

    Blender data cannot be accessed from the Sionna subprocess. When HDF5 export
    is selected, persist the master tile PointCloud once in the worker run
    directory so the durable exporter can embed it and build coverage->tile
    spatial joins.
    """
    if str(getattr(settings, "export_format", "NONE") or "NONE").upper() != "HDF5":
        return None
    obj = _find_tile_spatial_dataset()
    if obj is None:
        return None

    import numpy as np

    data = obj.data
    point_count = len(data.points)
    if point_count <= 0:
        return None

    local = np.empty((point_count, 3), dtype=np.float64)
    try:
        data.points.foreach_get("co", local.reshape(-1))
    except Exception:
        local[:] = [tuple(point.co) for point in data.points]

    matrix = np.asarray(
        [[float(value) for value in row] for row in obj.matrix_world],
        dtype=np.float64,
    )
    homogeneous = np.concatenate(
        [local, np.ones((point_count, 1), dtype=np.float64)], axis=1
    )
    world = (homogeneous @ matrix.T)[:, :3]

    arrays = {
        "positions_local_m": local,
        "positions_world_m": world,
    }
    attribute_meta = []
    for index, attribute in enumerate(data.attributes):
        arr = _pointcloud_attribute_array(attribute, point_count, np)
        if arr is None or len(arr) != point_count:
            continue
        key = f"attribute_{index:03d}"
        arrays[key] = arr
        attribute_meta.append({
            "name": str(attribute.name),
            "npz_key": key,
            "data_type": str(getattr(attribute, "data_type", "")),
            "domain": str(getattr(attribute, "domain", "POINT")),
            "shape": list(arr.shape),
            "dtype": str(arr.dtype),
        })

    run_dir = Path(run_dir)
    npz_path = run_dir / "tile_spacial_dataset_snapshot.npz"
    json_path = run_dir / "tile_spacial_dataset_snapshot.json"
    np.savez_compressed(npz_path, **arrays)

    object_properties = {}
    try:
        object_properties = {
            str(key): _idprop_json_safe(value)
            for key, value in obj.items()
            if key != "_RNA_UI"
        }
    except Exception:
        pass
    metadata = {
        "schema": "sionna_tile_spatial_dataset_snapshot",
        "schema_version": 1,
        "object_name": str(obj.name),
        "data_name": str(data.name),
        "point_count": int(point_count),
        "matrix_world": matrix.tolist(),
        "positions_coordinate_system": "Blender world coordinates, meters",
        "attributes": attribute_meta,
        "object_properties": object_properties,
    }
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2, ensure_ascii=False)

    return {
        "schema": metadata["schema"],
        "schema_version": metadata["schema_version"],
        "object_name": str(obj.name),
        "point_count": int(point_count),
        "snapshot_npz": str(npz_path),
        "snapshot_json": str(json_path),
        "snapshot_sha256": _sha256(npz_path),
        "attribute_names": [item["name"] for item in attribute_meta],
    }


def _prepare_export_bundle(settings):
    """Create a shared durable-export destination for one Run Simulation batch."""
    mode = str(getattr(settings, "export_format", "NONE") or "NONE").upper()
    if mode == "NONE":
        return {}
    workspace = _workspace(settings)
    created_utc = _now_utc()
    stamp = datetime.fromisoformat(created_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
    timestamp = stamp.strftime("%Y%m%dT%H%M%S_%fZ")
    run_id = uuid.uuid4().hex[:8]
    blend_stem = Path(bpy.data.filepath).stem if bpy.data.filepath else "untitled"
    project = _sanitize_name(blend_stem)
    bundle_dir = workspace / f"{project}_simulation_{timestamp}_{run_id}"
    bundle = {
        "export_format": mode,
        "export_run_id": run_id,
        "bundle_dir": str(bundle_dir),
        "project": project,
        "timestamp": timestamp,
        "created_utc": created_utc,
    }
    if mode == "HDF5":
        base = f"{project}__simulation__{timestamp}__{run_id}"
        bundle["export_file"] = str(bundle_dir / f"{base}.h5")
        bundle["export_metadata_json"] = str(bundle_dir / f"{base}.metadata.json")
    return bundle


def _export_output_spec(settings, run_dir, category, created_utc):
    """Return a traceable durable-export descriptor for one simulation run."""
    run_dir = Path(run_dir)
    mode = str(getattr(settings, "export_format", "NONE") or "NONE").upper()
    if mode in {"CSV", "HDF5"} and _BATCH_STATE.get("active"):
        bundle = dict(_BATCH_STATE.get("export_bundle") or {})
        if bundle.get("bundle_dir"):
            if mode == "HDF5" and bundle.get("export_file"):
                return {
                    "export_format": "HDF5",
                    "export_category": category,
                    "export_run_id": str(bundle.get("export_run_id") or ""),
                    "export_file": str(bundle.get("export_file") or ""),
                    "export_metadata_json": str(bundle.get("export_metadata_json") or ""),
                }
            if mode == "CSV":
                category_token = {
                    "paths": "paths",
                    "coverage_2d": "coverage2d",
                    "coverage_3d": "coverage3d",
                }.get(category, _sanitize_name(category))
                base = (
                    f"{bundle.get('project', 'simulation')}__{category_token}__"
                    f"{bundle.get('timestamp', '')}__{bundle.get('export_run_id', '')}"
                )
                bundle_dir = Path(bundle["bundle_dir"])
                return {
                    "export_format": "CSV",
                    "export_category": category,
                    "export_run_id": str(bundle.get("export_run_id") or ""),
                    "export_file": str(bundle_dir / f"{base}.csv"),
                    "export_metadata_json": str(bundle_dir / f"{base}.metadata.json"),
                }
    match = re.search(r"([0-9a-fA-F]{8})(?:_\d+)?$", run_dir.name)
    run_id = match.group(1).lower() if match else hashlib.sha256(run_dir.name.encode("utf-8")).hexdigest()[:8]
    try:
        stamp = datetime.fromisoformat(str(created_utc).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        stamp = datetime.now(timezone.utc)
    timestamp = stamp.strftime("%Y%m%dT%H%M%S_%fZ")
    blend_stem = Path(bpy.data.filepath).stem if bpy.data.filepath else "untitled"
    project = _sanitize_name(blend_stem)
    category_token = {
        "paths": "paths",
        "coverage_2d": "coverage2d",
        "coverage_3d": "coverage3d",
    }.get(category, _sanitize_name(category))
    base = f"{project}__{category_token}__{timestamp}__{run_id}"
    extension = {"CSV": ".csv", "HDF5": ".h5"}.get(mode, "")
    return {
        "export_format": mode,
        "export_category": category,
        "export_run_id": run_id,
        "export_file": str(run_dir / f"{base}{extension}") if extension else "",
        "export_metadata_json": str(run_dir / f"{base}.metadata.json") if extension else "",
    }


def _make_run_dir(settings):
    workspace = _workspace(settings)
    workspace.mkdir(parents=True, exist_ok=True)

    blend_stem = Path(bpy.data.filepath).stem if bpy.data.filepath else "untitled"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    token = uuid.uuid4().hex[:8]
    run_dir = workspace / f"{_sanitize_name(blend_stem)}_paths_{timestamp}_{token}"

    suffix = 1
    candidate = run_dir
    while candidate.exists():
        candidate = Path(str(run_dir) + f"_{suffix:02d}")
        suffix += 1

    candidate.mkdir(parents=True)
    return candidate


def _export_scene_package(context, xml_path, export_objects):
    """Export the evaluated Blender scene using the bundled Blender 5 exporter."""
    xml_path = Path(xml_path)
    xml_path.parent.mkdir(parents=True, exist_ok=True)
    exporter = _integrated_exporter_module()

    wm = context.window_manager
    wm.progress_begin(0, max(1, len(export_objects)))

    def progress(current, total):
        try:
            wm.progress_update(min(max(int(current), 0), max(1, int(total))))
        except Exception:
            pass

    try:
        # No selection manipulation and no external Mitsuba add-on are needed.
        # The integrated exporter filters the dependency graph using the explicit
        # sionna_env/scene object list and writes Mitsuba-compatible XML/PLY.
        context.view_layer.update()
        result = exporter.export_scene(
            context,
            xml_path,
            export_objects,
            progress_callback=progress,
        )
    finally:
        wm.progress_end()

    if not xml_path.exists():
        raise RuntimeError(f"Integrated scene export did not create {xml_path}")
    shape_count, radio_material_ids = _patch_xml_to_radio_materials(xml_path)
    if int(result.get("shape_count", shape_count)) != shape_count:
        raise RuntimeError(
            "Integrated exporter/XML patch shape-count mismatch: "
            f"{result.get('shape_count')} vs {shape_count}"
        )
    return shape_count, radio_material_ids


def _remove_tree_with_retries(path, *, attempts=6, delay=0.15, ignore_errors=False):
    """Remove a generated directory while tolerating short Windows file locks."""
    path = Path(path)
    if not path.exists():
        return True
    last_error = None
    for attempt in range(max(1, int(attempts))):
        try:
            shutil.rmtree(path)
            return True
        except FileNotFoundError:
            return True
        except (PermissionError, OSError) as exc:
            last_error = exc
            time.sleep(float(delay) * (attempt + 1))
    if ignore_errors:
        return False
    raise RuntimeError(
        f"Windows could not release generated cache directory '{path}'. "
        "Close Explorer windows or other processes using the cache and retry. "
        f"Last error: {last_error}"
    ) from last_error


def _export_scene_cache(context):
    """Export sionna_env/scene into an immutable reusable scene package.

    Refresh must never delete or replace the package currently used by an
    simulation worker. Each completed export becomes a new cache version and the
    settings pointer is switched only after publication succeeds.
    """
    settings = context.scene.sionna_bridge
    export_objects = _scene_export_objects(context.scene)
    cache_base = _scene_cache_dir(settings)
    cache_base.parent.mkdir(parents=True, exist_ok=True)
    final_dir = _new_versioned_cache_dir(cache_base, kind="cache")
    temp_dir = Path(tempfile.mkdtemp(
        prefix=f"{final_dir.name}__building_",
        dir=str(cache_base.parent),
    ))

    xml_path = temp_dir / "scene.xml"
    try:
        shape_count, radio_material_ids = _export_scene_package(
            context, xml_path, export_objects
        )
        # Publish only after XML and all PLY meshes are complete.
        temp_dir.replace(final_dir)
    except Exception:
        _remove_tree_with_retries(temp_dir, ignore_errors=True)
        raise

    xml_path = final_dir / "scene.xml"
    settings.last_scene_xml = str(xml_path)
    settings.last_status = (
        f"Scene cache refreshed from sionna_env/scene: {shape_count} shapes, "
        f"{len(radio_material_ids)} radio materials (immutable cache version)"
    )
    return xml_path, shape_count, radio_material_ids

def _procedural_scene_cache_dir(settings):
    static_dir = _scene_cache_dir(settings)
    return static_dir.parent / f"{static_dir.name}_procedural_frames"


def _procedural_export_error_reason(exc):
    """Return a concise reason while preserving the useful nested exception."""
    messages = []
    current = exc
    visited = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        message = str(current).strip()
        if message and message not in messages:
            messages.append(message)
        current = current.__cause__ or current.__context__

    combined = " | ".join(reversed(messages)) if messages else type(exc).__name__
    known = (
        ("invalid normals", "Invalid normals in evaluated mesh"),
        ("DepsgraphObjectInstance has been removed", "Evaluated dependency-graph instance became invalid"),
        ("is not supported", "Unsupported evaluated object or geometry type"),
        ("did not create", "Integrated scene export did not create a scene XML file"),
    )
    lowered = combined.lower()
    labels = [label for needle, label in known if needle.lower() in lowered]
    if labels:
        detail = labels[0]
        if combined and detail.lower() not in combined.lower():
            return f"{detail}: {combined}"
    return combined or type(exc).__name__


def _store_procedural_export_report(settings, report, report_path=None):
    settings.procedural_export_report_json = json.dumps(report, ensure_ascii=False)
    settings.procedural_export_report_path = str(report_path) if report_path else ""


def _export_procedural_scene_frames(context, frames):
    """Export one evaluated scene per frame, optionally skipping bad frames."""
    settings = context.scene.sionna_bridge
    procedural_objects = _procedural_scene_objects(context.scene)
    if not procedural_objects:
        raise RuntimeError(
            "Procedural Geometry is enabled, but sionna_env/scene/procedural_geometry is empty"
        )
    export_objects = _scene_export_objects(context.scene)
    cache_dir = _procedural_scene_cache_dir(settings)
    cache_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(
        prefix=f"{cache_dir.name}__building_",
        dir=str(cache_dir.parent),
    ))

    requested_frames = [int(frame) for frame in frames]
    original = int(context.scene.frame_current)
    result = {}
    failures = []
    total_shapes = 0
    try:
        for index, frame in enumerate(requested_frames, start=1):
            context.scene.frame_set(frame)
            context.view_layer.update()
            frame_dir = temp_dir / f"F{_frame_token(frame)}"
            xml_path = frame_dir / "scene.xml"
            settings.last_status = (
                f"Exporting procedural scene frame {index}/{len(requested_frames)} (F{frame})"
            )
            try:
                shape_count, _ = _export_scene_package(context, xml_path, export_objects)
                total_shapes += int(shape_count)
                result[frame] = xml_path
            except Exception as exc:
                reason = _procedural_export_error_reason(exc)
                failures.append({
                    "frame": frame,
                    "reason": reason,
                    "exception_type": type(exc).__name__,
                    "traceback": traceback.format_exc(),
                })
                _remove_tree_with_retries(frame_dir, ignore_errors=True)
                if not settings.procedural_skip_failed_frames:
                    raise RuntimeError(
                        f"Procedural scene export failed at frame {frame}: {reason}"
                    ) from exc
                settings.last_status = (
                    f"Skipped incompatible procedural frame F{frame}: {reason}"
                )
                continue
    except Exception:
        report = {
            "schema_version": 1,
            "bridge_version": _ADDON_VERSION,
            "created_utc": _now_utc(),
            "requested_frames": requested_frames,
            "exported_frames": sorted(result),
            "failed_frames": failures,
            "complete": False,
        }
        _store_procedural_export_report(settings, report)
        _remove_tree_with_retries(temp_dir, ignore_errors=True)
        raise
    finally:
        context.scene.frame_set(original)
        try:
            context.view_layer.update()
        except Exception:
            pass

    report = {
        "schema_version": 1,
        "bridge_version": _ADDON_VERSION,
        "created_utc": _now_utc(),
        "requested_frames": requested_frames,
        "exported_frames": sorted(result),
        "failed_frames": failures,
        "complete": bool(result),
        "procedural_object_count": len(procedural_objects),
        "total_exported_shapes": total_shapes,
    }

    if not result:
        _store_procedural_export_report(settings, report)
        _remove_tree_with_retries(temp_dir, ignore_errors=True)
        summary = "; ".join(
            f"F{item['frame']}: {item['reason']}" for item in failures[:5]
        ) or "unknown export error"
        raise RuntimeError(
            "All procedural scene frames failed to export. " + summary
        )

    report_path = temp_dir / "procedural_export_report.json"
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)

    final_dir = _new_versioned_cache_dir(cache_dir, kind="cache")
    temp_dir.replace(final_dir)
    result = {
        frame: final_dir / path.relative_to(temp_dir)
        for frame, path in result.items()
    }
    report_path = final_dir / "procedural_export_report.json"
    _store_procedural_export_report(settings, report, report_path)

    first_frame = next(frame for frame in requested_frames if frame in result)
    settings.last_scene_xml = str(result[first_frame])
    if failures:
        failed_tokens = ", ".join(f"F{item['frame']}" for item in failures)
        settings.last_status = (
            f"Exported {len(result)}/{len(requested_frames)} procedural frame(s); "
            f"skipped {len(failures)} incompatible frame(s): {failed_tokens}"
        )
    else:
        settings.last_status = (
            f"Exported {len(result)} evaluated scene frame(s) from "
            f"{len(procedural_objects)} procedural object(s)"
        )
    return result


def _scene_xml_uses_valid_radio_materials(path):
    """Return False for caches created by the broken v0.17.0 placeholder code."""
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return False
    for bsdf in root.findall("bsdf"):
        material_id = str(bsdf.attrib.get("id", ""))
        material_type = str(bsdf.attrib.get("type", ""))
        # v0.17.2 requires configured placeholders to be mutable generic
        # RadioMaterial instances. Older ITU placeholders are re-exported.
        if material_id.startswith("sb_") and material_type != "radio-material":
            return False
    return True


def _cached_scene_xml(settings):
    candidates = []
    if settings.last_scene_xml.strip():
        candidates.append(_absolute_path(settings.last_scene_xml))

    cache_base = _scene_cache_dir(settings)
    # v1.1.2+ publishes immutable siblings such as
    # ``untitled__cache_20260811_.../scene.xml``. Recover the newest valid one
    # after restart even if last_scene_xml is stale.
    try:
        versioned = sorted(
            cache_base.parent.glob(f"{cache_base.name}__cache_*/scene.xml"),
            key=lambda item: item.stat().st_mtime_ns,
            reverse=True,
        )
        candidates.extend(versioned)
    except OSError:
        pass

    # Compatibility fallback for caches produced by <= 1.1.1.
    candidates.append(cache_base / "scene.xml")
    invalid_caches = []
    seen = set()
    for path in candidates:
        path = Path(path)
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if not path.is_file():
            continue
        if not _scene_xml_uses_valid_radio_materials(path):
            invalid_caches.append(path)
            continue
        settings.last_scene_xml = str(path)
        return path
    if invalid_caches:
        raise RuntimeError(
            "The cached scene uses an incompatible material placeholder from "
            "an earlier material build. Refreshing the scene export is required."
        )
    raise RuntimeError(
        "No reusable scene export exists. Click Export/Refresh Scene first, "
        "or use Export + Run Sionna."
    )

def _frame_range(scene, step):
    step = max(1, int(step))
    start = int(scene.frame_start)
    end = int(scene.frame_end)
    frames = list(range(start, end + 1, step))
    if not frames:
        frames = [int(scene.frame_current)]
    elif frames[-1] != end:
        frames.append(end)
    return frames


def _device_position_signature(context, devices):
    """Signature of animated device position, orientation, and look-at target."""
    depsgraph = context.evaluated_depsgraph_get()
    signature = []
    for obj in devices:
        payload = _device_payload(obj, depsgraph)
        signature.extend(float(value) for value in payload["position"])
        signature.extend(float(value) for value in payload["orientation_sionna_rad"])
        target = payload.get("look_at_target_position")
        if target is not None:
            signature.extend(float(value) for value in target)
        else:
            signature.extend((0.0, 0.0, 0.0))
    return tuple(signature)


def _evaluated_bridge_settings(context):
    """Return animation-evaluated bridge settings for the current frame.

    ``Scene.frame_set()`` evaluates RNA animation on the original Scene
    datablock. Reading a PropertyGroup from ``scene.evaluated_get()`` can keep
    the source/default values for nested add-on properties, which caused a
    keyed frequency sweep to repeat its first value. Always read the original
    scene after forcing view-layer/depsgraph evaluation.
    """
    try:
        context.view_layer.update()
    except Exception:
        pass
    try:
        depsgraph = context.evaluated_depsgraph_get()
        depsgraph.update()
    except Exception:
        pass
    return context.scene.sionna_bridge


def _simulation_settings_payload(settings):
    """Read all keyframeable solver controls at the current Blender frame."""
    frequency_ghz = float(settings.frequency_ghz)
    return {
        "frequency_ghz": frequency_ghz,
        "frequency_hz": frequency_ghz * 1e9,
        "bandwidth_hz": float(settings.bandwidth_mhz) * 1e6,
        "temperature_k": float(settings.temperature_k),
        "max_depth": int(settings.max_depth),
        "max_num_paths_per_src": int(settings.max_num_paths_per_src),
        "samples_per_src": int(settings.samples_per_src),
        "synthetic_array": True,
        "los": bool(settings.enable_los),
        "specular_reflection": bool(settings.enable_reflection),
        "diffuse_reflection": bool(settings.enable_diffuse),
        "refraction": bool(settings.enable_refraction),
        "diffraction": bool(settings.enable_diffraction),
        "edge_diffraction": bool(settings.enable_edge_diffraction),
        "diffraction_lit_region": bool(settings.diffraction_lit_region),
        "seed": int(settings.seed),
        "sim_numeric_id": int(settings.sim_numeric_id),
        "mobility_doppler": bool(settings.enable_mobility_doppler),
    }


def _simulation_parameter_signature(settings):
    payload = _simulation_settings_payload(settings)
    return tuple(payload[key] for key in (
        "frequency_ghz",
        "bandwidth_hz",
        "temperature_k",
        "max_depth",
        "max_num_paths_per_src",
        "samples_per_src",
        "los",
        "specular_reflection",
        "diffuse_reflection",
        "refraction",
        "diffraction",
        "edge_diffraction",
        "diffraction_lit_region",
        "seed",
        "sim_numeric_id",
        "mobility_doppler",
    ))


def _timeline_change_reasons(context, devices, frames):
    """Detect animated devices, solver controls, and radio-material properties."""
    if len(frames) <= 1:
        return False, False, False
    scene = context.scene
    original = int(scene.frame_current)
    device_changed = False
    parameter_changed = False
    material_changed = False
    try:
        scene.frame_set(frames[0])
        baseline_devices = _device_position_signature(context, devices)
        baseline_parameters = _simulation_parameter_signature(_evaluated_bridge_settings(context))
        baseline_materials = _material_parameter_signature(scene)
        for frame in frames[1:]:
            scene.frame_set(frame)
            if not device_changed:
                current_devices = _device_position_signature(context, devices)
                device_changed = any(
                    abs(a - b) > 1e-7
                    for a, b in zip(baseline_devices, current_devices)
                )
            if not parameter_changed:
                current_parameters = _simulation_parameter_signature(_evaluated_bridge_settings(context))
                parameter_changed = any(
                    (abs(float(a) - float(b)) > 1e-7)
                    if isinstance(a, float) or isinstance(b, float)
                    else a != b
                    for a, b in zip(baseline_parameters, current_parameters)
                )
            if not material_changed:
                current_materials = _material_parameter_signature(scene)
                material_changed = current_materials != baseline_materials
            if device_changed and parameter_changed and material_changed:
                break
        return device_changed, parameter_changed, material_changed
    finally:
        scene.frame_set(original)


def _simulation_frames(context, devices):
    settings = context.scene.sionna_bridge
    mode = settings.timeline_mode
    if mode == "CURRENT":
        return [int(context.scene.frame_current)], "current frame"

    candidate_frames = _frame_range(context.scene, settings.timeline_step)
    if mode == "RANGE":
        return candidate_frames, "scene frame range"
    if _procedural_scene_active(context.scene):
        return candidate_frames, "procedural scene geometry detected"

    device_changed, parameter_changed, material_changed = _timeline_change_reasons(
        context, devices, candidate_frames
    )
    if device_changed or parameter_changed or material_changed:
        reasons = []
        if device_changed:
            reasons.append("animated TX/RX")
        if parameter_changed:
            reasons.append("animated simulation settings")
        if material_changed:
            reasons.append("animated radio materials")
        return candidate_frames, " and ".join(reasons) + " detected"
    return [int(context.scene.frame_current)], "no animated devices or settings detected"


def _scene_frame_rate(scene):
    """Return the evaluated Blender timeline rate in frames per second."""
    fps_base = float(getattr(scene.render, "fps_base", 1.0) or 1.0)
    return float(getattr(scene.render, "fps", 24.0) or 24.0) / fps_base


def _sample_device_world_positions(context, frames, devices):
    """Evaluate device world positions at the requested Blender frames."""
    scene = context.scene
    original = int(scene.frame_current)
    result = {}
    try:
        for frame in sorted({int(value) for value in frames}):
            scene.frame_set(frame)
            try:
                context.view_layer.update()
            except Exception:
                pass
            depsgraph = context.evaluated_depsgraph_get()
            try:
                depsgraph.update()
            except Exception:
                pass
            frame_positions = {}
            for obj in devices:
                evaluated = obj.evaluated_get(depsgraph)
                location = evaluated.matrix_world.translation
                frame_positions[obj.name] = (
                    float(location.x), float(location.y), float(location.z)
                )
            result[frame] = frame_positions
    finally:
        scene.frame_set(original)
    return result


def _device_animation_velocity_cache(context, frames, devices):
    """Estimate world-space device velocity from adjacent Blender frames.

    Interior samples use a centered finite difference over ``frame-1`` and
    ``frame+1``. The first and last scene frames use a one-sided difference.
    This remains independent from the simulation Frame Step and converts the
    result to metres per second using Blender's FPS/FPS Base settings.
    """
    scene = context.scene
    fps = max(1e-9, _scene_frame_rate(scene))
    frame_start = int(scene.frame_start)
    frame_end = int(scene.frame_end)
    requested = [int(value) for value in frames]
    neighborhoods = {}
    evaluation_frames = set()
    for frame in requested:
        previous = max(frame_start, frame - 1)
        following = min(frame_end, frame + 1)
        if previous == following:
            previous = following = frame
        neighborhoods[frame] = (previous, following)
        evaluation_frames.update((previous, following))
    positions = _sample_device_world_positions(context, evaluation_frames, devices)
    cache = {}
    for frame in requested:
        previous, following = neighborhoods[frame]
        dt_seconds = float(following - previous) / fps
        frame_velocities = {}
        for obj in devices:
            if dt_seconds <= 0.0:
                velocity = (0.0, 0.0, 0.0)
            else:
                p0 = positions[previous][obj.name]
                p1 = positions[following][obj.name]
                velocity = tuple((p1[index] - p0[index]) / dt_seconds for index in range(3))
            frame_velocities[obj.name] = velocity
        cache[frame] = frame_velocities
    return cache, fps


def _apply_device_velocity_payload(items, velocity_by_name, enabled):
    for item in items:
        velocity = velocity_by_name.get(item.get("blender_name", ""), (0.0, 0.0, 0.0))
        if not enabled:
            velocity = (0.0, 0.0, 0.0)
        velocity = [float(value) for value in velocity]
        item["velocity_m_s"] = velocity
        item["speed_m_s"] = math.sqrt(sum(value * value for value in velocity))


def _sample_frame_payloads(context, frames, transmitters, receivers):
    scene = context.scene
    original = int(scene.frame_current)
    payloads = []
    devices = list(transmitters) + list(receivers)
    velocity_cache, timeline_fps = _device_animation_velocity_cache(
        context, frames, devices
    )
    try:
        for frame in frames:
            scene.frame_set(int(frame))
            try:
                context.view_layer.update()
            except Exception:
                pass
            depsgraph = context.evaluated_depsgraph_get()
            try:
                depsgraph.update()
            except Exception:
                pass
            simulation = _simulation_settings_payload(_evaluated_bridge_settings(context))
            simulation["timeline_fps"] = float(timeline_fps)
            simulation["mobility_velocity_method"] = "adjacent_blender_frames"
            tx_payloads = [_device_payload(obj, depsgraph) for obj in transmitters]
            rx_payloads = [_device_payload(obj, depsgraph) for obj in receivers]
            frame_velocities = velocity_cache.get(int(frame), {})
            mobility_enabled = bool(simulation.get("mobility_doppler", True))
            _apply_device_velocity_payload(tx_payloads, frame_velocities, mobility_enabled)
            _apply_device_velocity_payload(rx_payloads, frame_velocities, mobility_enabled)
            payload = {
                "frame": int(frame),
                "time_seconds": (int(frame) - int(scene.frame_start)) / max(1e-9, timeline_fps),
                "simulation": simulation,
                "transmitters": tx_payloads,
                "receivers": rx_payloads,
                "materials": _material_payloads(scene),
            }
            procedural_stats = _procedural_stats_for_payload(context, depsgraph)
            if procedural_stats is not None:
                payload["procedural_geometry_stats"] = procedural_stats
            payloads.append(payload)
    finally:
        scene.frame_set(original)
    return payloads


def _build_run_package(context, scene_source, *, force_current_frame=False):
    settings = context.scene.sionna_bridge
    transmitters = _device_objects(context.scene, "TX")
    receivers = _device_objects(context.scene, "RX")
    if not transmitters:
        raise RuntimeError("Add at least one Sionna transmitter.")
    if not receivers:
        raise RuntimeError("Add at least one Sionna receiver.")

    devices = transmitters + receivers
    if force_current_frame:
        frames = [int(context.scene.frame_current)]
        frame_reason = "current frame (automatic device-move recompute)"
    else:
        frames, frame_reason = _simulation_frames(context, devices)
    frame_payloads = _sample_frame_payloads(
        context, frames, transmitters, receivers
    )
    _attach_scene_sources(frame_payloads, scene_source)
    run_dir = _make_run_dir(settings)
    config_path = run_dir / "sionna_config.json"
    created_utc = _now_utc()
    export_spec = _export_output_spec(settings, run_dir, "paths", created_utc)

    for payload in frame_payloads:
        token = _frame_token(payload["frame"])
        payload["output"] = {
            "results_npz": str(run_dir / f"paths_frame_{token}.npz"),
            "results_json": str(run_dir / f"paths_frame_{token}.json"),
            # Frame-local JSON/NPZ remain separate; all frames share one combined CSV.
            "results_csv": str(run_dir / "paths_all_frames.csv"),
            "status_json": str(run_dir / f"status_frame_{token}.json"),
        }

    first_scene_xml = Path(frame_payloads[0]["scene_xml"])
    config = {
        "schema_version": 6,
        "bridge_version": _ADDON_VERSION,
        "created_utc": created_utc,
        "blend_file": bpy.data.filepath or None,
        "scene_name": context.scene.name,
        "scene_xml": str(first_scene_xml),
        "scene_xml_sha256": _sha256(first_scene_xml),
        "procedural_scene": isinstance(scene_source, dict),
        "coordinate_system": {
            "units": "meters",
            "blender_up_axis": "Z",
            "note": "TX/RX positions are evaluated Blender world-space coordinates.",
        },
        # Backward-compatible fallback. Every frame also stores its evaluated
        # keyframed simulation settings in frames[*].simulation.
        "simulation": dict(frame_payloads[0]["simulation"]),
        "antenna": _antenna_config(settings, transmitters, receivers),
        "materials": list(frame_payloads[0].get("materials", [])),
        "analytics": {
            "cir_component_limit": int(settings.analytics_cir_component_limit),
            "pdp_bins": int(settings.analytics_pdp_bins),
            "significant_path_threshold_db": float(settings.analytics_significant_path_threshold_db),
        },
        "frames": frame_payloads,
        "output": {
            "status_json": str(run_dir / "status.json"),
            "frames_manifest_json": str(run_dir / "frames_manifest.json"),
            "results_csv": str(run_dir / "paths_all_frames.csv"),
            "top_paths_per_pair": int(settings.pointcloud_top_paths_per_pair),
            "keep_external_results": settings.export_format == "HDF5" or settings.post_run_action == "CURVES",
            **export_spec,
        },
    }

    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)

    current_frame = int(context.scene.frame_current)
    preferred = min(
        frame_payloads,
        key=lambda item: abs(int(item["frame"]) - current_frame),
    )
    settings.last_run_dir = str(run_dir)
    settings.last_config_path = str(config_path)
    # Keep the last successful result active until this worker completes.
    # The expected output path is held in _RUN_STATE and is committed only
    # after status/CSV verification succeeds.
    settings.last_csv_pattern = ""
    settings.last_status = (
        f"Prepared {len(frame_payloads)} frame(s): {frame_reason}; "
        + ("using evaluated per-frame scenes" if isinstance(scene_source, dict) else f"reusing {first_scene_xml.name}")
    )
    return run_dir, config_path, config, preferred


def _start_sionna_process(
    context, scene_source, *, force_current_frame=False, auto_triggered=False
):
    settings = context.scene.sionna_bridge
    executable, error = _resolve_python_executable(settings)
    worker = _worker_script()
    if executable is None:
        raise RuntimeError(error)
    if not worker.exists():
        raise RuntimeError(f"Worker script is missing: {worker}")

    run_dir, config_path, config, preferred = _build_run_package(
        context, scene_source, force_current_frame=force_current_frame
    )
    started_ns = time.time_ns()
    # Do not connect Blender's Import CSV node to the output file while the
    # simulation worker is writing it. On Windows, Import CSV can keep the file
    # open and prevent the worker's atomic os.replace(), leaving a header-only
    # placeholder. Keep the last verified CSV active until the new file is
    # fully written and verified in _poll_sionna_process().
    preflight_notes = []

    _check_stale_or_active_lock(settings)
    log_path = run_dir / "sionna.log"
    log_handle = open(log_path, "w", encoding="utf-8", buffering=1)
    command = [str(executable), str(worker), "--config", str(config_path)]
    worker_env, _libllvm_path = _sionna_worker_environment(settings, executable)
    try:
        process = _popen_with_retries(
            command, cwd=run_dir, stdout=log_handle,
            creationflags=_subprocess_creationflags(), env=worker_env,
        )
        lock_path = _write_active_run_lock(settings, process, "propagation-path", run_dir)
    except Exception:
        log_handle.close()
        raise

    _RUN_STATE.update({
        "process": process,
        "log_handle": log_handle,
        "scene_name": context.scene.name,
        "run_dir": str(run_dir),
        "results_json": preferred["output"]["results_json"],
        "results_csv": config["output"]["results_csv"],
        "frame_count": len(config["frames"]),
        "config_path": str(config_path),
        "started_ns": int(started_ns),
        "pid": int(process.pid),
        "lock_path": str(lock_path),
        "auto_triggered": bool(auto_triggered),
    })
    requested_frequencies = sorted({
        float(item.get("simulation", {}).get("frequency_ghz", 0.0))
        for item in config.get("frames", [])
    })
    frequency_note = ", ".join(f"{value:g}" for value in requested_frequencies)
    _set_status(
        settings,
        f"Sionna running {len(config['frames'])} frame(s) at {frequency_note} GHz (PID {process.pid})",
        details=(
            "Previous verified path data remains active until completion.\n"
            f"Run folder: {run_dir}\nLog file: {log_path}\nConfig: {config_path}"
        ),
        run_dir=run_dir, log_path=log_path,
    )
    if preflight_notes:
        settings.last_status += "; " + "; ".join(preflight_notes)
    if not bpy.app.timers.is_registered(_poll_sionna_process):
        bpy.app.timers.register(
            _poll_sionna_process,
            first_interval=0.5,
            persistent=False,
        )
    return process, config


def _close_run_handles():
    handle = _RUN_STATE.get("log_handle")
    if handle:
        try:
            handle.close()
        except Exception:
            pass
    _release_active_run_lock(_RUN_STATE.get("lock_path"), _RUN_STATE.get("pid", 0))
    _RUN_STATE["log_handle"] = None
    _RUN_STATE["process"] = None
    _RUN_STATE["pid"] = 0
    _RUN_STATE["lock_path"] = ""
    _RUN_STATE["auto_triggered"] = False




def _make_radio_map_run_dir(settings):
    workspace = _workspace(settings)
    workspace.mkdir(parents=True, exist_ok=True)
    blend_stem = Path(bpy.data.filepath).stem if bpy.data.filepath else "untitled"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    token = uuid.uuid4().hex[:8]
    base = workspace / f"{_sanitize_name(blend_stem)}_radio_map_{timestamp}_{token}"
    candidate = base
    suffix = 1
    while candidate.exists():
        candidate = Path(str(base) + f"_{suffix:02d}")
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


def _radio_map_reference_mesh_object(settings):
    obj = getattr(settings, "radio_map_reference_mesh", None)
    if obj is None:
        return None
    if getattr(obj, "type", "") != "MESH":
        raise RuntimeError("The projected radio-map reference must be a mesh object")
    if bool(obj.get("sionna_blender_only", False)):
        raise RuntimeError(
            "Blender-only helper objects cannot be used as projected radio-map surfaces"
        )
    return obj


def _export_projected_measurement_surface(
    context, source_obj, frame, run_dir, depsgraph=None,
):
    """Export one evaluated Blender mesh as a Sionna measurement surface.

    Sionna's MeshRadioMap uses one triangle per radio-map cell. The PLY face
    order is mirrored in a compact CSV containing the world-space center,
    normal, and area of every triangle so the Blender point cloud can expose
    those values as Geometry Nodes attributes after the worker returns.
    """
    if source_obj is None or getattr(source_obj, "type", "") != "MESH":
        raise RuntimeError("Select a mesh object for Projected Mesh radio maps")
    if depsgraph is None:
        depsgraph = context.evaluated_depsgraph_get()
    try:
        evaluated = source_obj.evaluated_get(depsgraph)
    except Exception:
        evaluated = source_obj

    mesh = None
    try:
        mesh = evaluated.to_mesh(
            preserve_all_data_layers=False,
            depsgraph=depsgraph,
        )
        if mesh is None:
            raise RuntimeError(
                f"Could not evaluate projected radio-map mesh '{source_obj.name}'"
            )
        mesh.calc_loop_triangles()
        if not mesh.vertices or not mesh.loop_triangles:
            raise RuntimeError(
                f"Projected radio-map mesh '{source_obj.name}' has no triangles"
            )

        matrix = evaluated.matrix_world.copy()
        world_vertices = [matrix @ vertex.co for vertex in mesh.vertices]
        faces = []
        cell_rows = []
        skipped = 0
        for triangle in mesh.loop_triangles:
            indices = tuple(int(index) for index in triangle.vertices)
            p0, p1, p2 = (world_vertices[index] for index in indices)
            edge01 = p1 - p0
            edge12 = p2 - p1
            edge20 = p0 - p2
            cross = edge01.cross(p2 - p0)
            double_area = float(cross.length)
            if double_area <= 1e-12:
                skipped += 1
                continue
            normal = cross / double_area
            tangent = edge01.normalized() if edge01.length > 1e-12 else (p2 - p0).normalized()
            bitangent = normal.cross(tangent)
            if bitangent.length > 1e-12:
                bitangent.normalize()
            center = (p0 + p1 + p2) / 3.0
            primitive_index = len(faces)
            faces.append(indices)
            cell_rows.append({
                "primitive_index": primitive_index,
                "center_x": float(center.x),
                "center_y": float(center.y),
                "center_z": float(center.z),
                "normal_x": float(normal.x),
                "normal_y": float(normal.y),
                "normal_z": float(normal.z),
                "tangent_x": float(tangent.x),
                "tangent_y": float(tangent.y),
                "tangent_z": float(tangent.z),
                "bitangent_x": float(bitangent.x),
                "bitangent_y": float(bitangent.y),
                "bitangent_z": float(bitangent.z),
                "triangle_v0_x": float(p0.x),
                "triangle_v0_y": float(p0.y),
                "triangle_v0_z": float(p0.z),
                "triangle_v1_x": float(p1.x),
                "triangle_v1_y": float(p1.y),
                "triangle_v1_z": float(p1.z),
                "triangle_v2_x": float(p2.x),
                "triangle_v2_y": float(p2.y),
                "triangle_v2_z": float(p2.z),
                "edge_length_01": float(edge01.length),
                "edge_length_12": float(edge12.length),
                "edge_length_20": float(edge20.length),
                "cell_area": 0.5 * double_area,
            })
        if not faces:
            raise RuntimeError(
                f"Projected radio-map mesh '{source_obj.name}' contains only degenerate triangles"
            )

        token = _sanitize_name(source_obj.name) or "ReferenceMesh"
        frame_token = _frame_token(frame)
        ply_path = Path(run_dir) / f"measurement_surface_{token}_F{frame_token}.ply"
        cells_path = Path(run_dir) / f"measurement_surface_{token}_F{frame_token}_cells.csv"

        temporary_ply = ply_path.with_suffix(ply_path.suffix + ".tmp")
        with open(temporary_ply, "w", encoding="ascii", newline="\n") as handle:
            handle.write("ply\n")
            handle.write("format ascii 1.0\n")
            handle.write("comment SionnaRT-Bridge projected measurement surface\n")
            handle.write(f"element vertex {len(world_vertices)}\n")
            handle.write("property float x\nproperty float y\nproperty float z\n")
            handle.write(f"element face {len(faces)}\n")
            handle.write("property list uchar int vertex_indices\n")
            handle.write("end_header\n")
            for co in world_vertices:
                handle.write(f"{float(co.x):.9g} {float(co.y):.9g} {float(co.z):.9g}\n")
            for a, b, c in faces:
                handle.write(f"3 {a} {b} {c}\n")
        os.replace(temporary_ply, ply_path)

        temporary_cells = cells_path.with_suffix(cells_path.suffix + ".tmp")
        with open(temporary_cells, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=(
                    "primitive_index", "center_x", "center_y", "center_z",
                    "normal_x", "normal_y", "normal_z", "cell_area",
                    "tangent_x", "tangent_y", "tangent_z",
                    "bitangent_x", "bitangent_y", "bitangent_z",
                    "triangle_v0_x", "triangle_v0_y", "triangle_v0_z",
                    "triangle_v1_x", "triangle_v1_y", "triangle_v1_z",
                    "triangle_v2_x", "triangle_v2_y", "triangle_v2_z",
                    "edge_length_01", "edge_length_12", "edge_length_20",
                ),
            )
            writer.writeheader()
            writer.writerows(cell_rows)
        os.replace(temporary_cells, cells_path)

        return {
            "surface_mode": "PROJECTED",
            "reference_mesh_blender_name": source_obj.name,
            "reference_mesh_data_name": getattr(source_obj.data, "name", ""),
            "measurement_surface_mesh": str(ply_path),
            "measurement_surface_cells_csv": str(cells_path),
            "measurement_surface_sha256": _sha256(ply_path),
            "measurement_surface_vertex_count": len(world_vertices),
            "measurement_surface_triangle_count": len(faces),
            "measurement_surface_skipped_degenerate": skipped,
        }
    finally:
        if mesh is not None:
            try:
                evaluated.to_mesh_clear()
            except Exception:
                pass


def _radio_map_settings_payload(settings):
    surface_mode = _normalize_radio_map_surface_mode(
        getattr(settings, "radio_map_surface_mode", "PLANAR")
    )
    reference_obj = (
        _radio_map_reference_mesh_object(settings)
        if surface_mode == "PROJECTED" else None
    )
    payload = {
        "center_x": float(settings.radio_map_center_x),
        "center_y": float(settings.radio_map_center_y),
        "height": float(settings.radio_map_height),
        "size_x": float(settings.radio_map_size_x),
        "size_y": float(settings.radio_map_size_y),
        "cell_size_x": float(settings.radio_map_cell_size_x),
        "cell_size_y": float(settings.radio_map_cell_size_y),
        "metric": str(settings.radio_map_metric).lower(),
        "surface_mode": surface_mode,
        "reference_mesh_blender_name": reference_obj.name if reference_obj else "",
    }
    if surface_mode == "PROJECTED":
        if reference_obj is None:
            raise RuntimeError(
                "Select a Reference Mesh for the Projected Mesh radio map"
            )
        # The first projected node group supplied with this feature is Path Gain.
        _radio_map_mode_definition(payload["metric"], surface_mode)
    else:
        if payload["size_x"] <= 0.0 or payload["size_y"] <= 0.0:
            raise RuntimeError("Radio-map area dimensions must be larger than zero")
        if payload["cell_size_x"] <= 0.0 or payload["cell_size_y"] <= 0.0:
            raise RuntimeError("Radio-map cell dimensions must be larger than zero")
    return payload


def _radio_map_parameter_signature(settings):
    payload = _radio_map_settings_payload(settings)
    return tuple(payload[key] for key in (
        "center_x", "center_y", "height", "size_x", "size_y",
        "cell_size_x", "cell_size_y", "metric", "surface_mode",
        "reference_mesh_blender_name",
    ))


def _radio_map_parameters_change(context, frames):
    if len(frames) <= 1:
        return False
    scene = context.scene
    original = int(scene.frame_current)
    try:
        scene.frame_set(int(frames[0]))
        baseline = _radio_map_parameter_signature(_evaluated_bridge_settings(context))
        for frame in frames[1:]:
            scene.frame_set(int(frame))
            current = _radio_map_parameter_signature(_evaluated_bridge_settings(context))
            if any(
                (str(a) != str(b)) if isinstance(a, str) or isinstance(b, str)
                else abs(float(a) - float(b)) > 1e-7
                for a, b in zip(baseline, current)
            ):
                return True
        return False
    finally:
        scene.frame_set(original)


def _evaluated_reference_mesh_signature(context, source_obj):
    """Return a compact signature for AUTO timeline detection."""
    depsgraph = context.evaluated_depsgraph_get()
    try:
        evaluated = source_obj.evaluated_get(depsgraph)
    except Exception:
        evaluated = source_obj
    mesh = None
    try:
        mesh = evaluated.to_mesh(
            preserve_all_data_layers=False,
            depsgraph=depsgraph,
        )
        if mesh is None:
            return (source_obj.name, "missing")
        mesh.calc_loop_triangles()
        matrix = tuple(round(float(value), 7) for row in evaluated.matrix_world for value in row)
        count = len(mesh.vertices)
        step = max(1, count // 128)
        sampled = []
        for index in range(0, count, step):
            vertex = mesh.vertices[index]
            co = evaluated.matrix_world @ vertex.co
            sampled.extend((round(float(co.x), 6), round(float(co.y), 6), round(float(co.z), 6)))
        return (
            source_obj.name,
            len(mesh.vertices),
            len(mesh.edges),
            len(mesh.loop_triangles),
            matrix,
            tuple(sampled),
        )
    finally:
        if mesh is not None:
            try:
                evaluated.to_mesh_clear()
            except Exception:
                pass


def _radio_map_reference_mesh_changes(context, frames):
    if len(frames) <= 1:
        return False
    settings = context.scene.sionna_bridge
    if _normalize_radio_map_surface_mode(settings.radio_map_surface_mode) != "PROJECTED":
        return False
    source_obj = _radio_map_reference_mesh_object(settings)
    if source_obj is None:
        return False
    scene = context.scene
    original = int(scene.frame_current)
    try:
        scene.frame_set(int(frames[0]))
        baseline = _evaluated_reference_mesh_signature(context, source_obj)
        for frame in frames[1:]:
            scene.frame_set(int(frame))
            if _evaluated_reference_mesh_signature(context, source_obj) != baseline:
                return True
        return False
    finally:
        scene.frame_set(original)


def _radio_map_simulation_frames(context, transmitters):
    settings = context.scene.sionna_bridge
    mode = settings.timeline_mode
    if mode == "CURRENT":
        return [int(context.scene.frame_current)], "current frame"

    candidate_frames = _frame_range(context.scene, settings.timeline_step)
    if mode == "RANGE":
        return candidate_frames, "scene frame range"
    if _procedural_scene_active(context.scene):
        return candidate_frames, "procedural scene geometry detected"

    device_changed, parameter_changed, material_changed = _timeline_change_reasons(
        context, transmitters, candidate_frames
    )
    map_changed = _radio_map_parameters_change(context, candidate_frames)
    reference_mesh_changed = _radio_map_reference_mesh_changes(context, candidate_frames)
    if device_changed or parameter_changed or material_changed or map_changed or reference_mesh_changed:
        reasons = []
        if device_changed:
            reasons.append("animated TX")
        if parameter_changed:
            reasons.append("animated simulation settings")
        if material_changed:
            reasons.append("animated radio materials")
        if map_changed:
            reasons.append("animated radio-map settings")
        if reference_mesh_changed:
            reasons.append("animated projected reference mesh")
        return candidate_frames, " and ".join(reasons) + " detected"
    return [int(context.scene.frame_current)], "no animated TX or settings detected"


def _auto_center_radio_map_payload(
    payload, scene, depsgraph, tx_name, *, include_z=False
):
    """Override a coverage region center with the evaluated moving TX position."""
    tx = _auto_center_tx_object(scene, tx_name)
    if tx is None:
        return False
    try:
        evaluated = tx.evaluated_get(depsgraph) if depsgraph is not None else tx
        location = evaluated.matrix_world.translation
    except (ReferenceError, RuntimeError):
        return False
    payload["center_x"] = float(location.x)
    payload["center_y"] = float(location.y)
    if include_z:
        payload["center_z"] = float(location.z)
    payload["auto_center_tx_name"] = tx.name
    return True


def _sample_radio_map_frame_payloads(
    context, frames, transmitters, run_dir, *, auto_center_tx_name=""
):
    scene = context.scene
    original = int(scene.frame_current)
    payloads = []
    try:
        for frame in frames:
            scene.frame_set(int(frame))
            settings = _evaluated_bridge_settings(context)
            depsgraph = context.evaluated_depsgraph_get()
            try:
                depsgraph.update()
            except Exception:
                pass
            radio_map_payload = _radio_map_settings_payload(settings)
            if (
                auto_center_tx_name
                and getattr(settings, "radio_map_auto_center_on_tx", True)
                and _normalize_radio_map_surface_mode(
                    radio_map_payload.get("surface_mode", "PLANAR")
                ) == "PLANAR"
            ):
                _auto_center_radio_map_payload(
                    radio_map_payload, scene, depsgraph, auto_center_tx_name, include_z=False
                )
            payload = {
                "frame": int(frame),
                "simulation": _simulation_settings_payload(settings),
                "radio_map": radio_map_payload,
                "transmitters": [
                    _device_payload(obj, depsgraph) for obj in transmitters
                ],
                "materials": _material_payloads(scene),
            }
            procedural_stats = _procedural_stats_for_payload(context, depsgraph)
            if procedural_stats is not None:
                payload["procedural_geometry_stats"] = procedural_stats
            if payload["radio_map"].get("surface_mode") == "PROJECTED":
                reference_obj = _radio_map_reference_mesh_object(settings)
                payload["radio_map"].update(
                    _export_projected_measurement_surface(
                        context, reference_obj, frame, run_dir, depsgraph=depsgraph
                    )
                )
            payloads.append(payload)
    finally:
        scene.frame_set(original)
    return payloads


def _build_radio_map_package(
    context, scene_source, *, force_current_frame=False, auto_anchor_tx_name=""
):
    settings = context.scene.sionna_bridge
    transmitters = _device_objects(context.scene, "TX")
    if not transmitters:
        raise RuntimeError("Add at least one Sionna transmitter before generating a radio map")

    initial_map_settings = _radio_map_settings_payload(settings)
    initial_surface_mode = _normalize_radio_map_surface_mode(
        initial_map_settings.get("surface_mode", "PLANAR")
    )
    if initial_surface_mode == "PROJECTED":
        projected_mode = _radio_map_mode_definition(
            initial_map_settings.get("metric", "path_gain"), initial_surface_mode
        )
        # The selected Blender mesh is a simulation input only. The generated
        # Geometry Nodes object already contains the Sionna cell centers in
        # world coordinates, so the node group does not need an Object socket.
        _existing_geometry_nodes_group(
            projected_mode["node_group"], "projected radio-map point cloud"
        )

    if force_current_frame:
        frames = [int(context.scene.frame_current)]
        frame_reason = "current frame (automatic device-move recompute)"
    else:
        frames, frame_reason = _radio_map_simulation_frames(context, transmitters)
    run_dir = _make_radio_map_run_dir(settings)
    created_utc = _now_utc()
    export_spec = _export_output_spec(settings, run_dir, "coverage_2d", created_utc)
    frame_payloads = _sample_radio_map_frame_payloads(
        context, frames, transmitters, run_dir,
        auto_center_tx_name=(auto_anchor_tx_name if force_current_frame else ""),
    )
    _attach_scene_sources(frame_payloads, scene_source)
    config_path = run_dir / "radio_map_config.json"

    for payload in frame_payloads:
        token = _frame_token(payload["frame"])
        payload["output"] = {
            "results_json": str(run_dir / f"radio_map_frame_{token}.json"),
            "results_npz": str(run_dir / f"radio_map_frame_{token}.npz"),
            "status_json": str(run_dir / f"status_frame_{token}.json"),
        }

    first = frame_payloads[0]
    first_scene_xml = Path(first["scene_xml"])
    config = {
        "schema_version": 7,
        "bridge_version": _ADDON_VERSION,
        "created_utc": created_utc,
        "blend_file": bpy.data.filepath or None,
        "scene_name": context.scene.name,
        "scene_xml": str(first_scene_xml),
        "scene_xml_sha256": _sha256(first_scene_xml),
        "procedural_scene": isinstance(scene_source, dict),
        # Single-frame fallbacks for compatibility with older workers/tools.
        "frame": int(first["frame"]),
        "transmitters": first["transmitters"],
        "simulation": first["simulation"],
        "antenna": _antenna_config(settings, transmitters),
        "materials": list(first.get("materials", [])),
        "radio_map": first["radio_map"],
        "frames": frame_payloads,
        "output": {
            "status_json": str(run_dir / "status.json"),
            "results_csv": str(run_dir / "radio_map_all_frames.csv"),
            "results_json": str(run_dir / "radio_map_frames_manifest.json"),
            "frames_manifest_json": str(run_dir / "radio_map_frames_manifest.json"),
            "keep_external_results": settings.export_format == "HDF5",
            **export_spec,
        },
    }
    tile_snapshot = _snapshot_tile_spatial_dataset(run_dir, settings)
    if tile_snapshot is not None:
        config["tile_spatial_dataset"] = tile_snapshot
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)

    settings.last_radio_map_run_dir = str(run_dir)
    frequencies = sorted({
        float(item["simulation"]["frequency_ghz"]) for item in frame_payloads
    })
    frequency_note = ", ".join(f"{value:g}" for value in frequencies)
    settings.last_status = (
        f"Prepared {len(frame_payloads)} radio-map frame(s): {frame_reason}; "
        f"frequencies {frequency_note} GHz"
    )
    return run_dir, config_path, config


def _start_radio_map_process(
    context, scene_source, *, force_current_frame=False, auto_triggered=False,
    auto_anchor_tx_name=""
):
    settings = context.scene.sionna_bridge
    executable, error = _resolve_python_executable(settings)
    worker = _radio_map_worker_script()
    if executable is None:
        raise RuntimeError(error)
    if not worker.exists():
        raise RuntimeError(f"Radio-map worker script is missing: {worker}")

    run_dir, config_path, config = _build_radio_map_package(
        context, scene_source, force_current_frame=force_current_frame,
        auto_anchor_tx_name=auto_anchor_tx_name,
    )
    started_ns = time.time_ns()
    # Keep the previous verified radio-map CSV connected while the worker
    # writes a new, uniquely named output. The node is updated only after the
    # new CSV passes freshness and settings verification.
    preflight_notes = []

    _check_stale_or_active_lock(settings)
    log_path = run_dir / "radio_map.log"
    log_handle = open(log_path, "w", encoding="utf-8", buffering=1)
    command = [str(executable), str(worker), "--config", str(config_path)]
    worker_env, _libllvm_path = _sionna_worker_environment(settings, executable)
    try:
        process = _popen_with_retries(
            command, cwd=run_dir, stdout=log_handle,
            creationflags=_subprocess_creationflags(), env=worker_env,
        )
        lock_path = _write_active_run_lock(settings, process, "2D-radio-map", run_dir)
    except Exception:
        log_handle.close()
        raise

    _RADIO_MAP_STATE.update({
        "process": process,
        "log_handle": log_handle,
        "scene_name": context.scene.name,
        "run_dir": str(run_dir),
        "results_json": config["output"]["results_json"],
        "results_csv": config["output"]["results_csv"],
        "expected_frequency_ghz": float(config["frames"][0]["simulation"]["frequency_ghz"]),
        "frame": int(config["frames"][0]["frame"]),
        "frame_count": len(config["frames"]),
        "config_path": str(config_path),
        "started_ns": int(started_ns),
        "pid": int(process.pid),
        "lock_path": str(lock_path),
        "auto_triggered": bool(auto_triggered),
    })
    requested_frequencies = sorted({
        float(item["simulation"]["frequency_ghz"]) for item in config["frames"]
    })
    frequency_note = ", ".join(f"{value:g}" for value in requested_frequencies)
    _set_status(
        settings,
        f"Sionna radio map running {len(config['frames'])} frame(s) at {frequency_note} GHz (PID {process.pid})",
        details=(
            "Previous verified map data remains active until completion.\n"
            f"Run folder: {run_dir}\nLog file: {log_path}\nConfig: {config_path}"
        ),
        run_dir=run_dir, log_path=log_path,
    )
    if preflight_notes:
        settings.last_status += "; " + "; ".join(preflight_notes)
    if not bpy.app.timers.is_registered(_poll_radio_map_process):
        bpy.app.timers.register(
            _poll_radio_map_process,
            first_interval=0.5,
            persistent=False,
        )
    return process, config


def _close_radio_map_handles():
    handle = _RADIO_MAP_STATE.get("log_handle")
    if handle:
        try:
            handle.close()
        except Exception:
            pass
    _release_active_run_lock(_RADIO_MAP_STATE.get("lock_path"), _RADIO_MAP_STATE.get("pid", 0))
    _RADIO_MAP_STATE["log_handle"] = None
    _RADIO_MAP_STATE["process"] = None
    _RADIO_MAP_STATE["pid"] = 0
    _RADIO_MAP_STATE["lock_path"] = ""
    _RADIO_MAP_STATE["auto_triggered"] = False



def _make_radio_map_3d_run_dir(settings):
    workspace = _workspace(settings)
    workspace.mkdir(parents=True, exist_ok=True)
    blend_stem = Path(bpy.data.filepath).stem if bpy.data.filepath else "untitled"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    token = uuid.uuid4().hex[:8]
    base = workspace / f"{_sanitize_name(blend_stem)}_radio_map_3d_{timestamp}_{token}"
    candidate = base
    suffix = 1
    while candidate.exists():
        candidate = Path(str(base) + f"_{suffix:02d}")
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


def _radio_map_3d_settings_payload(settings):
    payload = {
        "center_x": float(settings.radio_map_3d_center_x),
        "center_y": float(settings.radio_map_3d_center_y),
        "center_z": float(settings.radio_map_3d_center_z),
        "size_x": float(settings.radio_map_3d_size_x),
        "size_y": float(settings.radio_map_3d_size_y),
        "size_z": float(settings.radio_map_3d_size_z),
        "cell_size_x": float(settings.radio_map_3d_cell_size_x),
        "cell_size_y": float(settings.radio_map_3d_cell_size_y),
        "cell_size_z": float(settings.radio_map_3d_cell_size_z),
        "metric": str(settings.radio_map_3d_metric).lower(),
    }
    for key in ("size_x", "size_y", "size_z", "cell_size_x", "cell_size_y", "cell_size_z"):
        if payload[key] <= 0.0:
            raise RuntimeError(f"3D radio-map {key} must be larger than zero")
    return payload


def _radio_map_3d_parameter_signature(settings):
    payload = _radio_map_3d_settings_payload(settings)
    return tuple(payload[key] for key in (
        "center_x", "center_y", "center_z", "size_x", "size_y", "size_z",
        "cell_size_x", "cell_size_y", "cell_size_z", "metric",
    ))


def _radio_map_3d_parameters_change(context, frames):
    if len(frames) <= 1:
        return False
    scene = context.scene
    original = int(scene.frame_current)
    try:
        scene.frame_set(int(frames[0]))
        baseline = _radio_map_3d_parameter_signature(_evaluated_bridge_settings(context))
        for frame in frames[1:]:
            scene.frame_set(int(frame))
            current = _radio_map_3d_parameter_signature(_evaluated_bridge_settings(context))
            if any(
                (str(a) != str(b)) if isinstance(a, str) or isinstance(b, str)
                else abs(float(a) - float(b)) > 1e-7
                for a, b in zip(baseline, current)
            ):
                return True
        return False
    finally:
        scene.frame_set(original)


def _radio_map_3d_simulation_frames(context, transmitters):
    settings = context.scene.sionna_bridge
    if settings.timeline_mode == "CURRENT":
        return [int(context.scene.frame_current)], "current frame"
    candidate_frames = _frame_range(context.scene, settings.timeline_step)
    if settings.timeline_mode == "RANGE":
        return candidate_frames, "scene frame range"
    if _procedural_scene_active(context.scene):
        return candidate_frames, "procedural scene geometry detected"
    device_changed, parameter_changed, material_changed = _timeline_change_reasons(
        context, transmitters, candidate_frames
    )
    volume_changed = _radio_map_3d_parameters_change(context, candidate_frames)
    if device_changed or parameter_changed or material_changed or volume_changed:
        reasons = []
        if device_changed:
            reasons.append("animated TX")
        if parameter_changed:
            reasons.append("animated simulation settings")
        if material_changed:
            reasons.append("animated radio materials")
        if volume_changed:
            reasons.append("animated 3D volume settings")
        return candidate_frames, " and ".join(reasons) + " detected"
    return [int(context.scene.frame_current)], "no animated TX or settings detected"


def _sample_radio_map_3d_frame_payloads(
    context, frames, transmitters, *, auto_center_tx_name=""
):
    scene = context.scene
    original = int(scene.frame_current)
    payloads = []
    try:
        for frame in frames:
            scene.frame_set(int(frame))
            settings = _evaluated_bridge_settings(context)
            depsgraph = context.evaluated_depsgraph_get()
            try:
                depsgraph.update()
            except Exception:
                pass
            radio_map_3d_payload = _radio_map_3d_settings_payload(settings)
            if (
                auto_center_tx_name
                and getattr(settings, "radio_map_3d_auto_center_on_tx", True)
            ):
                _auto_center_radio_map_payload(
                    radio_map_3d_payload, scene, depsgraph, auto_center_tx_name, include_z=True
                )
            payload = {
                "frame": int(frame),
                "simulation": _simulation_settings_payload(settings),
                "radio_map_3d": radio_map_3d_payload,
                "transmitters": [_device_payload(obj, depsgraph) for obj in transmitters],
                "materials": _material_payloads(scene),
            }
            procedural_stats = _procedural_stats_for_payload(context, depsgraph)
            if procedural_stats is not None:
                payload["procedural_geometry_stats"] = procedural_stats
            payloads.append(payload)
    finally:
        scene.frame_set(original)
    return payloads


def _build_radio_map_3d_package(
    context, scene_source, *, force_current_frame=False, auto_anchor_tx_name=""
):
    settings = context.scene.sionna_bridge
    transmitters = _device_objects(context.scene, "TX")
    if not transmitters:
        raise RuntimeError("Add at least one Sionna transmitter before generating a 3D radio map")
    if force_current_frame:
        frames = [int(context.scene.frame_current)]
        frame_reason = "current frame (automatic device-move recompute)"
    else:
        frames, frame_reason = _radio_map_3d_simulation_frames(context, transmitters)
    frame_payloads = _sample_radio_map_3d_frame_payloads(
        context, frames, transmitters,
        auto_center_tx_name=(auto_anchor_tx_name if force_current_frame else ""),
    )
    _attach_scene_sources(frame_payloads, scene_source)
    run_dir = _make_radio_map_3d_run_dir(settings)
    config_path = run_dir / "radio_map_3d_config.json"
    created_utc = _now_utc()
    export_spec = _export_output_spec(settings, run_dir, "coverage_3d", created_utc)
    for payload in frame_payloads:
        token = _frame_token(payload["frame"])
        payload["output"] = {
            "results_json": str(run_dir / f"radio_map_3d_frame_{token}.json"),
            "results_npz": str(run_dir / f"radio_map_3d_frame_{token}.npz"),
            "status_json": str(run_dir / f"status_3d_frame_{token}.json"),
        }
    first = frame_payloads[0]
    first_scene_xml = Path(first["scene_xml"])
    config = {
        "schema_version": 4,
        "bridge_version": _ADDON_VERSION,
        "created_utc": created_utc,
        "blend_file": bpy.data.filepath or None,
        "scene_name": context.scene.name,
        "scene_xml": str(first_scene_xml),
        "scene_xml_sha256": _sha256(first_scene_xml),
        "procedural_scene": isinstance(scene_source, dict),
        "frame": int(first["frame"]),
        "transmitters": first["transmitters"],
        "simulation": first["simulation"],
        "antenna": _antenna_config(settings, transmitters),
        "materials": list(first.get("materials", [])),
        "radio_map_3d": first["radio_map_3d"],
        "frames": frame_payloads,
        "output": {
            "status_json": str(run_dir / "status.json"),
            "results_csv": str(run_dir / "radio_map_3d_all_frames.csv"),
            "results_json": str(run_dir / "radio_map_3d_frames_manifest.json"),
            "frames_manifest_json": str(run_dir / "radio_map_3d_frames_manifest.json"),
            "keep_external_results": settings.export_format == "HDF5",
            **export_spec,
        },
    }
    tile_snapshot = _snapshot_tile_spatial_dataset(run_dir, settings)
    if tile_snapshot is not None:
        config["tile_spatial_dataset"] = tile_snapshot
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
    settings.last_radio_map_3d_run_dir = str(run_dir)
    frequencies = sorted({float(item["simulation"]["frequency_ghz"]) for item in frame_payloads})
    settings.last_status = (
        f"Prepared {len(frame_payloads)} 3D radio-map frame(s): {frame_reason}; "
        f"frequencies {', '.join(f'{value:g}' for value in frequencies)} GHz"
    )
    return run_dir, config_path, config


def _start_radio_map_3d_process(
    context, scene_source, *, force_current_frame=False, auto_triggered=False,
    auto_anchor_tx_name=""
):
    settings = context.scene.sionna_bridge
    executable, error = _resolve_python_executable(settings)
    worker = _radio_map_3d_worker_script()
    if executable is None:
        raise RuntimeError(error)
    if not worker.exists():
        raise RuntimeError(f"3D radio-map worker script is missing: {worker}")
    run_dir, config_path, config = _build_radio_map_3d_package(
        context, scene_source, force_current_frame=force_current_frame,
        auto_anchor_tx_name=auto_anchor_tx_name,
    )
    started_ns = time.time_ns()
    _check_stale_or_active_lock(settings)
    log_path = run_dir / "radio_map_3d.log"
    log_handle = open(log_path, "w", encoding="utf-8", buffering=1)
    command = [str(executable), str(worker), "--config", str(config_path)]
    worker_env, _libllvm_path = _sionna_worker_environment(settings, executable)
    try:
        process = _popen_with_retries(
            command, cwd=run_dir, stdout=log_handle,
            creationflags=_subprocess_creationflags(), env=worker_env,
        )
        lock_path = _write_active_run_lock(settings, process, "3D-radio-map", run_dir)
    except Exception:
        log_handle.close()
        raise
    _RADIO_MAP_3D_STATE.update({
        "process": process,
        "log_handle": log_handle,
        "scene_name": context.scene.name,
        "run_dir": str(run_dir),
        "results_json": config["output"]["results_json"],
        "results_csv": config["output"]["results_csv"],
        "frame_count": len(config["frames"]),
        "config_path": str(config_path),
        "started_ns": int(started_ns),
        "pid": int(process.pid),
        "lock_path": str(lock_path),
        "auto_triggered": bool(auto_triggered),
    })
    frequencies = sorted({float(item["simulation"]["frequency_ghz"]) for item in config["frames"]})
    frequency_note = ", ".join(f"{value:g}" for value in frequencies)
    _set_status(
        settings,
        f"Sionna 3D radio map running {len(config['frames'])} frame(s) at {frequency_note} GHz (PID {process.pid})",
        details=f"Run folder: {run_dir}\nLog file: {log_path}\nConfig: {config_path}",
        run_dir=run_dir, log_path=log_path,
    )
    if not bpy.app.timers.is_registered(_poll_radio_map_3d_process):
        bpy.app.timers.register(_poll_radio_map_3d_process, first_interval=0.5, persistent=False)
    return process, config


def _close_radio_map_3d_handles():
    handle = _RADIO_MAP_3D_STATE.get("log_handle")
    if handle:
        try:
            handle.close()
        except Exception:
            pass
    _release_active_run_lock(_RADIO_MAP_3D_STATE.get("lock_path"), _RADIO_MAP_3D_STATE.get("pid", 0))
    _RADIO_MAP_3D_STATE["log_handle"] = None
    _RADIO_MAP_3D_STATE["process"] = None
    _RADIO_MAP_3D_STATE["pid"] = 0
    _RADIO_MAP_3D_STATE["lock_path"] = ""
    _RADIO_MAP_3D_STATE["auto_triggered"] = False



def _remove_previous_auto_embedded_results(scene, collection_key):
    """Remove prior auto-move results while preserving manually generated outputs."""
    workflow = _ensure_environment(scene, migrate=True)
    collection = workflow[collection_key]
    removed = 0
    for obj in list(collection.objects):
        if not (
            bool(obj.get("sionna_auto_device_move_result", False))
            or bool(obj.get("sionna_auto_tx_move_result", False))
        ):
            continue
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        removed += 1
        if data is None or getattr(data, "users", 1) != 0:
            continue
        try:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.PointCloud):
                bpy.data.pointclouds.remove(data)
            elif isinstance(data, bpy.types.Curve):
                bpy.data.curves.remove(data)
        except Exception:
            pass
    return removed

def _verify_radio_map_3d_output(csv_path, config_path, status_path, started_ns):
    _verify_fresh_file(csv_path, started_ns, "3D radio-map CSV")
    config = _load_json_file(config_path)
    status = _completed_status_with_recovery(
        config_path, status_path, csv_path, started_ns, "3D radio-map"
    )
    if status.get("state") != "finished":
        raise RuntimeError(
            f"3D radio-map worker did not report a finished state: {status.get('state', 'missing')}"
        )
    if int(status.get("point_count", 0) or 0) <= 0:
        raise RuntimeError("The 3D radio-map worker produced no voxel rows")
    expected = {int(item.get("frame", 0)): item for item in config.get("frames", [])}
    actual = {int(item.get("frame", 0)): item for item in status.get("frames", [])}
    if set(expected) != set(actual):
        raise RuntimeError(
            f"3D radio-map frame mismatch: requested {sorted(expected)}, generated {sorted(actual)}"
        )
    for frame, requested in expected.items():
        generated = actual[frame]
        for key in ("frequency_ghz", "max_depth", "samples_per_src", "seed"):
            if not _float_close(
                generated.get("simulation", {}).get(key, 0.0),
                requested.get("simulation", {}).get(key, 0.0), abs_tol=1e-5,
            ):
                raise RuntimeError(f"3D radio-map frame {frame} {key} mismatch")
        for key in (
            "center_x", "center_y", "center_z", "size_x", "size_y", "size_z",
            "cell_size_x", "cell_size_y", "cell_size_z",
        ):
            if not _float_close(
                generated.get("radio_map_3d", {}).get(key, 0.0),
                requested.get("radio_map_3d", {}).get(key, 0.0), abs_tol=1e-5,
            ):
                raise RuntimeError(f"3D radio-map frame {frame} {key} mismatch")
    first = _read_csv_first_row(csv_path)
    if not first:
        raise RuntimeError("The generated 3D radio-map CSV contains no rows")
    metric = str((config.get("radio_map_3d") or {}).get("metric", "path_gain")).lower()
    metric_columns = {
        "path_gain": {"path_gain", "path_gain_db"},
        "rss": {"rss", "rss_dbm"},
        "sinr": {"sinr", "sinr_db"},
    }
    required = {"x", "y", "z", "frame", "cell_size_x", "cell_size_y", "cell_size_z"} | metric_columns.get(metric, set())
    missing = sorted(required.difference(first))
    if missing:
        raise RuntimeError("3D radio-map CSV is missing columns: " + ", ".join(missing))
    return config, status


def _poll_radio_map_3d_process():
    process = _RADIO_MAP_3D_STATE.get("process")
    if process is None:
        return None
    if process.poll() is None:
        scene = bpy.data.scenes.get(_RADIO_MAP_3D_STATE.get("scene_name", ""))
        if scene is not None:
            _update_running_status(
                scene, "3D radio map", _RADIO_MAP_3D_STATE.get("run_dir", ""),
                _RADIO_MAP_3D_STATE.get("started_ns", 0),
            )
        return 0.5
    return_code = process.returncode
    run_dir = Path(_RADIO_MAP_3D_STATE.get("run_dir") or "")
    results_csv = Path(_RADIO_MAP_3D_STATE.get("results_csv") or "")
    results_json = Path(_RADIO_MAP_3D_STATE.get("results_json") or "")
    config_path = Path(_RADIO_MAP_3D_STATE.get("config_path") or "")
    started_ns = int(_RADIO_MAP_3D_STATE.get("started_ns", 0) or 0)
    scene_name = _RADIO_MAP_3D_STATE.get("scene_name", "")
    worker_pid = int(_RADIO_MAP_3D_STATE.get("pid", 0) or 0)
    expected_frame_count = int(_RADIO_MAP_3D_STATE.get("frame_count", 1) or 1)
    auto_triggered = bool(_RADIO_MAP_3D_STATE.get("auto_triggered", False))
    _close_radio_map_3d_handles()
    scene = bpy.data.scenes.get(scene_name)
    if scene is None:
        return None
    settings = scene.sionna_bridge
    status_path = run_dir / "status.json"
    status_payload = _completed_status_with_recovery(
        config_path, status_path, results_csv, started_ns, "3D radio-map"
    )
    success = False
    try:
        if status_payload.get("state") != "finished":
            raise RuntimeError(
                f"worker exit {return_code}, state {status_payload.get('state', 'missing')}. "
                f"{status_payload.get('error', '')}"
            )
        config, verified_status = _verify_radio_map_3d_output(
            results_csv, config_path, status_path, started_ns
        )
        output_spec = dict(config.get("output") or {})
        export_format = str(verified_status.get("export_format") or output_spec.get("export_format") or "NONE")
        export_file = str(verified_status.get("export_file") or output_spec.get("export_file") or "")
        export_metadata = str(verified_status.get("export_metadata_json") or output_spec.get("export_metadata_json") or "")
        settings.last_radio_map_3d_csv = str(results_csv)
        settings.last_radio_map_3d_json = str(results_json) if results_json.exists() else ""
        map_metric = _normalize_radio_map_metric(
            (config.get("radio_map_3d") or {}).get("metric", "path_gain")
        )
        mode = _radio_map_3d_mode_definition(map_metric)
        group_name = _radio_map_3d_geometry_nodes_group_name(map_metric)
        if auto_triggered:
            _remove_previous_auto_embedded_results(scene, "radio_maps_3d")
        embedded_obj, embedded_count, _group = _create_embedded_point_object(
            scene, results_csv, config, prefix=_radio_map_3d_object_prefix(map_metric),
            collection_key="radio_maps_3d", group_name=group_name,
            result_type="radio_map_3d_pointcloud",
            modifier_name=f"Sionna 3D Coverage Map {mode['label']}",
            replace=(False if auto_triggered else bool(settings.radio_map_3d_replace_existing)),
            radius=max(0.001, float(settings.radio_map_3d_point_radius)),
        )
        if auto_triggered:
            embedded_obj["sionna_auto_device_move_result"] = True
        settings.last_radio_map_3d_object = embedded_obj.name
        _maybe_auto_refresh_analytics(scene, "RADIO_MAP_3D")
        frame_count = int(verified_status.get("frame_count", expected_frame_count) or expected_frame_count)
        frequencies = sorted({
            float(item.get("simulation", {}).get("frequency_ghz", 0.0))
            for item in config.get("frames", [])
        })
        frequency_note = ", ".join(f"{value:g}" for value in frequencies)
        _set_status(
            settings,
            f"3D {map_metric.upper()} radio map embedded: {embedded_obj.name}; {embedded_count} voxels; {frame_count} frame(s), {frequency_note} GHz",
            details=(
                f"Worker PID: {worker_pid}\nWorker exit code: {return_code}\n"
                f"Result CSV: {results_csv}\nRun folder: {run_dir}\n"
                f"Geometry Nodes: {group_name}\n"
                f"Metric attributes: {mode['linear_attribute']}, {mode['db_attribute']}"
                + ("\n" + str(verified_status.get("status_recovery_note"))
                   if verified_status.get("recovered_from_manifest") else "")
            ),
            run_dir=run_dir, log_path=run_dir / "radio_map_3d.log",
        )
        cleanup_note = _cleanup_external_run(
            run_dir, settings, path_result=False, radio_result=False,
            radio_3d_result=True, export_file=export_file,
            export_metadata=export_metadata, export_format=export_format,
        )
        settings.last_status += f"; {cleanup_note}"
        success = True
    except Exception as exc:
        _set_status(
            settings,
            f"3D radio-map result rejected: {exc}",
            _failure_details("3D radio map", return_code, status_payload, run_dir, "radio_map_3d.log"),
            run_dir=run_dir, log_path=run_dir / "radio_map_3d.log",
        )
    if _BATCH_STATE.get("active") and _BATCH_STATE.get("scene_name") == scene_name:
        statuses = [
            str(_BATCH_STATE.get("path_status") or "").strip(),
            str(_BATCH_STATE.get("radio_map_status") or "").strip(),
            settings.last_status,
        ]
        statuses = [item for item in statuses if item]
        settings.last_status = ("Batch complete — " if success else "Batch finished with errors — ") + " | ".join(statuses)
        _reset_batch_state()
    _redraw_sionna_ui()
    return None


def _clear_radio_map_collection(collection):
    """Remove radio-map carrier objects without touching user node groups."""
    for obj in list(collection.objects):
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None and getattr(data, "users", 1) == 0:
            try:
                if isinstance(data, bpy.types.Mesh):
                    bpy.data.meshes.remove(data)
                elif isinstance(data, bpy.types.PointCloud):
                    bpy.data.pointclouds.remove(data)
            except Exception:
                pass



def _existing_geometry_nodes_group(requested_name, label):
    """Return an exact Geometry Nodes group, restoring bundled groups if needed."""
    requested_name = str(requested_name or "").strip()
    group = bpy.data.node_groups.get(requested_name) if requested_name else None
    if group is None or getattr(group, "bl_idname", "") != "GeometryNodeTree":
        # Self-heal when a bundled group was deleted during the current Blender
        # session. This keeps simulation operators independent from manual Append.
        _ensure_bundled_geometry_nodes(verbose=False)
        group = bpy.data.node_groups.get(requested_name) if requested_name else None
    if group is None or getattr(group, "bl_idname", "") != "GeometryNodeTree":
        raise RuntimeError(
            f"Geometry Nodes group '{requested_name}' was not found for {label}. "
            f"The bundled library '{_BUNDLED_NODE_LIBRARY}' does not contain it."
        )
    return group


def _carrier_object_in_collection(collection, result_type):
    for obj in collection.objects:
        if str(obj.get("sionna_result_type", "")) == result_type:
            return obj
    return None


def _ensure_carrier_mesh(
    scene,
    collection_key,
    group_name,
    object_name,
    modifier_name,
    result_type,
    csv_path=None,
    replace=False,
):
    """Create or repair a lightweight mesh carrying an existing GN group.

    This never creates or rewires a node tree. If ``csv_path`` is provided, the
    existing Import CSV node in ``group_name`` is updated before assignment.
    """
    workflow = _ensure_environment(scene, migrate=True)
    collection = workflow[collection_key]
    group = _existing_geometry_nodes_group(group_name, result_type)

    if csv_path is not None:
        csv_path = Path(csv_path).expanduser().resolve()
        if not csv_path.is_file():
            raise RuntimeError(f"CSV not found: {csv_path}")
        _update_named_geometry_nodes_csv_path(csv_path, group.name, result_type)

    obj = _carrier_object_in_collection(collection, result_type)
    if replace and obj is not None:
        old_data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if isinstance(old_data, bpy.types.Mesh) and old_data.users == 0:
            bpy.data.meshes.remove(old_data)
        obj = None

    if obj is None or not isinstance(getattr(obj, "data", None), bpy.types.Mesh):
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
        mesh = bpy.data.meshes.new(object_name + "_Carrier")
        mesh.from_pydata([], [], [])
        mesh.update()
        obj = bpy.data.objects.new(object_name, mesh)
        collection.objects.link(obj)
    else:
        _move_object_to_collection(obj, collection)
        obj.name = object_name

    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    obj["sionna_result_type"] = result_type
    if csv_path is not None:
        obj["sionna_csv"] = str(csv_path)

    modifier = next(
        (item for item in obj.modifiers if item.type == "NODES" and item.name == modifier_name),
        None,
    )
    if modifier is None:
        modifier = obj.modifiers.new(name=modifier_name, type="NODES")
    modifier.node_group = group

    try:
        group.update_tag()
        obj.update_tag()
    except Exception:
        pass
    return obj, group


def _ensure_path_carrier(scene, csv_path=None):
    settings = scene.sionna_bridge
    group_name = settings.geometry_nodes_group_name.strip() or _DEFAULT_GEOMETRY_NODES_GROUP
    return _ensure_carrier_mesh(
        scene=scene,
        collection_key="simulated_paths",
        group_name=group_name,
        object_name="Sionna_Paths_Carrier",
        modifier_name="Sionna Paths",
        result_type="paths_csv_carrier",
        csv_path=csv_path,
        replace=False,
    )


def _normalize_radio_map_metric(metric):
    value = str(metric or "path_gain").strip().lower()
    aliases = {
        "pathgain": "path_gain",
        "path gain": "path_gain",
        "sirn": "sinr",
    }
    value = aliases.get(value, value)
    return value if value in _RADIO_MAP_MODE_DEFINITIONS else "path_gain"


def _normalize_radio_map_surface_mode(surface_mode):
    value = str(surface_mode or "PLANAR").strip().upper()
    aliases = {
        "PLANE": "PLANAR",
        "GRID": "PLANAR",
        "PROJECT": "PROJECTED",
        "MESH": "PROJECTED",
        "PROJECTED_MESH": "PROJECTED",
    }
    value = aliases.get(value, value)
    return value if value in {"PLANAR", "PROJECTED"} else "PLANAR"


def _radio_map_mode_definition(metric, surface_mode="PLANAR"):
    metric = _normalize_radio_map_metric(metric)
    surface_mode = _normalize_radio_map_surface_mode(surface_mode)
    if surface_mode == "PROJECTED":
        mode = _RADIO_MAP_PROJECTED_MODE_DEFINITIONS.get(metric)
        if mode is None:
            raise RuntimeError(
                "Projected mesh radio maps currently support Path Gain only. "
                "Select Path Gain or switch Map Surface back to Planar Grid."
            )
        return mode
    return _RADIO_MAP_MODE_DEFINITIONS[metric]


def _radio_map_metric_from_csv(csv_path, fallback="path_gain"):
    """Infer the selected map metric from the metric columns in a result CSV."""
    if csv_path is None:
        return _normalize_radio_map_metric(fallback)
    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as handle:
            columns = {str(name).strip().lower() for name in (csv.DictReader(handle).fieldnames or [])}
    except (OSError, TypeError, ValueError):
        return _normalize_radio_map_metric(fallback)
    if {"sinr", "sinr_db"}.intersection(columns):
        return "sinr"
    if {"rss", "rss_dbm"}.intersection(columns):
        return "rss"
    if {"path_gain", "path_gain_db"}.intersection(columns):
        return "path_gain"
    return _normalize_radio_map_metric(fallback)


def _radio_map_surface_mode_from_csv(csv_path, fallback="PLANAR"):
    """Infer planar/projected output from an embedded or retained result CSV."""
    if csv_path is None:
        return _normalize_radio_map_surface_mode(fallback)
    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as handle:
            first = next(csv.DictReader(handle), None) or {}
    except (OSError, TypeError, ValueError):
        return _normalize_radio_map_surface_mode(fallback)
    try:
        if int(float(first.get("is_projected", 0) or 0)) != 0:
            return "PROJECTED"
    except (TypeError, ValueError):
        pass
    return _normalize_radio_map_surface_mode(fallback)


def _radio_map_geometry_nodes_group_name(metric, surface_mode="PLANAR"):
    return str(_radio_map_mode_definition(metric, surface_mode)["node_group"])


def _radio_map_object_prefix(metric, surface_mode="PLANAR"):
    token = str(_radio_map_mode_definition(metric, surface_mode)["name_token"])
    return f"Sionna_CoverageMap_{token}"


def _radio_map_3d_mode_definition(metric):
    return _RADIO_MAP_3D_MODE_DEFINITIONS[_normalize_radio_map_metric(metric)]


def _radio_map_3d_geometry_nodes_group_name(metric):
    return str(_radio_map_3d_mode_definition(metric)["node_group"])


def _radio_map_3d_object_prefix(metric):
    token = str(_radio_map_3d_mode_definition(metric)["name_token"])
    return f"Sionna_CoverageMap3D_{token}"


def _ensure_radio_map_carrier(
    scene, csv_path=None, replace=False, frame=None, metric=None, surface_mode=None,
):
    settings = scene.sionna_bridge
    map_metric = _normalize_radio_map_metric(
        metric or _radio_map_metric_from_csv(csv_path, settings.radio_map_metric)
    )
    map_surface_mode = _normalize_radio_map_surface_mode(
        surface_mode or _radio_map_surface_mode_from_csv(
            csv_path, getattr(settings, "radio_map_surface_mode", "PLANAR")
        )
    )
    mode = _radio_map_mode_definition(map_metric, map_surface_mode)
    group_name = str(mode["node_group"])
    name_token = str(mode["name_token"])
    return _ensure_carrier_mesh(
        scene=scene,
        collection_key="radio_maps",
        group_name=group_name,
        object_name=f"Sionna_CoverageMap_{name_token}_Carrier",
        modifier_name=f"Sionna Coverage Map {mode['label']}",
        result_type="radio_map_csv_carrier",
        csv_path=csv_path,
        replace=replace,
    )



_INTEGER_POINT_ATTRIBUTES = {
    "frame", "max_depth", "max_num_paths_per_src", "samples_per_src", "seed",
    "los_enabled", "specular_reflection_enabled", "diffuse_reflection_enabled",
    "refraction_enabled", "diffraction_enabled", "edge_diffraction_enabled",
    "diffraction_lit_region_enabled", "sim_numeric_id", "pos_idx", "top_rank",
    "path_uid_num", "path_index", "point_order", "point_role_id",
    "interaction_id", "interaction_type_id", "object_id", "num_events",
    "path_is_los", "path_num_specular", "path_num_diffuse",
    "path_num_refraction", "path_num_diffraction", "path_num_mixed",
    "segment_from_prev_type_id", "segment_from_prev_object_id",
    "segment_to_next_type_id", "segment_to_next_object_id", "cell_index",
    "cell_x", "cell_y", "tx_index", "tx_count", "valid", "num_cells_x",
    "num_cells_y", "voxel_index", "layer_index", "cell_z", "num_cells_z",
    "associated_tx", "primitive_index", "is_projected", "coverage_valid",
}

_VECTOR_POINT_ATTRIBUTE_COLUMNS = {
    "surface_normal": ("normal_x", "normal_y", "normal_z"),
    "surface_tangent": ("tangent_x", "tangent_y", "tangent_z"),
    "surface_bitangent": ("bitangent_x", "bitangent_y", "bitangent_z"),
    "triangle_v0": ("triangle_v0_x", "triangle_v0_y", "triangle_v0_z"),
    "triangle_v1": ("triangle_v1_x", "triangle_v1_y", "triangle_v1_z"),
    "triangle_v2": ("triangle_v2_x", "triangle_v2_y", "triangle_v2_z"),
    "tx_velocity": ("tx_velocity_x", "tx_velocity_y", "tx_velocity_z"),
    "rx_velocity": ("rx_velocity_x", "rx_velocity_y", "rx_velocity_z"),
    "relative_velocity": (
        "relative_velocity_x", "relative_velocity_y", "relative_velocity_z"
    ),
}


def _number_token(value):
    value = float(value)
    if abs(value - round(value)) < 1e-9:
        token = str(int(round(value)))
    else:
        token = f"{value:.6g}"
    return token.replace("-", "m").replace(".", "p").replace("+", "")


def _result_object_name(prefix, config):
    frames = list(config.get("frames") or [])
    frame_numbers = [int(item.get("frame", 0)) for item in frames] or [0]
    frequencies = [
        float(item.get("simulation", {}).get("frequency_ghz", 0.0))
        for item in frames
    ] or [float(config.get("simulation", {}).get("frequency_ghz", 0.0))]
    created = str(config.get("created_utc", ""))
    try:
        timestamp = datetime.fromisoformat(created.replace("Z", "+00:00")).strftime("%Y%m%d_%H%M%S")
    except Exception:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if max(frequencies) - min(frequencies) <= 1e-9:
        frequency_token = f"{_number_token(frequencies[0])}GHz"
    else:
        frequency_token = (
            f"{_number_token(frequencies[0])}to{_number_token(frequencies[-1])}GHz"
        )
    if min(frame_numbers) == max(frame_numbers):
        frame_token = f"F{frame_numbers[0]:04d}"
    else:
        frame_token = f"F{min(frame_numbers):04d}-F{max(frame_numbers):04d}"
    return _sanitize_name(f"{prefix}_{timestamp}_{frequency_token}_{frame_token}")


def _find_group_geometry_input(group):
    for node in group.nodes:
        if getattr(node, "bl_idname", "") != "NodeGroupInput":
            continue
        socket = node.outputs.get("Geometry") if hasattr(node.outputs, "get") else None
        if socket is not None:
            return node, socket
    return None, None


def _route_embedded_geometry_to_csv_consumers(group):
    """Make an existing CSV-based node group consume the object's embedded points.

    The user's node tree is preserved. Import CSV nodes remain in place but their
    outgoing geometry links are redirected through one Mesh to Points helper fed
    by the group Geometry input.
    """
    group_input, geometry_socket = _find_group_geometry_input(group)
    if geometry_socket is None:
        raise RuntimeError(
            f"Geometry Nodes group '{group.name}' has no Geometry group input"
        )
    helper_name = "Sionna Embedded Mesh to Points"
    helper = group.nodes.get(helper_name)
    if helper is None or getattr(helper, "bl_idname", "") != "GeometryNodeMeshToPoints":
        helper = group.nodes.new("GeometryNodeMeshToPoints")
        helper.name = helper_name
        helper.label = "Embedded point data"
        helper.hide = True
        helper.location = (group_input.location.x + 180.0, group_input.location.y)
    mesh_input = helper.inputs.get("Mesh") if hasattr(helper.inputs, "get") else helper.inputs[0]
    point_output = helper.outputs.get("Points") if hasattr(helper.outputs, "get") else helper.outputs[0]
    if not any(link.from_socket == geometry_socket and link.to_socket == mesh_input for link in group.links):
        group.links.new(geometry_socket, mesh_input)

    redirected = 0
    for node in list(group.nodes):
        if getattr(node, "bl_idname", "") != "GeometryNodeImportCSV":
            continue
        source = node.outputs.get("Point Cloud") if hasattr(node.outputs, "get") else None
        if source is None and len(node.outputs):
            source = node.outputs[0]
        if source is None:
            continue
        for link in list(source.links):
            target = link.to_socket
            group.links.remove(link)
            group.links.new(point_output, target)
            redirected += 1
    group["sionna_embedded_point_source"] = True
    try:
        group.update_tag()
    except Exception:
        pass
    return redirected


def _read_csv_first_row(csv_path, attempts=8):
    csv_path = Path(csv_path).expanduser().resolve()
    last_error = None
    for attempt in range(max(1, int(attempts))):
        try:
            with open(csv_path, "r", encoding="utf-8", newline="") as handle:
                return next(csv.DictReader(handle), None)
        except (PermissionError, OSError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.05 * (attempt + 1))
    if last_error:
        raise last_error
    return None


def _read_csv_numeric_rows(csv_path):
    csv_path = Path(csv_path).expanduser().resolve()
    last_error = None
    for attempt in range(8):
        try:
            with open(csv_path, "r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                fieldnames = list(reader.fieldnames or [])
                if not {"x", "y", "z"}.issubset(fieldnames):
                    raise RuntimeError(f"CSV is missing x/y/z columns: {csv_path}")
                rows = list(reader)
            if not rows:
                raise RuntimeError(f"CSV contains no point rows: {csv_path}")
            return fieldnames, rows
        except (PermissionError, OSError) as exc:
            last_error = exc
            if attempt < 7:
                time.sleep(0.08 * (attempt + 1))
    raise last_error or RuntimeError(f"Could not read CSV: {csv_path}")


def _create_embedded_point_object(
    scene, csv_path, config, *, prefix, collection_key, group_name,
    result_type, modifier_name, replace=False, radius=0.02,
):
    """Embed numeric rows as point-domain attributes in a Blender data object.

    The stored datablock is an efficient loose-vertex mesh for compatibility
    across supported Blender builds. The assigned Geometry Nodes group receives it
    through Group Input and immediately converts it to a native point-cloud
    component with Mesh to Points. External files can then be deleted safely.
    """
    fieldnames, rows = _read_csv_numeric_rows(csv_path)
    workflow = _ensure_environment(scene, migrate=True)
    collection = workflow[collection_key]
    group = _existing_geometry_nodes_group(group_name, result_type)
    _route_embedded_geometry_to_csv_consumers(group)

    legacy_types = {"paths_csv_carrier", "radio_map_csv_carrier"}
    for old in list(collection.objects):
        old_type = str(old.get("sionna_result_type", ""))
        should_remove = old_type in legacy_types or (replace and old_type == result_type)
        if not should_remove:
            continue
        old_data = old.data
        bpy.data.objects.remove(old, do_unlink=True)
        if isinstance(old_data, bpy.types.Mesh) and old_data.users == 0:
            bpy.data.meshes.remove(old_data)

    object_name = _result_object_name(prefix, config)
    mesh = bpy.data.meshes.new(object_name + "_data")
    mesh.vertices.add(len(rows))
    coordinates = []
    for row in rows:
        coordinates.extend((float(row["x"]), float(row["y"]), float(row["z"])))
    mesh.vertices.foreach_set("co", coordinates)

    for column in fieldnames:
        if column in _INTEGER_POINT_ATTRIBUTES:
            attribute = mesh.attributes.new(column, type="INT", domain="POINT")
            values = [int(float(row.get(column, 0) or 0)) for row in rows]
        else:
            attribute = mesh.attributes.new(column, type="FLOAT", domain="POINT")
            values = [float(row.get(column, 0.0) or 0.0) for row in rows]
        attribute.data.foreach_set("value", values)

    for vector_name, component_names in _VECTOR_POINT_ATTRIBUTE_COLUMNS.items():
        if not set(component_names).issubset(fieldnames):
            continue
        vector_attribute = mesh.attributes.get(vector_name)
        if vector_attribute is None:
            vector_attribute = mesh.attributes.new(
                vector_name, type="FLOAT_VECTOR", domain="POINT"
            )
        vector_values = []
        for row in rows:
            for component_name in component_names:
                raw = row.get(component_name, "")
                vector_values.append(float(raw) if raw not in (None, "") else 0.0)
        vector_attribute.data.foreach_set("vector", vector_values)

    radius_attribute = mesh.attributes.get("radius")
    if radius_attribute is None:
        radius_attribute = mesh.attributes.new("radius", type="FLOAT", domain="POINT")
    radius_attribute.data.foreach_set("value", [float(radius)] * len(rows))
    mesh.update()

    obj = bpy.data.objects.new(object_name, mesh)
    collection.objects.link(obj)
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    obj["sionna_result_type"] = result_type
    obj["sionna_point_count"] = len(rows)
    obj["sionna_source_csv"] = str(Path(csv_path).resolve())
    obj["sionna_embedded"] = True
    if result_type in {"radio_map_pointcloud", "radio_map_3d_pointcloud"}:
        map_key = "radio_map_3d" if result_type == "radio_map_3d_pointcloud" else "radio_map"
        map_settings = dict(config.get(map_key, {}) or {})
        metric = _normalize_radio_map_metric(map_settings.get("metric", "path_gain"))
        surface_mode = _normalize_radio_map_surface_mode(
            map_settings.get("surface_mode", "PLANAR")
        ) if result_type == "radio_map_pointcloud" else "VOLUME"
        mode = (
            _radio_map_3d_mode_definition(metric)
            if result_type == "radio_map_3d_pointcloud"
            else _radio_map_mode_definition(metric, surface_mode)
        )
        linear_attribute = str(mode.get("linear_attribute", metric))
        db_attribute = str(mode.get("db_attribute", {
            "path_gain": "path_gain_db", "rss": "rss_dbm", "sinr": "sinr_db"
        }.get(metric, "path_gain_db")))
        obj["sionna_map_metric"] = metric
        obj["sionna_map_dimension"] = "3D" if result_type == "radio_map_3d_pointcloud" else "2D"
        obj["sionna_map_surface_mode"] = surface_mode
        obj["sionna_metric_label"] = str(mode.get("label", metric.upper()))
        obj["sionna_metric_unit"] = str(mode.get("unit", "dBm" if metric == "rss" else "dB"))
        obj["sionna_metric_linear_attribute"] = linear_attribute
        obj["sionna_metric_db_attribute"] = db_attribute
        obj["sionna_metric_attributes"] = json.dumps([linear_attribute, db_attribute])
        obj["sionna_geometry_nodes_group"] = str(group.name)
        frames = list(config.get("frames") or [])
        obj["sionna_frame_count"] = len(frames) or 1
        tx_items = list(
            frames[0].get("transmitters", []) if frames
            else config.get("transmitters", [])
        )
        obj["sionna_tx_powers_dbm"] = json.dumps([
            {"name": tx.get("name", ""), "power_dbm": float(tx.get("power_dbm", 44.0))}
            for tx in tx_items
        ])
        obj["sionna_association_attribute"] = "associated_tx"
        obj["sionna_association_metric"] = metric
        if result_type == "radio_map_pointcloud":
            obj["sionna_geometry_component"] = "POINT_CLOUD"
            obj["sionna_storage_datablock"] = "LOOSE_VERTEX_MESH"
            obj["sionna_projected_pointcloud_contract"] = 2
            obj["sionna_surface_normal_attribute"] = "surface_normal"
            obj["sionna_surface_tangent_attribute"] = "surface_tangent"
            obj["sionna_surface_bitangent_attribute"] = "surface_bitangent"
            obj["sionna_cell_area_attribute"] = "cell_area"
            obj["sionna_primitive_index_attribute"] = "primitive_index"
            obj["sionna_triangle_vertex_attributes"] = json.dumps([
                "triangle_v0", "triangle_v1", "triangle_v2"
            ])
            if surface_mode == "PROJECTED":
                reference_name = str(
                    map_settings.get("reference_mesh_blender_name", "")
                )
                obj["sionna_reference_mesh"] = reference_name
                obj["sionna_measurement_surface_triangle_count"] = int(
                    map_settings.get("measurement_surface_triangle_count", 0) or 0
                )
                per_tx_attributes = sorted(
                    column for column in fieldnames
                    if re.match(r"^(?:path_gain|path_gain_db|rss|rss_dbm|sinr|sinr_db)_tx_\d{3}$", column)
                )
                obj["sionna_per_tx_metric_attributes"] = json.dumps(per_tx_attributes)
                obj["sionna_per_tx_metric_attribute_count"] = len(per_tx_attributes)
        obj["sionna_tx_index_map"] = json.dumps([
            {"index": index, "name": str(tx.get("name", f"TX_{index:03d}"))}
            for index, tx in enumerate(tx_items)
        ])
        obj["sionna_tx_count"] = len(tx_items)
        if {"coverage_valid", "metric_db"}.issubset(fieldnames):
            valid_metric_db = []
            for row in rows:
                try:
                    is_valid = int(float(row.get("coverage_valid", 0) or 0)) != 0
                    value_db = float(row.get("metric_db", -300.0) or -300.0)
                except (TypeError, ValueError):
                    continue
                if is_valid and math.isfinite(value_db):
                    valid_metric_db.append(value_db)
            valid_count = len(valid_metric_db)
            obj["sionna_valid_cell_count"] = valid_count
            obj["sionna_invalid_cell_count"] = max(0, len(rows) - valid_count)
            obj["sionna_coverage_fraction"] = (
                float(valid_count) / float(len(rows)) if rows else 0.0
            )
            if valid_metric_db:
                obj["sionna_metric_db_min"] = min(valid_metric_db)
                obj["sionna_metric_db_max"] = max(valid_metric_db)
                obj["sionna_metric_db_median"] = statistics.median(valid_metric_db)

    if result_type == "paths_pointcloud":
        frames = list(config.get("frames") or [])
        simulations = [dict(item.get("simulation", {}) or {}) for item in frames]
        obj["sionna_mobility_doppler"] = any(
            bool(item.get("mobility_doppler", True)) for item in simulations
        ) if simulations else bool(
            dict(config.get("simulation", {}) or {}).get("mobility_doppler", True)
        )
        obj["sionna_doppler_attribute"] = "doppler_hz"
        obj["sionna_velocity_attributes"] = json.dumps([
            "tx_velocity", "rx_velocity", "relative_velocity"
        ])
        obj["sionna_mobility_schema"] = 1

    procedural_records = []
    for frame_payload in list(config.get("frames") or []):
        stats = frame_payload.get("procedural_geometry_stats")
        if not isinstance(stats, dict):
            continue
        record = {"frame": int(frame_payload.get("frame", 0))}
        record.update(stats)
        record["scene_xml_sha256"] = str(frame_payload.get("scene_xml_sha256", ""))
        procedural_records.append(record)
    if procedural_records:
        obj["sionna_procedural_scene"] = True
        obj["sionna_procedural_geometry_stats"] = json.dumps(
            procedural_records, separators=(",", ":")
        )
        obj["sionna_procedural_frame_count"] = len(procedural_records)

    modifier = obj.modifiers.new(name=modifier_name, type="NODES")
    modifier.node_group = group
    # Projected maps are self-contained point data. The reference mesh is used
    # only to build Sionna's measurement surface before the worker starts; it
    # is intentionally not assigned to the Geometry Nodes modifier.
    try:
        obj.update_tag()
        group.update_tag()
    except Exception:
        pass
    return obj, len(rows), group



def _attach_channel_analytics_from_manifest(obj, run_dir):
    """Embed compact worker-side channel summaries before temporary cleanup."""
    manifest_path = Path(run_dir) / "frames_manifest.json"
    payload = _load_json_file(manifest_path)
    frame_entries = []
    for frame_result in list(payload.get("frames") or []):
        analytics = frame_result.get("channel_analytics")
        if not isinstance(analytics, dict):
            continue
        frame_entries.append({
            "frame": int(frame_result.get("frame", 0)),
            "simulation": dict(frame_result.get("simulation", {}) or {}),
            "channel_analytics": analytics,
        })
    if not frame_entries:
        return 0
    embedded = {
        "schema_version": 2,
        "source": "worker_all_valid_paths",
        "created_utc": str(payload.get("created_utc", "")),
        "frames": frame_entries,
    }
    obj["sionna_channel_analytics"] = json.dumps(
        embedded, separators=(",", ":"), allow_nan=False
    )
    obj["sionna_channel_analytics_schema"] = 2
    obj["sionna_channel_analytics_frame_count"] = len(frame_entries)
    return len(frame_entries)

def _cleanup_external_run(
    run_dir, settings, *, path_result=False, radio_result=False,
    radio_3d_result=False, export_file="", export_metadata="", export_format="",
):
    """Remove worker intermediates while preserving only the requested export."""
    run_dir = Path(run_dir)
    mode = str(export_format or getattr(settings, "export_format", "NONE") or "NONE").upper()
    export_file = Path(export_file) if export_file else None
    export_metadata = Path(export_metadata) if export_metadata else None

    keep = set()
    for item in (export_file, export_metadata):
        if item is not None:
            try:
                if item.exists():
                    keep.add(item.resolve())
            except OSError:
                pass

    removed = False
    last_error = None
    for attempt in range(8):
        try:
            if mode == "NONE":
                if run_dir.exists():
                    shutil.rmtree(run_dir)
            elif run_dir.exists():
                for child in list(run_dir.iterdir()):
                    try:
                        resolved = child.resolve()
                    except OSError:
                        resolved = child
                    if resolved in keep:
                        continue
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink(missing_ok=True)
            removed = True
            break
        except (PermissionError, OSError) as exc:
            last_error = exc
            time.sleep(0.10 * (attempt + 1))

    if not removed:
        return f"temporary files retained because cleanup was blocked: {last_error}"

    # A shared HDF5 batch export can live outside this worker's run directory.
    # Remove the now-empty worker directory so the workspace contains only the
    # durable batch export folder.
    try:
        if run_dir.exists() and not any(run_dir.iterdir()) and not any(
            item is not None and item.exists() and item.parent.resolve() == run_dir.resolve()
            for item in (export_file, export_metadata)
        ):
            run_dir.rmdir()
    except OSError:
        pass

    settings.last_export_path = str(export_file) if export_file and export_file.exists() else ""
    settings.last_export_metadata_path = (
        str(export_metadata) if export_metadata and export_metadata.exists() else ""
    )

    if path_result:
        settings.last_results_json = ""
        settings.last_config_path = ""
        if mode == "CSV" and export_file and export_file.exists():
            settings.last_results_csv = str(export_file)
            settings.last_run_dir = str(export_file.parent)
        else:
            settings.last_results_csv = ""
            if mode == "NONE":
                settings.last_run_dir = ""
            elif export_file and export_file.exists():
                settings.last_run_dir = str(export_file.parent)
    if radio_result:
        settings.last_radio_map_json = ""
        if mode == "CSV" and export_file and export_file.exists():
            settings.last_radio_map_csv = str(export_file)
            settings.last_radio_map_run_dir = str(export_file.parent)
        else:
            settings.last_radio_map_csv = ""
            if mode == "NONE":
                settings.last_radio_map_run_dir = ""
            elif export_file and export_file.exists():
                settings.last_radio_map_run_dir = str(export_file.parent)
    if radio_3d_result:
        settings.last_radio_map_3d_json = ""
        if mode == "CSV" and export_file and export_file.exists():
            settings.last_radio_map_3d_csv = str(export_file)
            settings.last_radio_map_3d_run_dir = str(export_file.parent)
        else:
            settings.last_radio_map_3d_csv = ""
            if mode == "NONE":
                settings.last_radio_map_3d_run_dir = ""
            elif export_file and export_file.exists():
                settings.last_radio_map_3d_run_dir = str(export_file.parent)

    if mode == "NONE":
        return "temporary worker files removed; no file export requested"
    label = "CSV" if mode == "CSV" else "HDF5"
    return f"{label} export kept with metadata; worker intermediates removed"


def _elapsed_label(started_ns):
    if not started_ns:
        return "00:00"
    elapsed = max(0, int((time.time_ns() - int(started_ns)) / 1_000_000_000))
    minutes, seconds = divmod(elapsed, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def _redraw_sionna_ui():
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
    except Exception:
        pass


def _update_running_status(scene, label, run_dir, started_ns):
    settings = scene.sionna_bridge
    status = _load_json_file(Path(run_dir) / "status.json")
    state = str(status.get("state", "starting")).replace("_", " ")
    frame_index = int(status.get("frame_index", 0) or 0)
    frame_count = int(status.get("frame_count", 0) or 0)
    frame = status.get("frame")
    frequency = status.get("frequency_ghz")
    detail = state
    if frame_count and frame_index:
        detail = f"frame {frame_index}/{frame_count}"
        if frame is not None:
            detail += f" (F{int(frame)})"
    if frequency is not None:
        detail += f" at {float(frequency):g} GHz"
    layer_index = int(status.get("layer_index", 0) or 0)
    layer_count = int(status.get("layer_count", 0) or 0)
    if layer_index and layer_count:
        detail += f" — layer {layer_index}/{layer_count}"
        if status.get("height") is not None:
            detail += f" at Z {float(status['height']):g} m"
    summary = f"{label} running — {detail} — elapsed {_elapsed_label(started_ns)}"
    _set_status(
        settings, summary,
        details=(
            f"State: {state}\nRun folder: {run_dir}\n"
            f"Status file: {Path(run_dir) / 'status.json'}"
        ),
        run_dir=run_dir,
    )
    _redraw_sionna_ui()

def _read_csv_frequency_ghz(csv_path):
    with open(csv_path, "r", encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle), None)
    if not row:
        raise RuntimeError("The generated radio-map CSV contains no rows")
    try:
        return float(row["frequency_ghz"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("The generated radio-map CSV has no valid frequency_ghz value") from exc




def _write_pending_csv(csv_path, columns):
    """Legacy helper. Do not connect this file while a simulation worker writes it."""
    csv_path = Path(csv_path).expanduser().resolve()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = csv_path.with_suffix(csv_path.suffix + ".pending")
    with open(temporary, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(tuple(columns))
    os.replace(temporary, csv_path)
    return csv_path


def _load_json_file(path, attempts=6):
    path = Path(path)
    if not path.is_file():
        return {}
    for attempt in range(max(1, int(attempts))):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (PermissionError, json.JSONDecodeError, OSError):
            if attempt + 1 >= attempts:
                break
            time.sleep(0.03 * (attempt + 1))
        except Exception:
            break
    return {}


def _float_close(a, b, *, rel=1e-8, abs_tol=1e-6):
    return abs(float(a) - float(b)) <= max(abs_tol, abs(float(b)) * rel)


def _verify_fresh_file(path, started_ns, label):
    path = Path(path)
    if not path.is_file():
        raise RuntimeError(f"{label} was not created: {path}")
    if int(started_ns or 0) and path.stat().st_mtime_ns < int(started_ns):
        raise RuntimeError(f"{label} is older than the current simulation run")


def _completed_status_with_recovery(config_path, status_path, results_csv, started_ns, label):
    """Return a finished status, recovering it from a verified manifest if needed."""
    status = _load_json_file(status_path, attempts=10)
    if status.get("state") == "finished":
        return status
    config = _load_json_file(config_path, attempts=6)
    output = config.get("output", {}) if isinstance(config, dict) else {}
    manifest_path = Path(
        output.get("frames_manifest_json") or output.get("results_json") or ""
    )
    try:
        _verify_fresh_file(results_csv, started_ns, f"{label} CSV")
        _verify_fresh_file(manifest_path, started_ns, f"{label} manifest")
    except Exception:
        return status
    manifest = _load_json_file(manifest_path, attempts=10)
    frames = list(manifest.get("frames") or []) if isinstance(manifest, dict) else []
    point_count = int(manifest.get("point_count", 0) or 0) if isinstance(manifest, dict) else 0
    if not frames or point_count <= 0:
        return status
    recovered = dict(manifest)
    recovered.update({
        "state": "finished",
        "completed_frames": int(manifest.get("frame_count", len(frames)) or len(frames)),
        "recovered_from_manifest": True,
        "status_recovery_note": (
            "The final status file was unavailable or incomplete; completion was "
            "verified from the fresh result CSV and frame manifest."
        ),
    })
    return recovered


def _verify_path_output(csv_path, config_path, status_path, started_ns):
    """Verify a completed multi-frame path CSV against the run snapshot."""
    _verify_fresh_file(csv_path, started_ns, "Path CSV")
    config = _load_json_file(config_path)
    status = _completed_status_with_recovery(
        config_path, status_path, csv_path, started_ns, "Path"
    )
    if status.get("state") != "finished":
        raise RuntimeError(
            f"Path worker did not report a finished state: {status.get('state', 'missing')}"
        )
    if int(status.get("point_count", 0) or 0) <= 0:
        raise RuntimeError("The path worker produced no path-point rows")

    expected_frames = {int(item.get("frame", 0)): item for item in config.get("frames", [])}
    actual_frames = {int(item.get("frame", 0)): item for item in status.get("frames", [])}
    if set(actual_frames) != set(expected_frames):
        raise RuntimeError(
            f"Path frame mismatch: requested {sorted(expected_frames)}, "
            f"generated {sorted(actual_frames)}"
        )
    for frame, expected in expected_frames.items():
        expected_sim = expected.get("simulation", {})
        actual_sim = actual_frames[frame].get("simulation", {})
        for key in ("frequency_ghz", "max_depth", "samples_per_src", "seed"):
            if not _float_close(actual_sim.get(key, 0.0), expected_sim.get(key, 0.0), abs_tol=1e-5):
                raise RuntimeError(
                    f"Path frame {frame} {key} mismatch: requested "
                    f"{expected_sim.get(key)}, generated {actual_sim.get(key)}"
                )

    first = _read_csv_first_row(csv_path)
    if not first:
        raise RuntimeError("The generated path CSV contains no data rows")
    first_frame = int(float(first.get("frame", 0)))
    expected = expected_frames.get(first_frame)
    if expected is not None:
        expected_frequency = float(expected.get("simulation", {}).get("frequency_ghz", 0.0))
        actual_frequency = float(first.get("frequency_ghz", 0.0))
        if not _float_close(actual_frequency, expected_frequency):
            raise RuntimeError(
                f"Path CSV frequency mismatch: requested {expected_frequency:g} GHz, "
                f"generated {actual_frequency:g} GHz"
            )
    return config, status


def _verify_radio_map_output(csv_path, config_path, status_path, started_ns):
    """Verify every requested radio-map frame and the combined CSV."""
    _verify_fresh_file(csv_path, started_ns, "Radio-map CSV")
    config = _load_json_file(config_path)
    status = _completed_status_with_recovery(
        config_path, status_path, csv_path, started_ns, "Radio-map"
    )
    if status.get("state") != "finished":
        raise RuntimeError(
            f"Radio-map worker did not report a finished state: {status.get('state', 'missing')}"
        )
    if int(status.get("point_count", 0) or 0) <= 0:
        raise RuntimeError("The radio-map worker produced no cell rows")

    expected_frames = list(config.get("frames") or [{
        "frame": config.get("frame", 0),
        "simulation": config.get("simulation", {}),
        "radio_map": config.get("radio_map", {}),
    }])
    expected_by_frame = {int(item.get("frame", 0)): item for item in expected_frames}
    actual_by_frame = {
        int(item.get("frame", 0)): item for item in status.get("frames", [])
    }
    if set(actual_by_frame) != set(expected_by_frame):
        raise RuntimeError(
            f"Radio-map frame mismatch: requested {sorted(expected_by_frame)}, "
            f"generated {sorted(actual_by_frame)}"
        )

    for frame, expected in expected_by_frame.items():
        actual = actual_by_frame[frame]
        expected_sim = expected.get("simulation", {})
        actual_sim = actual.get("simulation", {})
        expected_radio = expected.get("radio_map", {})
        actual_radio = actual.get("radio_map", {})
        checks = (
            ("frequency_ghz", actual_sim, expected_sim),
            ("max_depth", actual_sim, expected_sim),
            ("samples_per_src", actual_sim, expected_sim),
            ("seed", actual_sim, expected_sim),
            ("center_x", actual_radio, expected_radio),
            ("center_y", actual_radio, expected_radio),
            ("height", actual_radio, expected_radio),
            ("size_x", actual_radio, expected_radio),
            ("size_y", actual_radio, expected_radio),
            ("cell_size_x", actual_radio, expected_radio),
            ("cell_size_y", actual_radio, expected_radio),
        )
        for key, actual_values, expected_values in checks:
            if not _float_close(
                actual_values.get(key, 0.0), expected_values.get(key, 0.0), abs_tol=1e-5
            ):
                raise RuntimeError(
                    f"Radio-map frame {frame} {key} mismatch: requested "
                    f"{expected_values.get(key)}, generated {actual_values.get(key)}"
                )
        expected_surface = _normalize_radio_map_surface_mode(
            expected_radio.get("surface_mode", "PLANAR")
        )
        actual_surface = _normalize_radio_map_surface_mode(
            actual_radio.get("surface_mode", "PLANAR")
        )
        if actual_surface != expected_surface:
            raise RuntimeError(
                f"Radio-map frame {frame} surface mismatch: requested "
                f"{expected_surface}, generated {actual_surface}"
            )
        if expected_surface == "PROJECTED":
            for key in (
                "reference_mesh_blender_name",
                "measurement_surface_sha256",
                "measurement_surface_triangle_count",
            ):
                if str(actual_radio.get(key, "")) != str(expected_radio.get(key, "")):
                    raise RuntimeError(
                        f"Radio-map frame {frame} {key} mismatch: requested "
                        f"{expected_radio.get(key)}, generated {actual_radio.get(key)}"
                    )

    first = _read_csv_first_row(csv_path)
    if not first:
        raise RuntimeError("The generated radio-map CSV contains no rows")
    metric = str((config.get("radio_map") or {}).get("metric", "path_gain")).lower()
    metric_columns = {
        "path_gain": {"path_gain", "path_gain_db"},
        "rss": {"rss", "rss_dbm"},
        "sinr": {"sinr", "sinr_db"},
    }
    surface_mode = _normalize_radio_map_surface_mode(
        (config.get("radio_map") or {}).get("surface_mode", "PLANAR")
    )
    required = {
        "frame", "x", "y", "z", "cell_size_x", "cell_size_y",
        "is_projected", "normal_x", "normal_y", "normal_z", "cell_area",
        "coverage_valid", "metric_linear", "metric_db", "metric_norm",
    } | metric_columns.get(metric, set())
    if surface_mode == "PROJECTED":
        required.add("primitive_index")
    missing = sorted(required.difference(first))
    if missing:
        raise RuntimeError("Radio-map CSV is missing columns: " + ", ".join(missing))
    return config, status


def _existing_radio_map_geometry_nodes_group(
    settings, metric=None, surface_mode=None,
):
    """Return the user-authored radio-map Geometry Nodes group.

    The bridge deliberately never creates, copies, or rewires this node tree.
    It only changes the existing Import CSV path through the same update helper
    used by the Sionna path workflow.
    """
    requested_name = _radio_map_geometry_nodes_group_name(
        metric or settings.radio_map_metric,
        surface_mode or getattr(settings, "radio_map_surface_mode", "PLANAR"),
    )
    return _existing_geometry_nodes_group(requested_name, "radio-map carrier")


def _create_radio_map_carrier_object(collection, csv_path, name, settings):
    """Compatibility wrapper using the existing user-authored node group."""
    scene = bpy.context.scene
    frame_match = re.search(r"F(-?\d+)$", name)
    frame = int(frame_match.group(1)) if frame_match else int(scene.frame_current)
    return _ensure_radio_map_carrier(
        scene,
        csv_path=csv_path,
        replace=bool(settings.radio_map_replace_existing),
        frame=frame,
    )

def _import_radio_map_pointcloud(scene, csv_path):
    settings = scene.sionna_bridge
    csv_path = Path(csv_path)
    if not csv_path.is_file():
        raise RuntimeError(f"Radio-map CSV not found: {csv_path}")

    with open(csv_path, "r", encoding="utf-8", newline="") as handle:
        first = next(csv.DictReader(handle), None)
    if not first:
        raise RuntimeError("The radio-map CSV contains no cells")
    required = {"x", "y", "z", "frame", "cell_size_x", "cell_size_y"}
    missing = sorted(required.difference(first))
    if missing:
        raise RuntimeError(
            "Radio-map CSV is missing required columns: " + ", ".join(missing)
        )

    map_metric = _radio_map_metric_from_csv(csv_path, settings.radio_map_metric)
    map_surface_mode = _radio_map_surface_mode_from_csv(
        csv_path, getattr(settings, "radio_map_surface_mode", "PLANAR")
    )

    _ensure_environment(scene, migrate=True)
    obj, group = _ensure_radio_map_carrier(
        scene,
        csv_path=csv_path,
        replace=bool(settings.radio_map_replace_existing),
        frame=None,
        metric=map_metric,
        surface_mode=map_surface_mode,
    )
    obj["sionna_content_type"] = "radio_map"
    obj["sionna_radio_map_csv"] = str(csv_path.resolve())
    obj["sionna_first_frame"] = int(float(first.get("frame", scene.frame_current)))
    obj["sionna_map_metric"] = map_metric
    obj["sionna_map_surface_mode"] = map_surface_mode
    obj["sionna_metric_geometry_nodes_group"] = _radio_map_geometry_nodes_group_name(
        map_metric, map_surface_mode
    )
    return obj, int(obj.get("sionna_point_count", 0))


def _poll_radio_map_process():
    process = _RADIO_MAP_STATE.get("process")
    if process is None:
        return None
    if process.poll() is None:
        scene = bpy.data.scenes.get(_RADIO_MAP_STATE.get("scene_name", ""))
        if scene is not None:
            _update_running_status(
                scene, "Radio map", _RADIO_MAP_STATE.get("run_dir", ""),
                _RADIO_MAP_STATE.get("started_ns", 0),
            )
        return 0.5

    return_code = process.returncode
    run_dir = Path(_RADIO_MAP_STATE.get("run_dir") or "")
    results_csv = Path(_RADIO_MAP_STATE.get("results_csv") or "")
    results_json = Path(_RADIO_MAP_STATE.get("results_json") or "")
    config_path = Path(_RADIO_MAP_STATE.get("config_path") or "")
    started_ns = int(_RADIO_MAP_STATE.get("started_ns", 0) or 0)
    scene_name = _RADIO_MAP_STATE.get("scene_name", "")
    worker_pid = int(_RADIO_MAP_STATE.get("pid", 0) or 0)
    expected_frame = int(_RADIO_MAP_STATE.get("frame", 0) or 0)
    expected_frame_count = int(_RADIO_MAP_STATE.get("frame_count", 1) or 1)
    auto_triggered = bool(_RADIO_MAP_STATE.get("auto_triggered", False))
    _close_radio_map_handles()

    scene = bpy.data.scenes.get(scene_name)
    if scene is None:
        return None
    settings = scene.sionna_bridge
    status_path = run_dir / "status.json"
    status_payload = _completed_status_with_recovery(
        config_path, status_path, results_csv, started_ns, "Radio-map"
    )
    success = False

    try:
        if status_payload.get("state") != "finished":
            error_text = status_payload.get("error", "")
            raise RuntimeError(
                f"worker exit {return_code}, state {status_payload.get('state', 'missing')}. {error_text}"
            )
        config, verified_status = _verify_radio_map_output(
            results_csv, config_path, status_path, started_ns
        )
        output_spec = dict(config.get("output") or {})
        export_format = str(verified_status.get("export_format") or output_spec.get("export_format") or "NONE")
        export_file = str(verified_status.get("export_file") or output_spec.get("export_file") or "")
        export_metadata = str(verified_status.get("export_metadata_json") or output_spec.get("export_metadata_json") or "")
        settings.last_radio_map_csv = str(results_csv)
        settings.last_radio_map_json = str(results_json) if results_json.exists() else ""
        map_settings = dict(config.get("radio_map") or {})
        map_metric = str(map_settings.get("metric", "path_gain")).lower()
        surface_mode = _normalize_radio_map_surface_mode(
            map_settings.get("surface_mode", "PLANAR")
        )
        mode = _radio_map_mode_definition(map_metric, surface_mode)
        group_name = str(mode["node_group"])
        if auto_triggered:
            _remove_previous_auto_embedded_results(scene, "radio_maps")
        embedded_obj, embedded_count, _group = _create_embedded_point_object(
            scene, results_csv, config,
            prefix=_radio_map_object_prefix(map_metric, surface_mode),
            collection_key="radio_maps", group_name=group_name,
            result_type="radio_map_pointcloud",
            modifier_name=f"Sionna Coverage Map {mode['label']}",
            replace=(False if auto_triggered else bool(settings.radio_map_replace_existing)),
            radius=max(0.001, float(settings.radio_map_point_radius)),
        )
        if auto_triggered:
            embedded_obj["sionna_auto_device_move_result"] = True
        embedded_obj["sionna_metric_geometry_nodes_group"] = group_name
        settings.last_radio_map_object = embedded_obj.name
        _maybe_auto_refresh_analytics(scene, "RADIO_MAP")
        point_count = int(verified_status.get("point_count", embedded_count) or embedded_count)
        frame_count = int(verified_status.get("frame_count", expected_frame_count) or expected_frame_count)
        frequencies = sorted({
            float(item.get("simulation", {}).get("frequency_ghz", 0.0))
            for item in config.get("frames", [])
        })
        frequency_note = ", ".join(f"{value:g}" for value in frequencies)
        _set_status(
            settings,
            f"{mode['label']} radio map embedded: {embedded_obj.name}; {point_count} cells; {frame_count} frame(s), {frequency_note} GHz",
            details=(
                f"Worker PID: {worker_pid}\nWorker exit code: {return_code}\n"
                f"Result CSV: {results_csv}\nRun folder: {run_dir}"
                + (
                    f"\nReference mesh: {map_settings.get('reference_mesh_blender_name', '')}"
                    f"\nMeasurement triangles: {map_settings.get('measurement_surface_triangle_count', 0)}"
                    f"\nValid coverage cells: {verified_status.get('valid_cell_count', embedded_obj.get('sionna_valid_cell_count', 0))}"
                    f" ({100.0 * float(verified_status.get('coverage_fraction', embedded_obj.get('sionna_coverage_fraction', 0.0)) or 0.0):.1f}%)"
                    f"\nMetric range: {float(verified_status.get('metric_db_min', embedded_obj.get('sionna_metric_db_min', -300.0))):.2f}"
                    f" to {float(verified_status.get('metric_db_max', embedded_obj.get('sionna_metric_db_max', -300.0))):.2f} {mode['unit']}"
                    if surface_mode == "PROJECTED" else ""
                )
                + ("\n" + str(verified_status.get("status_recovery_note"))
                   if verified_status.get("recovered_from_manifest") else "")
            ),
            run_dir=run_dir, log_path=run_dir / "radio_map.log",
        )
        cleanup_note = _cleanup_external_run(
            run_dir, settings, path_result=False, radio_result=True,
            export_file=export_file, export_metadata=export_metadata,
            export_format=export_format,
        )
        settings.last_status += f"; {cleanup_note}"
        success = True
    except Exception as exc:
        _set_status(
            settings,
            f"Radio map result rejected: {exc}",
            _failure_details("2D radio map", return_code, status_payload, run_dir, "radio_map.log"),
            run_dir=run_dir, log_path=run_dir / "radio_map.log",
        )

    if _BATCH_STATE.get("active") and _BATCH_STATE.get("scene_name") == scene_name:
        _BATCH_STATE["radio_map_status"] = settings.last_status
        if _BATCH_STATE.get("pending_radio_map_3d"):
            _BATCH_STATE["pending_radio_map_3d"] = False
            try:
                if getattr(bpy.context, "scene", None) != scene:
                    raise RuntimeError(
                        "The active Blender scene changed before the queued 3D radio-map run started"
                    )
                _start_radio_map_3d_process(
                    bpy.context, _BATCH_STATE["scene_source"],
                    force_current_frame=bool(_BATCH_STATE.get("force_current_frame", False)),
                    auto_triggered=bool(_BATCH_STATE.get("auto_triggered", False)),
                    auto_anchor_tx_name=str(_BATCH_STATE.get("auto_anchor_tx_name", "")),
                )
                prior = " | ".join(filter(None, (
                    str(_BATCH_STATE.get("path_status") or "").strip(),
                    str(_BATCH_STATE.get("radio_map_status") or "").strip(),
                )))
                settings.last_status = f"{prior}; starting selected 3D radio map"
            except Exception as exc:
                settings.last_status += f"; 3D radio-map start failed: {exc}"
                _reset_batch_state()
        else:
            statuses = [
                str(_BATCH_STATE.get("path_status") or "").strip(),
                str(_BATCH_STATE.get("radio_map_status") or "").strip(),
            ]
            statuses = [item for item in statuses if item]
            settings.last_status = ("Batch complete — " if success else "Batch finished with errors — ") + " | ".join(statuses)
            _reset_batch_state()

    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
    return None


def _geometry_nodes_import_csv_socket(node):
    """Return an unlinked string path socket from a GeometryNodeImportCSV node."""
    path_socket = node.inputs.get("Path") if hasattr(node.inputs, "get") else None
    candidates = [path_socket] if path_socket is not None else []
    candidates.extend(socket for socket in node.inputs if socket is not path_socket)
    for socket in candidates:
        if socket is None or getattr(socket, "is_linked", False):
            continue
        try:
            value = socket.default_value
        except (AttributeError, TypeError):
            continue
        if isinstance(value, str):
            return socket
    return None


def _normalized_csv_socket_name(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _matching_geometry_node_groups(requested_name):
    requested_name = str(requested_name or "").strip()
    if not requested_name:
        return []

    def collect():
        exact = bpy.data.node_groups.get(requested_name)
        groups = []
        if exact is not None and getattr(exact, "bl_idname", "") == "GeometryNodeTree":
            groups.append(exact)
        if not groups:
            groups = [
                group for group in bpy.data.node_groups
                if getattr(group, "bl_idname", "") == "GeometryNodeTree"
                and group.name.startswith(requested_name)
            ]
        return groups

    groups = collect()
    if not groups:
        _ensure_bundled_geometry_nodes(verbose=False)
        groups = collect()
    return groups


def _csv_group_input_sockets(group):
    """Yield exposed string inputs that look like a CSV/file-path input."""
    accepted = {
        "csv", "csv_path", "csv_file", "csv_filepath",
        "file", "file_path", "filepath", "path",
        "radio_map_csv", "radio_map_csv_path", "radio_map_path",
    }
    interface = getattr(group, "interface", None)
    items = getattr(interface, "items_tree", ()) if interface is not None else ()
    for item in items:
        if getattr(item, "item_type", "") != "SOCKET":
            continue
        if getattr(item, "in_out", "") != "INPUT":
            continue
        socket_type = str(getattr(item, "socket_type", ""))
        if socket_type != "NodeSocketString":
            continue
        if _normalized_csv_socket_name(getattr(item, "name", "")) in accepted:
            yield item


def _set_geometry_nodes_modifier_input(modifier, identifier, value):
    """Set a Geometry Nodes modifier input across Blender API generations.

    Blender 5.2 moved public Geometry Nodes modifier inputs from ID-properties
    (``modifier[identifier]``) to runtime RNA properties under
    ``modifier.properties.inputs``. Prefer the 5.2 API and retain the old
    assignment only as a compatibility fallback for legacy files/builds.
    """
    if not identifier:
        return False

    properties = getattr(modifier, "properties", None)
    inputs = getattr(properties, "inputs", None) if properties is not None else None
    if inputs is not None:
        input_property = None
        try:
            input_property = getattr(inputs, identifier)
        except Exception:
            pass
        if input_property is None:
            try:
                input_property = inputs.get(identifier)
            except Exception:
                pass
        if input_property is None:
            try:
                input_property = inputs[identifier]
            except Exception:
                pass
        if input_property is not None:
            try:
                input_property.value = value
                return True
            except Exception:
                pass

    # Blender <=5.1 / compatibility fallback.
    try:
        modifier[identifier] = value
        return True
    except Exception:
        return False


def _set_exposed_csv_inputs(group, csv_path):
    """Set CSV string inputs on group defaults, modifiers, and nested group nodes."""
    csv_value = str(csv_path)
    sockets = list(_csv_group_input_sockets(group))
    if not sockets:
        return 0

    updates = 0
    for socket in sockets:
        try:
            socket.default_value = csv_value
            updates += 1
        except Exception:
            pass

        identifier = str(getattr(socket, "identifier", ""))
        socket_name = str(getattr(socket, "name", ""))

        # Geometry Nodes modifiers store interface values by socket identifier.
        for obj in bpy.data.objects:
            for modifier in obj.modifiers:
                if modifier.type != "NODES" or modifier.node_group != group:
                    continue
                if identifier and _set_geometry_nodes_modifier_input(
                    modifier, identifier, csv_value
                ):
                    updates += 1
                try:
                    obj.update_tag()
                except Exception:
                    pass

        # Also update this group when it is nested as a Geometry Node Group node.
        for parent in bpy.data.node_groups:
            if getattr(parent, "bl_idname", "") != "GeometryNodeTree":
                continue
            for node in parent.nodes:
                if getattr(node, "bl_idname", "") != "GeometryNodeGroup":
                    continue
                if getattr(node, "node_tree", None) != group:
                    continue
                target = None
                if identifier:
                    target = next(
                        (input_socket for input_socket in node.inputs
                         if getattr(input_socket, "identifier", "") == identifier),
                        None,
                    )
                if target is None and hasattr(node.inputs, "get"):
                    target = node.inputs.get(socket_name)
                if target is None or getattr(target, "is_linked", False):
                    continue
                try:
                    target.default_value = csv_value
                    updates += 1
                    parent.update_tag()
                except Exception:
                    pass
    return updates


def _force_geometry_nodes_recompute(root_groups, visited_groups):
    """Force modifiers using the affected node trees to evaluate again."""
    root_groups = set(root_groups)
    visited_groups = set(visited_groups)
    for obj in bpy.data.objects:
        for modifier in obj.modifiers:
            if modifier.type != "NODES":
                continue
            if modifier.node_group not in root_groups and modifier.node_group not in visited_groups:
                continue
            try:
                visible = bool(modifier.show_viewport)
                modifier.show_viewport = False
                obj.update_tag()
                modifier.show_viewport = visible
                obj.update_tag()
            except Exception:
                try:
                    obj.update_tag()
                except Exception:
                    pass
            data = getattr(obj, "data", None)
            if data is not None and hasattr(data, "update"):
                try:
                    data.update()
                except Exception:
                    pass

    try:
        scene = bpy.context.scene
        scene.frame_set(int(scene.frame_current), subframe=float(scene.frame_subframe))
    except Exception:
        pass
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


def _update_named_geometry_nodes_csv_path(csv_path, requested_name, label):
    """Update and forcibly reload Import CSV nodes in named GN groups.

    Blender can keep the previously evaluated Import CSV geometry when an
    external file is replaced. The path is therefore changed to a unique
    invalid sentinel, the node trees are evaluated, and then the real path is
    assigned and evaluated again.
    """
    csv_path = Path(csv_path).expanduser().resolve()
    if not csv_path.is_file():
        raise RuntimeError(f"{label} CSV not found: {csv_path}")

    groups = _matching_geometry_node_groups(requested_name)
    if not groups:
        raise RuntimeError(f"Geometry Nodes group '{requested_name}' was not found")

    sentinel = csv_path.with_name(f".__sionna_reload_{time.time_ns()}.csv")
    import_sockets = []
    linked_import_nodes = 0
    visited = set()
    visited_groups = []

    def collect_group(group):
        nonlocal linked_import_nodes
        pointer = group.as_pointer()
        if pointer in visited:
            return
        visited.add(pointer)
        visited_groups.append(group)
        for node in group.nodes:
            node_type = getattr(node, "bl_idname", "")
            if node_type == "GeometryNodeImportCSV":
                socket = _geometry_nodes_import_csv_socket(node)
                if socket is None:
                    linked_import_nodes += 1
                    continue
                import_sockets.append((node, socket))
            elif node_type == "GeometryNodeGroup":
                nested = getattr(node, "node_tree", None)
                if nested is not None and getattr(nested, "bl_idname", "") == "GeometryNodeTree":
                    collect_group(nested)

    for group in groups:
        collect_group(group)

    # First detach every editable source from the previous evaluated CSV.
    for group in visited_groups:
        _set_exposed_csv_inputs(group, sentinel)
    for node, socket in import_sockets:
        try:
            socket.default_value = str(sentinel)
            node.label = "Reloading CSV..."
        except Exception:
            pass
    for group in visited_groups:
        try:
            group.update_tag()
        except Exception:
            pass
    _force_geometry_nodes_recompute(groups, visited_groups)

    # Assign the completed file and evaluate the trees again.
    exposed_input_updates = 0
    for group in visited_groups:
        exposed_input_updates += _set_exposed_csv_inputs(group, csv_path)
    updated_import_nodes = 0
    for node, socket in import_sockets:
        try:
            socket.default_value = str(csv_path)
            node.label = csv_path.name
            updated_import_nodes += 1
        except Exception:
            pass
    for group in visited_groups:
        try:
            group.update_tag()
        except Exception:
            pass
    _force_geometry_nodes_recompute(groups, visited_groups)

    total_updates = updated_import_nodes + exposed_input_updates
    if total_updates == 0:
        suffix = " Import CSV Path is linked and no exposed CSV string input was found." if linked_import_nodes else ""
        raise RuntimeError(
            f"No editable CSV input was found in '{requested_name}'.{suffix}"
        )

    return (
        f"Reloaded {updated_import_nodes} Import CSV node(s) and "
        f"{exposed_input_updates} exposed CSV input value(s) in {label}"
    )


def _update_geometry_nodes_csv_path(scene, csv_path):
    """Point Sionna_Paths at the newest combined path-result CSV."""
    settings = scene.sionna_bridge
    requested_name = settings.geometry_nodes_group_name.strip() or _DEFAULT_GEOMETRY_NODES_GROUP
    return _update_named_geometry_nodes_csv_path(
        csv_path, requested_name, "path Geometry Nodes"
    )


def _update_radio_map_geometry_nodes_csv_path(scene, csv_path):
    """Point the metric-specific radio-map Geometry Nodes group at the latest CSV."""
    settings = scene.sionna_bridge
    map_metric = _radio_map_metric_from_csv(
        csv_path, settings.radio_map_metric
    )
    surface_mode = _radio_map_surface_mode_from_csv(
        csv_path, getattr(settings, "radio_map_surface_mode", "PLANAR")
    )
    requested_name = _radio_map_geometry_nodes_group_name(
        map_metric, surface_mode
    )
    return _update_named_geometry_nodes_csv_path(
        csv_path, requested_name,
        f"{_radio_map_mode_definition(map_metric, surface_mode)['label']} radio-map Geometry Nodes",
    )

def _result_collection(scene):
    return _ensure_environment(scene)["simulated_paths"]


def _clear_result_collection(collection):
    for obj in list(collection.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def _import_paths_from_json(scene, results_path, clear_existing=True):
    settings = scene.sionna_bridge
    results_path = Path(results_path)
    if not results_path.exists():
        raise RuntimeError(f"Result file not found: {results_path}")

    with open(results_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    paths = payload.get("paths", [])
    paths.sort(
        key=lambda item: (
            item.get("path_gain_db") is not None,
            item.get("path_gain_db", -1e30),
        ),
        reverse=True,
    )
    paths = paths[: int(settings.max_imported_paths)]

    collection = _result_collection(scene)

    if clear_existing:
        for obj in list(collection.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

    imported = 0
    for index, item in enumerate(paths):
        points = item.get("points", [])
        if len(points) < 2:
            continue

        tx_name = item.get("tx_name", "tx")
        rx_name = item.get("rx_name", "rx")
        curve_name = f"Sionna_{_sanitize_name(tx_name)}_{_sanitize_name(rx_name)}_{index:05d}"

        curve_data = bpy.data.curves.new(curve_name, type="CURVE")
        curve_data.dimensions = "3D"
        curve_data.resolution_u = 1
        curve_data.bevel_depth = float(settings.path_thickness)
        curve_data.bevel_resolution = 2

        spline = curve_data.splines.new(type="POLY")
        spline.points.add(len(points) - 1)
        for point_index, coords in enumerate(points):
            spline.points[point_index].co = (
                float(coords[0]),
                float(coords[1]),
                float(coords[2]),
                1.0,
            )

        curve_obj = bpy.data.objects.new(curve_name, curve_data)
        collection.objects.link(curve_obj)

        curve_obj["sionna_tx"] = tx_name
        curve_obj["sionna_rx"] = rx_name
        curve_obj["sionna_path_index"] = int(item.get("path_index", index))
        curve_obj["sionna_delay_s"] = float(item.get("delay_s", 0.0))
        curve_obj["sionna_path_gain_db"] = float(item.get("path_gain_db", -300.0))
        curve_obj["sionna_interactions"] = ",".join(
            str(value) for value in item.get("interactions", [])
        )
        imported += 1

    settings.last_status = f"Imported {imported} propagation paths"
    return imported


def _import_latest_curves(scene, clear_existing=True):
    """Import the legacy curve representation from the most recent JSON file."""
    settings = scene.sionna_bridge
    if not settings.last_results_json:
        raise RuntimeError("No path JSON is available yet")
    curve_count = _import_paths_from_json(
        scene,
        settings.last_results_json,
        clear_existing=clear_existing,
    )
    settings.last_status = f"Imported {curve_count} propagation-path curves"
    return settings.last_status


def _poll_sionna_process():
    process = _RUN_STATE.get("process")
    if process is None:
        return None
    if process.poll() is None:
        scene = bpy.data.scenes.get(_RUN_STATE.get("scene_name", ""))
        if scene is not None:
            _update_running_status(
                scene, "Propagation paths", _RUN_STATE.get("run_dir", ""),
                _RUN_STATE.get("started_ns", 0),
            )
        return 0.5

    return_code = process.returncode
    run_dir = Path(_RUN_STATE.get("run_dir") or "")
    results_json = Path(_RUN_STATE.get("results_json") or "")
    results_csv = Path(_RUN_STATE.get("results_csv") or "")
    config_path = Path(_RUN_STATE.get("config_path") or "")
    started_ns = int(_RUN_STATE.get("started_ns", 0) or 0)
    scene_name = _RUN_STATE.get("scene_name", "")
    worker_pid = int(_RUN_STATE.get("pid", 0) or 0)
    auto_triggered = bool(_RUN_STATE.get("auto_triggered", False))
    _close_run_handles()

    scene = bpy.data.scenes.get(scene_name)
    if scene is None:
        return None
    settings = scene.sionna_bridge
    status_path = run_dir / "status.json"
    status_payload = _completed_status_with_recovery(
        config_path, status_path, results_csv, started_ns, "Path"
    )
    success = False

    try:
        if status_payload.get("state") != "finished":
            error_text = status_payload.get("error", "")
            raise RuntimeError(
                f"worker exit {return_code}, state {status_payload.get('state', 'missing')}. {error_text}"
            )
        config, verified_status = _verify_path_output(
            results_csv, config_path, status_path, started_ns
        )
        output_spec = dict(config.get("output") or {})
        export_format = str(verified_status.get("export_format") or output_spec.get("export_format") or "NONE")
        export_file = str(verified_status.get("export_file") or output_spec.get("export_file") or "")
        export_metadata = str(verified_status.get("export_metadata_json") or output_spec.get("export_metadata_json") or "")
        settings.last_results_json = str(results_json) if results_json.exists() else ""
        settings.last_results_csv = str(results_csv)
        group_name = settings.geometry_nodes_group_name.strip() or _DEFAULT_GEOMETRY_NODES_GROUP
        if auto_triggered:
            _remove_previous_auto_embedded_results(scene, "simulated_paths")
        embedded_obj, embedded_count, _group = _create_embedded_point_object(
            scene, results_csv, config, prefix="paths",
            collection_key="simulated_paths", group_name=group_name,
            result_type="paths_pointcloud", modifier_name="Sionna Paths",
            replace=False, radius=max(0.001, float(settings.path_thickness)),
        )
        settings.last_paths_object = embedded_obj.name
        if auto_triggered:
            embedded_obj["sionna_auto_device_move_result"] = True
        channel_frame_count = _attach_channel_analytics_from_manifest(embedded_obj, run_dir)
        _maybe_auto_refresh_analytics(scene, "PATHS")
        frame_count = int(verified_status.get("frame_count", _RUN_STATE.get("frame_count", 1)) or 1)
        completed_frames = int(verified_status.get("completed_frames", frame_count) or frame_count)
        frequencies = sorted({
            float(item.get("simulation", {}).get("frequency_ghz", 0.0))
            for item in config.get("frames", [])
        })
        frequency_note = ", ".join(f"{value:g}" for value in frequencies)
        _set_status(
            settings,
            f"Paths embedded: {embedded_obj.name}; {embedded_count} points; {completed_frames}/{frame_count} frame(s), {frequency_note} GHz",
            details=(
                f"Worker PID: {worker_pid}\nWorker exit code: {return_code}\n"
                f"Result CSV: {results_csv}\nRun folder: {run_dir}"
                + ("\n" + str(verified_status.get("status_recovery_note"))
                   if verified_status.get("recovered_from_manifest") else "")
            ),
            run_dir=run_dir, log_path=run_dir / "sionna.log",
        )
        if settings.post_run_action == "CURVES" and results_json.exists():
            try:
                _import_latest_curves(scene, clear_existing=True)
            except Exception as exc:
                settings.last_status += f"; curve import failed: {exc}"
        cleanup_note = _cleanup_external_run(
            run_dir, settings, path_result=True, radio_result=False,
            export_file=export_file, export_metadata=export_metadata,
            export_format=export_format,
        )
        settings.last_status += f"; {cleanup_note}"
        success = True
    except Exception as exc:
        _set_status(
            settings,
            f"Path result rejected: {exc}",
            _failure_details("Propagation paths", return_code, status_payload, run_dir, "sionna.log"),
            run_dir=run_dir, log_path=run_dir / "sionna.log",
        )

    # A selected radio map is an independent output. Start it after the path
    # worker exits even when path verification failed, so one failed output
    # does not leave the other pointing at an older CSV indefinitely.
    if _BATCH_STATE.get("active") and _BATCH_STATE.get("scene_name") == scene_name:
        _BATCH_STATE["path_status"] = settings.last_status
        if _BATCH_STATE.get("pending_radio_map"):
            _BATCH_STATE["pending_radio_map"] = False
            try:
                if getattr(bpy.context, "scene", None) != scene:
                    raise RuntimeError(
                        "The active Blender scene changed before the queued radio-map run started"
                    )
                scene_xml = _BATCH_STATE["scene_source"]
                _start_radio_map_process(
                    bpy.context, scene_xml,
                    force_current_frame=bool(_BATCH_STATE.get("force_current_frame", False)),
                    auto_triggered=bool(_BATCH_STATE.get("auto_triggered", False)),
                    auto_anchor_tx_name=str(_BATCH_STATE.get("auto_anchor_tx_name", "")),
                )
                settings.last_status = f"{_BATCH_STATE['path_status']}; starting selected 2D radio map"
            except Exception as exc:
                settings.last_status = f"{_BATCH_STATE['path_status']}; 2D radio-map start failed: {exc}"
                if _BATCH_STATE.get("pending_radio_map_3d"):
                    _BATCH_STATE["pending_radio_map_3d"] = False
                    try:
                        _start_radio_map_3d_process(
                            bpy.context, _BATCH_STATE["scene_source"],
                            force_current_frame=bool(_BATCH_STATE.get("force_current_frame", False)),
                            auto_triggered=bool(_BATCH_STATE.get("auto_triggered", False)),
                            auto_anchor_tx_name=str(_BATCH_STATE.get("auto_anchor_tx_name", "")),
                        )
                    except Exception as next_exc:
                        settings.last_status += f"; 3D radio-map start failed: {next_exc}"
                        _reset_batch_state()
                else:
                    _reset_batch_state()
        elif _BATCH_STATE.get("pending_radio_map_3d"):
            _BATCH_STATE["pending_radio_map_3d"] = False
            try:
                _start_radio_map_3d_process(
                    bpy.context, _BATCH_STATE["scene_source"],
                    force_current_frame=bool(_BATCH_STATE.get("force_current_frame", False)),
                    auto_triggered=bool(_BATCH_STATE.get("auto_triggered", False)),
                    auto_anchor_tx_name=str(_BATCH_STATE.get("auto_anchor_tx_name", "")),
                )
                settings.last_status = f"{_BATCH_STATE['path_status']}; starting selected 3D radio map"
            except Exception as exc:
                settings.last_status = f"{_BATCH_STATE['path_status']}; 3D radio-map start failed: {exc}"
                _reset_batch_state()
        else:
            _reset_batch_state()

    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
    return None


# -----------------------------------------------------------------------------
# Embedded-result analytics
# -----------------------------------------------------------------------------

_ANALYTICS_SOURCE_INFO = {
    "PATHS": ("last_paths_object", "paths_pointcloud", "simulated_paths"),
    "RADIO_MAP": ("last_radio_map_object", "radio_map_pointcloud", "radio_maps"),
    "RADIO_MAP_3D": (
        "last_radio_map_3d_object", "radio_map_3d_pointcloud", "radio_maps_3d"
    ),
}


def _analytics_attribute_values(obj, name, default=0.0):
    mesh = getattr(obj, "data", None)
    if not isinstance(mesh, bpy.types.Mesh):
        return []
    count = len(mesh.vertices)
    attribute = mesh.attributes.get(name)
    if attribute is None or len(attribute.data) != count:
        return [default] * count
    values = [default] * count
    try:
        attribute.data.foreach_get("value", values)
    except Exception:
        values = [getattr(item, "value", default) for item in attribute.data]
    return values


def _analytics_target_object(scene, source):
    source = str(source or "PATHS")
    last_property, result_type, collection_key = _ANALYTICS_SOURCE_INFO[source]

    view_layer = getattr(bpy.context, "view_layer", None)
    view_objects = getattr(view_layer, "objects", None) if view_layer is not None else None
    active = getattr(view_objects, "active", None)
    if active is not None and str(active.get("sionna_result_type", "")) == result_type:
        return active

    settings = scene.sionna_bridge
    last_name = str(getattr(settings, last_property, "") or "")
    obj = bpy.data.objects.get(last_name) if last_name else None
    if obj is not None and str(obj.get("sionna_result_type", "")) == result_type:
        return obj

    workflow = _find_environment(scene)
    if workflow is not None:
        candidates = [
            item for item in workflow[collection_key].objects
            if str(item.get("sionna_result_type", "")) == result_type
        ]
        if candidates:
            candidates.sort(key=lambda item: item.name)
            return candidates[-1]
    return None


def _finite_numbers(values):
    result = []
    for value in values:
        try:
            number = float(value)
        except Exception:
            continue
        if math.isfinite(number):
            result.append(number)
    return result


def _number_stats(values):
    values = _finite_numbers(values)
    if not values:
        return {"min": 0.0, "max": 0.0, "mean": 0.0, "median": 0.0}
    return {
        "min": min(values),
        "max": max(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
    }



def _percentile(values, percentile):
    numbers = sorted(_finite_numbers(values))
    if not numbers:
        return 0.0
    percentile = max(0.0, min(100.0, float(percentile)))
    if len(numbers) == 1:
        return numbers[0]
    position = (len(numbers) - 1) * percentile / 100.0
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return numbers[lower]
    fraction = position - lower
    return numbers[lower] * (1.0 - fraction) + numbers[upper] * fraction


def _db_to_linear(value_db):
    try:
        value_db = float(value_db)
    except Exception:
        return 0.0
    if not math.isfinite(value_db) or value_db <= -600.0:
        return 0.0
    return 10.0 ** (value_db / 10.0)


def _linear_to_db(value, floor=-600.0):
    try:
        value = float(value)
    except Exception:
        return float(floor)
    if not math.isfinite(value) or value <= 0.0:
        return float(floor)
    return 10.0 * math.log10(value)


def _embedded_channel_links(obj):
    raw = obj.get("sionna_channel_analytics", "")
    if not raw:
        return [], "embedded_path_subset"
    try:
        payload = json.loads(str(raw))
    except Exception:
        return [], "embedded_path_subset"
    links = []
    for frame_item in list(payload.get("frames") or []):
        frame = int(frame_item.get("frame", 0))
        analytics = frame_item.get("channel_analytics") or {}
        for link in list(analytics.get("links") or []):
            item = dict(link)
            item["frame"] = int(item.get("frame", frame))
            links.append(item)
    return links, str(payload.get("source", "worker_all_valid_paths"))


def _channel_link_from_records(frame, pos_idx, records, settings):
    records = list(records)
    if not records:
        return None
    first_arrival = min(float(item["delay_ns"]) for item in records)
    powers = [_db_to_linear(item["path_gain_db"]) for item in records]
    total_power = sum(powers)
    strongest = max(records, key=lambda item: float(item["path_gain_db"]))
    strongest_power = _db_to_linear(strongest["path_gain_db"])
    rest = max(0.0, total_power - strongest_power)
    excess = [float(item["delay_ns"]) - first_arrival for item in records]
    if total_power > 0.0:
        mean_excess = sum(p*d for p, d in zip(powers, excess)) / total_power
        rms = math.sqrt(max(0.0, sum(
            p * (d - mean_excess) ** 2 for p, d in zip(powers, excess)
        ) / total_power))
    else:
        mean_excess = 0.0
        rms = 0.0
    dopplers = [float(item.get("doppler_hz", 0.0)) for item in records]
    if total_power > 0.0:
        doppler_mean = sum(p*d for p, d in zip(powers, dopplers)) / total_power
        rms_doppler = math.sqrt(max(0.0, sum(
            p * (d - doppler_mean) ** 2 for p, d in zip(powers, dopplers)
        ) / total_power))
    else:
        doppler_mean = 0.0
        rms_doppler = 0.0
    drop = float(settings.analytics_significant_path_threshold_db)
    strongest_db = float(strongest["path_gain_db"])
    significant = [
        delay for delay, record in zip(excess, records)
        if float(record["path_gain_db"]) >= strongest_db - drop
    ]
    type_counts = {}
    type_power = {}
    for record, power in zip(records, powers):
        label = str(record.get("path_type", "Other"))
        type_counts[label] = type_counts.get(label, 0) + 1
        type_power[label] = type_power.get(label, 0.0) + power
    components = []
    for record in sorted(records, key=lambda item: item["path_gain_db"], reverse=True)[
        : int(settings.analytics_cir_component_limit)
    ]:
        components.append({
            "path_index": int(record.get("path_index", 0)),
            "delay_ns": float(record["delay_ns"]),
            "excess_delay_ns": float(record["delay_ns"]) - first_arrival,
            "coefficient_real": float(record.get("coefficient_real", 0.0)),
            "coefficient_imag": float(record.get("coefficient_imag", 0.0)),
            "amplitude": float(record.get("amplitude", 0.0)),
            "phase_rad": float(record.get("phase_rad", 0.0)),
            "path_gain_db": float(record["path_gain_db"]),
            "doppler_hz": float(record.get("doppler_hz", 0.0)),
            "path_type": record.get("path_type", "Other"),
            "aod_azimuth_deg": record.get("aod_azimuth_deg"),
            "aoa_azimuth_deg": record.get("aoa_azimuth_deg"),
        })
    bin_count = max(16, int(settings.analytics_pdp_bins))
    max_delay = max(excess) if excess else 0.0
    bins = [0.0] * (1 if max_delay <= 1e-12 else bin_count)
    for delay, power in zip(excess, powers):
        index = 0 if max_delay <= 1e-12 else min(
            bin_count - 1, int(max(0.0, delay) / max_delay * bin_count)
        )
        bins[index] += power
    pdp = []
    for index, power in enumerate(bins):
        center = 0.0 if max_delay <= 1e-12 else (index + 0.5) * max_delay / len(bins)
        pdp.append({
            "excess_delay_ns": center,
            "power_linear": power,
            "power_db": _linear_to_db(power),
        })
    return {
        "frame": int(frame), "pos_idx": int(pos_idx),
        "path_count": len(records),
        "los_available": any(item.get("path_type") == "LoS" for item in records),
        "total_power_linear": total_power,
        "total_power_db": _linear_to_db(total_power),
        "strongest_path_gain_db": strongest_db,
        "dominant_to_rest_db": _linear_to_db(strongest_power / rest) if rest > 0 else 300.0,
        "first_arrival_ns": first_arrival,
        "mean_excess_delay_ns": mean_excess,
        "rms_delay_spread_ns": rms,
        "doppler_mean_hz": float(doppler_mean),
        "rms_doppler_spread_hz": float(rms_doppler),
        "doppler_min_hz": min(dopplers) if dopplers else 0.0,
        "doppler_max_hz": max(dopplers) if dopplers else 0.0,
        "max_abs_doppler_hz": max((abs(value) for value in dopplers), default=0.0),
        "tx_velocity_m_s": list(records[0].get("tx_velocity_m_s", [0.0, 0.0, 0.0])),
        "rx_velocity_m_s": list(records[0].get("rx_velocity_m_s", [0.0, 0.0, 0.0])),
        "relative_velocity_m_s": list(records[0].get("relative_velocity_m_s", [0.0, 0.0, 0.0])),
        "tx_speed_m_s": float(records[0].get("tx_speed_m_s", 0.0)),
        "rx_speed_m_s": float(records[0].get("rx_speed_m_s", 0.0)),
        "relative_speed_m_s": float(records[0].get("relative_speed_m_s", 0.0)),
        "max_significant_excess_delay_ns": max(significant) if significant else 0.0,
        "significant_path_threshold_db": drop,
        "path_type_counts": type_counts,
        "path_type_power_db": {key: _linear_to_db(value) for key, value in type_power.items()},
        "cir_components": components,
        "pdp_bins": pdp,
        "antenna_pair_note": "Derived from embedded visualization paths",
    }


def _channel_frame_series(links):
    grouped = {}
    for link in links:
        grouped.setdefault(int(link.get("frame", 0)), []).append(link)
    rows = []
    for frame in sorted(grouped):
        frame_links = grouped[frame]
        total_linear = sum(max(0.0, float(item.get("total_power_linear", 0.0))) for item in frame_links)
        rms_values = _finite_numbers(item.get("rms_delay_spread_ns") for item in frame_links)
        first_values = _finite_numbers(item.get("first_arrival_ns") for item in frame_links)
        dominant_values = _finite_numbers(item.get("dominant_to_rest_db") for item in frame_links)
        doppler_spreads = _finite_numbers(item.get("rms_doppler_spread_hz") for item in frame_links)
        doppler_maxima = _finite_numbers(item.get("max_abs_doppler_hz") for item in frame_links)
        tx_speeds = _finite_numbers(item.get("tx_speed_m_s") for item in frame_links)
        rx_speeds = _finite_numbers(item.get("rx_speed_m_s") for item in frame_links)
        relative_speeds = _finite_numbers(item.get("relative_speed_m_s") for item in frame_links)
        rows.append({
            "frame": frame,
            "link_count": len(frame_links),
            "path_count": sum(int(item.get("path_count", 0)) for item in frame_links),
            "total_power_db": _linear_to_db(total_linear),
            "rms_delay_spread_ns": statistics.fmean(rms_values) if rms_values else None,
            "first_arrival_ns": min(first_values) if first_values else None,
            "dominant_to_rest_db": statistics.fmean(dominant_values) if dominant_values else None,
            "rms_doppler_spread_hz": statistics.fmean(doppler_spreads) if doppler_spreads else None,
            "max_abs_doppler_hz": max(doppler_maxima) if doppler_maxima else None,
            "tx_speed_m_s": statistics.fmean(tx_speeds) if tx_speeds else 0.0,
            "rx_speed_m_s": statistics.fmean(rx_speeds) if rx_speeds else 0.0,
            "relative_speed_m_s": statistics.fmean(relative_speeds) if relative_speeds else 0.0,
            "los_percent": 100.0 * sum(bool(item.get("los_available")) for item in frame_links) / max(1, len(frame_links)),
        })
    return rows


def _path_classification(record):
    if int(record.get("path_is_los", 0)):
        return "LoS"
    active = []
    if int(record.get("path_num_specular", 0)) > 0:
        active.append("Specular")
    if int(record.get("path_num_diffuse", 0)) > 0:
        active.append("Diffuse")
    if int(record.get("path_num_refraction", 0)) > 0:
        active.append("Refraction")
    if int(record.get("path_num_diffraction", 0)) > 0:
        active.append("Diffraction")
    if int(record.get("path_num_mixed", 0)) > 0 or len(active) > 1:
        return "Mixed"
    return active[0] if active else "Other"


_GEOMETRY_ANALYTICS_METRICS = {
    "SURFACE_AREA": ("surface_area_m2", "Surface area", "m²"),
    "VOLUME": ("volume_m3", "Enclosed volume", "m³"),
    "BBOX_VOLUME": ("bbox_volume_m3", "Bounding-box volume", "m³"),
    "VERTICES": ("vertex_count", "Vertex count", ""),
    "FACES": ("face_count", "Face count", ""),
}


def _procedural_geometry_records(obj):
    raw = obj.get("sionna_procedural_geometry_stats", "")
    if not raw:
        return []
    try:
        records = json.loads(str(raw))
    except Exception:
        return []
    result = []
    for item in records if isinstance(records, list) else []:
        if not isinstance(item, dict):
            continue
        record = dict(item)
        record["frame"] = int(record.get("frame", 0))
        result.append(record)
    result.sort(key=lambda item: item["frame"])
    return result


def _pearson_correlation(x_values, y_values):
    pairs = []
    for x, y in zip(x_values, y_values):
        if x is None or y is None:
            continue
        try:
            x_value, y_value = float(x), float(y)
        except Exception:
            continue
        if math.isfinite(x_value) and math.isfinite(y_value):
            pairs.append((x_value, y_value))
    if len(pairs) < 2:
        return None
    xs = [item[0] for item in pairs]
    ys = [item[1] for item in pairs]
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    denominator_x = sum((x - mean_x) ** 2 for x in xs)
    denominator_y = sum((y - mean_y) ** 2 for y in ys)
    denominator = math.sqrt(denominator_x * denominator_y)
    if denominator <= 1e-20:
        return None
    return numerator / denominator


def _relative_change_percent(value, baseline):
    value = float(value)
    baseline = float(baseline)
    if abs(baseline) <= 1e-20:
        return 0.0 if abs(value) <= 1e-20 else 100.0
    return 100.0 * (value - baseline) / abs(baseline)


def _standard_deviation(values):
    numbers = _finite_numbers(values)
    return statistics.pstdev(numbers) if len(numbers) > 1 else 0.0


def _selected_geometry_metric(scene):
    return _GEOMETRY_ANALYTICS_METRICS.get(
        scene.sionna_bridge.analytics_geometry_metric,
        _GEOMETRY_ANALYTICS_METRICS["SURFACE_AREA"],
    )


def _path_procedural_animation(scene, obj, records, scope, channel_series=None):
    geometry_records = _procedural_geometry_records(obj)
    if scope == "CURRENT":
        current = int(scene.frame_current)
        geometry_records = [item for item in geometry_records if item["frame"] == current]
    if not geometry_records:
        return None
    metric_key, metric_label, metric_unit = _selected_geometry_metric(scene)
    by_frame = {}
    for record in records:
        by_frame.setdefault(int(record["frame"]), []).append(record)
    channel_by_frame = {
        int(item.get("frame", 0)): item for item in list(channel_series or [])
    }
    baseline = float(geometry_records[0].get(metric_key, 0.0))
    frame_rows = []
    for geometry in geometry_records:
        frame = int(geometry["frame"])
        paths = by_frame.get(frame, [])
        gains = [item["path_gain_db"] for item in paths]
        delays = [item["delay_ns"] for item in paths]
        distances = [item["straight_distance_m"] for item in paths]
        channel = channel_by_frame.get(frame, {})
        type_counts = {}
        for path in paths:
            type_counts[path["path_type"]] = type_counts.get(path["path_type"], 0) + 1
        metric_value = float(geometry.get(metric_key, 0.0))
        frame_rows.append({
            "frame": frame, "geometry_value": metric_value,
            "geometry_change_percent": _relative_change_percent(metric_value, baseline),
            "vertex_count": int(geometry.get("vertex_count", 0)),
            "face_count": int(geometry.get("face_count", 0)),
            "surface_area_m2": float(geometry.get("surface_area_m2", 0.0)),
            "volume_m3": float(geometry.get("volume_m3", 0.0)),
            "bbox_volume_m3": float(geometry.get("bbox_volume_m3", 0.0)),
            "path_count": int(channel.get("path_count", len(paths))),
            "gain_mean_db": _number_stats(gains)["mean"] if gains else None,
            "gain_median_db": _number_stats(gains)["median"] if gains else None,
            "gain_max_db": _number_stats(gains)["max"] if gains else None,
            "gain_std_db": _standard_deviation(gains) if gains else None,
            "delay_mean_ns": _number_stats(delays)["mean"] if delays else None,
            "delay_median_ns": _number_stats(delays)["median"] if delays else None,
            "delay_std_ns": _standard_deviation(delays) if delays else None,
            "distance_mean_m": _number_stats(distances)["mean"] if distances else None,
            "channel_total_power_db": channel.get("total_power_db"),
            "rms_delay_spread_ns": channel.get("rms_delay_spread_ns"),
            "first_arrival_ns": channel.get("first_arrival_ns"),
            "dominant_to_rest_db": channel.get("dominant_to_rest_db"),
            "los_percent": channel.get("los_percent"),
            "dominant_path_type": max(type_counts.items(), key=lambda item: item[1])[0] if type_counts else "None",
            "path_types": type_counts,
            "geometry_signature": str(geometry.get("geometry_signature", "")),
        })
    geometry_values = [row["geometry_value"] for row in frame_rows]
    strongest_change = max(frame_rows, key=lambda row: abs(row["geometry_change_percent"]))
    def corr(key):
        rows = [row for row in frame_rows if row.get(key) is not None]
        return _pearson_correlation(
            [row["geometry_value"] for row in rows], [row[key] for row in rows]
        )
    return {
        "enabled": True, "frame_count": len(frame_rows),
        "geometry_metric": metric_key, "geometry_label": metric_label,
        "geometry_unit": metric_unit, "geometry_stats": _number_stats(geometry_values),
        "distinct_geometry_states": len({
            row.get("geometry_signature") for row in frame_rows if row.get("geometry_signature")
        }),
        "max_change_frame": strongest_change["frame"],
        "max_change_percent": strongest_change["geometry_change_percent"],
        "correlation_gain": corr("gain_median_db"),
        "correlation_delay": corr("delay_median_ns"),
        "correlation_path_count": corr("path_count"),
        "correlation_channel_power": corr("channel_total_power_db"),
        "correlation_rms_delay": corr("rms_delay_spread_ns"),
        "correlation_first_arrival": corr("first_arrival_ns"),
        "frames": frame_rows,
    }


def _map_procedural_animation(scene, obj, records, scope, metric_label, metric_unit):
    geometry_records = _procedural_geometry_records(obj)
    if scope == "CURRENT":
        current = int(scene.frame_current)
        geometry_records = [item for item in geometry_records if item["frame"] == current]
    if not geometry_records:
        return None
    metric_key, geometry_label, geometry_unit = _selected_geometry_metric(scene)
    by_frame = {}
    for record in records:
        by_frame.setdefault(int(record["frame"]), []).append(record)
    baseline = float(geometry_records[0].get(metric_key, 0.0))
    frame_rows = []
    for geometry in geometry_records:
        frame = int(geometry["frame"])
        points = by_frame.get(frame, [])
        values = [item["metric_db"] for item in points if item.get("valid")]
        metric_value = float(geometry.get(metric_key, 0.0))
        frame_rows.append({
            "frame": frame,
            "geometry_value": metric_value,
            "geometry_change_percent": _relative_change_percent(metric_value, baseline),
            "vertex_count": int(geometry.get("vertex_count", 0)),
            "face_count": int(geometry.get("face_count", 0)),
            "surface_area_m2": float(geometry.get("surface_area_m2", 0.0)),
            "volume_m3": float(geometry.get("volume_m3", 0.0)),
            "bbox_volume_m3": float(geometry.get("bbox_volume_m3", 0.0)),
            "point_count": len(points),
            "valid_percent": 100.0 * len(values) / max(1, len(points)),
            "metric_mean": _number_stats(values)["mean"] if values else None,
            "metric_median": _number_stats(values)["median"] if values else None,
            "metric_max": _number_stats(values)["max"] if values else None,
            "metric_std": _standard_deviation(values) if values else None,
            "geometry_signature": str(geometry.get("geometry_signature", "")),
        })
    valid_metric = [row for row in frame_rows if row["metric_median"] is not None]
    geometry_values = [row["geometry_value"] for row in frame_rows]
    strongest_change = max(frame_rows, key=lambda row: abs(row["geometry_change_percent"]))
    return {
        "enabled": True,
        "frame_count": len(frame_rows),
        "geometry_metric": metric_key,
        "geometry_label": geometry_label,
        "geometry_unit": geometry_unit,
        "map_metric_label": metric_label,
        "map_metric_unit": metric_unit,
        "geometry_stats": _number_stats(geometry_values),
        "distinct_geometry_states": len({
            row.get("geometry_signature") for row in frame_rows
            if row.get("geometry_signature")
        }),
        "max_change_frame": strongest_change["frame"],
        "max_change_percent": strongest_change["geometry_change_percent"],
        "correlation_metric": _pearson_correlation(
            [row["geometry_value"] for row in valid_metric],
            [row["metric_median"] for row in valid_metric],
        ),
        "correlation_coverage": _pearson_correlation(
            [row["geometry_value"] for row in frame_rows],
            [row["valid_percent"] for row in frame_rows],
        ),
        "frames": frame_rows,
    }


def _collect_path_analytics(scene, obj, scope):
    settings = scene.sionna_bridge
    mesh = obj.data
    count = len(mesh.vertices)
    names = (
        "frame", "frequency_ghz", "pos_idx", "path_uid_num", "path_index",
        "point_order", "top_rank", "path_is_los", "path_num_specular",
        "path_num_diffuse", "path_num_refraction", "path_num_diffraction",
        "path_num_mixed", "path_gain_db", "delay_ns", "straight_distance_m",
        "path_length_m", "excess_distance_m", "amplitude", "phase_rad",
        "doppler_hz", "doppler_abs_hz", "tx_speed_m_s", "rx_speed_m_s",
        "relative_speed_m_s", "tx_velocity_x", "tx_velocity_y", "tx_velocity_z",
        "rx_velocity_x", "rx_velocity_y", "rx_velocity_z",
        "relative_velocity_x", "relative_velocity_y", "relative_velocity_z",
        "num_events", "x", "y", "z",
    )
    arrays = {name: _analytics_attribute_values(obj, name, 0.0) for name in names}
    current_frame = int(scene.frame_current)
    pair_filter = int(settings.analytics_pair_index)
    records = []
    for index in range(count):
        if int(arrays["point_order"][index]) != 0:
            continue
        frame = int(arrays["frame"][index])
        pos_idx = int(arrays["pos_idx"][index])
        if scope == "CURRENT" and frame != current_frame:
            continue
        if pair_filter >= 0 and pos_idx != pair_filter:
            continue
        amplitude = float(arrays["amplitude"][index])
        phase = float(arrays["phase_rad"][index])
        record = {
            "frame": frame,
            "frequency_ghz": float(arrays["frequency_ghz"][index]),
            "pos_idx": pos_idx,
            "path_uid_num": int(arrays["path_uid_num"][index]),
            "path_index": int(arrays["path_index"][index]),
            "top_rank": int(arrays["top_rank"][index]),
            "path_is_los": int(arrays["path_is_los"][index]),
            "path_num_specular": int(arrays["path_num_specular"][index]),
            "path_num_diffuse": int(arrays["path_num_diffuse"][index]),
            "path_num_refraction": int(arrays["path_num_refraction"][index]),
            "path_num_diffraction": int(arrays["path_num_diffraction"][index]),
            "path_num_mixed": int(arrays["path_num_mixed"][index]),
            "path_gain_db": float(arrays["path_gain_db"][index]),
            "delay_ns": float(arrays["delay_ns"][index]),
            "straight_distance_m": float(arrays["straight_distance_m"][index]),
            "path_length_m": float(arrays["path_length_m"][index]),
            "excess_distance_m": float(arrays["excess_distance_m"][index]),
            "amplitude": amplitude,
            "phase_rad": phase,
            "doppler_hz": float(arrays["doppler_hz"][index]),
            "doppler_abs_hz": float(arrays["doppler_abs_hz"][index]),
            "tx_speed_m_s": float(arrays["tx_speed_m_s"][index]),
            "rx_speed_m_s": float(arrays["rx_speed_m_s"][index]),
            "relative_speed_m_s": float(arrays["relative_speed_m_s"][index]),
            "tx_velocity_m_s": [
                float(arrays["tx_velocity_x"][index]),
                float(arrays["tx_velocity_y"][index]),
                float(arrays["tx_velocity_z"][index]),
            ],
            "rx_velocity_m_s": [
                float(arrays["rx_velocity_x"][index]),
                float(arrays["rx_velocity_y"][index]),
                float(arrays["rx_velocity_z"][index]),
            ],
            "relative_velocity_m_s": [
                float(arrays["relative_velocity_x"][index]),
                float(arrays["relative_velocity_y"][index]),
                float(arrays["relative_velocity_z"][index]),
            ],
            "coefficient_real": amplitude * math.cos(phase),
            "coefficient_imag": amplitude * math.sin(phase),
        }
        record["path_type"] = _path_classification(record)
        next_index = index + 1
        if (
            next_index < count
            and int(arrays["path_uid_num"][next_index]) == record["path_uid_num"]
            and int(arrays["point_order"][next_index]) == 1
        ):
            dx = float(arrays["x"][next_index]) - float(arrays["x"][index])
            dy = float(arrays["y"][next_index]) - float(arrays["y"][index])
            record["aod_azimuth_deg"] = math.degrees(math.atan2(dy, dx)) % 360.0
        else:
            record["aod_azimuth_deg"] = None
        end_index = index
        while (
            end_index + 1 < count
            and int(arrays["path_uid_num"][end_index + 1]) == record["path_uid_num"]
        ):
            end_index += 1
        if end_index > index:
            dx = float(arrays["x"][end_index]) - float(arrays["x"][end_index - 1])
            dy = float(arrays["y"][end_index]) - float(arrays["y"][end_index - 1])
            record["aoa_azimuth_deg"] = math.degrees(math.atan2(dy, dx)) % 360.0
        else:
            record["aoa_azimuth_deg"] = None
        records.append(record)

    if not records:
        pair_note = f" for TX/RX pair {pair_filter}" if pair_filter >= 0 else ""
        raise RuntimeError(
            f"No propagation paths are available{pair_note} for "
            f"{'frame ' + str(current_frame) if scope == 'CURRENT' else 'the selected scope'}"
        )

    links = {}
    for record in records:
        links.setdefault((record["frame"], record["pos_idx"]), record["straight_distance_m"])
    path_types = {}
    reflection_orders = {}
    path_type_power_linear = {}
    for record in records:
        label = record["path_type"]
        path_types[label] = path_types.get(label, 0) + 1
        reflection_orders[int(record["path_num_specular"])] = reflection_orders.get(
            int(record["path_num_specular"]), 0
        ) + 1
        path_type_power_linear[label] = path_type_power_linear.get(label, 0.0) + _db_to_linear(
            record["path_gain_db"]
        )

    channel_links, channel_source = _embedded_channel_links(obj)
    channel_links = [
        item for item in channel_links
        if (scope != "CURRENT" or int(item.get("frame", 0)) == current_frame)
        and (pair_filter < 0 or int(item.get("pos_idx", -1)) == pair_filter)
    ]
    if not channel_links:
        grouped = {}
        for record in records:
            grouped.setdefault((record["frame"], record["pos_idx"]), []).append(record)
        channel_links = [
            _channel_link_from_records(frame, pos_idx, items, settings)
            for (frame, pos_idx), items in sorted(grouped.items())
        ]
        channel_links = [item for item in channel_links if item]
        channel_source = "embedded_visualization_paths"

    channel_series = _channel_frame_series(channel_links)
    total_power_values = [item.get("total_power_db") for item in channel_links]
    rms_values = [item.get("rms_delay_spread_ns") for item in channel_links]
    first_values = [item.get("first_arrival_ns") for item in channel_links]
    mean_excess_values = [item.get("mean_excess_delay_ns") for item in channel_links]
    dominant_values = [item.get("dominant_to_rest_db") for item in channel_links]
    rms_doppler_values = [item.get("rms_doppler_spread_hz") for item in channel_links]
    max_doppler_values = [item.get("max_abs_doppler_hz") for item in channel_links]
    tx_speed_values = [item.get("tx_speed_m_s") for item in channel_links]
    rx_speed_values = [item.get("rx_speed_m_s") for item in channel_links]
    relative_speed_values = [item.get("relative_speed_m_s") for item in channel_links]
    selected_candidates = [
        item for item in channel_links if int(item.get("frame", -1)) == current_frame
    ] or channel_links
    selected_channel = sorted(
        selected_candidates,
        key=lambda item: (int(item.get("pos_idx", 0)), int(item.get("frame", 0))),
    )[0] if selected_candidates else {}

    gains = [item["path_gain_db"] for item in records]
    delays = [item["delay_ns"] for item in records]
    dopplers = [item.get("doppler_hz", 0.0) for item in records]
    distances = list(links.values())
    lengths = [item["path_length_m"] for item in records]
    excess = [item["excess_distance_m"] for item in records]
    frequencies = sorted({round(item["frequency_ghz"], 9) for item in records})
    frames = sorted({item["frame"] for item in records})
    sorted_records = sorted(records, key=lambda item: item["path_gain_db"], reverse=True)

    summary = {
        "source": "PATHS", "object": obj.name, "scope": scope,
        "frame": current_frame, "pair_filter": pair_filter,
        "path_count": len(records), "link_count": len(links),
        "frame_count": len(frames), "frames": frames,
        "frequencies_ghz": frequencies,
        "distance_m": _number_stats(distances), "gain_db": _number_stats(gains),
        "delay_ns": _number_stats(delays), "path_length_m": _number_stats(lengths),
        "excess_distance_m": _number_stats(excess), "path_types": path_types,
        "path_type_power_db": {
            key: _linear_to_db(value) for key, value in path_type_power_linear.items()
        },
        "reflection_orders": reflection_orders, "top_paths": sorted_records[:20],
        "channel_source": channel_source,
        "channel_link_count": len(channel_links),
        "channel_total_power_db": _number_stats(total_power_values),
        "rms_delay_spread_ns": _number_stats(rms_values),
        "first_arrival_ns": _number_stats(first_values),
        "mean_excess_delay_ns": _number_stats(mean_excess_values),
        "dominant_to_rest_db": _number_stats(dominant_values),
        "doppler_hz": _number_stats(dopplers),
        "doppler_abs_hz": _number_stats(abs(value) for value in dopplers),
        "rms_doppler_spread_hz": _number_stats(rms_doppler_values),
        "max_abs_doppler_hz": _number_stats(max_doppler_values),
        "tx_speed_m_s": _number_stats(tx_speed_values),
        "rx_speed_m_s": _number_stats(rx_speed_values),
        "relative_speed_m_s": _number_stats(relative_speed_values),
        "mobility_available": mesh.attributes.get("doppler_hz") is not None,
        "mobility_detected": any(
            abs(float(value or 0.0)) > 1e-7
            for value in tx_speed_values + rx_speed_values
        ),
        "los_link_percent": 100.0 * sum(bool(item.get("los_available")) for item in channel_links) / max(1, len(channel_links)),
        "channel_links": channel_links,
        "channel_frame_series": channel_series,
        "selected_channel": selected_channel,
        "delay_reference": settings.analytics_delay_reference,
        "significant_path_threshold_db": float(settings.analytics_significant_path_threshold_db),
        "channel_note": (
            "Worker summaries use every valid path for the first antenna pair. "
            "Older result objects fall back to the embedded visualization-path subset."
        ),
    }
    procedural_animation = _path_procedural_animation(
        scene, obj, records, scope, channel_series
    )
    if procedural_animation is not None:
        summary["procedural_animation"] = procedural_animation
    return summary, records


def _collect_map_analytics(scene, obj, source, scope):
    settings = scene.sionna_bridge
    count = len(obj.data.vertices)
    current_frame = int(scene.frame_current)
    frames = _analytics_attribute_values(obj, "frame", 0)
    metric = str(obj.get("sionna_map_metric", "path_gain")).lower()
    db_attribute = str(obj.get("sionna_metric_db_attribute", {
        "path_gain": "path_gain_db", "rss": "rss_dbm", "sinr": "sinr_db"
    }.get(metric, "path_gain_db")))
    values_db = _analytics_attribute_values(obj, db_attribute, -300.0)
    association_available = obj.data.attributes.get("associated_tx") is not None
    associations = (
        _analytics_attribute_values(obj, "associated_tx", -1)
        if association_available else [-1] * count
    )
    try:
        tx_index_items = json.loads(str(obj.get("sionna_tx_index_map", "[]")))
    except Exception:
        tx_index_items = []
    tx_names = {
        int(item.get("index", index)): str(item.get("name", f"TX_{index:03d}"))
        for index, item in enumerate(tx_index_items)
        if isinstance(item, dict)
    }

    def tx_name(index):
        index = int(index)
        return tx_names.get(index, f"TX {index}")

    def association_summary(indices):
        counts = {}
        unassociated = 0
        for index in indices:
            tx_index = int(associations[index])
            if tx_index < 0 or float(values_db[index]) <= -299.999:
                unassociated += 1
                continue
            counts[tx_index] = counts.get(tx_index, 0) + 1
        associated_count = sum(counts.values())
        rows = [
            {
                "index": tx_index,
                "name": tx_name(tx_index),
                "count": cell_count,
                "share_percent": 100.0 * cell_count / max(1, associated_count),
            }
            for tx_index, cell_count in sorted(counts.items())
        ]
        dominant = max(rows, key=lambda item: item["count"]) if rows else None
        return {
            "available": association_available,
            "metric": metric,
            "associated_count": associated_count,
            "unassociated_count": unassociated,
            "unassociated_percent": 100.0 * unassociated / max(1, len(indices)),
            "tx_count": len(rows),
            "transmitters": rows,
            "dominant": dominant,
        }

    selected = [
        index for index in range(count)
        if scope != "CURRENT" or int(frames[index]) == current_frame
    ]
    if not selected:
        raise RuntimeError(f"No radio-map points are available for frame {current_frame}")
    selected_values = [
        float(values_db[index]) for index in selected
        if float(values_db[index]) > -299.999
    ]
    frame_values = sorted({int(frames[index]) for index in selected})
    threshold = float(settings.analytics_map_threshold)
    threshold_count = sum(value >= threshold for value in selected_values)
    percentiles = {
        str(p): _percentile(selected_values, p) for p in (5, 10, 50, 90, 95)
    }
    frame_series = []
    for frame in frame_values:
        frame_indices = [index for index in selected if int(frames[index]) == frame]
        values = [
            float(values_db[index]) for index in frame_indices
            if float(values_db[index]) > -299.999
        ]
        frame_association = association_summary(frame_indices)
        dominant = frame_association.get("dominant") or {}
        frame_series.append({
            "frame": frame,
            "point_count": len(frame_indices),
            "valid_count": len(values),
            "median": _percentile(values, 50) if values else None,
            "p10": _percentile(values, 10) if values else None,
            "p90": _percentile(values, 90) if values else None,
            "mean": statistics.fmean(values) if values else None,
            "std": _standard_deviation(values) if values else None,
            "coverage_percent": 100.0 * sum(value >= threshold for value in values) / max(1, len(values)),
            "associated_tx_count": int(frame_association.get("tx_count", 0)),
            "dominant_tx": dominant.get("name"),
            "dominant_tx_index": dominant.get("index"),
            "dominant_tx_share_percent": dominant.get("share_percent"),
            "unassociated_percent": float(frame_association.get("unassociated_percent", 0.0)),
        })
    records = [
        {
            "frame": int(frames[index]), "metric_db": float(values_db[index]),
            "valid": int(float(values_db[index]) > -299.999),
            "associated_tx": int(associations[index]) if association_available else -1,
            "associated_tx_name": tx_name(int(associations[index]))
                if association_available and int(associations[index]) >= 0 else "Unassociated",
            "x": float(obj.data.vertices[index].co.x),
            "y": float(obj.data.vertices[index].co.y),
            "z": float(obj.data.vertices[index].co.z),
        }
        for index in selected
    ]
    if source == "RADIO_MAP_3D":
        z_values = sorted({round(item["z"], 6) for item in records})
        layer_count = len(z_values)
        height_profile = []
        for z_value in z_values:
            layer_records = [item for item in records if round(item["z"], 6) == z_value]
            values = [item["metric_db"] for item in layer_records if item["valid"]]
            layer_counts = {}
            for item in layer_records:
                tx_index = int(item.get("associated_tx", -1))
                if item["valid"] and tx_index >= 0:
                    layer_counts[tx_index] = layer_counts.get(tx_index, 0) + 1
            dominant_index = max(layer_counts, key=layer_counts.get) if layer_counts else None
            associated_total = sum(layer_counts.values())
            height_profile.append({
                "z": z_value,
                "point_count": len(layer_records),
                "median": _percentile(values, 50) if values else None,
                "p10": _percentile(values, 10) if values else None,
                "coverage_percent": 100.0 * sum(value >= threshold for value in values) / max(1, len(values)),
                "dominant_tx": tx_name(dominant_index) if dominant_index is not None else None,
                "dominant_tx_index": dominant_index,
                "dominant_tx_share_percent": (
                    100.0 * layer_counts[dominant_index] / max(1, associated_total)
                    if dominant_index is not None else None
                ),
            })
    else:
        layer_count = 1
        height_profile = []
    metric_label = {"path_gain": "Path gain", "rss": "RSS", "sinr": "SINR"}.get(metric, metric)
    metric_unit = "dBm" if metric == "rss" else "dB"
    association = association_summary(selected)
    summary = {
        "source": source, "object": obj.name, "scope": scope, "frame": current_frame,
        "point_count": len(selected), "valid_count": len(selected_values),
        "valid_percent": 100.0 * len(selected_values) / max(1, len(selected)),
        "frame_count": len(frame_values), "frames": frame_values,
        "frequencies_ghz": [], "gain_db": _number_stats(selected_values),
        "percentiles": percentiles,
        "coverage_threshold": threshold,
        "coverage_above_threshold_percent": 100.0 * threshold_count / max(1, len(selected_values)),
        "outage_below_threshold_percent": 100.0 - 100.0 * threshold_count / max(1, len(selected_values)),
        "frame_series": frame_series,
        "height_profile": height_profile,
        "layer_count": layer_count, "metric": metric, "metric_label": metric_label,
        "metric_unit": metric_unit, "metric_db_attribute": db_attribute,
        "tx_association": association,
        "association_attribute": "associated_tx" if association_available else "",
        "association_note": (
            "associated_tx is the zero-based Sionna transmitter index providing "
            f"the highest {metric_label}; -1 marks an invalid or unassociated cell."
        ),
    }
    procedural_animation = _map_procedural_animation(
        scene, obj, records, scope, metric_label, metric_unit
    )
    if procedural_animation is not None:
        summary["procedural_animation"] = procedural_animation
    return summary, records

def _collect_analytics(scene):
    settings = scene.sionna_bridge
    source = settings.analytics_source
    obj = _analytics_target_object(scene, source)
    if obj is None:
        label = {
            "PATHS": "propagation-path",
            "RADIO_MAP": "2D radio-map",
            "RADIO_MAP_3D": "3D radio-map",
        }[source]
        raise RuntimeError(f"No embedded {label} result object was found")
    if source == "PATHS":
        return _collect_path_analytics(scene, obj, settings.analytics_scope)
    return _collect_map_analytics(scene, obj, source, settings.analytics_scope)


def _refresh_analytics_cache(scene):
    summary, _records = _collect_analytics(scene)
    settings = scene.sionna_bridge
    cache_summary = dict(summary)
    # The UI cache keeps scalar summaries only. CIR components, PDP bins, and
    # all-link arrays remain embedded on the result object and are rebuilt for
    # the external dashboard on demand.
    if cache_summary.get("source") == "PATHS":
        selected = dict(cache_summary.get("selected_channel") or {})
        selected.pop("cir_components", None)
        selected.pop("pdp_bins", None)
        cache_summary["selected_channel"] = selected
        cache_summary.pop("channel_links", None)
        cache_summary.pop("channel_frame_series", None)
    else:
        cache_summary.pop("frame_series", None)
        cache_summary.pop("height_profile", None)
    settings.analytics_json = json.dumps(cache_summary, separators=(",", ":"))
    settings.analytics_last_object = str(summary.get("object", ""))
    return summary


def _format_frequency_range(values):
    values = list(values or [])
    if not values:
        return "—"
    if len(values) == 1:
        return f"{values[0]:g} GHz"
    return f"{min(values):g}–{max(values):g} GHz"


def _svg_histogram(values, title, x_label, bins=28, width=560, height=260):
    values = _finite_numbers(values)
    if not values:
        return f'<section class="chart"><h3>{html.escape(title)}</h3><p>No data.</p></section>'
    low, high = min(values), max(values)
    if abs(high - low) < 1e-12:
        high = low + 1.0
    counts = [0] * bins
    for value in values:
        index = min(bins - 1, max(0, int((value - low) / (high - low) * bins)))
        counts[index] += 1
    max_count = max(counts) or 1
    left, right, top, bottom = 54, 16, 28, 42
    plot_w, plot_h = width - left - right, height - top - bottom
    bar_w = plot_w / bins
    bars = []
    for index, count in enumerate(counts):
        bar_h = plot_h * count / max_count
        x = left + index * bar_w + 1
        y = top + plot_h - bar_h
        bars.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{max(1.0, bar_w-2):.2f}" '
            f'height="{bar_h:.2f}" rx="1" />'
        )
    return f'''<section class="chart"><h3>{html.escape(title)}</h3>
<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">
<line class="axis" x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" />
<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" />
<g class="bars">{''.join(bars)}</g>
<text class="tick" x="{left}" y="{height-20}">{low:.3g}</text>
<text class="tick" text-anchor="end" x="{left+plot_w}" y="{height-20}">{high:.3g}</text>
<text class="axis-label" text-anchor="middle" x="{left+plot_w/2}" y="{height-4}">{html.escape(x_label)}</text>
<text class="tick" text-anchor="end" x="{left-8}" y="{top+5}">{max_count}</text>
<text class="tick" text-anchor="end" x="{left-8}" y="{top+plot_h}">0</text>
</svg></section>'''


def _svg_bar_chart(items, title, width=560, height=260):
    items = list(items)
    if not items:
        return f'<section class="chart"><h3>{html.escape(title)}</h3><p>No data.</p></section>'
    max_value = max(value for _label, value in items) or 1
    left, right, top, bottom = 62, 16, 28, 52
    plot_w, plot_h = width - left - right, height - top - bottom
    gap = 10
    bar_w = max(8, (plot_w - gap * (len(items)-1)) / max(1, len(items)))
    shapes = []
    for index, (label, value) in enumerate(items):
        bar_h = plot_h * value / max_value
        x = left + index * (bar_w + gap)
        y = top + plot_h - bar_h
        shapes.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_w:.2f}" height="{bar_h:.2f}" rx="2" />'
            f'<text class="bar-value" text-anchor="middle" x="{x+bar_w/2:.2f}" y="{max(top+12, y-5):.2f}">{value}</text>'
            f'<text class="tick" text-anchor="middle" x="{x+bar_w/2:.2f}" y="{height-22}">{html.escape(str(label))}</text>'
        )
    return f'''<section class="chart"><h3>{html.escape(title)}</h3>
<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">
<line class="axis" x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" />
<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" />
<g class="bars">{''.join(shapes)}</g>
</svg></section>'''


def _svg_scatter(x_values, y_values, title, x_label, y_label, width=560, height=260):
    pairs = [
        (float(x), float(y)) for x, y in zip(x_values, y_values)
        if math.isfinite(float(x)) and math.isfinite(float(y))
    ]
    if not pairs:
        return f'<section class="chart"><h3>{html.escape(title)}</h3><p>No data.</p></section>'
    if len(pairs) > 3000:
        step = max(1, len(pairs) // 3000)
        pairs = pairs[::step]
    x_min, x_max = min(x for x, _ in pairs), max(x for x, _ in pairs)
    y_min, y_max = min(y for _, y in pairs), max(y for _, y in pairs)
    if abs(x_max - x_min) < 1e-12:
        x_max = x_min + 1.0
    if abs(y_max - y_min) < 1e-12:
        y_max = y_min + 1.0
    left, right, top, bottom = 62, 16, 28, 46
    plot_w, plot_h = width-left-right, height-top-bottom
    circles = []
    for x, y in pairs:
        px = left + (x-x_min)/(x_max-x_min)*plot_w
        py = top + plot_h - (y-y_min)/(y_max-y_min)*plot_h
        circles.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="2.1" />')
    return f'''<section class="chart"><h3>{html.escape(title)}</h3>
<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">
<line class="axis" x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" />
<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" />
<g class="points">{''.join(circles)}</g>
<text class="tick" x="{left}" y="{height-22}">{x_min:.3g}</text>
<text class="tick" text-anchor="end" x="{left+plot_w}" y="{height-22}">{x_max:.3g}</text>
<text class="tick" text-anchor="end" x="{left-8}" y="{top+5}">{y_max:.3g}</text>
<text class="tick" text-anchor="end" x="{left-8}" y="{top+plot_h}">{y_min:.3g}</text>
<text class="axis-label" text-anchor="middle" x="{left+plot_w/2}" y="{height-4}">{html.escape(x_label)}</text>
<text class="axis-label" text-anchor="middle" transform="translate(15 {top+plot_h/2}) rotate(-90)">{html.escape(y_label)}</text>
</svg></section>'''


def _svg_line_chart(x_values, y_values, title, x_label, y_label, width=560, height=260):
    pairs = []
    for x, y in zip(x_values, y_values):
        if y is None:
            continue
        try:
            x_value, y_value = float(x), float(y)
        except Exception:
            continue
        if math.isfinite(x_value) and math.isfinite(y_value):
            pairs.append((x_value, y_value))
    if not pairs:
        return f'<section class="chart"><h3>{html.escape(title)}</h3><p>No data.</p></section>'
    pairs.sort(key=lambda item: item[0])
    x_min, x_max = min(x for x, _ in pairs), max(x for x, _ in pairs)
    y_min, y_max = min(y for _, y in pairs), max(y for _, y in pairs)
    if abs(x_max - x_min) < 1e-12:
        x_max = x_min + 1.0
    if abs(y_max - y_min) < 1e-12:
        margin = max(1.0, abs(y_min) * 0.02)
        y_min -= margin
        y_max += margin
    left, right, top, bottom = 62, 16, 28, 46
    plot_w, plot_h = width-left-right, height-top-bottom
    points = []
    circles = []
    for x, y in pairs:
        px = left + (x-x_min)/(x_max-x_min)*plot_w
        py = top + plot_h - (y-y_min)/(y_max-y_min)*plot_h
        points.append(f'{px:.2f},{py:.2f}')
        circles.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="2.6" />')
    return (
        f'<section class="chart"><h3>{html.escape(title)}</h3>'
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">'
        f'<line class="axis" x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" />'
        f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" />'
        f'<polyline class="trend-line" points="{" ".join(points)}" />'
        f'<g class="trend-points">{"".join(circles)}</g>'
        f'<text class="tick" x="{left}" y="{height-22}">{x_min:.3g}</text>'
        f'<text class="tick" text-anchor="end" x="{left+plot_w}" y="{height-22}">{x_max:.3g}</text>'
        f'<text class="tick" text-anchor="end" x="{left-8}" y="{top+5}">{y_max:.3g}</text>'
        f'<text class="tick" text-anchor="end" x="{left-8}" y="{top+plot_h}">{y_min:.3g}</text>'
        f'<text class="axis-label" text-anchor="middle" x="{left+plot_w/2}" y="{height-4}">{html.escape(x_label)}</text>'
        f'<text class="axis-label" text-anchor="middle" transform="translate(15 {top+plot_h/2}) rotate(-90)">{html.escape(y_label)}</text>'
        '</svg></section>'
    )



def _svg_cdf(values, title, x_label, width=560, height=260):
    values = sorted(_finite_numbers(values))
    if not values:
        return f'<section class="chart"><h3>{html.escape(title)}</h3><p>No data.</p></section>'
    if len(values) > 2000:
        step = max(1, len(values) // 2000)
        values = values[::step]
    x_min, x_max = min(values), max(values)
    if abs(x_max - x_min) < 1e-12:
        x_max = x_min + 1.0
    left, right, top, bottom = 62, 16, 28, 46
    plot_w, plot_h = width-left-right, height-top-bottom
    points = []
    for index, value in enumerate(values):
        x = left + (value-x_min)/(x_max-x_min)*plot_w
        y = top + plot_h - (index+1)/len(values)*plot_h
        points.append(f'{x:.2f},{y:.2f}')
    return (
        f'<section class="chart"><h3>{html.escape(title)}</h3>'
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">'
        f'<line class="axis" x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" />'
        f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" />'
        f'<polyline class="trend-line" points="{" ".join(points)}" />'
        f'<text class="tick" x="{left}" y="{height-22}">{x_min:.3g}</text>'
        f'<text class="tick" text-anchor="end" x="{left+plot_w}" y="{height-22}">{x_max:.3g}</text>'
        f'<text class="tick" text-anchor="end" x="{left-8}" y="{top+5}">1</text>'
        f'<text class="tick" text-anchor="end" x="{left-8}" y="{top+plot_h}">0</text>'
        f'<text class="axis-label" text-anchor="middle" x="{left+plot_w/2}" y="{height-4}">{html.escape(x_label)}</text>'
        f'<text class="axis-label" text-anchor="middle" transform="translate(15 {top+plot_h/2}) rotate(-90)">CDF</text>'
        '</svg></section>'
    )


def _svg_cir_stem(components, delay_reference="RELATIVE", width=560, height=260):
    components = list(components or [])
    if not components:
        return '<section class="chart"><h3>Channel Impulse Response</h3><p>No CIR components.</p></section>'
    delay_key = "excess_delay_ns" if delay_reference == "RELATIVE" else "delay_ns"
    pairs = [
        (float(item.get(delay_key, 0.0)), float(item.get("amplitude", 0.0)))
        for item in components
        if math.isfinite(float(item.get(delay_key, 0.0)))
        and math.isfinite(float(item.get("amplitude", 0.0)))
    ]
    if not pairs:
        return '<section class="chart"><h3>Channel Impulse Response</h3><p>No CIR components.</p></section>'
    x_min, x_max = min(x for x, _ in pairs), max(x for x, _ in pairs)
    y_max = max(y for _, y in pairs) or 1.0
    if abs(x_max-x_min) < 1e-12:
        x_max = x_min + 1.0
    left, right, top, bottom = 62, 16, 28, 46
    plot_w, plot_h = width-left-right, height-top-bottom
    stems=[]
    for x,y in pairs:
        px=left+(x-x_min)/(x_max-x_min)*plot_w
        py=top+plot_h-y/y_max*plot_h
        stems.append(
            f'<line class="stem" x1="{px:.2f}" y1="{top+plot_h}" x2="{px:.2f}" y2="{py:.2f}" />'
            f'<circle class="stem-point" cx="{px:.2f}" cy="{py:.2f}" r="2.4" />'
        )
    delay_label = "Excess delay (ns)" if delay_reference == "RELATIVE" else "Absolute delay (ns)"
    return f'''<section class="chart"><h3>Channel Impulse Response |a(τ)|</h3>
<svg viewBox="0 0 {width} {height}" role="img" aria-label="Channel impulse response magnitude">
<line class="axis" x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" />
<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" />
<g>{''.join(stems)}</g>
<text class="tick" x="{left}" y="{height-22}">{x_min:.3g}</text>
<text class="tick" text-anchor="end" x="{left+plot_w}" y="{height-22}">{x_max:.3g}</text>
<text class="tick" text-anchor="end" x="{left-8}" y="{top+5}">{y_max:.3g}</text>
<text class="tick" text-anchor="end" x="{left-8}" y="{top+plot_h}">0</text>
<text class="axis-label" text-anchor="middle" x="{left+plot_w/2}" y="{height-4}">{html.escape(delay_label)}</text>
<text class="axis-label" text-anchor="middle" transform="translate(15 {top+plot_h/2}) rotate(-90)">|a|</text>
</svg></section>'''


def _svg_pdp(pdp_bins, title="Power Delay Profile", width=560, height=260):
    bins = [item for item in list(pdp_bins or []) if float(item.get("power_db", -600.0)) > -599.0]
    if not bins:
        return f'<section class="chart"><h3>{html.escape(title)}</h3><p>No PDP data.</p></section>'
    x_values=[float(item.get("excess_delay_ns",0.0)) for item in bins]
    y_values=[float(item.get("power_db",-600.0)) for item in bins]
    return _svg_line_chart(x_values, y_values, title, "Excess delay (ns)", "Power (dB)", width, height)


def _svg_frame_delay_heatmap(channel_links, delay_reference="RELATIVE", width=1120, height=330):
    links=list(channel_links or [])
    frames=sorted({int(item.get("frame",0)) for item in links})
    if len(frames) < 2:
        return '<section class="chart wide"><h3>Frame–Delay Power</h3><p>At least two frames are required.</p></section>'
    samples=[]
    for link in links:
        first=float(link.get("first_arrival_ns") or 0.0)
        for item in list(link.get("pdp_bins") or []):
            power=float(item.get("power_linear",0.0))
            if power <= 0.0:
                continue
            delay=float(item.get("excess_delay_ns",0.0))
            if delay_reference == "ABSOLUTE":
                delay += first
            samples.append((int(link.get("frame",0)),delay,power))
    if not samples:
        return '<section class="chart wide"><h3>Frame–Delay Power</h3><p>No PDP data.</p></section>'
    d_min=min(item[1] for item in samples); d_max=max(item[1] for item in samples)
    if abs(d_max-d_min)<1e-12: d_max=d_min+1.0
    delay_bins=64
    grid={(frame,index):0.0 for frame in frames for index in range(delay_bins)}
    for frame,delay,power in samples:
        index=min(delay_bins-1,max(0,int((delay-d_min)/(d_max-d_min)*delay_bins)))
        grid[(frame,index)]+=power
    db_values=[_linear_to_db(value) for value in grid.values() if value>0]
    db_min=min(db_values) if db_values else -120.0
    db_max=max(db_values) if db_values else 0.0
    if abs(db_max-db_min)<1e-12: db_min=db_max-1.0
    left,right,top,bottom=68,22,30,48
    plot_w,plot_h=width-left-right,height-top-bottom
    cell_w=plot_w/delay_bins; cell_h=plot_h/len(frames)
    rects=[]
    for row,frame in enumerate(frames):
        for index in range(delay_bins):
            power=grid[(frame,index)]
            if power<=0: continue
            value=_linear_to_db(power)
            opacity=0.12+0.88*(value-db_min)/(db_max-db_min)
            x=left+index*cell_w; y=top+row*cell_h
            rects.append(f'<rect class="heat" x="{x:.2f}" y="{y:.2f}" width="{cell_w+0.3:.2f}" height="{cell_h+0.3:.2f}" opacity="{opacity:.3f}" />')
    delay_label="Excess delay (ns)" if delay_reference=="RELATIVE" else "Absolute delay (ns)"
    return f'''<section class="chart wide"><h3>Frame–Delay Power</h3>
<svg viewBox="0 0 {width} {height}" role="img" aria-label="Power delay profile across frames">
<line class="axis" x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" />
<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" />
<g>{''.join(rects)}</g>
<text class="tick" x="{left}" y="{height-22}">{d_min:.3g}</text>
<text class="tick" text-anchor="end" x="{left+plot_w}" y="{height-22}">{d_max:.3g}</text>
<text class="tick" text-anchor="end" x="{left-8}" y="{top+8}">F{frames[0]}</text>
<text class="tick" text-anchor="end" x="{left-8}" y="{top+plot_h}">F{frames[-1]}</text>
<text class="axis-label" text-anchor="middle" x="{left+plot_w/2}" y="{height-4}">{html.escape(delay_label)}</text>
<text class="axis-label" text-anchor="middle" transform="translate(15 {top+plot_h/2}) rotate(-90)">Frame</text>
</svg></section>'''

def _correlation_text(value):
    return "—" if value is None else f"{float(value):+.3f}"


def _optional_number(value, format_spec):
    if value is None:
        return "—"
    return format(float(value), format_spec)


def _procedural_dashboard_sections(summary):
    animation = summary.get("procedural_animation") or {}
    rows = list(animation.get("frames") or [])
    if not rows:
        return [], ""
    geometry_label = animation.get("geometry_label", "Geometry")
    geometry_unit = animation.get("geometry_unit", "")
    geometry_axis = geometry_label + (f" ({geometry_unit})" if geometry_unit else "")
    source = summary.get("source")
    frames = [row.get("frame") for row in rows]
    charts = [
        _svg_line_chart(
            frames, [row.get("geometry_value") for row in rows],
            f"{geometry_label} vs Frame", "Frame", geometry_axis,
        ),
    ]
    if source == "PATHS":
        charts.extend([
            _svg_line_chart(
                frames, [row.get("channel_total_power_db") for row in rows],
                "Total Channel Power vs Frame", "Frame", "Channel power (dB)",
            ),
            _svg_line_chart(
                frames, [row.get("rms_delay_spread_ns") for row in rows],
                "RMS Delay Spread vs Frame", "Frame", "RMS delay spread (ns)",
            ),
            _svg_line_chart(
                frames, [row.get("first_arrival_ns") for row in rows],
                "First Arrival vs Frame", "Frame", "First-arrival delay (ns)",
            ),
            _svg_line_chart(
                frames, [row.get("los_percent") for row in rows],
                "LoS Availability vs Frame", "Frame", "LoS links (%)",
            ),
            _svg_line_chart(
                frames, [row.get("path_count") for row in rows],
                "Path Count vs Frame", "Frame", "Path count",
            ),
            _svg_scatter(
                [row.get("geometry_value") for row in rows],
                [row.get("channel_total_power_db") for row in rows],
                f"{geometry_label} vs Channel Power", geometry_axis, "Channel power (dB)",
            ),
            _svg_scatter(
                [row.get("geometry_value") for row in rows],
                [row.get("rms_delay_spread_ns") for row in rows],
                f"{geometry_label} vs RMS Delay Spread", geometry_axis,
                "RMS delay spread (ns)",
            ),
        ])
        table_rows = []
        for row in rows:
            table_rows.append(
                '<tr>'
                f'<td>{int(row.get("frame", 0))}</td>'
                f'<td>{float(row.get("geometry_value", 0.0)):.6g}</td>'
                f'<td>{int(row.get("path_count", 0))}</td>'
                f'<td>{_optional_number(row.get("channel_total_power_db"), ".3f")}</td>'
                f'<td>{_optional_number(row.get("rms_delay_spread_ns"), ".4g")}</td>'
                f'<td>{_optional_number(row.get("first_arrival_ns"), ".4g")}</td>'
                f'<td>{_optional_number(row.get("los_percent"), ".1f")}</td>'
                '</tr>'
            )
        table = (
            '<section><h2>Procedural frame summary</h2><div class="table-wrap"><table>'
            f'<thead><tr><th>Frame</th><th>{html.escape(geometry_axis)}</th><th>Paths</th>'
            '<th>Channel power (dB)</th><th>RMS delay (ns)</th>'
            '<th>First arrival (ns)</th><th>LoS (%)</th></tr></thead>'
            f'<tbody>{"".join(table_rows)}</tbody></table></div></section>'
        )
    else:
        metric_label = animation.get("map_metric_label", "Map metric")
        metric_unit = animation.get("map_metric_unit", "dB")
        charts.extend([
            _svg_line_chart(
                frames, [row.get("metric_median") for row in rows],
                f"Median {metric_label} vs Frame", "Frame", f"{metric_label} ({metric_unit})",
            ),
            _svg_line_chart(
                frames, [row.get("valid_percent") for row in rows],
                "Valid Coverage vs Frame", "Frame", "Valid coverage (%)",
            ),
            _svg_line_chart(
                frames, [row.get("metric_std") for row in rows],
                f"{metric_label} Spread vs Frame", "Frame", f"{metric_label} standard deviation ({metric_unit})",
            ),
            _svg_scatter(
                [row.get("geometry_value") for row in rows],
                [row.get("metric_median") for row in rows],
                f"{geometry_label} vs Median {metric_label}", geometry_axis,
                f"{metric_label} ({metric_unit})",
            ),
        ])
        table_rows = []
        for row in rows:
            table_rows.append(
                '<tr>'
                f'<td>{int(row.get("frame", 0))}</td>'
                f'<td>{float(row.get("geometry_value", 0.0)):.6g}</td>'
                f'<td>{int(row.get("point_count", 0))}</td>'
                f'<td>{_optional_number(row.get("metric_median"), ".3f")}</td>'
                f'<td>{float(row.get("valid_percent", 0.0)):.2f}</td>'
                '</tr>'
            )
        table = (
            '<section><h2>Procedural frame summary</h2><div class="table-wrap"><table>'
            f'<thead><tr><th>Frame</th><th>{html.escape(geometry_axis)}</th><th>Points</th>'
            f'<th>Median {html.escape(metric_label)}</th><th>Valid (%)</th></tr></thead>'
            f'<tbody>{"".join(table_rows)}</tbody></table></div></section>'
        )
    return charts, table


def _analytics_dashboard_html(summary, records):
    source = summary.get("source")
    title = {
        "PATHS": "Sionna Propagation and Channel Analytics",
        "RADIO_MAP": "Sionna 2D Radio Map Analytics",
        "RADIO_MAP_3D": "Sionna 3D Radio Map Analytics",
    }.get(source, "Sionna Analytics")
    frequency = _format_frequency_range(summary.get("frequencies_ghz"))
    scope = "Current frame" if summary.get("scope") == "CURRENT" else "All simulated frames"

    if source == "PATHS":
        selected = summary.get("selected_channel") or {}
        metric_cards = [
            ("Visualization paths", f"{summary['path_count']:,}"),
            ("Channel links", f"{summary.get('channel_link_count', 0):,}"),
            ("Total channel power", f"{summary['channel_total_power_db']['mean']:.2f} dB"),
            ("RMS delay spread", f"{summary['rms_delay_spread_ns']['mean']:.3g} ns"),
            ("First arrival", f"{summary['first_arrival_ns']['mean']:.3g} ns"),
            ("LoS links", f"{summary.get('los_link_percent', 0.0):.1f}%"),
            ("Dominant/rest ratio", f"{summary['dominant_to_rest_db']['mean']:.2f} dB"),
            ("Max |Doppler|", f"{summary.get('doppler_abs_hz', {}).get('max', 0.0):.3g} Hz"),
            ("RMS Doppler spread", f"{summary.get('rms_doppler_spread_hz', {}).get('mean', 0.0):.3g} Hz"),
            ("Mean TX speed", f"{summary.get('tx_speed_m_s', {}).get('mean', 0.0):.3g} m/s"),
            ("Mean RX speed", f"{summary.get('rx_speed_m_s', {}).get('mean', 0.0):.3g} m/s"),
            ("Frames", f"{summary['frame_count']:,}"),
        ]
        charts = [
            _svg_cir_stem(
                selected.get("cir_components", []),
                summary.get("delay_reference", "RELATIVE"),
            ),
            _svg_pdp(selected.get("pdp_bins", [])),
        ]
        if summary.get("scope") == "ALL":
            charts.append(_svg_frame_delay_heatmap(
                summary.get("channel_links", []),
                summary.get("delay_reference", "RELATIVE"),
            ))
        frame_series = list(summary.get("channel_frame_series") or [])
        if frame_series:
            frames = [item.get("frame") for item in frame_series]
            charts.extend([
                _svg_line_chart(
                    frames, [item.get("total_power_db") for item in frame_series],
                    "Total Channel Power vs Frame", "Frame", "Channel power (dB)",
                ),
                _svg_line_chart(
                    frames, [item.get("rms_delay_spread_ns") for item in frame_series],
                    "RMS Delay Spread vs Frame", "Frame", "RMS delay spread (ns)",
                ),
                _svg_line_chart(
                    frames, [item.get("first_arrival_ns") for item in frame_series],
                    "First Arrival vs Frame", "Frame", "Delay (ns)",
                ),
                _svg_line_chart(
                    frames, [item.get("los_percent") for item in frame_series],
                    "LoS Availability vs Frame", "Frame", "LoS links (%)",
                ),
                _svg_line_chart(
                    frames, [item.get("path_count") for item in frame_series],
                    "Detected Paths vs Frame", "Frame", "Path count",
                ),
                _svg_line_chart(
                    frames, [item.get("max_abs_doppler_hz") for item in frame_series],
                    "Maximum Absolute Doppler vs Frame", "Frame", "|Doppler| (Hz)",
                ),
                _svg_line_chart(
                    frames, [item.get("rms_doppler_spread_hz") for item in frame_series],
                    "RMS Doppler Spread vs Frame", "Frame", "RMS Doppler spread (Hz)",
                ),
                _svg_line_chart(
                    frames, [item.get("tx_speed_m_s") for item in frame_series],
                    "Mean TX Speed vs Frame", "Frame", "Speed (m/s)",
                ),
                _svg_line_chart(
                    frames, [item.get("rx_speed_m_s") for item in frame_series],
                    "Mean RX Speed vs Frame", "Frame", "Speed (m/s)",
                ),
            ])
        charts.extend([
            _svg_histogram([r['delay_ns'] for r in records], "Path Delay Distribution", "Delay (ns)"),
            _svg_histogram([r['path_gain_db'] for r in records], "Path Gain Distribution", "Path gain (dB)"),
            _svg_histogram([r.get('doppler_hz', 0.0) for r in records], "Path Doppler Distribution", "Doppler shift (Hz)"),
            _svg_scatter([r['delay_ns'] for r in records], [r['path_gain_db'] for r in records], "Path Gain vs Delay", "Delay (ns)", "Path gain (dB)"),
            _svg_scatter([r.get('doppler_hz', 0.0) for r in records], [r['path_gain_db'] for r in records], "Path Gain vs Doppler", "Doppler shift (Hz)", "Path gain (dB)"),
            _svg_histogram([r['aod_azimuth_deg'] for r in records if r.get('aod_azimuth_deg') is not None], "Geometric AoD Azimuth", "Azimuth (deg)"),
            _svg_histogram([r['aoa_azimuth_deg'] for r in records if r.get('aoa_azimuth_deg') is not None], "Geometric AoA Azimuth", "Azimuth (deg)"),
            _svg_bar_chart(sorted(summary['path_types'].items()), "Path Type Distribution"),
            _svg_bar_chart([(str(k), v) for k, v in sorted(summary['reflection_orders'].items())], "Specular Reflection Order"),
        ])
        channel_rows = ''.join(
            '<tr>'
            f'<td>{int(item.get("frame", 0))}</td>'
            f'<td>{int(item.get("pos_idx", 0))}</td>'
            f'<td>{int(item.get("path_count", 0))}</td>'
            f'<td>{float(item.get("total_power_db", -600.0)):.3f}</td>'
            f'<td>{_optional_number(item.get("rms_delay_spread_ns"), ".4g")}</td>'
            f'<td>{_optional_number(item.get("rms_doppler_spread_hz"), ".4g")}</td>'
            f'<td>{_optional_number(item.get("max_abs_doppler_hz"), ".4g")}</td>'
            f'<td>{_optional_number(item.get("first_arrival_ns"), ".4g")}</td>'
            f'<td>{"Yes" if item.get("los_available") else "No"}</td>'
            '</tr>'
            for item in summary.get("channel_links", [])
        )
        top_rows = ''.join(
            '<tr>'
            f'<td>{item["frame"]}</td><td>{item["pos_idx"]}</td>'
            f'<td>{html.escape(item["path_type"])}</td>'
            f'<td>{item["path_gain_db"]:.3f}</td><td>{item["delay_ns"]:.4g}</td>'
            f'<td>{float(item.get("doppler_hz", 0.0)):+.4g}</td>'
            f'<td>{item["path_length_m"]:.4g}</td>'
            '</tr>'
            for item in summary['top_paths'][:20]
        )
        detail_table = f'''<section><h2>Channel links</h2><p class="note">{html.escape(summary.get("channel_note", ""))}</p><div class="table-wrap"><table>
<thead><tr><th>Frame</th><th>Pair</th><th>Paths</th><th>Total power (dB)</th><th>RMS delay (ns)</th><th>RMS Doppler (Hz)</th><th>Max |Doppler| (Hz)</th><th>First arrival (ns)</th><th>LoS</th></tr></thead>
<tbody>{channel_rows}</tbody></table></div></section>
<section><h2>Strongest visualization paths</h2><div class="table-wrap"><table>
<thead><tr><th>Frame</th><th>Pair</th><th>Type</th><th>Gain (dB)</th><th>Delay (ns)</th><th>Doppler (Hz)</th><th>Length (m)</th></tr></thead>
<tbody>{top_rows}</tbody></table></div></section>'''
    else:
        metric_label = summary.get("metric_label", "Path gain")
        metric_unit = summary.get("metric_unit", "dB")
        percentile = summary.get("percentiles", {})
        threshold = float(summary.get("coverage_threshold", 0.0))
        metric_cards = [
            ("Points", f"{summary['point_count']:,}"),
            ("Valid values", f"{summary['valid_percent']:.1f}%"),
            ("5th percentile", f"{float(percentile.get('5', 0.0)):.2f} {metric_unit}"),
            ("Median", f"{float(percentile.get('50', 0.0)):.2f} {metric_unit}"),
            ("95th percentile", f"{float(percentile.get('95', 0.0)):.2f} {metric_unit}"),
            (f"Coverage ≥ {threshold:g}", f"{summary.get('coverage_above_threshold_percent', 0.0):.1f}%"),
            ("Outage", f"{summary.get('outage_below_threshold_percent', 0.0):.1f}%"),
            ("Frames", f"{summary['frame_count']:,}"),
        ]
        association = summary.get("tx_association") or {}
        dominant_tx = association.get("dominant") or {}
        if association.get("available"):
            metric_cards.extend([
                ("Associated TXs", f"{int(association.get('tx_count', 0)):,}"),
                ("Dominant TX", (
                    f"{dominant_tx.get('name', '—')} · "
                    f"{float(dominant_tx.get('share_percent', 0.0)):.1f}%"
                )),
                ("Unassociated", f"{float(association.get('unassociated_percent', 0.0)):.1f}%"),
            ])
        valid_records = [r for r in records if r.get('valid')]
        values = [r['metric_db'] for r in valid_records]
        charts = [
            _svg_cdf(values, f"{metric_label} CDF", f"{metric_label} ({metric_unit})"),
            _svg_histogram(values, f"{metric_label} Distribution", f"{metric_label} ({metric_unit})"),
            _svg_bar_chart([("Valid", summary['valid_count']), ("Invalid", summary['point_count']-summary['valid_count'])], "Coverage Validity"),
        ]
        if association.get("available") and association.get("transmitters"):
            charts.append(_svg_bar_chart(
                [
                    (f"{item.get('name', 'TX')} [{int(item.get('index', -1))}]",
                     float(item.get('share_percent', 0.0)))
                    for item in association.get("transmitters", [])
                ],
                f"TX Association Share by {metric_label}",
            ))
        frame_series = list(summary.get("frame_series") or [])
        if len(frame_series) > 1:
            frames = [item.get("frame") for item in frame_series]
            charts.extend([
                _svg_line_chart(frames, [item.get("median") for item in frame_series], f"Median {metric_label} vs Frame", "Frame", f"{metric_label} ({metric_unit})"),
                _svg_line_chart(frames, [item.get("coverage_percent") for item in frame_series], "Threshold Coverage vs Frame", "Frame", "Coverage (%)"),
                _svg_line_chart(frames, [item.get("std") for item in frame_series], f"{metric_label} Spread vs Frame", "Frame", f"Standard deviation ({metric_unit})"),
            ])
        height_profile = list(summary.get("height_profile") or [])
        if height_profile:
            charts.extend([
                _svg_line_chart(
                    [item.get("z") for item in height_profile],
                    [item.get("median") for item in height_profile],
                    f"Median {metric_label} by Height", "Height (m)", f"{metric_label} ({metric_unit})",
                ),
                _svg_line_chart(
                    [item.get("z") for item in height_profile],
                    [item.get("coverage_percent") for item in height_profile],
                    "Coverage by Height", "Height (m)", "Coverage (%)",
                ),
            ])
        frame_rows = ''.join(
            '<tr>'
            f'<td>{int(item.get("frame", 0))}</td>'
            f'<td>{int(item.get("point_count", 0))}</td>'
            f'<td>{_optional_number(item.get("p10"), ".3f")}</td>'
            f'<td>{_optional_number(item.get("median"), ".3f")}</td>'
            f'<td>{_optional_number(item.get("p90"), ".3f")}</td>'
            f'<td>{float(item.get("coverage_percent", 0.0)):.2f}</td>'
            f'<td>{html.escape(str(item.get("dominant_tx") or "—"))}</td>'
            f'<td>{_optional_number(item.get("dominant_tx_share_percent"), ".2f")}</td>'
            '</tr>'
            for item in frame_series
        )
        association_rows = ''.join(
            '<tr>'
            f'<td>{int(item.get("index", -1))}</td>'
            f'<td>{html.escape(str(item.get("name", "TX")))}</td>'
            f'<td>{int(item.get("count", 0)):,}</td>'
            f'<td>{float(item.get("share_percent", 0.0)):.3f}</td>'
            '</tr>'
            for item in association.get("transmitters", [])
        )
        association_table = (
            f'''<section><h2>Transmitter association</h2><p class="note">{html.escape(summary.get("association_note", ""))}</p><div class="table-wrap"><table>
<thead><tr><th>Index</th><th>Transmitter</th><th>Cells / voxels</th><th>Share (%)</th></tr></thead>
<tbody>{association_rows}</tbody></table></div></section>'''
            if association.get("available") else ""
        )
        detail_table = f'''<section><h2>Frame summary</h2><div class="table-wrap"><table>
<thead><tr><th>Frame</th><th>Points</th><th>P10</th><th>Median</th><th>P90</th><th>Coverage (%)</th><th>Dominant TX</th><th>TX share (%)</th></tr></thead>
<tbody>{frame_rows}</tbody></table></div></section>{association_table}'''


    animation = summary.get("procedural_animation") or {}
    animation_charts, animation_table = _procedural_dashboard_sections(summary)
    if animation:
        geometry_label = animation.get("geometry_label", "Geometry")
        geometry_unit = animation.get("geometry_unit", "")
        geometry_stats = animation.get("geometry_stats", {})
        metric_cards.extend([
            ("Procedural frames", f"{int(animation.get('frame_count', 0)):,}"),
            ("Geometry states", f"{int(animation.get('distinct_geometry_states', 0)):,}"),
            (f"{geometry_label} range", (
                f"{float(geometry_stats.get('min', 0.0)):.4g}–"
                f"{float(geometry_stats.get('max', 0.0)):.4g}"
                + (f" {geometry_unit}" if geometry_unit else "")
            )),
            ("Largest geometry change", (
                f"F{int(animation.get('max_change_frame', 0))} · "
                f"{float(animation.get('max_change_percent', 0.0)):+.2f}%"
            )),
        ])
        if source == "PATHS":
            metric_cards.extend([
                ("Geometry ↔ channel power r", _correlation_text(animation.get("correlation_channel_power"))),
                ("Geometry ↔ RMS delay r", _correlation_text(animation.get("correlation_rms_delay"))),
                ("Geometry ↔ path count r", _correlation_text(animation.get("correlation_path_count"))),
            ])
        else:
            metric_cards.extend([
                ("Geometry ↔ metric r", _correlation_text(animation.get("correlation_metric"))),
                ("Geometry ↔ coverage r", _correlation_text(animation.get("correlation_coverage"))),
            ])
        charts.extend(animation_charts)
        detail_table += animation_table

    cards = ''.join(
        f'<div class="metric"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>'
        for label, value in metric_cards
    )
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
:root{{--bg:#111827;--panel:#1f2937;--text:#e5e7eb;--muted:#9ca3af;--border:#374151;--accent:#55c7c3;--accent2:#f59e0b;}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 system-ui,Segoe UI,sans-serif}}
main{{max-width:1240px;margin:auto;padding:24px}} h1{{font-size:24px;margin:0 0 4px}} h2{{font-size:18px;margin:28px 0 12px}} h3{{font-size:15px;margin:0 0 8px}}
.meta,.note{{color:var(--muted);margin-bottom:18px}} .metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:10px}}
.metric,.chart{{background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:14px}} .metric span{{display:block;color:var(--muted)}} .metric strong{{display:block;font-size:20px;margin-top:5px}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}} .chart svg{{width:100%;height:auto}} .wide{{grid-column:1/-1}} .axis{{stroke:#6b7280;stroke-width:1}} .bars rect{{fill:var(--accent2);opacity:.88}} .points circle{{fill:var(--accent);opacity:.78}} .trend-line{{fill:none;stroke:var(--accent);stroke-width:2.2}} .trend-points circle{{fill:var(--accent2)}} .stem{{stroke:var(--accent);stroke-width:1.3}} .stem-point{{fill:var(--accent2)}} .heat{{fill:var(--accent)}} .tick,.axis-label,.bar-value{{fill:var(--muted);font-size:11px}} .bar-value{{fill:var(--text)}}
table{{border-collapse:collapse;width:100%;background:var(--panel)}} th,td{{padding:8px 10px;border-bottom:1px solid var(--border);text-align:right}} th:first-child,td:first-child,th:nth-child(3),td:nth-child(3){{text-align:left}} th{{color:var(--muted);font-weight:600}} .table-wrap{{overflow:auto;border:1px solid var(--border);border-radius:8px}}
@media(max-width:760px){{.grid{{grid-template-columns:1fr}} .wide{{grid-column:auto}} main{{padding:14px}}}}
</style></head><body><main>
<h1>{html.escape(title)}</h1><div class="meta">{html.escape(summary.get('object',''))} · {html.escape(scope)} · {html.escape(frequency)}</div>
<div class="metrics">{cards}</div><h2>Plots</h2><div class="grid">{''.join(charts)}</div>{detail_table}
</main></body></html>'''


def _write_analytics_dashboard(scene):
    summary, records = _collect_analytics(scene)
    html_text = _analytics_dashboard_html(summary, records)
    token = _sanitize_name(scene.name)
    path = Path(tempfile.gettempdir()) / f"sionna_analytics_{token}.html"
    path.write_text(html_text, encoding="utf-8")
    scene.sionna_bridge.analytics_dashboard_path = str(path)
    return path, summary


def _maybe_auto_refresh_analytics(scene, source):
    settings = scene.sionna_bridge
    if not settings.analytics_auto_refresh:
        return
    if settings.analytics_source != source and settings.analytics_json:
        return
    settings.analytics_source = source
    try:
        _refresh_analytics_cache(scene)
    except Exception:
        pass


class SIONNA_PG_DeviceConfig(PropertyGroup):
    configured: BoolProperty(
        name="Configured",
        description="The per-device orientation controls have been initialized",
        default=False,
    )
    orientation_mode: EnumProperty(
        name="Orientation",
        description="How this radio device is oriented in Sionna RT",
        items=(
            ("BLENDER", "Blender Rotation", "Use the evaluated Blender world rotation"),
            ("LOOK_AT", "Look At Target", "Point the Sionna device local +X boresight toward a target"),
            ("FIXED", "Fixed Sionna Euler", "Use fixed alpha, beta, gamma angles about z, y, x"),
        ),
        default="BLENDER",
    )
    fixed_alpha: FloatProperty(name="Alpha (Z)", subtype="ANGLE", default=0.0)
    fixed_beta: FloatProperty(name="Beta (Y)", subtype="ANGLE", default=0.0)
    fixed_gamma: FloatProperty(name="Gamma (X)", subtype="ANGLE", default=0.0)
    look_at_target: PointerProperty(
        name="Look At",
        description="Target object for the Sionna local +X antenna boresight",
        type=bpy.types.Object,
    )
    tx_power_dbm: FloatProperty(
        name="Transmit Power",
        description="Per-transmitter radiated power used by Sionna RSS and SINR maps [dBm]",
        default=44.0,
        soft_min=-60.0,
        soft_max=80.0,
    )


class SIONNA_PG_MaterialConfig(PropertyGroup):
    configured: BoolProperty(
        name="Configured",
        description="This Blender material has initialized Sionna radio properties",
        default=False,
    )
    enabled: BoolProperty(
        name="Use as Sionna Material",
        description="Export this Blender material as a frame-evaluated Sionna radio material",
        default=False,
    )
    model: EnumProperty(
        name="Material Model",
        description="Use an ITU-R P.2040 frequency-dependent model or constant custom properties",
        items=(
            ("ITU", "ITU Preset", "Use a Sionna ITURadioMaterial whose permittivity and conductivity follow scene frequency"),
            ("CUSTOM", "Custom", "Use a Sionna RadioMaterial with editable constant permittivity and conductivity"),
        ),
        default="ITU",
    )
    itu_type: EnumProperty(
        name="ITU Type",
        items=_ITU_MATERIAL_ITEMS,
        default="concrete",
    )
    thickness: FloatProperty(
        name="Thickness",
        description="Equivalent slab thickness used for reflection and transmission [m]",
        default=0.1,
        min=0.0,
        soft_max=2.0,
        unit="LENGTH",
    )
    relative_permittivity: FloatProperty(
        name="Relative Permittivity",
        description="Real relative permittivity for a custom radio material",
        default=5.24,
        min=1.0,
        soft_max=100.0,
    )
    conductivity: FloatProperty(
        name="Conductivity",
        description="Electrical conductivity for a custom radio material [S/m]",
        default=0.0462,
        min=0.0,
        soft_max=1.0e7,
    )
    scattering_coefficient: FloatProperty(
        name="Scattering Coefficient",
        description="Effective-roughness scattering coefficient S in [0,1]",
        default=0.0,
        min=0.0,
        max=1.0,
    )
    xpd_coefficient: FloatProperty(
        name="XPD Coefficient",
        description="Cross-polarization discrimination coefficient Kx in [0,1]",
        default=0.0,
        min=0.0,
        max=1.0,
    )
    scattering_pattern: EnumProperty(
        name="Scattering Pattern",
        description="Diffuse-scattering angular pattern",
        items=(
            ("lambertian", "Lambertian", "Lambertian scattering pattern"),
            ("directive", "Directive", "Directive lobe around the specular direction"),
            ("backscattering", "Backscattering", "Two-lobe backscattering model"),
        ),
        default="lambertian",
    )
    directive_alpha_r: IntProperty(
        name="Directive Alpha R",
        description="Width exponent of the directive scattering lobe",
        default=1,
        min=1,
        soft_max=100,
    )
    backscatter_alpha_r: IntProperty(
        name="Backscatter Alpha R",
        default=1,
        min=1,
        soft_max=100,
    )
    backscatter_alpha_i: IntProperty(
        name="Backscatter Alpha I",
        default=1,
        min=1,
        soft_max=100,
    )
    backscatter_lambda: FloatProperty(
        name="Backscatter Lambda",
        description="Fraction of diffuse energy assigned to the specular-side lobe",
        default=1.0,
        min=0.0,
        max=1.0,
    )


def _radio_map_reference_mesh_poll(_settings, obj):
    return bool(
        obj is not None
        and getattr(obj, "type", "") == "MESH"
        and not bool(obj.get("sionna_blender_only", False))
        and not str(obj.get("sionna_result_type", ""))
    )


def _radio_map_surface_mode_update(settings, _context):
    if _normalize_radio_map_surface_mode(
        getattr(settings, "radio_map_surface_mode", "PLANAR")
    ) == "PROJECTED" and getattr(settings, "radio_map_metric", "path_gain") != "path_gain":
        settings.radio_map_metric = "path_gain"


def _radio_map_metric_update(settings, _context):
    if _normalize_radio_map_surface_mode(
        getattr(settings, "radio_map_surface_mode", "PLANAR")
    ) == "PROJECTED" and getattr(settings, "radio_map_metric", "path_gain") != "path_gain":
        settings.radio_map_metric = "path_gain"


def _dynamic_mode_toggle_update(settings, context):
    scene = getattr(context, "scene", None) or getattr(settings, "id_data", None)
    if not isinstance(scene, bpy.types.Scene):
        _sync_dynamic_mode_handlers()
        return

    # The old development timer must never run alongside the add-on watcher.
    _stop_legacy_live_update_timer()
    _clear_auto_path_scene_state(scene.name)

    if _dynamic_mode_enabled(settings):
        # Make the master switch useful immediately. If no output-specific live
        # toggle has ever been selected, choose the first enabled simulation type.
        if not any((
            getattr(settings, "auto_compute_paths_on_tx_move", False),
            getattr(settings, "auto_compute_radio_map_on_device_move", False),
            getattr(settings, "auto_compute_radio_map_3d_on_device_move", False),
        )):
            if getattr(settings, "simulate_paths", False):
                settings.auto_compute_paths_on_tx_move = True
            elif getattr(settings, "simulate_radio_map", False):
                settings.auto_compute_radio_map_on_device_move = True
            elif getattr(settings, "simulate_radio_map_3d", False):
                settings.auto_compute_radio_map_3d_on_device_move = True
        try:
            depsgraph = (
                context.evaluated_depsgraph_get()
                if getattr(context, "scene", None) == scene
                else None
            )
            _prime_auto_path_transform_signatures(scene, depsgraph)
        except Exception:
            traceback.print_exc()
        settings.last_status = "Dynamic Mode enabled: TX/RX movement watcher is active"
    else:
        settings.last_status = "Dynamic Mode disabled: no movement-driven Sionna watcher is running"

    _sync_dynamic_mode_handlers()


def _auto_compute_paths_toggle_update(settings, context):
    scene = getattr(context, "scene", None) or getattr(settings, "id_data", None)
    if not isinstance(scene, bpy.types.Scene):
        return
    _clear_auto_path_scene_state(scene.name)
    if not _auto_move_enabled(settings):
        return
    try:
        depsgraph = (
            context.evaluated_depsgraph_get()
            if getattr(context, "scene", None) == scene
            else None
        )
        _prime_auto_path_transform_signatures(scene, depsgraph)
    except Exception:
        traceback.print_exc()


class SIONNA_PG_Settings(PropertyGroup):
    runtime_mode: EnumProperty(
        name="Runtime",
        description="Choose how Sionna simulation workers obtain Python and packages",
        items=(
            (
                "BLENDER",
                "Blender 5.2 Python",
                "Use Blender's bundled Python and the Sionna installation available to Blender; keeps simulations in isolated workers so the UI remains responsive",
            ),
            (
                "EXTERNAL",
                "External Python (Legacy)",
                "Use a separately configured Python/Conda/venv interpreter as in the Blender 5.0 bridge workflow",
            ),
        ),
        default="BLENDER",
    )
    sionna_site_packages: StringProperty(
        name="Sionna Packages",
        description=(
            "Optional Sionna site-packages directory or virtualenv root for Blender 5.2 Python. "
            "Leave blank to auto-detect an importable Sionna installation or ~/blender52-sionna"
        ),
        subtype="DIR_PATH",
        default="",
    )
    sionna_python: StringProperty(
        name="Sionna Python",
        description=(
            "Legacy external Sionna Python executable or environment folder. "
            "Only used when Runtime is External Python (Legacy)"
        ),
        subtype="FILE_PATH",
        default="",
    )
    drjit_libllvm_path: StringProperty(
        name="LLVM-C.dll",
        description=(
            "Optional LLVM-C.dll for Dr.Jit's CPU backend. Leave blank to auto-detect "
            "common Windows LLVM installations and PATH entries"
        ),
        subtype="FILE_PATH",
        default="",
    )
    workspace_dir: StringProperty(
        name="Workspace",
        description="Directory for timestamped exports and simulation results",
        subtype="DIR_PATH",
        default="//sionna_runs",
    )

    material_selection: PointerProperty(
        name="Material",
        description="Blender material to configure and assign as a Sionna radio material",
        type=bpy.types.Material,
    )

    frequency_ghz: FloatProperty(
        name="Frequency",
        description="Carrier frequency in GHz",
        default=28.0,
        min=0.001,
        soft_max=300.0,
        unit="NONE",
    )
    bandwidth_mhz: FloatProperty(
        name="Bandwidth",
        description="Scene bandwidth used to compute thermal noise for SINR [MHz]",
        default=1.0,
        min=0.000001,
        soft_max=1000.0,
    )
    temperature_k: FloatProperty(
        name="Temperature",
        description="Scene temperature used to compute thermal noise for SINR [K]",
        default=293.0,
        min=0.0,
        soft_max=500.0,
    )

    max_depth: IntProperty(
        name="Max Depth",
        default=3,
        min=0,
        soft_max=10,
    )
    samples_per_src: IntProperty(
        name="Samples / Source",
        default=100000,
        min=1,
        soft_max=10000000,
    )
    max_num_paths_per_src: IntProperty(
        name="Max Paths / Source",
        default=10000,
        min=1,
        soft_max=1000000,
    )
    seed: IntProperty(name="Seed", default=42, min=0)
    sim_numeric_id: IntProperty(
        name="Simulation ID",
        description="Numeric simulation identifier written to every Geometry Nodes CSV row",
        default=0,
        min=0,
    )
    timeline_mode: EnumProperty(
        name="Timeline",
        description="Choose whether to solve the current frame or a sampled animation range",
        items=(
            (
                "AUTO",
                "Auto Detect Animation",
                "Use the current frame when devices and solver settings are static; otherwise solve the scene frame range",
            ),
            (
                "CURRENT",
                "Current Frame Only",
                "Solve only the current Blender frame",
            ),
            (
                "RANGE",
                "Scene Frame Range",
                "Always solve from scene start to end",
            ),
        ),
        default="AUTO",
    )
    timeline_step: IntProperty(
        name="Frame Step",
        description="Sample every Nth frame when an animation range is solved",
        default=1,
        min=1,
        soft_max=100,
    )

    enable_mobility_doppler: BoolProperty(
        name="Mobility / Doppler",
        description=(
            "Estimate animated TX/RX world-space velocities from adjacent Blender "
            "frames and let Sionna compute path-wise Doppler shifts"
        ),
        default=True,
    )

    enable_los: BoolProperty(name="Line of Sight", default=True)
    enable_reflection: BoolProperty(name="Specular Reflection", default=True)
    enable_diffuse: BoolProperty(name="Diffuse Reflection", default=False)
    enable_refraction: BoolProperty(name="Refraction", default=True)
    enable_diffraction: BoolProperty(name="Diffraction", default=False)
    enable_edge_diffraction: BoolProperty(
        name="Edge Diffraction",
        description="Include free-floating edges when diffraction is enabled",
        default=False,
    )
    diffraction_lit_region: BoolProperty(
        name="Diffraction in Lit Region",
        description="Allow diffraction contributions in the geometrically lit region",
        default=True,
    )

    tx_antenna_pattern: EnumProperty(
        name="TX Pattern",
        items=(("iso", "Isotropic", "Isotropic antenna pattern"), ("dipole", "Dipole", "Ideal dipole pattern"), ("hw_dipole", "Half-wave Dipole", "Half-wave dipole pattern"), ("tr38901", "3GPP TR 38.901", "Directional 3GPP antenna element")),
        default="iso",
    )
    tx_array_rows: IntProperty(name="TX Rows", default=1, min=1, soft_max=64)
    tx_array_cols: IntProperty(name="TX Columns", default=1, min=1, soft_max=64)
    tx_vertical_spacing: FloatProperty(name="TX Vertical Spacing", description="Spacing in wavelengths", default=0.5, min=0.001, soft_max=4.0)
    tx_horizontal_spacing: FloatProperty(name="TX Horizontal Spacing", description="Spacing in wavelengths", default=0.5, min=0.001, soft_max=4.0)
    tx_polarization: EnumProperty(name="TX Polarization", items=(("V", "V", "Vertical"), ("H", "H", "Horizontal"), ("VH", "VH", "Dual vertical/horizontal"), ("cross", "Cross", "Cross-polarized")), default="V")
    tx_polarization_model: EnumProperty(name="TX Polarization Model", items=(("tr38901_2", "TR 38.901 model 2", "Default polarization model"), ("tr38901_1", "TR 38.901 model 1", "Alternative polarization model")), default="tr38901_2")

    rx_antenna_pattern: EnumProperty(
        name="RX Pattern",
        items=(("iso", "Isotropic", "Isotropic antenna pattern"), ("dipole", "Dipole", "Ideal dipole pattern"), ("hw_dipole", "Half-wave Dipole", "Half-wave dipole pattern"), ("tr38901", "3GPP TR 38.901", "Directional 3GPP antenna element")),
        default="iso",
    )
    rx_array_rows: IntProperty(name="RX Rows", default=1, min=1, soft_max=64)
    rx_array_cols: IntProperty(name="RX Columns", default=1, min=1, soft_max=64)
    rx_vertical_spacing: FloatProperty(name="RX Vertical Spacing", description="Spacing in wavelengths", default=0.5, min=0.001, soft_max=4.0)
    rx_horizontal_spacing: FloatProperty(name="RX Horizontal Spacing", description="Spacing in wavelengths", default=0.5, min=0.001, soft_max=4.0)
    rx_polarization: EnumProperty(name="RX Polarization", items=(("V", "V", "Vertical"), ("H", "H", "Horizontal"), ("VH", "VH", "Dual vertical/horizontal"), ("cross", "Cross", "Cross-polarized")), default="V")
    rx_polarization_model: EnumProperty(name="RX Polarization Model", items=(("tr38901_2", "TR 38.901 model 2", "Default polarization model"), ("tr38901_1", "TR 38.901 model 1", "Alternative polarization model")), default="tr38901_2")

    device_pattern: EnumProperty(
        name="Antenna Pattern",
        description="Sionna PlanarArray antenna pattern encoded in the selected device name",
        items=(
            ("iso", "Isotropic", "Isotropic antenna pattern"),
            ("dipole", "Dipole", "Ideal dipole pattern"),
            ("hw_dipole", "Half-wave Dipole", "Half-wave dipole pattern"),
            ("tr38901", "3GPP TR 38.901", "Directional 3GPP antenna element"),
        ),
        default="iso",
    )
    device_array_rows: IntProperty(name="Rows", default=1, min=1, soft_max=64)
    device_array_cols: IntProperty(name="Columns", default=1, min=1, soft_max=64)
    device_vertical_spacing: FloatProperty(
        name="Vertical Spacing", description="Array spacing in wavelengths", default=0.5, min=0.001, soft_max=4.0,
    )
    device_horizontal_spacing: FloatProperty(
        name="Horizontal Spacing", description="Array spacing in wavelengths", default=0.5, min=0.001, soft_max=4.0,
    )
    device_polarization: EnumProperty(
        name="Polarization",
        items=(("V", "V", "Vertical"), ("H", "H", "Horizontal"), ("VH", "VH", "Dual vertical/horizontal"), ("cross", "Cross", "Cross-polarized")),
        default="V",
    )
    device_polarization_model: EnumProperty(
        name="Polarization Model",
        items=(("tr38901_2", "TR 38.901 model 2", "Default polarization model"), ("tr38901_1", "TR 38.901 model 1", "Alternative polarization model")),
        default="tr38901_2",
    )
    device_orientation_mode: EnumProperty(
        name="Orientation",
        description="How the selected radio device is oriented in Sionna RT",
        items=(
            ("BLENDER", "Blender Object", "Use the evaluated Blender world rotation"),
            ("LOOK_AT", "Look At Target", "Dynamically point the Sionna device local +X axis toward a Blender target"),
            ("FIXED", "Fixed Sionna Euler", "Use fixed alpha, beta, gamma angles about z, y, x"),
        ),
        default="BLENDER",
    )
    device_fixed_alpha: FloatProperty(name="Alpha (Z)", subtype="ANGLE", default=0.0)
    device_fixed_beta: FloatProperty(name="Beta (Y)", subtype="ANGLE", default=0.0)
    device_fixed_gamma: FloatProperty(name="Gamma (X)", subtype="ANGLE", default=0.0)
    device_look_at_target: PointerProperty(
        name="Look At",
        description="Blender object dynamically targeted by the selected TX or RX",
        type=bpy.types.Object,
    )
    device_apply_array_to_role: BoolProperty(
        name="Apply Array to All Same-role Devices",
        description="Sionna RT uses one shared TX array and one shared RX array, so apply pattern and array settings to every device of this role",
        default=True,
    )

    motion_template_enabled: BoolProperty(
        name="TX / RX Motion Path",
        description=(
            "Show controls for creating reusable TX/RX motion templates. "
            "The generated helper stays in Blender and drives the selected radio device"
        ),
        default=False,
    )
    motion_template_style: EnumProperty(
        name="Template Style",
        description="Motion template used to sweep the associated TX or RX",
        items=(
            ("GRID", "Grid", "Sweep a TX or RX over a 2D serpentine grid; one point per frame"),
            ("POINT_CLOUD", "PointCloud", "Follow a Blender PointCloud by index; point i maps to frame Start+i"),
        ),
        default="GRID",
    )
    motion_template_device: PointerProperty(
        name="Associated TX / RX",
        description="Marked transmitter or receiver that will be driven by this motion template",
        type=bpy.types.Object,
        poll=_poll_motion_template_device,
    )
    motion_template_pointcloud: PointerProperty(
        name="PointCloud Path",
        description=(
            "PointCloud whose stored point order defines the trajectory. "
            "Point index 0 maps to Start Frame, index 1 to the next frame, and so on"
        ),
        type=bpy.types.Object,
        poll=_poll_motion_template_pointcloud,
    )
    motion_template_grid_rows: IntProperty(
        name="Rows",
        description="Number of grid rows",
        default=5,
        min=1,
        soft_max=100,
    )
    motion_template_grid_columns: IntProperty(
        name="Columns",
        description="Number of grid columns",
        default=5,
        min=1,
        soft_max=100,
    )
    motion_template_grid_row_spacing: FloatProperty(
        name="Row Spacing",
        description="Distance between grid rows in Blender units/meters",
        default=1.0,
        min=0.001,
        soft_max=100.0,
        unit="LENGTH",
    )
    motion_template_grid_column_spacing: FloatProperty(
        name="Column Spacing",
        description="Distance between grid columns in Blender units/meters",
        default=1.0,
        min=0.001,
        soft_max=100.0,
        unit="LENGTH",
    )
    motion_template_start_frame: IntProperty(
        name="Start Frame",
        description="Frame assigned to point index 0; every following path point uses the next frame",
        default=1,
        min=-1000000,
        max=1000000,
    )
    motion_template_set_scene_range: BoolProperty(
        name="Set Scene Range to Path",
        description=(
            "Set Blender's frame start/end to exactly this sweep so Timeline Auto/Range "
            "runs one simulation sample for every path point"
        ),
        default=True,
    )

    dynamic_mode: BoolProperty(
        name="Dynamic Mode",
        description=(
            "Master switch for movement-driven Sionna updates. When disabled, the "
            "add-on unregisters its TX/RX depsgraph movement listeners and does not "
            "schedule automatic simulations in the background"
        ),
        default=False,
        update=_dynamic_mode_toggle_update,
    )

    auto_compute_paths_on_tx_move: BoolProperty(
        name="Auto Compute on TX / RX Move",
        description=(
            "After a marked TX or RX transform stops changing, automatically run "
            "propagation paths for the current frame when at least one TX and RX exist. "
            "If a simulation is already running, only the newest device position is queued"
        ),
        default=False,
        update=_auto_compute_paths_toggle_update,
    )
    auto_compute_radio_map_on_device_move: BoolProperty(
        name="Auto Compute Coverage on TX Move",
        description=(
            "After a marked TX transform stops changing, automatically regenerate the "
            "2D coverage map for the current frame. RX movement does not trigger this "
            "because receivers are not inputs to the coverage-map solver"
        ),
        default=False,
        update=_auto_compute_paths_toggle_update,
    )
    auto_compute_radio_map_3d_on_device_move: BoolProperty(
        name="Auto Compute 3D Coverage on TX Move",
        description=(
            "After a marked TX transform stops changing, automatically regenerate the "
            "3D coverage map for the current frame. RX movement does not trigger this "
            "because receivers are not inputs to the coverage-map solver"
        ),
        default=False,
        update=_auto_compute_paths_toggle_update,
    )
    radio_map_auto_center_on_tx: BoolProperty(
        name="Center Coverage on Moving TX",
        description=(
            "For automatic TX-move 2D coverage runs, override Center X/Y with the "
            "evaluated world position of the transmitter that moved. The measurement "
            "plane Height stays unchanged"
        ),
        default=True,
    )
    radio_map_3d_auto_center_on_tx: BoolProperty(
        name="Center 3D Coverage on Moving TX",
        description=(
            "For automatic TX-move 3D coverage runs, override Center X/Y/Z with the "
            "evaluated world position of the transmitter that moved"
        ),
        default=True,
    )
    auto_compute_paths_delay: FloatProperty(
        name="Move Debounce",
        description=(
            "Seconds to wait after the last marked TX/RX transform update before launching "
            "an enabled automatic current-frame simulation"
        ),
        default=0.35,
        min=0.05,
        max=5.0,
        soft_max=1.5,
        precision=2,
        subtype="TIME",
    )

    post_run_action: EnumProperty(
        name="After Run",
        description="Keep the result as an external CSV, or also create legacy Blender curves",
        items=(
            (
                "CSV_ONLY",
                "CSV for Geometry Nodes",
                "Write the numeric path-point CSV and do not create Blender geometry",
            ),
            (
                "CURVES",
                "CSV + Legacy Curves",
                "Write the CSV and also import one Blender curve object per path",
            ),
        ),
        default="CSV_ONLY",
    )
    pointcloud_top_paths_per_pair: IntProperty(
        name="Top Paths / TX-RX",
        description="Write the strongest N valid paths for every TX/RX pair; 0 writes all",
        default=50,
        min=0,
        soft_max=1000,
    )
    max_imported_paths: IntProperty(
        name="Max Imported Paths",
        default=500,
        min=1,
        soft_max=10000,
    )
    path_thickness: FloatProperty(
        name="Path Thickness",
        default=0.015,
        min=0.0,
        soft_max=0.25,
        precision=4,
    )

    geometry_nodes_group_name: StringProperty(
        name="Geometry Nodes Group",
        description="Geometry Nodes group containing the Import CSV node to update after a run",
        default=_DEFAULT_GEOMETRY_NODES_GROUP,
    )
    auto_update_geometry_nodes: BoolProperty(
        name="Auto-update Import CSV",
        description="After a successful run, set the Import CSV Path in the configured Geometry Nodes group",
        default=True,
    )

    radio_map_metric: EnumProperty(
        name="Metric",
        description="Radio-map quantity embedded in Blender; maximum across transmitters per cell",
        items=(
            ("path_gain", "Path Gain", "Store path_gain and path_gain_db"),
            ("rss", "RSS", "Store received signal strength in W and dBm"),
            ("sinr", "SINR", "Store SINR in linear scale and dB"),
        ),
        default="path_gain",
        update=_radio_map_metric_update,
    )
    radio_map_surface_mode: EnumProperty(
        name="Map Surface",
        description=(
            "Use a regular horizontal plane or compute a Sionna MeshRadioMap on "
            "the triangles of a selected Blender mesh"
        ),
        items=(
            ("PLANAR", "Planar Grid", "Regular XY radio-map grid"),
            (
                "PROJECTED", "Projected Mesh",
                "Use the selected evaluated mesh as the Sionna measurement surface; one triangle is one cell",
            ),
        ),
        default="PLANAR",
        update=_radio_map_surface_mode_update,
    )
    radio_map_reference_mesh: PointerProperty(
        name="Reference Mesh",
        description=(
            "Evaluated Blender mesh used as the projected Sionna measurement surface. "
            "The generated Geometry Nodes object already contains world-space cell centers"
        ),
        type=bpy.types.Object,
        poll=_radio_map_reference_mesh_poll,
    )
    radio_map_center_x: FloatProperty(
        name="Center X",
        description="World-space X coordinate of the radio-map center",
        default=0.0,
        unit="LENGTH",
    )
    radio_map_center_y: FloatProperty(
        name="Center Y",
        description="World-space Y coordinate of the radio-map center",
        default=0.0,
        unit="LENGTH",
    )
    radio_map_height: FloatProperty(
        name="Height",
        description="World-space Z height of the horizontal measurement plane",
        default=1.5,
        unit="LENGTH",
    )
    radio_map_size_x: FloatProperty(
        name="Area Size X",
        description="Radio-map width along the world X axis",
        default=100.0,
        min=0.001,
        unit="LENGTH",
    )
    radio_map_size_y: FloatProperty(
        name="Area Size Y",
        description="Radio-map width along the world Y axis",
        default=100.0,
        min=0.001,
        unit="LENGTH",
    )
    radio_map_cell_size_x: FloatProperty(
        name="Cell Size X",
        description="Cell width along the world X axis",
        default=1.0,
        min=0.001,
        unit="LENGTH",
    )
    radio_map_cell_size_y: FloatProperty(
        name="Cell Size Y",
        description="Cell width along the world Y axis",
        default=1.0,
        min=0.001,
        unit="LENGTH",
    )
    radio_map_point_radius: FloatProperty(
        name="Point Radius",
        description="Radius attribute assigned to imported radio-map points",
        default=0.25,
        min=0.0,
        unit="LENGTH",
    )
    radio_map_auto_import: BoolProperty(
        name="Create Embedded Point Cloud After Run",
        description=(
            "Embed one point per radio-map cell in sionna_env/radio_maps and assign "
            "the metric-specific Geometry Nodes group"
        ),
        default=True,
    )
    radio_map_geometry_nodes_group_name: StringProperty(
        name="Legacy Radio Map Geometry Nodes Group",
        description=(
            "Compatibility setting retained for older scenes. The 2D radio-map node "
            "group is now selected automatically from the Path Gain, RSS, or SINR mode"
        ),
        default=_DEFAULT_RADIO_MAP_GEOMETRY_NODES_GROUP,
    )
    radio_map_auto_update_geometry_nodes: BoolProperty(
        name="Auto-update Radio Map CSV",
        description=(
            "After a successful run, update the existing Import CSV node in the "
            "Geometry Nodes group selected for the active map metric"
        ),
        default=True,
    )
    radio_map_replace_existing: BoolProperty(
        name="Replace Existing Radio Maps",
        description="Remove existing objects from sionna_env/radio_maps before importing",
        default=True,
    )

    # 3D radio-map volume controls
    radio_map_3d_metric: EnumProperty(
        name="Metric",
        description="3D radio-map quantity embedded in Blender; maximum across transmitters per voxel",
        items=(
            ("path_gain", "Path Gain", "Store path_gain and path_gain_db"),
            ("rss", "RSS", "Store received signal strength in W and dBm"),
            ("sinr", "SINR", "Store SINR in linear scale and dB"),
        ),
        default="path_gain",
    )
    radio_map_3d_center_x: FloatProperty(name="Center X", default=0.0, unit="LENGTH")
    radio_map_3d_center_y: FloatProperty(name="Center Y", default=0.0, unit="LENGTH")
    radio_map_3d_center_z: FloatProperty(name="Center Z", default=5.0, unit="LENGTH")
    radio_map_3d_size_x: FloatProperty(name="Size X", default=50.0, min=0.001, unit="LENGTH")
    radio_map_3d_size_y: FloatProperty(name="Size Y", default=50.0, min=0.001, unit="LENGTH")
    radio_map_3d_size_z: FloatProperty(name="Size Z", default=10.0, min=0.001, unit="LENGTH")
    radio_map_3d_cell_size_x: FloatProperty(name="Cell X", default=1.0, min=0.001, unit="LENGTH")
    radio_map_3d_cell_size_y: FloatProperty(name="Cell Y", default=1.0, min=0.001, unit="LENGTH")
    radio_map_3d_cell_size_z: FloatProperty(name="Cell Z", default=1.0, min=0.001, unit="LENGTH")
    radio_map_3d_point_radius: FloatProperty(
        name="Point Radius", default=0.2, min=0.0, unit="LENGTH"
    )
    radio_map_3d_geometry_nodes_group_name: StringProperty(
        name="Legacy 3D Radio Map Geometry Nodes Group",
        description=(
            "Compatibility setting retained for older scenes. The 3D radio-map node "
            "group is selected automatically from the Path Gain, RSS, or SINR mode"
        ),
        default=_DEFAULT_RADIO_MAP_3D_GEOMETRY_NODES_GROUP,
    )
    radio_map_3d_replace_existing: BoolProperty(
        name="Replace Existing 3D Radio Maps", default=True,
    )

    # Procedural scene evaluation
    procedural_geometry_enabled: BoolProperty(
        name="Procedural Geometry per Frame",
        description=(
            "Evaluate modifiers and Geometry Nodes in sionna_env/scene/procedural_geometry "
            "and export a distinct Mitsuba XML/PLY scene for every sampled frame"
        ),
        default=False,
    )
    procedural_capture_analytics: BoolProperty(
        name="Capture Geometry Statistics",
        description=(
            "Store compact per-frame evaluated mesh descriptors on result objects for "
            "procedural animation analytics; no values are duplicated on point attributes"
        ),
        default=True,
    )
    procedural_skip_failed_frames: BoolProperty(
        name="Skip Incompatible Frames",
        description=(
            "Continue exporting and simulating the remaining timeline frames when one "
            "evaluated procedural scene cannot be converted by Mitsuba"
        ),
        default=True,
    )
    procedural_export_report_json: StringProperty(
        name="Procedural Export Report", default="",
    )
    procedural_export_report_path: StringProperty(
        name="Procedural Export Report Path", default="",
    )

    # Central run controls
    simulate_paths: BoolProperty(
        name="Propagation Paths",
        description="Run the propagation-path solver and update Sionna_Paths",
        default=True,
    )
    simulate_radio_map: BoolProperty(
        name="Radio Map",
        description="Run the radio-map solver and use the Geometry Nodes group assigned to the selected metric",
        default=False,
    )
    simulate_radio_map_3d: BoolProperty(
        name="3D Radio Map",
        description="Stack horizontal Sionna radio maps into a voxel point volume",
        default=False,
    )
    refresh_scene_before_run: BoolProperty(
        name="Refresh Scene Before Run",
        description="Re-export a static scene before running; procedural geometry is always evaluated and exported per sampled frame",
        default=False,
    )

    # Panel disclosure states
    ui_show_workflow: BoolProperty(name="Workflow", default=True)
    ui_show_environment: BoolProperty(name="Sionna Runtime", default=True)
    ui_show_devices: BoolProperty(name="Devices", default=True)
    ui_show_device_antenna: BoolProperty(name="Device Antenna & Orientation", default=True)
    ui_show_materials: BoolProperty(name="Radio Materials", default=True)
    ui_show_simulation: BoolProperty(name="Simulation Settings", default=True)
    ui_show_procedural: BoolProperty(name="Procedural Geometry", default=True)
    ui_show_paths: BoolProperty(name="Propagation Paths", default=True)
    ui_show_radio_map: BoolProperty(name="Radio Map", default=True)
    ui_show_radio_map_3d: BoolProperty(name="3D Radio Map", default=True)
    ui_show_scene_cache: BoolProperty(name="Simulation", default=True)
    ui_show_status: BoolProperty(name="Status", default=True)
    ui_show_analytics: BoolProperty(name="Analytics", default=True)

    analytics_source: EnumProperty(
        name="Data Source",
        items=(
            ("PATHS", "Propagation Paths", "Analyze the latest or selected embedded path result"),
            ("RADIO_MAP", "2D Radio Map", "Analyze the latest or selected 2D radio map"),
            ("RADIO_MAP_3D", "3D Radio Map", "Analyze the latest or selected 3D radio map"),
        ),
        default="PATHS",
    )
    analytics_scope: EnumProperty(
        name="Scope",
        items=(
            ("CURRENT", "Current Frame", "Analyze only rows matching the current Blender frame"),
            ("ALL", "All Frames", "Analyze every embedded simulation frame"),
        ),
        default="CURRENT",
    )
    analytics_geometry_metric: EnumProperty(
        name="Geometry Descriptor",
        description="Frame-level evaluated geometry descriptor used for procedural correlations",
        items=(
            ("SURFACE_AREA", "Surface Area", "Evaluated world-space triangle surface area"),
            ("VOLUME", "Enclosed Volume", "Approximate volume; reliable for closed meshes"),
            ("BBOX_VOLUME", "Bounding-box Volume", "World-space bounding-box volume"),
            ("VERTICES", "Vertex Count", "Evaluated mesh vertex count"),
            ("FACES", "Face Count", "Evaluated mesh polygon count"),
        ),
        default="SURFACE_AREA",
    )
    analytics_pair_index: IntProperty(
        name="TX/RX Pair",
        description="Pair index to analyze; use -1 to aggregate all TX/RX links",
        default=-1, min=-1, max=100000,
    )
    analytics_delay_reference: EnumProperty(
        name="Delay Reference",
        items=(
            ("RELATIVE", "First Arrival = 0", "Show excess delay relative to the first arrival"),
            ("ABSOLUTE", "Absolute Delay", "Show absolute propagation delay"),
        ),
        default="RELATIVE",
    )
    analytics_significant_path_threshold_db: FloatProperty(
        name="Significant Path Drop (dB)",
        description="Paths within this many dB of the strongest path are treated as significant",
        default=20.0, min=0.0, max=120.0,
    )
    analytics_cir_component_limit: IntProperty(
        name="CIR Components",
        description="Maximum strongest CIR components stored per frame and TX/RX link on the next run",
        default=96, min=8, max=512,
    )
    analytics_pdp_bins: IntProperty(
        name="PDP Bins",
        description="Number of excess-delay bins stored per frame and TX/RX link on the next run",
        default=64, min=16, max=256,
    )
    analytics_map_threshold: FloatProperty(
        name="Coverage Threshold",
        description="Threshold used for map coverage and outage statistics (dB, dBm, or dB SINR according to the selected map)",
        default=-100.0, min=-600.0, max=300.0,
    )
    analytics_top_rows: IntProperty(
        name="Top Paths", default=5, min=1, max=20,
    )
    analytics_auto_refresh: BoolProperty(
        name="Auto-refresh After Simulation",
        description="Refresh the analytics cache when the selected result type finishes",
        default=True,
    )
    analytics_json: StringProperty(name="Analytics Cache", default="")
    analytics_last_object: StringProperty(name="Analytics Object", default="")
    analytics_dashboard_path: StringProperty(name="Analytics Dashboard", default="")

    export_format: EnumProperty(
        name="Export Results",
        description="Choose the durable on-disk export created after Blender embeds the simulation result",
        items=(
            (
                "NONE",
                "No File Export",
                "Keep the result in Blender only; temporary worker files are removed after import",
            ),
            (
                "CSV",
                "CSV + Metadata",
                "Export a simulation-specific CSV plus a traceability metadata JSON file",
            ),
            (
                "HDF5",
                "HDF5 + Metadata",
                "Export one structured HDF5 result plus a traceability metadata JSON file",
            ),
        ),
        default="NONE",
    )
    last_export_path: StringProperty(name="Last Export File", default="")
    last_export_metadata_path: StringProperty(name="Last Export Metadata", default="")

    last_status: StringProperty(name="Status", default="Ready")
    last_status_details: StringProperty(name="Full Status Details", default="")
    last_status_run_dir: StringProperty(name="Status Run Directory", default="")
    last_status_log_path: StringProperty(name="Status Log Path", default="")
    last_scene_xml: StringProperty(name="Reusable Scene XML", default="")
    last_run_dir: StringProperty(name="Last Run Directory", default="")
    last_config_path: StringProperty(name="Last Config", default="")
    last_results_json: StringProperty(name="Last JSON Results", default="")
    last_results_csv: StringProperty(name="Last Geometry Nodes CSV", default="")
    last_csv_pattern: StringProperty(name="Animated CSV Pattern", default="")
    last_radio_map_run_dir: StringProperty(name="Last Radio Map Run", default="")
    last_radio_map_csv: StringProperty(name="Last Radio Map CSV", default="")
    last_radio_map_json: StringProperty(name="Last Radio Map JSON", default="")
    last_paths_object: StringProperty(name="Last Paths Object", default="")
    last_radio_map_object: StringProperty(name="Last Radio Map Object", default="")
    last_radio_map_3d_run_dir: StringProperty(name="Last 3D Radio Map Run", default="")
    last_radio_map_3d_csv: StringProperty(name="Last 3D Radio Map CSV", default="")
    last_radio_map_3d_json: StringProperty(name="Last 3D Radio Map JSON", default="")
    last_radio_map_3d_object: StringProperty(name="Last 3D Radio Map Object", default="")



class SIONNA_OT_CreateDefaultMaterials(Operator):
    bl_idname = "sionna_bridge.create_default_materials"
    bl_label = "Create Default Sionna Materials"
    bl_description = "Create built-in Sionna ITU materials and Blender-only TX/RX representation materials"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            created, configured = _ensure_default_sionna_materials()
            settings = context.scene.sionna_bridge
            if settings.material_selection is None:
                settings.material_selection = bpy.data.materials.get("itu_concrete")
            settings.last_status = (
                f"Sionna materials ready: {created} created, {configured} configured"
            )
            self.report({"INFO"}, settings.last_status)
            return {"FINISHED"}
        except Exception as exc:
            traceback.print_exc()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class SIONNA_OT_PickActiveMaterial(Operator):
    bl_idname = "sionna_bridge.pick_active_material"
    bl_label = "Use Active Material"
    bl_description = "Load the active object's active material into the Sionna material editor"

    def execute(self, context):
        obj = context.active_object
        material = getattr(obj, "active_material", None) if obj is not None else None
        if material is None:
            self.report({"ERROR"}, "The active object has no active material")
            return {"CANCELLED"}
        context.scene.sionna_bridge.material_selection = material
        self.report({"INFO"}, f"Selected material: {material.name}")
        return {"FINISHED"}


class SIONNA_OT_EnableMaterial(Operator):
    bl_idname = "sionna_bridge.enable_material"
    bl_label = "Enable for Sionna"
    bl_description = "Prefix the selected material with itu_ and initialize editable radio properties"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.sionna_bridge
        material = settings.material_selection
        if material is None:
            self.report({"ERROR"}, "Choose a Blender material")
            return {"CANCELLED"}
        try:
            old_name = material.name
            if not material.name.lower().startswith("itu_"):
                proposed = "itu_" + _material_slug(material.name)
                existing = bpy.data.materials.get(proposed)
                if existing is not None and existing != material:
                    raise RuntimeError(
                        f"A material named '{proposed}' already exists; select it or rename the current material first"
                    )
                material.name = proposed
            config = material.sionna_radio
            inferred = _material_slug(material.name)
            config.enabled = True
            if not config.configured:
                config.configured = True
                if inferred in _ITU_MATERIAL_DEFINITIONS:
                    config.model = "ITU"
                    config.itu_type = inferred
                else:
                    config.model = "CUSTOM"
            settings.refresh_scene_before_run = True
            settings.last_status = (
                f"Enabled {material.name} for Sionna"
                + (f" (renamed from {old_name})" if old_name != material.name else "")
            )
            self.report({"INFO"}, settings.last_status)
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class SIONNA_OT_AssignMaterial(Operator):
    bl_idname = "sionna_bridge.assign_material"
    bl_label = "Assign to Selected Objects"
    bl_description = "Assign the chosen Sionna material to the active material slot of each selected mesh object"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.sionna_bridge
        material = settings.material_selection
        if material is None:
            self.report({"ERROR"}, "Choose a Blender material")
            return {"CANCELLED"}
        if not _material_is_sionna(material):
            self.report({"ERROR"}, "Enable the material for Sionna first")
            return {"CANCELLED"}
        assigned = 0
        for obj in context.selected_objects:
            data = getattr(obj, "data", None)
            slots = getattr(data, "materials", None)
            if slots is None:
                continue
            if len(slots) == 0:
                slots.append(material)
            else:
                index = min(max(int(getattr(obj, "active_material_index", 0)), 0), len(slots) - 1)
                slots[index] = material
            assigned += 1
        if assigned == 0:
            self.report({"ERROR"}, "Select at least one object that supports materials")
            return {"CANCELLED"}
        settings.refresh_scene_before_run = True
        settings.last_status = f"Assigned {material.name} to {assigned} object(s); scene refresh enabled"
        self.report({"INFO"}, settings.last_status)
        return {"FINISHED"}


class SIONNA_OT_CreateEnvironment(Operator):
    bl_idname = "sionna_bridge.create_environment"
    bl_label = "Create Env"
    bl_description = "Create or repair the Sionna workflow collection hierarchy"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            workflow = _ensure_environment(context.scene, migrate=True)
            created_materials, configured_materials = _ensure_default_sionna_materials()
            representation_count = _sync_device_representations(context.scene)
            scene_objects = len(_collection_objects_recursive(workflow["scene"]))
            tx_count = len(workflow["txs"].objects)
            rx_count = len(workflow["rxs"].objects)
            radio_map_count = len(workflow["radio_maps"].objects)
            radio_map_3d_count = len(workflow["radio_maps_3d"].objects)
            procedural_count = len(_collection_objects_recursive(workflow["procedural_geometry"]))
            context.scene.sionna_bridge.last_status = (
                f"Sionna environment ready: {scene_objects} scene objects "
                f"({procedural_count} procedural), {tx_count} TX, {rx_count} RX, "
                f"{radio_map_count} radio maps, {radio_map_3d_count} 3D radio maps; "
                f"{representation_count} device representation objects; "
                f"{created_materials} standard materials created"
            )
            self.report({"INFO"}, "Created sionna_env workflow collections")
            return {"FINISHED"}
        except Exception as exc:
            context.scene.sionna_bridge.last_status = f"Create Env failed: {exc}"
            traceback.print_exc()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class SIONNA_OT_MoveSelectedToScene(Operator):
    bl_idname = "sionna_bridge.move_selected_to_scene"
    bl_label = "Move Selected to Scene"
    bl_description = "Move selected environment objects into sionna_env/scene"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        selected = list(context.selected_objects)
        if not selected:
            self.report({"ERROR"}, "Select at least one object")
            return {"CANCELLED"}

        workflow = _ensure_environment(context.scene, migrate=True)
        moved = 0
        skipped = 0
        for obj in selected:
            if str(obj.get("sionna_role", "")).upper() in {"TX", "RX"}:
                skipped += 1
                continue
            _move_object_to_collection(obj, workflow["scene"])
            moved += 1

        context.scene.sionna_bridge.last_status = (
            f"Moved {moved} objects to sionna_env/scene"
            + (f"; skipped {skipped} TX/RX devices" if skipped else "")
        )
        self.report({"INFO"}, context.scene.sionna_bridge.last_status)
        return {"FINISHED"}


class SIONNA_OT_MoveSelectedToProcedural(Operator):
    bl_idname = "sionna_bridge.move_selected_to_procedural"
    bl_label = "Move Selected to Procedural Geometry"
    bl_description = (
        "Move selected environment objects into sionna_env/scene/procedural_geometry; "
        "their evaluated modifier output is exported for every sampled frame"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        selected = list(context.selected_objects)
        if not selected:
            self.report({"ERROR"}, "Select at least one object")
            return {"CANCELLED"}
        workflow = _ensure_environment(context.scene, migrate=True)
        moved = 0
        skipped = 0
        for obj in selected:
            if str(obj.get("sionna_role", "")).upper() in {"TX", "RX"}:
                skipped += 1
                continue
            _move_object_to_collection(obj, workflow["procedural_geometry"])
            moved += 1
        context.scene.sionna_bridge.procedural_geometry_enabled = moved > 0 or context.scene.sionna_bridge.procedural_geometry_enabled
        context.scene.sionna_bridge.last_status = (
            f"Moved {moved} objects to sionna_env/scene/procedural_geometry"
            + (f"; skipped {skipped} TX/RX devices" if skipped else "")
        )
        self.report({"INFO"}, context.scene.sionna_bridge.last_status)
        return {"FINISHED"}


class SIONNA_OT_GenerateMotionTemplate(Operator):
    bl_idname = "sionna_bridge.generate_motion_template"
    bl_label = "Generate Motion Template"
    bl_description = "Create or rebuild the selected motion template and connect it to the chosen TX/RX"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.sionna_bridge
        device = settings.motion_template_device
        if device is None:
            self.report({"ERROR"}, "Choose an Associated TX / RX first")
            return {"CANCELLED"}
        try:
            if settings.motion_template_style == "GRID":
                grid, start_frame, end_frame, count = _create_grid_motion_template(
                    context, device, settings
                )
                settings.last_status = (
                    f"Generated {settings.motion_template_grid_rows}x"
                    f"{settings.motion_template_grid_columns} grid for {device.name}: "
                    f"{count} sweep points = frames {start_frame}-{end_frame}. "
                    f"Move/rotate/scale {grid.name} to reposition the whole sweep."
                )
            elif settings.motion_template_style == "POINT_CLOUD":
                source, start_frame, end_frame, count = _create_pointcloud_motion_template(
                    context, device, settings
                )
                settings.last_status = (
                    f"Connected {device.name} to PointCloud {source.name}: "
                    f"{count} points = frames {start_frame}-{end_frame}. "
                    "Point index i maps to frame Start+i."
                )
            else:
                raise RuntimeError(f"Unsupported motion template: {settings.motion_template_style}")
            self.report({"INFO"}, settings.last_status)
            return {"FINISHED"}
        except Exception as exc:
            settings.last_status = f"Motion template failed: {exc}"
            settings.last_status_details = traceback.format_exc()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class SIONNA_OT_RemoveMotionTemplate(Operator):
    bl_idname = "sionna_bridge.remove_motion_template"
    bl_label = "Disconnect Motion Template"
    bl_description = "Disconnect the chosen TX/RX from its generated sweep and remove the helper grid"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.sionna_bridge
        device = settings.motion_template_device
        if device is None:
            self.report({"ERROR"}, "Choose an Associated TX / RX first")
            return {"CANCELLED"}
        removed = _remove_motion_template_for_device(device, preserve_world_position=True)
        _sync_pointcloud_motion_handler()
        if removed:
            settings.last_status = f"Disconnected motion template from {device.name}"
            self.report({"INFO"}, settings.last_status)
            return {"FINISHED"}
        self.report({"INFO"}, f"{device.name} has no generated motion template")
        return {"CANCELLED"}


class SIONNA_OT_SelectMotionTemplate(Operator):
    bl_idname = "sionna_bridge.select_motion_template"
    bl_label = "Select Motion Template"
    bl_description = "Select the generated grid so it can be moved, rotated, or scaled as one sweep area"
    bl_options = {"REGISTER"}

    def execute(self, context):
        device = context.scene.sionna_bridge.motion_template_device
        template = _sweep_template_object(device) if device is not None else None
        if template is None:
            self.report({"ERROR"}, "The selected device has no generated motion template")
            return {"CANCELLED"}
        target = template
        if str(device.get("sionna_sweep_style", "")) == "POINT_CLOUD":
            source = _sweep_source_object(device)
            if source is not None:
                target = source
        try:
            for obj in context.selected_objects:
                obj.select_set(False)
            target.hide_set(False)
            target.select_set(True)
            context.view_layer.objects.active = target
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class SIONNA_OT_AddDevice(Operator):
    bl_idname = "sionna_bridge.add_device"
    bl_label = "Add Sionna Device"
    bl_options = {"REGISTER", "UNDO"}

    role: StringProperty(default="TX")

    def execute(self, context):
        role = self.role.upper()
        if role not in {"TX", "RX"}:
            self.report({"ERROR"}, "Role must be TX or RX")
            return {"CANCELLED"}

        existing = _device_objects(context.scene, role)
        name = f"{role}_{len(existing) + 1:03d}"

        workflow = _ensure_environment(context.scene, migrate=True)
        bpy.ops.object.empty_add(type="PLAIN_AXES", location=context.scene.cursor.location)
        obj = context.active_object
        obj.name = name
        obj["sionna_role"] = role
        obj.sionna_device_config.configured = True
        obj.empty_display_size = 0.5
        obj.show_name = True

        # Viewport color only; simulation uses the role property.
        if role == "TX":
            obj.color = (0.1, 0.35, 1.0, 1.0)
            _move_object_to_collection(obj, workflow["txs"])
        else:
            obj.color = (0.1, 1.0, 0.25, 1.0)
            _move_object_to_collection(obj, workflow["rxs"])

        _sync_device_representations(context.scene)
        if _auto_move_enabled(context.scene.sionna_bridge):
            try:
                _prime_auto_path_transform_signatures(
                    context.scene, context.evaluated_depsgraph_get()
                )
            except Exception:
                pass
        self.report({"INFO"}, f"Added {obj.name} to sionna_env/devices/{role.lower()}s")
        return {"FINISHED"}


class SIONNA_OT_MarkSelected(Operator):
    bl_idname = "sionna_bridge.mark_selected"
    bl_label = "Mark Selected as Sionna Device"
    bl_options = {"REGISTER", "UNDO"}

    role: StringProperty(default="TX")

    def execute(self, context):
        obj = context.active_object
        if obj is None:
            self.report({"ERROR"}, "Select an object first")
            return {"CANCELLED"}
        role = self.role.upper()
        if role not in {"TX", "RX"}:
            return {"CANCELLED"}
        workflow = _ensure_environment(context.scene, migrate=True)
        obj["sionna_role"] = role
        if not obj.sionna_device_config.configured:
            parsed = _parse_device_name(obj.name, role)
            obj.sionna_device_config.orientation_mode = parsed["orientation_mode"]
            obj.sionna_device_config.look_at_target = _find_named_target(parsed["look_at_target"])
            obj.sionna_device_config.configured = True
        obj.show_name = True
        if role == "TX":
            obj.color = (0.1, 0.35, 1.0, 1.0)
            _move_object_to_collection(obj, workflow["txs"])
        else:
            obj.color = (0.1, 1.0, 0.25, 1.0)
            _move_object_to_collection(obj, workflow["rxs"])
        _sync_device_representations(context.scene)
        if _auto_move_enabled(context.scene.sionna_bridge):
            try:
                _prime_auto_path_transform_signatures(
                    context.scene, context.evaluated_depsgraph_get()
                )
            except Exception:
                pass
        self.report({"INFO"}, f"{obj.name} marked as {role} and organized")
        return {"FINISHED"}


class SIONNA_OT_ClearRole(Operator):
    bl_idname = "sionna_bridge.clear_role"
    bl_label = "Clear Sionna Role"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.active_object
        if obj is None:
            self.report({"ERROR"}, "Select an object first")
            return {"CANCELLED"}
        if str(obj.get("sionna_role", "")).upper() in {"TX", "RX"}:
            _remove_motion_template_for_device(obj, preserve_world_position=True)
        if "sionna_role" in obj:
            del obj["sionna_role"]
        _sync_device_representations(context.scene)
        self.report({"INFO"}, f"Cleared Sionna role from {obj.name}")
        return {"FINISHED"}


class SIONNA_OT_ReadDeviceName(Operator):
    bl_idname = "sionna_bridge.read_device_name"
    bl_label = "Read Device Name"
    bl_description = "Import a legacy or compact encoded device name into the independent TX/RX and orientation controls"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.active_object
        role = str(obj.get("sionna_role", "")).upper() if obj is not None else ""
        if obj is None or role not in {"TX", "RX"}:
            self.report({"ERROR"}, "Select a marked TX or RX object")
            return {"CANCELLED"}
        settings = context.scene.sionna_bridge
        parsed = _parse_device_name(obj.name, role)
        # Compact v0.13 names intentionally omit spacing and polarization
        # model. Preserve those role-wide controls unless legacy tokens carry
        # the values explicitly.
        imported_profile = dict(parsed["antenna"])
        current_profile = _role_antenna_profile(settings, role)
        lower_name = obj.name.lower()
        if "__sp-" not in lower_name and "__spacing-" not in lower_name:
            imported_profile["vertical_spacing"] = current_profile["vertical_spacing"]
            imported_profile["horizontal_spacing"] = current_profile["horizontal_spacing"]
        if "__pmod-" not in lower_name:
            imported_profile["polarization_model"] = current_profile["polarization_model"]
        _set_role_antenna_profile(settings, role, imported_profile)
        config = obj.sionna_device_config
        config.orientation_mode = parsed["orientation_mode"]
        fixed = parsed["fixed_orientation_deg"]
        config.fixed_alpha = math.radians(float(fixed[0]))
        config.fixed_beta = math.radians(float(fixed[1]))
        config.fixed_gamma = math.radians(float(fixed[2]))
        config.look_at_target = _find_named_target(parsed["look_at_target"])
        config.configured = True
        _sync_device_representations(context.scene)
        settings.last_status = f"Imported {role} array summary and orientation from {obj.name}"
        self.report({"INFO"}, settings.last_status)
        return {"FINISHED"}


class SIONNA_OT_ApplyDeviceName(Operator):
    bl_idname = "sionna_bridge.apply_device_name"
    bl_label = "Apply Compact Device Name"
    bl_description = "Write this device orientation and its role-wide array summary to a compact TX/RX name"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.active_object
        role = str(obj.get("sionna_role", "")).upper() if obj is not None else ""
        if obj is None or role not in {"TX", "RX"}:
            self.report({"ERROR"}, "Select a marked TX or RX object")
            return {"CANCELLED"}
        config = obj.sionna_device_config
        config.configured = True
        if config.orientation_mode == "LOOK_AT":
            if config.look_at_target is None:
                self.report({"ERROR"}, "Choose a Look At target")
                return {"CANCELLED"}
            if config.look_at_target == obj:
                self.report({"ERROR"}, "A TX or RX cannot look at itself")
                return {"CANCELLED"}
        old_name = obj.name
        new_name = _sync_device_name(obj, context.scene.sionna_bridge, role)
        _sync_device_representations(context.scene)
        context.scene.sionna_bridge.last_status = f"Updated {old_name} → {new_name}"
        self.report({"INFO"}, context.scene.sionna_bridge.last_status)
        return {"FINISHED"}


class SIONNA_OT_SyncRoleNames(Operator):
    bl_idname = "sionna_bridge.sync_role_names"
    bl_label = "Sync Role Device Names"
    bl_description = "Update all device names of this role to show the active shared array profile while preserving each orientation"
    bl_options = {"REGISTER", "UNDO"}

    role: StringProperty(default="TX")

    def execute(self, context):
        role = self.role.upper()
        if role not in {"TX", "RX"}:
            return {"CANCELLED"}
        count = _sync_role_device_names(context.scene, context.scene.sionna_bridge, role)
        _sync_device_representations(context.scene)
        context.scene.sionna_bridge.last_status = f"Synchronized {count} {role} compact device name(s)"
        self.report({"INFO"}, context.scene.sionna_bridge.last_status)
        return {"FINISHED"}


class SIONNA_OT_TestEnvironment(Operator):
    bl_idname = "sionna_bridge.test_environment"
    bl_label = "Test Sionna Runtime"

    def execute(self, context):
        settings = context.scene.sionna_bridge
        executable, error = _resolve_python_executable(settings)
        if executable is None:
            settings.last_status = error
            self.report({"ERROR"}, error)
            return {"CANCELLED"}

        # Dr.Jit/Mitsuba can occasionally return a Windows-native nonzero
        # shutdown code after all imports and output have succeeded. Force an
        # immediate clean exit after flushing the diagnostic JSON.
        probe = (
            "import json,sys,os,importlib.metadata as m;"
            "import sionna.rt;"
            "import mitsuba as mi;"
            "import numpy as np;"
            "import h5py;"
            "payload={"
            "'python':sys.version.split()[0],"
            "'python_executable':sys.executable,"
            "'numpy':np.__version__,"
            "'h5py':h5py.__version__,"
            "'sionna_rt':m.version('sionna-rt'),"
            "'mitsuba':getattr(mi,'__version__','unknown'),"
            "'variant':mi.variant(),"
            "'drjit_libllvm_path':os.environ.get('DRJIT_LIBLLVM_PATH','')"
            "};"
            "print(json.dumps(payload),flush=True);"
            "os._exit(0)"
        )
        probe_env, libllvm_path = _sionna_worker_environment(settings, executable)
        try:
            result = subprocess.run(
                [str(executable), "-c", probe],
                capture_output=True,
                text=True,
                timeout=45,
                creationflags=_subprocess_creationflags(),
                env=probe_env,
            )
        except Exception as exc:
            settings.last_status = f"Runtime test failed: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        stdout_lines = [
            line.strip() for line in result.stdout.splitlines() if line.strip()
        ]
        info = None
        for line in reversed(stdout_lines):
            try:
                candidate = json.loads(line)
                if isinstance(candidate, dict) and "sionna_rt" in candidate:
                    info = candidate
                    break
            except Exception:
                continue

        if info is not None:
            llvm_note = " | LLVM OK" if info.get("drjit_libllvm_path") else ""
            mode_label = "Blender 5.2 Python" if _runtime_mode(settings) == "BLENDER" else "External Python"
            settings.last_status = (
                f"{mode_label} {info['python']} | Sionna RT {info['sionna_rt']} | "
                f"Mitsuba {info['mitsuba']} | {info['variant']}{llvm_note}"
            )
            detected_packages = _resolve_sionna_site_packages(settings)
            settings.last_status_details = (
                "Scene exporter=Integrated Blender 5.2 XML/PLY\n"
                f"Worker Python={info.get('python_executable') or executable}\n"
                f"Worker NumPy={info.get('numpy', 'unknown')}\n"
                f"Sionna packages={detected_packages or '<interpreter native>'}\n"
                f"DRJIT_LIBLLVM_PATH={info.get('drjit_libllvm_path') or '<not set>'}"
            )
            self.report({"INFO"}, settings.last_status)
            return {"FINISHED"}

        if result.returncode != 0:
            message = (result.stderr or result.stdout or "Unknown error").strip()
            if "LLVM-C.dll" in message or "DRJIT_LIBLLVM_PATH" in message:
                if libllvm_path is None:
                    message += (
                        "\n\nDr.Jit's LLVM CPU backend could not find LLVM-C.dll. "
                        "Install a 64-bit LLVM build or select LLVM-C.dll in Sionna Runtime. "
                        "A common Windows location is C:\\Program Files\\LLVM\\bin\\LLVM-C.dll"
                    )
                else:
                    message += (
                        f"\n\nThe bridge set DRJIT_LIBLLVM_PATH={libllvm_path}, but Dr.Jit still could not load it. "
                        "Check that LLVM is 64-bit and its dependent DLLs are intact."
                    )
            settings.last_status = "Runtime test failed"
            settings.last_status_details = message[-5000:]
            self.report({"ERROR"}, message[-1000:])
            return {"CANCELLED"}

        settings.last_status = "Runtime responded without version information"
        self.report({"WARNING"}, settings.last_status)
        return {"FINISHED"}


class SIONNA_OT_ExportScene(Operator):
    bl_idname = "sionna_bridge.export_scene"
    bl_label = "Export/Refresh Scene Cache"

    def execute(self, context):
        try:
            xml_path, shape_count, _ = _export_scene_cache(context)
            self.report({"INFO"}, f"Cached {shape_count} shapes at {xml_path.parent}")
            return {"FINISHED"}
        except Exception as exc:
            context.scene.sionna_bridge.last_status = f"Export failed: {exc}"
            traceback.print_exc()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class SIONNA_OT_Run(Operator):
    bl_idname = "sionna_bridge.run"
    bl_label = "Export + Run Sionna"

    @classmethod
    def poll(cls, context):
        path_process = _RUN_STATE.get("process")
        map_process = _RADIO_MAP_STATE.get("process")
        return (
            (path_process is None or path_process.poll() is not None)
            and (map_process is None or map_process.poll() is not None)
        )

    def execute(self, context):
        settings = context.scene.sionna_bridge
        try:
            scene_xml, _, _ = _export_scene_cache(context)
            _start_sionna_process(context, scene_xml)
            self.report({"INFO"}, settings.last_status)
            return {"FINISHED"}
        except PermissionError as exc:
            _close_run_handles()
            message = (
                "Windows denied launching the Sionna worker Python. Check the selected "
                f"Sionna Runtime and package path. Original error: {exc}"
            )
            _set_status(
                settings,
                f"Run failed: {message}",
                traceback.format_exc(),
                run_dir=settings.last_status_run_dir,
                log_path=settings.last_status_log_path,
            )
            traceback.print_exc()
            self.report({"ERROR"}, message)
            return {"CANCELLED"}
        except Exception as exc:
            _close_run_handles()
            settings.last_status = f"Run failed: {exc}"
            traceback.print_exc()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class SIONNA_OT_RunCached(Operator):
    bl_idname = "sionna_bridge.run_cached"
    bl_label = "Run Sionna — Reuse Scene"

    @classmethod
    def poll(cls, context):
        path_process = _RUN_STATE.get("process")
        map_process = _RADIO_MAP_STATE.get("process")
        return (
            (path_process is None or path_process.poll() is not None)
            and (map_process is None or map_process.poll() is not None)
        )

    def execute(self, context):
        settings = context.scene.sionna_bridge
        try:
            scene_xml = _cached_scene_xml(settings)
            _start_sionna_process(context, scene_xml)
            self.report({"INFO"}, settings.last_status)
            return {"FINISHED"}
        except PermissionError as exc:
            _close_run_handles()
            message = (
                "Windows denied launching the Sionna worker Python. Check the selected "
                f"Sionna Runtime and package path. Original error: {exc}"
            )
            settings.last_status = f"Run failed: {message}"
            traceback.print_exc()
            self.report({"ERROR"}, message)
            return {"CANCELLED"}
        except Exception as exc:
            _close_run_handles()
            settings.last_status = f"Run failed: {exc}"
            traceback.print_exc()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class SIONNA_OT_GenerateRadioMap(Operator):
    bl_idname = "sionna_bridge.generate_radio_map"
    bl_label = "Export + Generate Radio Map"

    @classmethod
    def poll(cls, context):
        path_process = _RUN_STATE.get("process")
        map_process = _RADIO_MAP_STATE.get("process")
        return (
            (path_process is None or path_process.poll() is not None)
            and (map_process is None or map_process.poll() is not None)
        )

    def execute(self, context):
        settings = context.scene.sionna_bridge
        try:
            scene_xml, _, _ = _export_scene_cache(context)
            _start_radio_map_process(context, scene_xml)
            self.report({"INFO"}, settings.last_status)
            return {"FINISHED"}
        except Exception as exc:
            _close_radio_map_handles()
            settings.last_status = f"Radio-map run failed: {exc}"
            traceback.print_exc()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class SIONNA_OT_GenerateRadioMapCached(Operator):
    bl_idname = "sionna_bridge.generate_radio_map_cached"
    bl_label = "Generate Radio Map — Reuse Scene"

    @classmethod
    def poll(cls, context):
        path_process = _RUN_STATE.get("process")
        map_process = _RADIO_MAP_STATE.get("process")
        return (
            (path_process is None or path_process.poll() is not None)
            and (map_process is None or map_process.poll() is not None)
        )

    def execute(self, context):
        settings = context.scene.sionna_bridge
        try:
            scene_xml = _cached_scene_xml(settings)
            _start_radio_map_process(context, scene_xml)
            self.report({"INFO"}, settings.last_status)
            return {"FINISHED"}
        except Exception as exc:
            _close_radio_map_handles()
            settings.last_status = f"Radio-map run failed: {exc}"
            traceback.print_exc()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class SIONNA_OT_ImportRadioMap(Operator):
    bl_idname = "sionna_bridge.import_radio_map"
    bl_label = "Create Latest Radio Map Point Cloud"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.sionna_bridge
        if not settings.last_radio_map_csv:
            self.report({"ERROR"}, "No radio-map CSV is available yet")
            return {"CANCELLED"}
        try:
            obj, count = _import_radio_map_pointcloud(
                context.scene, settings.last_radio_map_csv
            )
            settings.last_status = f"Created {obj.name}: {count} radio-map points"
            self.report({"INFO"}, settings.last_status)
            return {"FINISHED"}
        except Exception as exc:
            settings.last_status = f"Radio-map import failed: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class SIONNA_OT_UpdateRadioMapGeometryNodesCSV(Operator):
    bl_idname = "sionna_bridge.update_radio_map_geometry_nodes_csv"
    bl_label = "Update Radio Map Geometry Nodes CSV"
    bl_description = (
        "Send the latest radio_map_points.csv to the Geometry Nodes group matching "
        "its Path Gain, RSS, or SINR metric"
    )

    def execute(self, context):
        settings = context.scene.sionna_bridge
        value = settings.last_radio_map_csv
        if not value:
            self.report({"ERROR"}, "No radio-map CSV is available yet")
            return {"CANCELLED"}
        try:
            status = _update_radio_map_geometry_nodes_csv_path(context.scene, value)
            frame = int(context.scene.frame_current)
            try:
                with open(value, "r", encoding="utf-8", newline="") as handle:
                    first = next(csv.DictReader(handle), None) or {}
                frame = int(float(first.get("frame", frame)))
            except Exception:
                pass
            carrier, _group = _ensure_radio_map_carrier(
                context.scene,
                csv_path=value,
                replace=False,
                frame=frame,
            )
            settings.last_status = f"{status}; carrier mesh: {carrier.name}"
            self.report({"INFO"}, status)
            return {"FINISHED"}
        except Exception as exc:
            settings.last_status = f"Radio-map Geometry Nodes update failed: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class SIONNA_OT_CopyRadioMapCSV(Operator):
    bl_idname = "sionna_bridge.copy_radio_map_csv"
    bl_label = "Copy Radio Map CSV Path"

    def execute(self, context):
        value = context.scene.sionna_bridge.last_radio_map_csv
        if not value or not Path(value).is_file():
            self.report({"ERROR"}, "No radio-map CSV is available yet")
            return {"CANCELLED"}
        context.window_manager.clipboard = str(Path(value).resolve())
        self.report({"INFO"}, "Radio-map CSV path copied")
        return {"FINISHED"}


class SIONNA_OT_ImportPaths(Operator):
    bl_idname = "sionna_bridge.import_paths"
    bl_label = "Import Latest Curves"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.sionna_bridge
        try:
            status = _import_latest_curves(context.scene, clear_existing=True)
            self.report({"INFO"}, status)
            return {"FINISHED"}
        except Exception as exc:
            settings.last_status = f"Import failed: {exc}"
            traceback.print_exc()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}



class SIONNA_OT_UpdateGeometryNodesCSV(Operator):
    bl_idname = "sionna_bridge.update_geometry_nodes_csv"
    bl_label = "Update Geometry Nodes CSV"
    bl_description = "Set the Import CSV path in the configured Geometry Nodes group to the latest paths_all_frames.csv"

    def execute(self, context):
        settings = context.scene.sionna_bridge
        value = settings.last_results_csv
        if not value:
            self.report({"ERROR"}, "No combined Geometry Nodes CSV is available yet")
            return {"CANCELLED"}
        try:
            status = _update_geometry_nodes_csv_path(context.scene, value)
            carrier, _group = _ensure_path_carrier(context.scene, csv_path=value)
            settings.last_status = f"{status}; carrier mesh: {carrier.name}"
            self.report({"INFO"}, status)
            return {"FINISHED"}
        except Exception as exc:
            settings.last_status = f"Geometry Nodes update failed: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

class SIONNA_OT_CopyCSVPath(Operator):
    bl_idname = "sionna_bridge.copy_csv_path"
    bl_label = "Copy CSV Path"

    def execute(self, context):
        value = context.scene.sionna_bridge.last_results_csv
        if not value:
            self.report({"ERROR"}, "No Geometry Nodes CSV is available yet")
            return {"CANCELLED"}
        path = Path(value)
        if not path.exists():
            self.report({"ERROR"}, f"CSV not found: {path}")
            return {"CANCELLED"}
        context.window_manager.clipboard = str(path)
        context.scene.sionna_bridge.last_status = f"Copied CSV path: {path.name}"
        self.report({"INFO"}, "Geometry Nodes CSV path copied")
        return {"FINISHED"}


class SIONNA_OT_CopyCSVPattern(Operator):
    bl_idname = "sionna_bridge.copy_csv_pattern"
    bl_label = "Copy CSV Path"

    def execute(self, context):
        value = context.scene.sionna_bridge.last_csv_pattern
        if not value:
            self.report({"ERROR"}, "All frames now share one CSV. Use Copy Combined CSV instead")
            return {"CANCELLED"}
        self.report({"ERROR"}, "All frames are exported into one combined CSV. Use Copy Combined CSV.")
        return {"CANCELLED"}


class SIONNA_OT_OpenCSVFolder(Operator):
    bl_idname = "sionna_bridge.open_csv_folder"
    bl_label = "Open CSV Folder"

    def execute(self, context):
        value = context.scene.sionna_bridge.last_results_csv
        if not value:
            self.report({"ERROR"}, "No Geometry Nodes CSV is available yet")
            return {"CANCELLED"}
        path = Path(value)
        folder = path.parent
        if not folder.exists():
            self.report({"ERROR"}, f"Directory not found: {folder}")
            return {"CANCELLED"}
        try:
            bpy.ops.wm.path_open(filepath=str(folder))
        except Exception:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", str(folder)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        return {"FINISHED"}


class SIONNA_OT_OpenWorkspace(Operator):
    bl_idname = "sionna_bridge.open_workspace"
    bl_label = "Open Workspace"

    def execute(self, context):
        path = _workspace(context.scene.sionna_bridge)
        path.mkdir(parents=True, exist_ok=True)
        try:
            bpy.ops.wm.path_open(filepath=str(path))
        except Exception:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", str(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        return {"FINISHED"}


class SIONNA_OT_OpenLastRun(Operator):
    bl_idname = "sionna_bridge.open_last_run"
    bl_label = "Open Last Run"

    def execute(self, context):
        settings = context.scene.sionna_bridge
        export_path = Path(settings.last_export_path) if settings.last_export_path else None
        value = (
            str(export_path.parent) if export_path and export_path.exists() else ""
        ) or (
            settings.last_status_run_dir or settings.last_run_dir
            or settings.last_radio_map_run_dir or settings.last_radio_map_3d_run_dir
        )
        if not value:
            self.report({"ERROR"}, "No run directory is available")
            return {"CANCELLED"}
        path = Path(value)
        if not path.exists():
            self.report({"ERROR"}, f"Directory not found: {path}")
            return {"CANCELLED"}
        try:
            bpy.ops.wm.path_open(filepath=str(path))
        except Exception:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", str(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        return {"FINISHED"}



class SIONNA_OT_CopyFullStatus(Operator):
    bl_idname = "sionna_bridge.copy_full_status"
    bl_label = "Copy Full Status"
    bl_description = "Copy the complete simulation status, traceback, and log tail"

    def execute(self, context):
        settings = context.scene.sionna_bridge
        text = settings.last_status
        if settings.last_status_details:
            text += "\n\n" + settings.last_status_details
        context.window_manager.clipboard = text
        self.report({"INFO"}, "Full simulation status copied")
        return {"FINISHED"}


class SIONNA_OT_OpenStatusLog(Operator):
    bl_idname = "sionna_bridge.open_status_log"
    bl_label = "Open Status Log"
    bl_description = "Open the latest worker log file or its containing folder"

    def execute(self, context):
        settings = context.scene.sionna_bridge
        path = Path(settings.last_status_log_path) if settings.last_status_log_path else None
        target = path if path and path.exists() else Path(settings.last_status_run_dir)
        if not target or not target.exists():
            self.report({"ERROR"}, "No status log or run folder is available")
            return {"CANCELLED"}
        try:
            bpy.ops.wm.path_open(filepath=str(target))
        except Exception:
            folder = target if target.is_dir() else target.parent
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", str(folder)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        return {"FINISHED"}


class SIONNA_OT_RunSelected(Operator):
    bl_idname = "sionna_bridge.run_selected"
    bl_label = "Run Simulation"
    bl_description = "Run enabled outputs using a static cached scene or evaluated per-frame procedural scenes"

    @classmethod
    def poll(cls, context):
        return _processes_idle()

    def execute(self, context):
        settings = context.scene.sionna_bridge
        if not (
            settings.simulate_paths or settings.simulate_radio_map
            or settings.simulate_radio_map_3d
        ):
            self.report({"ERROR"}, "Enable Propagation Paths, Radio Map, 3D Radio Map, or a combination")
            return {"CANCELLED"}

        try:
            _ensure_environment(context.scene, migrate=True)
            settings.procedural_export_report_json = ""
            settings.procedural_export_report_path = ""
            if _procedural_scene_active(context.scene):
                procedural_frames = _procedural_scene_frames(context)
                scene_source = _export_procedural_scene_frames(context, procedural_frames)
            elif settings.refresh_scene_before_run:
                scene_source, _, _ = _export_scene_cache(context)
            else:
                try:
                    scene_source = _cached_scene_xml(settings)
                except Exception:
                    scene_source, _, _ = _export_scene_cache(context)

            export_bundle = _prepare_export_bundle(settings)
            _BATCH_STATE.update({
                "active": True,
                "scene_name": context.scene.name,
                "scene_source": scene_source,
                "paths_requested": bool(settings.simulate_paths),
                "radio_map_requested": bool(settings.simulate_radio_map),
                "radio_map_3d_requested": bool(settings.simulate_radio_map_3d),
                "pending_radio_map": bool(settings.simulate_paths and settings.simulate_radio_map),
                "pending_radio_map_3d": bool(
                    settings.simulate_radio_map_3d
                    and (settings.simulate_paths or settings.simulate_radio_map)
                ),
                "path_status": "",
                "radio_map_status": "",
                "auto_triggered": False,
                "force_current_frame": False,
                "auto_anchor_tx_name": "",
                "export_bundle": export_bundle,
            })

            if settings.simulate_paths:
                _start_sionna_process(context, scene_source)
                queued = []
                if settings.simulate_radio_map:
                    queued.append("2D radio map")
                if settings.simulate_radio_map_3d:
                    queued.append("3D radio map")
                if queued:
                    settings.last_status = "Running propagation paths; queued next: " + ", ".join(queued)
            elif settings.simulate_radio_map:
                _start_radio_map_process(context, scene_source)
                if settings.simulate_radio_map_3d:
                    settings.last_status = "Running 2D radio map; 3D radio map is queued next"
            else:
                _start_radio_map_3d_process(context, scene_source)

            self.report({"INFO"}, settings.last_status)
            return {"FINISHED"}
        except PermissionError as exc:
            _close_run_handles()
            _close_radio_map_handles()
            _close_radio_map_3d_handles()
            _reset_batch_state()
            message = (
                "Windows denied launching the Sionna worker Python. Check the selected "
                f"Sionna Runtime and package path. Original error: {exc}"
            )
            settings.last_status = f"Run failed: {message}"
            traceback.print_exc()
            self.report({"ERROR"}, message)
            return {"CANCELLED"}
        except Exception as exc:
            _close_run_handles()
            _close_radio_map_handles()
            _close_radio_map_3d_handles()
            _reset_batch_state()
            _set_status(
                settings,
                f"Run failed: {exc}",
                traceback.format_exc(),
                run_dir=settings.last_status_run_dir,
                log_path=settings.last_status_log_path,
            )
            traceback.print_exc()
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}



def _draw_wrapped_text(layout, text, *, width=92, icon="NONE"):
    text = str(text or "").strip()
    if not text:
        return
    first = True
    for paragraph in text.splitlines() or [text]:
        if not paragraph.strip():
            layout.separator(factor=0.35)
            continue
        lines = textwrap.wrap(
            paragraph,
            width=max(36, int(width)),
            break_long_words=True,
            break_on_hyphens=False,
            replace_whitespace=False,
        ) or [""]
        for line in lines:
            layout.label(text=line, icon=icon if first and icon != "NONE" else "NONE")
            first = False


def _draw_collapsible_header(box, settings, property_name, label, icon=None):
    expanded = bool(getattr(settings, property_name))
    row = box.row(align=True)
    row.prop(
        settings, property_name, text=label,
        icon="TRIA_DOWN" if expanded else "TRIA_RIGHT", emboss=False,
    )
    return expanded


class SIONNA_OT_RefreshAnalytics(Operator):
    bl_idname = "sionna_bridge.refresh_analytics"
    bl_label = "Refresh Analytics"
    bl_description = "Calculate statistics from the selected or latest embedded Sionna result"

    def execute(self, context):
        try:
            summary = _refresh_analytics_cache(context.scene)
            context.scene.sionna_bridge.last_status = (
                f"Analytics refreshed from {summary.get('object', 'result')}"
            )
            self.report({"INFO"}, "Sionna analytics refreshed")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class SIONNA_OT_OpenAnalyticsDashboard(Operator):
    bl_idname = "sionna_bridge.open_analytics_dashboard"
    bl_label = "Open Analytics Plots"
    bl_description = "Generate and open a local HTML dashboard with Sionna plots"

    def execute(self, context):
        try:
            path, summary = _write_analytics_dashboard(context.scene)
            _refresh_analytics_cache(context.scene)
            url = path.resolve().as_uri()
            try:
                bpy.ops.wm.url_open(url=url)
            except Exception:
                webbrowser.open(url)
            context.scene.sionna_bridge.last_status = (
                f"Opened analytics plots for {summary.get('object', 'result')}"
            )
            self.report({"INFO"}, "Analytics dashboard opened")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class SIONNA_PT_MainPanel(Panel):
    bl_label = "SionnaRT-Bridge"
    bl_idname = "SIONNA_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Sionna RT"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.sionna_bridge

        # Sionna runtime and workspace
        box = layout.box()
        if _draw_collapsible_header(
            box, settings, "ui_show_environment", "Sionna Runtime", "CONSOLE"
        ):
            box.prop(settings, "runtime_mode", text="Runtime")
            if _runtime_mode(settings) == "BLENDER":
                box.label(text="Blender 5.2 Python; no external interpreter required", icon="CHECKMARK")
                box.prop(settings, "sionna_site_packages")
                detected_packages = _resolve_sionna_site_packages(settings)
                if detected_packages is not None:
                    box.label(text=f"Sionna packages: {detected_packages}", icon="CHECKMARK")
                else:
                    box.label(text="Sionna packages not detected", icon="ERROR")
            else:
                box.prop(settings, "sionna_python")

            box.label(text="Scene Export: Integrated Blender 5.2 Mitsuba XML/PLY", icon="CHECKMARK")
            box.prop(settings, "drjit_libllvm_path")
            resolved_python, python_error = _resolve_python_executable(settings)
            if resolved_python is not None:
                box.label(text=f"Worker Python: {resolved_python}", icon="CHECKMARK")
            else:
                box.label(text=python_error, icon="ERROR")
            detected_llvm = _resolve_drjit_libllvm(settings, resolved_python) if resolved_python else _resolve_drjit_libllvm(settings)
            if detected_llvm is not None:
                box.label(text=f"Dr.Jit LLVM: {detected_llvm}", icon="CHECKMARK")
            elif os.name == "nt":
                box.label(text="LLVM-C.dll not detected (only needed if CUDA is unavailable)", icon="INFO")
            box.prop(settings, "workspace_dir")
            row = box.row(align=True)
            row.operator("sionna_bridge.test_environment", text="Test Runtime")
            row.operator("sionna_bridge.open_workspace", text="Open Workspace")

        # Workflow
        box = layout.box()
        if _draw_collapsible_header(
            box, settings, "ui_show_workflow", "Workflow", "OUTLINER_COLLECTION"
        ):
            row = box.row(align=True)
            row.operator("sionna_bridge.create_environment", text="Create / Repair Env")
            row.operator("sionna_bridge.move_selected_to_scene", text="Move to Static Scene")
            box.operator(
                "sionna_bridge.move_selected_to_procedural",
                text="Move to Procedural Geometry",
                icon="GEOMETRY_NODES",
            )

        # Shared solver settings
        box = layout.box()
        if _draw_collapsible_header(
            box, settings, "ui_show_simulation", "Simulation Settings", "SETTINGS"
        ):
            box.prop(settings, "frequency_ghz")
            noise = box.box()
            noise.label(text="Power and Noise", icon="LIGHT")
            row = noise.row(align=True)
            row.prop(settings, "bandwidth_mhz", text="Bandwidth (MHz)")
            row.prop(settings, "temperature_k", text="Temperature (K)")
            arrays = box.box()
            arrays.label(text="Antenna Arrays — shared by role", icon="OUTLINER_OB_LIGHT")
            tx_box = arrays.box()
            tx_box.label(text="Transmitters (TX)")
            tx_box.prop(settings, "tx_antenna_pattern", text="Pattern")
            row = tx_box.row(align=True)
            row.prop(settings, "tx_array_rows", text="Rows")
            row.prop(settings, "tx_array_cols", text="Columns")
            row = tx_box.row(align=True)
            row.prop(settings, "tx_vertical_spacing", text="Vertical λ")
            row.prop(settings, "tx_horizontal_spacing", text="Horizontal λ")
            row = tx_box.row(align=True)
            row.prop(settings, "tx_polarization", text="Polarization")
            row.prop(settings, "tx_polarization_model", text="Model")
            op = tx_box.operator("sionna_bridge.sync_role_names", text="Sync TX Names")
            op.role = "TX"

            rx_box = arrays.box()
            rx_box.label(text="Receivers (RX)")
            rx_box.prop(settings, "rx_antenna_pattern", text="Pattern")
            row = rx_box.row(align=True)
            row.prop(settings, "rx_array_rows", text="Rows")
            row.prop(settings, "rx_array_cols", text="Columns")
            row = rx_box.row(align=True)
            row.prop(settings, "rx_vertical_spacing", text="Vertical λ")
            row.prop(settings, "rx_horizontal_spacing", text="Horizontal λ")
            row = rx_box.row(align=True)
            row.prop(settings, "rx_polarization", text="Polarization")
            row.prop(settings, "rx_polarization_model", text="Model")
            op = rx_box.operator("sionna_bridge.sync_role_names", text="Sync RX Names")
            op.role = "RX"

            row = box.row(align=True)
            row.prop(settings, "max_depth")
            row.prop(settings, "seed")
            box.prop(settings, "samples_per_src")
            box.prop(settings, "max_num_paths_per_src")
            box.prop(settings, "sim_numeric_id")
            box.prop(settings, "timeline_mode")
            if settings.timeline_mode != "CURRENT":
                box.prop(settings, "timeline_step")
            box.prop(settings, "enable_mobility_doppler")
            grid = box.grid_flow(row_major=True, columns=2, even_columns=True)
            grid.prop(settings, "enable_los")
            grid.prop(settings, "enable_reflection")
            grid.prop(settings, "enable_refraction")
            grid.prop(settings, "enable_diffuse")
            grid.prop(settings, "enable_diffraction")
            grid.prop(settings, "enable_edge_diffraction")
            grid.prop(settings, "diffraction_lit_region")

        # Radio materials
        box = layout.box()
        if _draw_collapsible_header(
            box, settings, "ui_show_materials", "Radio Materials", "MATERIAL"
        ):
            row = box.row(align=True)
            row.operator(
                "sionna_bridge.create_default_materials",
                text="Create Default Materials",
                icon="ADD",
            )
            row.operator(
                "sionna_bridge.pick_active_material",
                text="Use Active",
                icon="EYEDROPPER",
            )
            box.prop(settings, "material_selection", text="Material")
            material = settings.material_selection
            if material is not None:
                config = material.sionna_radio
                row = box.row(align=True)
                row.operator(
                    "sionna_bridge.enable_material",
                    text="Enable / Prefix itu_",
                    icon="CHECKMARK",
                )
                row.operator(
                    "sionna_bridge.assign_material",
                    text="Assign to Selected",
                    icon="MATERIAL",
                )
                if not material.name.lower().startswith("itu_"):
                    box.label(text="Material name must start with itu_ for export.", icon="ERROR")
                if config.enabled or material.name.lower().startswith("itu_"):
                    box.prop(config, "model")
                    if config.model == "ITU":
                        box.prop(config, "itu_type")
                    else:
                        row = box.row(align=True)
                        row.prop(config, "relative_permittivity")
                        row.prop(config, "conductivity")
                    box.prop(config, "thickness")
                    row = box.row(align=True)
                    row.prop(config, "scattering_coefficient")
                    row.prop(config, "xpd_coefficient")
                    box.prop(config, "scattering_pattern")
                    if config.scattering_pattern == "directive":
                        box.prop(config, "directive_alpha_r")
                    elif config.scattering_pattern == "backscattering":
                        row = box.row(align=True)
                        row.prop(config, "backscatter_alpha_r")
                        row.prop(config, "backscatter_alpha_i")
                        box.prop(config, "backscatter_lambda")

        # Procedural geometry
        box = layout.box()
        if _draw_collapsible_header(
            box, settings, "ui_show_procedural", "Procedural Geometry", "GEOMETRY_NODES"
        ):
            box.prop(settings, "procedural_geometry_enabled")
            if settings.procedural_geometry_enabled:
                box.prop(settings, "procedural_capture_analytics")
                box.prop(settings, "procedural_skip_failed_frames")
            box.operator(
                "sionna_bridge.move_selected_to_procedural",
                text="Move Selected to Procedural Geometry",
            )

        # Devices
        box = layout.box()
        tx_count = len(_device_objects(context.scene, "TX"))
        rx_count = len(_device_objects(context.scene, "RX"))
        if _draw_collapsible_header(
            box, settings, "ui_show_devices",
            f"Devices — {tx_count} TX / {rx_count} RX", "EMPTY_AXIS"
        ):
            row = box.row(align=True)
            op = row.operator("sionna_bridge.add_device", text="Add TX", icon="ADD")
            op.role = "TX"
            op = row.operator("sionna_bridge.add_device", text="Add RX", icon="ADD")
            op.role = "RX"
            row = box.row(align=True)
            op = row.operator("sionna_bridge.mark_selected", text="Mark TX")
            op.role = "TX"
            op = row.operator("sionna_bridge.mark_selected", text="Mark RX")
            op.role = "RX"
            row.operator("sionna_bridge.clear_role", text="Clear", icon="X")

            active = context.active_object
            active_role = str(active.get("sionna_role", "")).upper() if active is not None else ""
            sub = box.box()
            expanded_antenna = bool(settings.ui_show_device_antenna)
            sub.prop(
                settings, "ui_show_device_antenna", text="Per-device Orientation",
                icon="TRIA_DOWN" if expanded_antenna else "TRIA_RIGHT", emboss=False,
            )
            if expanded_antenna:
                if active is None or active_role not in {"TX", "RX"}:
                    sub.label(text="Select a marked TX or RX", icon="INFO")
                else:
                    config = active.sionna_device_config
                    if active_role == "TX":
                        sub.prop(config, "tx_power_dbm", text="Transmit Power (dBm)")
                    sub.prop(config, "orientation_mode")
                    if config.orientation_mode == "LOOK_AT":
                        sub.prop(config, "look_at_target")
                        if config.look_at_target == active:
                            sub.label(text="A device cannot look at itself", icon="ERROR")
                    elif config.orientation_mode == "FIXED":
                        row = sub.row(align=True)
                        row.prop(config, "fixed_alpha")
                        row.prop(config, "fixed_beta")
                        row.prop(config, "fixed_gamma")
                    row = sub.row(align=True)
                    row.operator("sionna_bridge.read_device_name", text="Read Name", icon="IMPORT")
                    row.operator("sionna_bridge.apply_device_name", text="Apply Compact Name", icon="CHECKMARK")

            # Reusable TX/RX motion templates
            motion_box = box.box()
            motion_box.prop(
                settings, "motion_template_enabled",
                text="TX / RX Motion Path", icon="ANIM",
            )
            if settings.motion_template_enabled:
                motion_box.prop(settings, "motion_template_style", text="Style")
                motion_box.prop(settings, "motion_template_device", text="Associated TX / RX")
                if settings.motion_template_style == "GRID":
                    row = motion_box.row(align=True)
                    row.prop(settings, "motion_template_grid_columns", text="Columns")
                    row.prop(settings, "motion_template_grid_rows", text="Rows")
                    row = motion_box.row(align=True)
                    row.prop(settings, "motion_template_grid_column_spacing", text="Column Spacing")
                    row.prop(settings, "motion_template_grid_row_spacing", text="Row Spacing")
                    motion_box.prop(settings, "motion_template_start_frame", text="Start Frame")
                    motion_box.prop(settings, "motion_template_set_scene_range", text="Set Scene Range to Path")
                    count = (
                        int(settings.motion_template_grid_columns)
                        * int(settings.motion_template_grid_rows)
                    )
                    end_frame = int(settings.motion_template_start_frame) + max(0, count - 1)
                    motion_box.label(
                        text=f"{count} points = frames {int(settings.motion_template_start_frame)}-{end_frame}; serpentine order.",
                        icon="INFO",
                    )
                    motion_box.label(
                        text="Use Timeline Auto/Range to compute the complete grid sweep.",
                        icon="INFO",
                    )
                elif settings.motion_template_style == "POINT_CLOUD":
                    motion_box.prop(settings, "motion_template_pointcloud", text="PointCloud Path")
                    motion_box.prop(settings, "motion_template_start_frame", text="Start Frame")
                    motion_box.prop(settings, "motion_template_set_scene_range", text="Set Scene Range to Path")
                    source = settings.motion_template_pointcloud
                    count = len(source.data.points) if source is not None and source.data is not None else 0
                    end_frame = int(settings.motion_template_start_frame) + max(0, count - 1)
                    if source is None:
                        motion_box.label(text="Choose a PointCloud with the eyedropper.", icon="EYEDROPPER")
                    elif count < 1:
                        motion_box.label(text=f"{source.name} contains no points.", icon="ERROR")
                    else:
                        motion_box.label(
                            text=f"{count} points = frames {int(settings.motion_template_start_frame)}-{end_frame}.",
                            icon="INFO",
                        )
                        motion_box.label(
                            text="Mapping: point index i → frame Start+i (one frame per point).",
                            icon="INFO",
                        )

                template_device = settings.motion_template_device
                existing_template = (
                    _sweep_template_object(template_device)
                    if template_device is not None else None
                )
                row = motion_box.row(align=True)
                source_ready = (
                    settings.motion_template_style != "POINT_CLOUD"
                    or settings.motion_template_pointcloud is not None
                )
                row.enabled = template_device is not None and source_ready
                is_pc = settings.motion_template_style == "POINT_CLOUD"
                row.operator(
                    "sionna_bridge.generate_motion_template",
                    text=(
                        "Update PointCloud Path" if existing_template is not None and is_pc
                        else "Connect PointCloud Path" if is_pc
                        else "Update Grid" if existing_template is not None
                        else "Generate Grid"
                    ),
                    icon="ANIM",
                )
                if existing_template is not None:
                    row = motion_box.row(align=True)
                    row.operator(
                        "sionna_bridge.select_motion_template",
                        text="Select Source" if is_pc else "Select Grid",
                        icon="POINTCLOUD_DATA" if is_pc else "EMPTY_AXIS",
                    )
                    row.operator(
                        "sionna_bridge.remove_motion_template",
                        text="Disconnect", icon="X",
                    )
                    if is_pc:
                        source_obj = _sweep_source_object(template_device)
                        source_name = source_obj.name if source_obj is not None else "missing source"
                        motion_box.label(
                            text=f"Live index follow: {source_name}; point index follows the current frame.",
                            icon="INFO",
                        )
                        if source_obj is not None:
                            try:
                                start = int(template_device.get("sionna_sweep_start_frame", 1))
                                raw_index = int(context.scene.frame_current) - start
                                count_now = len(source_obj.data.points)
                                index_now = max(0, min(raw_index, max(0, count_now - 1)))
                                expected = source_obj.matrix_world @ source_obj.data.points[index_now].co
                                actual = template_device.matrix_world.translation
                                error_m = float((actual - expected).length)
                                motion_box.label(
                                    text=(
                                        f"Frame {context.scene.frame_current} → point {index_now}; "
                                        f"alignment error {error_m:.6g} m"
                                    ),
                                    icon="CHECKMARK" if error_m <= 1e-5 else "ERROR",
                                )
                            except Exception:
                                pass
                    else:
                        motion_box.label(
                            text=f"Connected: {existing_template.name}. Move/rotate/scale the grid to reposition the sweep.",
                            icon="INFO",
                        )
                elif template_device is None:
                    motion_box.label(text="Choose a marked TX or RX to create the sweep.", icon="INFO")
                elif is_pc and settings.motion_template_pointcloud is None:
                    motion_box.label(text="Choose the PointCloud path before connecting.", icon="INFO")
                elif not is_pc:
                    motion_box.label(
                        text="The grid is centered on the device when generated and stays fully movable.",
                        icon="INFO",
                    )

        # Simulation and scene cache
        box = layout.box()
        if _draw_collapsible_header(
            box, settings, "ui_show_scene_cache", "Simulation", "PLAY"
        ):
            dynamic_box = box.box()
            dynamic_box.prop(
                settings, "dynamic_mode", text="Dynamic Mode", icon="FILE_REFRESH"
            )
            if settings.dynamic_mode:
                dynamic_box.label(
                    text="TX/RX movement watcher active", icon="CHECKMARK"
                )
                dynamic_box.prop(settings, "auto_compute_paths_delay", text="Move Debounce")
            else:
                dynamic_box.label(
                    text="Off: no movement-driven Sionna background watcher", icon="INFO"
                )
            box.prop(settings, "refresh_scene_before_run")
            box.prop(settings, "export_format", text="Export Results")
            if settings.export_format == "NONE":
                box.label(text="Results stay in Blender; temporary worker files are removed.", icon="INFO")
            elif settings.export_format == "CSV":
                box.label(text="Keeps one simulation-specific CSV + metadata JSON.", icon="INFO")
            else:
                box.label(text="Keeps one HDF5 with frame-stacked coverage + metadata JSON.", icon="INFO")
                tile_dataset = _find_tile_spatial_dataset()
                if tile_dataset is not None:
                    box.label(
                        text=f"Tile_spacial_dataset detected: {len(tile_dataset.data.points)} tiles will be linked",
                        icon="LINKED",
                    )
                else:
                    box.label(
                        text="No Tile_spacial_dataset detected; HDF5 coverage exports remain standalone",
                        icon="INFO",
                    )
            selected = []
            if settings.simulate_paths:
                selected.append("Paths")
            if settings.simulate_radio_map:
                selected.append("Radio Map")
            if settings.simulate_radio_map_3d:
                selected.append("3D Radio Map")
            row = box.row()
            row.scale_y = 1.5
            row.enabled = _processes_idle() and bool(selected)
            row.operator("sionna_bridge.run_selected", text="Run Simulation", icon="PLAY")
            row = box.row(align=True)
            row.operator("sionna_bridge.export_scene", text="Refresh Scene Cache")
            row.operator("sionna_bridge.open_last_run", text="Open Last Run")

        # Path output toggle and options
        box = layout.box()
        header = box.row(align=True)
        header.prop(settings, "simulate_paths", text="")
        expanded = bool(settings.ui_show_paths)
        header.prop(
            settings, "ui_show_paths", text="Propagation Paths",
            icon="TRIA_DOWN" if expanded else "TRIA_RIGHT", emboss=False,
        )
        if settings.simulate_paths and expanded:
            live_box = box.box()
            live_box.enabled = bool(settings.dynamic_mode)
            live_box.prop(
                settings, "auto_compute_paths_on_tx_move",
                text="Auto Compute on TX / RX Move", icon="FILE_REFRESH",
            )
            if not settings.dynamic_mode:
                live_box.label(text="Enable Dynamic Mode in Simulation for live updates.", icon="INFO")
            elif settings.auto_compute_paths_on_tx_move:
                if tx_count == 0:
                    live_box.label(text="Add at least one TX to enable automatic runs.", icon="ERROR")
                elif rx_count == 0:
                    live_box.label(text="Add at least one RX to enable automatic runs.", icon="ERROR")
                else:
                    live_box.label(
                        text="Current frame only; newest TX/RX position wins while busy.",
                        icon="INFO",
                    )
            box.prop(settings, "pointcloud_top_paths_per_pair")
            box.prop(settings, "post_run_action")
            if settings.post_run_action == "CURVES":
                box.prop(settings, "max_imported_paths")
                box.prop(settings, "path_thickness")
            box.prop(settings, "geometry_nodes_group_name")
            if settings.export_format == "CSV":
                row = box.row(align=True)
                row.operator("sionna_bridge.copy_csv_path", text="Copy Exported CSV")

        # Radio-map output toggle and options
        box = layout.box()
        header = box.row(align=True)
        header.prop(settings, "simulate_radio_map", text="")
        expanded = bool(settings.ui_show_radio_map)
        header.prop(
            settings, "ui_show_radio_map", text="Radio Maps",
            icon="TRIA_DOWN" if expanded else "TRIA_RIGHT", emboss=False,
        )
        if settings.simulate_radio_map and expanded:
            live_box = box.box()
            live_box.enabled = bool(settings.dynamic_mode)
            live_box.prop(
                settings, "auto_compute_radio_map_on_device_move",
                text="Auto Compute on TX Move", icon="FILE_REFRESH",
            )
            if not settings.dynamic_mode:
                live_box.label(text="Enable Dynamic Mode in Simulation for live updates.", icon="INFO")
            elif settings.auto_compute_radio_map_on_device_move:
                live_box.prop(
                    settings, "radio_map_auto_center_on_tx",
                    text="Center Map on Moving TX", icon="PIVOT_BOUNDBOX",
                )
                if tx_count == 0:
                    live_box.label(text="Add at least one TX to enable automatic coverage.", icon="ERROR")
                elif _normalize_radio_map_surface_mode(settings.radio_map_surface_mode) == "PROJECTED":
                    live_box.label(
                        text="TX centering applies to Planar Grid only; Projected Mesh uses its mesh surface.",
                        icon="INFO",
                    )
                elif settings.radio_map_auto_center_on_tx:
                    live_box.label(
                        text="Auto runs follow moved TX in X/Y; coverage Height stays unchanged.",
                        icon="INFO",
                    )
                else:
                    live_box.label(
                        text="Current frame only; RX movement does not affect coverage maps.",
                        icon="INFO",
                    )
            box.prop(settings, "radio_map_surface_mode", text="Map Surface")
            box.prop(settings, "radio_map_metric", text="Map Metric")
            surface_mode = _normalize_radio_map_surface_mode(
                settings.radio_map_surface_mode
            )
            if surface_mode == "PROJECTED":
                box.prop(settings, "radio_map_reference_mesh", text="Reference Mesh")
                if settings.radio_map_reference_mesh is None:
                    box.label(text="Select the mesh that will receive the radio map.", icon="ERROR")
                if settings.radio_map_metric != "path_gain":
                    box.label(
                        text="Projected Mesh currently supports Path Gain only.",
                        icon="ERROR",
                    )
            else:
                row = box.row(align=True)
                row.prop(settings, "radio_map_center_x")
                row.prop(settings, "radio_map_center_y")
                box.prop(settings, "radio_map_height")
                row = box.row(align=True)
                row.prop(settings, "radio_map_size_x")
                row.prop(settings, "radio_map_size_y")
                row = box.row(align=True)
                row.prop(settings, "radio_map_cell_size_x")
                row.prop(settings, "radio_map_cell_size_y")
            box.prop(settings, "radio_map_point_radius")
            box.prop(settings, "radio_map_replace_existing")
            if settings.export_format == "CSV":
                row = box.row(align=True)
                row.operator("sionna_bridge.copy_radio_map_csv", text="Copy Exported CSV")

        # 3D radio-map output toggle and options
        box = layout.box()
        header = box.row(align=True)
        header.prop(settings, "simulate_radio_map_3d", text="")
        expanded = bool(settings.ui_show_radio_map_3d)
        header.prop(
            settings, "ui_show_radio_map_3d", text="3D Radio Maps",
            icon="TRIA_DOWN" if expanded else "TRIA_RIGHT", emboss=False,
        )
        if settings.simulate_radio_map_3d and expanded:
            live_box = box.box()
            live_box.enabled = bool(settings.dynamic_mode)
            live_box.prop(
                settings, "auto_compute_radio_map_3d_on_device_move",
                text="Auto Compute on TX Move", icon="FILE_REFRESH",
            )
            if not settings.dynamic_mode:
                live_box.label(text="Enable Dynamic Mode in Simulation for live updates.", icon="INFO")
            elif settings.auto_compute_radio_map_3d_on_device_move:
                live_box.prop(
                    settings, "radio_map_3d_auto_center_on_tx",
                    text="Center Volume on Moving TX", icon="PIVOT_BOUNDBOX",
                )
                if tx_count == 0:
                    live_box.label(text="Add at least one TX to enable automatic 3D coverage.", icon="ERROR")
                elif settings.radio_map_3d_auto_center_on_tx:
                    live_box.label(
                        text="Auto runs follow the moved TX in X/Y/Z; volume size stays unchanged.",
                        icon="INFO",
                    )
                else:
                    live_box.label(
                        text="Current frame only; RX movement does not affect coverage maps.",
                        icon="INFO",
                    )
            box.prop(settings, "radio_map_3d_metric", text="Map Metric")
            row = box.row(align=True)
            row.prop(settings, "radio_map_3d_center_x")
            row.prop(settings, "radio_map_3d_center_y")
            box.prop(settings, "radio_map_3d_center_z")
            row = box.row(align=True)
            row.prop(settings, "radio_map_3d_size_x")
            row.prop(settings, "radio_map_3d_size_y")
            box.prop(settings, "radio_map_3d_size_z")
            row = box.row(align=True)
            row.prop(settings, "radio_map_3d_cell_size_x")
            row.prop(settings, "radio_map_3d_cell_size_y")
            box.prop(settings, "radio_map_3d_cell_size_z")
            box.prop(settings, "radio_map_3d_point_radius")
            box.prop(settings, "radio_map_3d_replace_existing")

        # Status
        box = layout.box()
        if _draw_collapsible_header(
            box, settings, "ui_show_status", "Status", "INFO"
        ):
            width = max(52, int(getattr(context.region, "width", 700) / 7.2))
            _draw_wrapped_text(box, settings.last_status, width=width, icon="INFO")
            if settings.last_status_details:
                detail_box = box.box()
                detail_box.label(text="Full details", icon="TEXT")
                _draw_wrapped_text(detail_box, settings.last_status_details, width=width)
            row = box.row(align=True)
            row.operator("sionna_bridge.copy_full_status", text="Copy Full Status", icon="COPY_ID")
            row.operator("sionna_bridge.open_status_log", text="Open Log / Run Folder", icon="FILE_FOLDER")
            try:
                export_report = (
                    json.loads(settings.procedural_export_report_json)
                    if settings.procedural_export_report_json else {}
                )
            except Exception:
                export_report = {}
            failed_exports = export_report.get("failed_frames", []) if isinstance(export_report, dict) else []
            if failed_exports:
                sub = box.box()
                sub.label(
                    text=(
                        f"Procedural export: {len(export_report.get('exported_frames', []))} succeeded, "
                        f"{len(failed_exports)} skipped"
                    ),
                    icon="ERROR",
                )
                for item in failed_exports[:20]:
                    reason = str(item.get("reason", "Unknown export error")).replace("\n", " ")
                    if len(reason) > 105:
                        reason = reason[:102] + "..."
                    sub.label(text=f"F{int(item.get('frame', 0)):04d}: {reason}")
                if len(failed_exports) > 20:
                    sub.label(text=f"...and {len(failed_exports) - 20} more failed frame(s)")
                if settings.procedural_export_report_path:
                    sub.label(text=f"Report: {Path(settings.procedural_export_report_path).name}")
            if settings.last_paths_object:
                box.label(text=f"Paths object: {settings.last_paths_object}", icon="POINTCLOUD_DATA")
            if settings.last_radio_map_object:
                box.label(text=f"Radio map object: {settings.last_radio_map_object}", icon="POINTCLOUD_DATA")
            if settings.last_radio_map_3d_object:
                box.label(text=f"3D radio map: {settings.last_radio_map_3d_object}", icon="VOLUME_DATA")
            if settings.last_export_path:
                export_label = "HDF5" if str(settings.last_export_path).lower().endswith((".h5", ".hdf5")) else "CSV"
                box.label(text=f"Last {export_label} export: {Path(settings.last_export_path).name}", icon="FILE")
            if settings.last_export_metadata_path:
                box.label(text=f"Metadata: {Path(settings.last_export_metadata_path).name}", icon="TEXT")

        # Analytics
        box = layout.box()
        if _draw_collapsible_header(
            box, settings, "ui_show_analytics", "Analytics", "GRAPH"
        ):
            row = box.row(align=True)
            row.prop(settings, "analytics_source", text="")
            row.prop(settings, "analytics_scope", text="")
            box.prop(settings, "analytics_auto_refresh")
            if settings.analytics_source == "PATHS":
                controls = box.box()
                controls.label(text="Channel analysis")
                row = controls.row(align=True)
                row.prop(settings, "analytics_pair_index")
                row.prop(settings, "analytics_delay_reference", text="")
                row = controls.row(align=True)
                row.prop(settings, "analytics_significant_path_threshold_db")
                row.prop(settings, "analytics_pdp_bins")
                controls.prop(settings, "analytics_cir_component_limit")
                controls.label(
                    text="CIR component and PDP limits apply to the next simulation.",
                    icon="INFO",
                )
            else:
                box.prop(settings, "analytics_map_threshold")
            if settings.analytics_scope == "ALL":
                box.prop(settings, "analytics_geometry_metric")
            row = box.row(align=True)
            row.operator("sionna_bridge.refresh_analytics", text="Refresh", icon="FILE_REFRESH")
            row.operator(
                "sionna_bridge.open_analytics_dashboard",
                text="Open Plots", icon="GRAPH",
            )
            try:
                analytics = json.loads(settings.analytics_json) if settings.analytics_json else {}
            except Exception:
                analytics = {}
            if not analytics:
                box.label(text="Run a simulation or press Refresh.", icon="INFO")
            elif analytics.get("source") == "PATHS":
                box.label(text=f"Source: {analytics.get('object', '—')}", icon="POINTCLOUD_DATA")
                row = box.row(align=True)
                row.label(text=f"Paths: {int(analytics.get('path_count', 0)):,}")
                row.label(text=f"Links: {int(analytics.get('link_count', 0)):,}")
                row.label(text=f"Frames: {int(analytics.get('frame_count', 0)):,}")
                gain = analytics.get("gain_db", {})
                distance = analytics.get("distance_m", {})
                channel_power = analytics.get("channel_total_power_db", {})
                rms_delay = analytics.get("rms_delay_spread_ns", {})
                first_arrival = analytics.get("first_arrival_ns", {})
                dominant = analytics.get("dominant_to_rest_db", {})
                row = box.row(align=True)
                row.label(text=f"Channel power: {float(channel_power.get('mean', 0.0)):.2f} dB")
                row.label(text=f"RMS delay: {float(rms_delay.get('mean', 0.0)):.3g} ns")
                row = box.row(align=True)
                row.label(text=f"First arrival: {float(first_arrival.get('mean', 0.0)):.3g} ns")
                row.label(text=f"LoS links: {float(analytics.get('los_link_percent', 0.0)):.1f}%")
                row = box.row(align=True)
                row.label(text=f"Dominant/rest: {float(dominant.get('mean', 0.0)):.2f} dB")
                row.label(text=f"Best path: {float(gain.get('max', 0.0)):.2f} dB")
                row = box.row(align=True)
                row.label(text=f"TX/RX mean: {float(distance.get('mean', 0.0)):.3g} m")
                row.label(text=f"Links analyzed: {int(analytics.get('channel_link_count', 0)):,}")
                if analytics.get("mobility_available"):
                    doppler_abs = analytics.get("doppler_abs_hz", {})
                    doppler_spread = analytics.get("rms_doppler_spread_hz", {})
                    tx_speed = analytics.get("tx_speed_m_s", {})
                    rx_speed = analytics.get("rx_speed_m_s", {})
                    row = box.row(align=True)
                    row.label(text=f"Max |Doppler|: {float(doppler_abs.get('max', 0.0)):.3g} Hz")
                    row.label(text=f"RMS Doppler: {float(doppler_spread.get('mean', 0.0)):.3g} Hz")
                    row = box.row(align=True)
                    row.label(text=f"TX speed: {float(tx_speed.get('mean', 0.0)):.3g} m/s")
                    row.label(text=f"RX speed: {float(rx_speed.get('mean', 0.0)):.3g} m/s")
                selected_channel = analytics.get("selected_channel") or {}
                if selected_channel:
                    sub = box.box()
                    sub.label(text=(
                        f"CIR/PDP selection: F{int(selected_channel.get('frame', 0))} · "
                        f"Pair {int(selected_channel.get('pos_idx', 0))}"
                    ))
                    row = sub.row(align=True)
                    row.label(text=f"Paths: {int(selected_channel.get('path_count', 0)):,}")
                    row.label(text=f"RMS: {float(selected_channel.get('rms_delay_spread_ns', 0.0) or 0.0):.3g} ns")
                    row = sub.row(align=True)
                    row.label(text=f"Power: {float(selected_channel.get('total_power_db', -600.0)):.2f} dB")
                    row.label(text=f"LoS: {'Yes' if selected_channel.get('los_available') else 'No'}")
                    if analytics.get("mobility_available"):
                        row = sub.row(align=True)
                        row.label(text=f"Mean Doppler: {float(selected_channel.get('doppler_mean_hz', 0.0)):.3g} Hz")
                        row.label(text=f"RMS spread: {float(selected_channel.get('rms_doppler_spread_hz', 0.0)):.3g} Hz")
                types = analytics.get("path_types", {})
                if types:
                    sub = box.box()
                    sub.label(text="Path types")
                    total = max(1, int(analytics.get("path_count", 0)))
                    for name, value in sorted(types.items(), key=lambda item: (-item[1], item[0])):
                        row = sub.row(align=True)
                        row.label(text=name)
                        row.label(text=f"{int(value):,}  ({100.0*int(value)/total:.1f}%)")
                top_paths = analytics.get("top_paths", [])[: int(settings.analytics_top_rows)]
                if top_paths:
                    box.prop(settings, "analytics_top_rows")
                    sub = box.box()
                    sub.label(text="Strongest paths")
                    for item in top_paths:
                        sub.label(
                            text=(
                                f"F{int(item.get('frame', 0))} Pair {int(item.get('pos_idx', 0))} · "
                                f"{item.get('path_type', 'Other')} · "
                                f"{float(item.get('path_gain_db', 0.0)):.2f} dB · "
                                f"{float(item.get('delay_ns', 0.0)):.3g} ns · "
                                f"{float(item.get('doppler_hz', 0.0)):+.3g} Hz"
                            )
                        )
            else:
                label = "2D radio map" if analytics.get("source") == "RADIO_MAP" else "3D radio map"
                box.label(text=f"Source: {analytics.get('object', '—')}", icon="POINTCLOUD_DATA")
                row = box.row(align=True)
                row.label(text=f"{label}: {int(analytics.get('point_count', 0)):,} points")
                row.label(text=f"Frames: {int(analytics.get('frame_count', 0)):,}")
                gain = analytics.get("gain_db", {})
                percentiles = analytics.get("percentiles", {})
                metric_label = analytics.get("metric_label", "Metric")
                metric_unit = analytics.get("metric_unit", "dB")
                row = box.row(align=True)
                row.label(text=f"P5: {float(percentiles.get('5', 0.0)):.2f} {metric_unit}")
                row.label(text=f"Median: {float(percentiles.get('50', 0.0)):.2f} {metric_unit}")
                row.label(text=f"P95: {float(percentiles.get('95', 0.0)):.2f} {metric_unit}")
                row = box.row(align=True)
                threshold = float(analytics.get("coverage_threshold", 0.0))
                row.label(text=f"Coverage ≥ {threshold:g}: {float(analytics.get('coverage_above_threshold_percent', 0.0)):.1f}%")
                row.label(text=f"Outage: {float(analytics.get('outage_below_threshold_percent', 0.0)):.1f}%")
                row = box.row(align=True)
                row.label(text=f"Strongest: {float(gain.get('max', 0.0)):.2f} {metric_unit}")
                row.label(text=f"Valid values: {float(analytics.get('valid_percent', 0.0)):.1f}%")
                association = analytics.get("tx_association") or {}
                if association.get("available"):
                    dominant = association.get("dominant") or {}
                    row = box.row(align=True)
                    row.label(text=f"Associated TXs: {int(association.get('tx_count', 0))}")
                    row.label(text=(
                        f"Dominant: {dominant.get('name', '—')} "
                        f"({float(dominant.get('share_percent', 0.0)):.1f}%)"
                    ))
                    row = box.row(align=True)
                    row.label(text=f"Unassociated: {float(association.get('unassociated_percent', 0.0)):.1f}%")
                    row.label(text=f"Attribute: associated_tx ({analytics.get('metric_label', 'metric')})")
                if analytics.get("source") == "RADIO_MAP_3D":
                    row.label(text=f"Layers: {int(analytics.get('layer_count', 0)):,}")

            animation = analytics.get("procedural_animation") or {}
            if animation:
                sub = box.box()
                sub.label(text="Procedural animation", icon="ANIM")
                row = sub.row(align=True)
                row.label(text=f"Frames: {int(animation.get('frame_count', 0)):,}")
                row.label(text=f"States: {int(animation.get('distinct_geometry_states', 0)):,}")
                row.label(text=f"Descriptor: {animation.get('geometry_label', 'Geometry')}")
                geometry = animation.get("geometry_stats", {})
                unit = animation.get("geometry_unit", "")
                row = sub.row(align=True)
                row.label(text=(
                    f"Range: {float(geometry.get('min', 0.0)):.4g}–"
                    f"{float(geometry.get('max', 0.0)):.4g}{(' ' + unit) if unit else ''}"
                ))
                row.label(text=(
                    f"Largest change: F{int(animation.get('max_change_frame', 0))} "
                    f"({float(animation.get('max_change_percent', 0.0)):+.2f}%)"
                ))
                row = sub.row(align=True)
                if analytics.get("source") == "PATHS":
                    row.label(text=f"Power r: {_correlation_text(animation.get('correlation_channel_power'))}")
                    row.label(text=f"RMS delay r: {_correlation_text(animation.get('correlation_rms_delay'))}")
                    row.label(text=f"Paths r: {_correlation_text(animation.get('correlation_path_count'))}")
                else:
                    row.label(text=f"Metric r: {_correlation_text(animation.get('correlation_metric'))}")
                    row.label(text=f"Coverage r: {_correlation_text(animation.get('correlation_coverage'))}")
                sub.label(
                    text="Open Plots for frame trends, correlations, and the frame table.",
                    icon="INFO",
                )
            elif settings.analytics_scope == "ALL" and _procedural_scene_active(context.scene):
                box.label(
                    text="Run a new procedural simulation with geometry statistics enabled.",
                    icon="INFO",
                )

def _post_register_init_timer():
    """Finish scene-dependent initialization after Blender registration.

    Blender extensions are registered while ``bpy.data`` can be a restricted
    proxy without ``scenes``. Anything that inspects scenes must therefore be
    deferred until the normal BlendData API is restored.
    """
    if getattr(bpy.data, "scenes", None) is None:
        return 0.10
    try:
        _stop_legacy_live_update_timer()
        _ensure_bundled_geometry_nodes(verbose=True)
        _sync_dynamic_mode_handlers()
        _sync_pointcloud_motion_handler()
        _schedule_device_representation_sync()
    except (AttributeError, ReferenceError):
        # A registration/load transition can still be completing. Retry shortly
        # rather than leaving the extension partially initialized.
        return 0.10
    except Exception:
        traceback.print_exc()
    return None


_CLASSES = (
    SIONNA_PG_DeviceConfig,
    SIONNA_PG_MaterialConfig,
    SIONNA_PG_Settings,
    SIONNA_OT_CreateDefaultMaterials,
    SIONNA_OT_PickActiveMaterial,
    SIONNA_OT_EnableMaterial,
    SIONNA_OT_AssignMaterial,
    SIONNA_OT_CreateEnvironment,
    SIONNA_OT_MoveSelectedToScene,
    SIONNA_OT_MoveSelectedToProcedural,
    SIONNA_OT_GenerateMotionTemplate,
    SIONNA_OT_RemoveMotionTemplate,
    SIONNA_OT_SelectMotionTemplate,
    SIONNA_OT_AddDevice,
    SIONNA_OT_MarkSelected,
    SIONNA_OT_ClearRole,
    SIONNA_OT_ReadDeviceName,
    SIONNA_OT_ApplyDeviceName,
    SIONNA_OT_SyncRoleNames,
    SIONNA_OT_TestEnvironment,
    SIONNA_OT_ExportScene,
    SIONNA_OT_RunSelected,
    SIONNA_OT_Run,
    SIONNA_OT_RunCached,
    SIONNA_OT_GenerateRadioMap,
    SIONNA_OT_GenerateRadioMapCached,
    SIONNA_OT_ImportRadioMap,
    SIONNA_OT_UpdateRadioMapGeometryNodesCSV,
    SIONNA_OT_CopyRadioMapCSV,
    SIONNA_OT_ImportPaths,
    SIONNA_OT_UpdateGeometryNodesCSV,
    SIONNA_OT_CopyCSVPath,
    SIONNA_OT_CopyCSVPattern,
    SIONNA_OT_OpenCSVFolder,
    SIONNA_OT_OpenWorkspace,
    SIONNA_OT_OpenLastRun,
    SIONNA_OT_CopyFullStatus,
    SIONNA_OT_OpenStatusLog,
    SIONNA_OT_RefreshAnalytics,
    SIONNA_OT_OpenAnalyticsDashboard,
    SIONNA_PT_MainPanel,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.sionna_bridge = PointerProperty(type=SIONNA_PG_Settings)
    bpy.types.Object.sionna_device_config = PointerProperty(type=SIONNA_PG_DeviceConfig)
    bpy.types.Material.sionna_radio = PointerProperty(type=SIONNA_PG_MaterialConfig)
    if _device_representation_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_device_representation_load_post)
    if _auto_path_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_auto_path_load_post)
    if _bundled_geometry_nodes_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_bundled_geometry_nodes_load_post)

    # Do not touch bpy.data.scenes here. Blender 5.2 may call extension register()
    # with bpy.data == _RestrictData. Finish scene-dependent setup on the first
    # normal timer tick instead.
    if not bpy.app.timers.is_registered(_post_register_init_timer):
        bpy.app.timers.register(
            _post_register_init_timer,
            first_interval=0.10,
            persistent=False,
        )


def unregister():
    global _DEVICE_REPRESENTATION_SYNC_PENDING, _DEVICE_REPRESENTATION_SYNC_GUARD
    _DEVICE_REPRESENTATION_SYNC_PENDING = False
    _DEVICE_REPRESENTATION_SYNC_GUARD = False
    _clear_auto_path_scene_state()
    _stop_legacy_live_update_timer()
    try:
        if _device_representation_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.remove(_device_representation_depsgraph_update)
        if _auto_path_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.remove(_auto_path_depsgraph_update)
        if _device_representation_load_post in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.remove(_device_representation_load_post)
        if _auto_path_load_post in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.remove(_auto_path_load_post)
        if _bundled_geometry_nodes_load_post in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.remove(_bundled_geometry_nodes_load_post)
        while _pointcloud_motion_frame_change in bpy.app.handlers.frame_change_post:
            bpy.app.handlers.frame_change_post.remove(_pointcloud_motion_frame_change)
        if bpy.app.timers.is_registered(_post_register_init_timer):
            bpy.app.timers.unregister(_post_register_init_timer)
        if bpy.app.timers.is_registered(_device_representation_sync_timer):
            bpy.app.timers.unregister(_device_representation_sync_timer)
        if bpy.app.timers.is_registered(_auto_path_compute_timer):
            bpy.app.timers.unregister(_auto_path_compute_timer)
        if bpy.app.timers.is_registered(_poll_sionna_process):
            bpy.app.timers.unregister(_poll_sionna_process)
        if bpy.app.timers.is_registered(_poll_radio_map_process):
            bpy.app.timers.unregister(_poll_radio_map_process)
        if bpy.app.timers.is_registered(_poll_radio_map_3d_process):
            bpy.app.timers.unregister(_poll_radio_map_3d_process)
    except Exception:
        pass

    _close_radio_map_handles()
    _close_radio_map_3d_handles()
    _close_run_handles()
    _reset_batch_state()
    if hasattr(bpy.types.Material, "sionna_radio"):
        del bpy.types.Material.sionna_radio
    if hasattr(bpy.types.Object, "sionna_device_config"):
        del bpy.types.Object.sionna_device_config
    if hasattr(bpy.types.Scene, "sionna_bridge"):
        del bpy.types.Scene.sionna_bridge
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass


if __name__ == "__main__":
    register()
