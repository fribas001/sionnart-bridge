#!/usr/bin/env python3
"""External multi-frame, multi-height Sionna RT 3D radio-map worker.

A volume is sampled as stacked horizontal radio maps. Only essential point
attributes and the selected path-gain/RSS/SINR metric are written.
"""

import argparse
import csv
import importlib.metadata
import json
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

BASE_COLUMNS = (
    "frame", "x", "y", "z", "cell_size_x", "cell_size_y", "cell_size_z",
    "associated_tx", "coverage_valid", "metric_norm",
)
METRIC_COLUMNS = {
    "path_gain": ("path_gain", "path_gain_db"),
    "rss": ("rss", "rss_dbm"),
    "sinr": ("sinr", "sinr_db"),
}
METRIC_METADATA = {
    "path_gain": {"label": "Path Gain", "unit": "dB"},
    "rss": {"label": "RSS", "unit": "dBm"},
    "sinr": {"label": "SINR", "unit": "dB"},
}


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def package_version():
    for distribution in ("sionna-rt", "sionna_rt"):
        try:
            return importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            pass
    return "unknown"


def _atomic_replace_with_retry(temporary, destination, attempts=24):
    temporary = Path(temporary)
    destination = Path(destination)
    last_error = None
    for attempt in range(max(1, int(attempts))):
        try:
            os.replace(temporary, destination)
            return
        except (PermissionError, OSError) as exc:
            last_error = exc
            if attempt + 1 >= attempts:
                break
            time.sleep(min(1.0, 0.04 * (attempt + 1)))
    raise last_error or RuntimeError(f"Could not replace {destination}")


def write_json(path, payload, *, best_effort=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        path.name + f".{os.getpid()}.{time.time_ns()}.tmp"
    )
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        _atomic_replace_with_retry(temporary, path)
        return True
    except Exception as exc:
        try:
            temporary.unlink(missing_ok=True)
        except Exception:
            pass
        if best_effort:
            print(f"WARNING: could not update status file {path}: {exc}", flush=True)
            return False
        raise


def write_status_json(path, payload):
    # Status updates must never terminate an otherwise valid long simulation.
    return write_json(path, payload, best_effort=True)


def csv_columns(rows):
    columns = list(BASE_COLUMNS)
    present = {key for row in rows for key in row}
    for metric in ("path_gain", "rss", "sinr"):
        for key in METRIC_COLUMNS[metric]:
            if key in present:
                columns.append(key)
    return columns


def write_csv(path, rows):
    if not rows:
        raise RuntimeError("The radio-map worker produced no point rows")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.{time.time_ns()}.tmp")
    columns = csv_columns(rows)
    with open(temporary, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    _atomic_replace_with_retry(temporary, path)


def to_numpy(value):
    if hasattr(value, "numpy"):
        return np.asarray(value.numpy())
    return np.asarray(value)




def frame_materials(runtime, frame):
    materials = list(frame.get("materials") or runtime.get("materials") or [])
    return materials


def make_scattering_pattern(spec, runtime):
    pattern = str(spec.get("scattering_pattern", "lambertian")).lower()
    if pattern == "directive":
        return runtime["DirectivePattern"](
            alpha_r=max(1, int(spec.get("directive_alpha_r", 1)))
        )
    if pattern == "backscattering":
        return runtime["BackscatteringPattern"](
            alpha_r=max(1, int(spec.get("backscatter_alpha_r", 1))),
            alpha_i=max(1, int(spec.get("backscatter_alpha_i", 1))),
            lambda_=min(1.0, max(0.0, float(spec.get("backscatter_lambda", 1.0)))),
        )
    return runtime["LambertianPattern"]()


def _radio_material_name_key(value):
    """Normalize Sionna/Mitsuba material IDs for stable matching."""
    value = str(value or "").strip().lower()
    if value.startswith("mat-"):
        value = value[4:]
    return value


def _scalar_float(value, default=0.0):
    """Convert a scalar Dr.Jit/Mitsuba value without assuming its container."""
    try:
        return float(value)
    except Exception:
        try:
            return float(value[0])
        except Exception:
            return float(default)


def _find_loaded_radio_material(scene, *names):
    wanted = {_radio_material_name_key(name) for name in names if name}
    materials = scene.radio_materials
    for key, material in materials.items():
        candidates = {
            _radio_material_name_key(key),
            _radio_material_name_key(getattr(material, "name", "")),
            _radio_material_name_key(getattr(material, "id", lambda: "")()),
        }
        if wanted & candidates:
            return material
    return None


def _itu_values(scene, itu_type, runtime):
    """Evaluate an ITU preset at the scene's current carrier frequency.

    A temporary material is attached to the scene only long enough for its
    frequency callback to evaluate. It is never added to ``scene.radio_materials``
    and is never assigned to a mesh.
    """
    probe = runtime["ITURadioMaterial"](
        name=f"__sbr_itu_probe_{itu_type}",
        itu_type=itu_type,
        thickness=0.1,
    )
    probe.scene = scene
    return (
        _scalar_float(probe.relative_permittivity, 1.0),
        _scalar_float(probe.conductivity, 0.0),
    )


def apply_radio_materials(scene, frame, runtime):
    """Update the radio materials loaded from XML in place.

    Replacing a material on an already-loaded/merged Mitsuba mesh can leave the
    renderer traversal out of sync and produced ``No object found with name`` in
    v0.17.1. The XML now creates one mutable ``radio-material`` placeholder per
    configured Blender material, so only its numeric properties are changed.
    """
    summaries = []
    available = sorted(scene.radio_materials.keys())
    for spec in frame_materials(runtime, frame):
        source_name = str(spec.get("source_name", "")).strip()
        runtime_root = str(spec.get("runtime_name", source_name or "sbr_material")).strip()
        if not source_name:
            continue

        material = _find_loaded_radio_material(scene, source_name, runtime_root)
        if material is None:
            raise RuntimeError(
                "Configured radio material placeholder was not loaded: "
                f"{source_name!r}. Available materials: {available[:12]}"
            )

        model = str(spec.get("model", "ITU")).upper()
        itu_type = str(spec.get("itu_type", "concrete"))
        if model == "ITU":
            eta_r, sigma = _itu_values(scene, itu_type, runtime)
        else:
            eta_r = max(1.0, float(spec.get("relative_permittivity", 1.0)))
            sigma = max(0.0, float(spec.get("conductivity", 0.0)))

        material.relative_permittivity = eta_r
        material.conductivity = sigma
        material.thickness = max(0.0, float(spec.get("thickness", 0.1)))
        material.scattering_coefficient = min(
            1.0, max(0.0, float(spec.get("scattering_coefficient", 0.0)))
        )
        material.xpd_coefficient = min(
            1.0, max(0.0, float(spec.get("xpd_coefficient", 0.0)))
        )
        material.scattering_pattern = make_scattering_pattern(spec, runtime)
        color = tuple(float(v) for v in spec.get("color", (0.5, 0.5, 0.5))[:3])
        try:
            material.color = color
        except Exception:
            pass

        object_count = sum(
            1 for obj in scene.objects.values()
            if getattr(obj, "radio_material", None) is material
        )
        summaries.append({
            "blender_name": spec.get("blender_name", source_name),
            "sionna_name": getattr(material, "name", source_name),
            "model": model,
            "itu_type": itu_type if model == "ITU" else None,
            "object_count": object_count,
            "relative_permittivity": eta_r,
            "conductivity": sigma,
            "thickness": _scalar_float(material.thickness, spec.get("thickness", 0.1)),
            "scattering_coefficient": _scalar_float(material.scattering_coefficient, 0.0),
            "xpd_coefficient": _scalar_float(material.xpd_coefficient, 0.0),
        })
    return summaries

def frame_payloads(config):
    frames = list(config.get("frames") or [])
    if frames:
        return frames
    return [{
        "frame": int(config.get("frame", 0)),
        "simulation": dict(config.get("simulation", {})),
        "radio_map_3d": dict(config.get("radio_map_3d", {})),
        "transmitters": list(config.get("transmitters", [])),
        "materials": list(config.get("materials", [])),
        "output": {
            "results_json": config.get("output", {}).get("results_json", ""),
            "results_npz": config.get("output", {}).get("results_npz", ""),
            "status_json": config.get("output", {}).get("frame_status_json", ""),
        },
    }]


def merged_frame(config, payload):
    simulation = dict(config.get("simulation", {}))
    simulation.update(payload.get("simulation", {}))
    radio = dict(config.get("radio_map_3d", {}))
    radio.update(payload.get("radio_map_3d", {}))
    return {
        "frame": int(payload.get("frame", config.get("frame", 0))),
        "simulation": simulation,
        "radio_map_3d": radio,
        "transmitters": list(payload.get("transmitters", config.get("transmitters", []))),
        "materials": list(payload.get("materials", config.get("materials", []))),
        "scene_xml": str(payload.get("scene_xml") or config.get("scene_xml", "")),
        "scene_xml_sha256": str(payload.get("scene_xml_sha256") or config.get("scene_xml_sha256", "")),
        "output": dict(payload.get("output", {})),
    }


def metric_name(frame):
    metric = str(frame.get("radio_map_3d", {}).get("metric", "path_gain")).strip().lower()
    metric = {"pathgain": "path_gain", "path gain": "path_gain", "sirn": "sinr"}.get(
        metric, metric
    )
    if metric not in METRIC_COLUMNS:
        raise ValueError(f"Unsupported radio-map metric: {metric}")
    return metric


def selected_metric_map(result, metric):
    try:
        values = result.transmitter_radio_map(metric=metric, tx=None)
        return to_numpy(values)
    except Exception:
        values = to_numpy(getattr(result, metric))
        if values.ndim == 2:
            return values
        if values.ndim != 3:
            raise ValueError(f"Unexpected {metric} tensor shape: {values.shape}")
        finite = np.where(np.isfinite(values), values, -np.inf)
        return np.max(finite, axis=0)


def tx_association_map(result, metric, selected_values):
    """Return the zero-based TX index serving each cell for ``metric``.

    Sionna's :meth:`RadioMap.tx_association` is the source of truth. The
    NumPy fallback keeps the add-on compatible with minor API variations.
    Invalid cells are encoded as ``-1`` so Geometry Nodes can remove or
    style them without a second validity attribute.
    """
    selected_values = np.asarray(selected_values, dtype=np.float64)
    try:
        association = to_numpy(result.tx_association(metric)).astype(np.int32, copy=False)
    except Exception:
        all_values = to_numpy(getattr(result, metric))
        if all_values.ndim == 2:
            association = np.zeros(all_values.shape, dtype=np.int32)
        elif all_values.ndim == 3:
            finite = np.where(np.isfinite(all_values), all_values, -np.inf)
            association = np.argmax(finite, axis=0).astype(np.int32, copy=False)
        else:
            raise ValueError(
                f"Unexpected {metric} tensor shape for TX association: {all_values.shape}"
            )
    if association.shape != selected_values.shape:
        association = np.asarray(association).squeeze()
    if association.shape != selected_values.shape:
        raise ValueError(
            f"TX-association grid mismatch: association={association.shape}, "
            f"metric={selected_values.shape}"
        )
    valid = np.isfinite(selected_values) & (selected_values > 0.0)
    return np.where(valid, association, -1).astype(np.int32, copy=False)


def metric_db(values, metric):
    values = np.asarray(values, dtype=np.float64)
    valid = np.isfinite(values) & (values > 0.0)
    db = np.full(values.shape, -300.0, dtype=np.float64)
    if metric == "rss":
        db[valid] = 30.0 + 10.0 * np.log10(values[valid])
    else:
        db[valid] = 10.0 * np.log10(values[valid])
    clean = np.where(valid, values, 0.0)
    return clean, db


def metric_volume_display_data(linear, db, association):
    """Validity and normalized display values for a complete Z/Y/X volume."""
    linear = np.asarray(linear, dtype=np.float64)
    db = np.asarray(db, dtype=np.float64)
    association = np.asarray(association, dtype=np.int32)
    valid = (association >= 0) & np.isfinite(linear) & (linear > 0.0) & np.isfinite(db)
    normalized = np.zeros(db.shape, dtype=np.float64)
    valid_db = db[valid]
    if valid_db.size:
        lo = float(np.min(valid_db))
        hi = float(np.max(valid_db))
        span = hi - lo
        if span > 1e-12:
            normalized[valid] = np.clip((valid_db - lo) / span, 0.0, 1.0)
        else:
            normalized[valid] = 1.0
    return valid.astype(np.int32), normalized.astype(np.float32)


def tx_array_profile(config):
    antenna = config.get("antenna", {})
    return antenna.get("tx", antenna) or {
        "num_rows": 1, "num_cols": 1, "vertical_spacing": 0.5,
        "horizontal_spacing": 0.5, "pattern": "iso", "polarization": "V",
        "polarization_model": "tr38901_2",
    }


def make_tx_array(config, PlanarArray):
    profile = tx_array_profile(config)
    return PlanarArray(
        num_rows=int(profile.get("num_rows", 1)),
        num_cols=int(profile.get("num_cols", 1)),
        vertical_spacing=float(profile.get("vertical_spacing", 0.5)),
        horizontal_spacing=float(profile.get("horizontal_spacing", 0.5)),
        pattern=str(profile.get("pattern", "iso")),
        polarization=str(profile.get("polarization", "V")),
        polarization_model=str(profile.get("polarization_model", "tr38901_2")),
    )


def apply_tx_orientation(tx, item):
    mode = str(item.get("orientation_mode", "BLENDER")).upper()
    if mode == "LOOK_AT":
        target = item.get("look_at_target_position")
        if target is None:
            raise RuntimeError(f"Transmitter {item.get('name')} has no look-at target position")
        delta = np.asarray(target, dtype=float) - np.asarray(item["position"], dtype=float)
        if float(np.dot(delta, delta)) <= 1e-12:
            raise RuntimeError(f"Transmitter {item.get('name')} cannot look at a coincident target")
        tx.look_at(target)
    else:
        tx.orientation = item.get("orientation_sionna_rad", [0.0, 0.0, 0.0])


def configure_frame(scene, frame, runtime):
    sim = frame["simulation"]
    scene.frequency = float(sim["frequency_hz"])
    scene.bandwidth = float(sim.get("bandwidth_hz", 1e6))
    scene.temperature = float(sim.get("temperature_k", 293.0))
    scene.tx_array = make_tx_array(runtime, runtime["PlanarArray"])

    wanted = {item["name"] for item in frame["transmitters"]}
    for name in list(scene.transmitters):
        if name not in wanted:
            scene.remove(name)
    for item in frame["transmitters"]:
        tx = scene.transmitters.get(item["name"])
        if tx is None:
            tx = runtime["Transmitter"](
                name=item["name"], position=item["position"], orientation=[0.0, 0.0, 0.0]
            )
            scene.add(tx)
        else:
            tx.position = item["position"]
        tx.power_dbm = float(item.get("power_dbm", 44.0))
    for item in frame["transmitters"]:
        apply_tx_orientation(scene.transmitters.get(item["name"]), item)
    return apply_radio_materials(scene, frame, runtime)


def voxel_layer_heights(volume):
    size_z = float(volume["size_z"])
    cell_z = float(volume["cell_size_z"])
    if size_z <= 0.0 or cell_z <= 0.0:
        raise ValueError("3D radio-map size_z and cell_size_z must be positive")
    count = max(1, int(np.ceil(size_z / cell_z - 1e-12)))
    center_z = float(volume["center_z"])
    offsets = (np.arange(count, dtype=np.float64) - (count - 1) * 0.5) * cell_z
    return center_z + offsets


def build_layer_rows(frame, centers, values, association, metric, layer_z):
    centers = np.asarray(centers, dtype=np.float64)
    values = np.asarray(values, dtype=np.float64)
    association = np.asarray(association, dtype=np.int32)
    if centers.ndim != 3 or centers.shape[-1] != 3:
        raise ValueError(f"Unexpected cell-centers shape: {centers.shape}")
    ny, nx, _ = centers.shape
    if values.shape != (ny, nx):
        raise ValueError(f"Metric grid mismatch: metric={values.shape}, centers={centers.shape}")
    if association.shape != (ny, nx):
        raise ValueError(
            f"TX-association grid mismatch: association={association.shape}, centers={centers.shape}"
        )
    linear, db = metric_db(values, metric)
    valid, metric_norm = metric_volume_display_data(linear, db, association)
    linear_key, db_key = METRIC_COLUMNS[metric]
    volume = frame["radio_map_3d"]
    rows = []
    for iy in range(ny):
        for ix in range(nx):
            p = centers[iy, ix]
            rows.append({
                "frame": int(frame["frame"]),
                "x": float(p[0]),
                "y": float(p[1]),
                "z": float(layer_z),
                "cell_size_x": float(volume["cell_size_x"]),
                "cell_size_y": float(volume["cell_size_y"]),
                "cell_size_z": float(volume["cell_size_z"]),
                "associated_tx": int(association[iy, ix]),
                "coverage_valid": int(valid[iy, ix]),
                "metric_norm": float(metric_norm[iy, ix]),
                linear_key: float(linear[iy, ix]),
                db_key: float(db[iy, ix]),
            })
    return rows, linear, db


def solve_frame(scene, solver, runtime, frame, status_path, frame_index, frame_count):
    material_summary = configure_frame(scene, frame, runtime)
    sim = frame["simulation"]
    volume = frame["radio_map_3d"]
    metric = metric_name(frame)
    heights = voxel_layer_heights(volume)
    all_rows, values_layers, db_layers = [], [], []
    association_layers, centers_layers = [], []
    for layer_index, layer_z in enumerate(heights):
        write_status_json(status_path, {
            "state": "solving_3d_radio_map", "updated_utc": now_utc(),
            "frame": int(frame["frame"]), "frame_index": int(frame_index),
            "frame_count": int(frame_count), "frequency_ghz": float(sim["frequency_ghz"]),
            "metric": metric, "layer_index": int(layer_index + 1),
            "layer_count": int(len(heights)), "height": float(layer_z),
            "num_tx": len(frame["transmitters"]),
        })
        result = solver(
            scene=scene,
            center=[float(volume["center_x"]), float(volume["center_y"]), float(layer_z)],
            orientation=[0.0, 0.0, 0.0],
            size=[float(volume["size_x"]), float(volume["size_y"])],
            cell_size=[float(volume["cell_size_x"]), float(volume["cell_size_y"])],
            samples_per_tx=int(sim["samples_per_src"]), max_depth=int(sim["max_depth"]),
            los=bool(sim["los"]), specular_reflection=bool(sim["specular_reflection"]),
            diffuse_reflection=bool(sim["diffuse_reflection"]), refraction=bool(sim["refraction"]),
            diffraction=bool(sim["diffraction"]), edge_diffraction=bool(sim.get("edge_diffraction", False)),
            diffraction_lit_region=bool(sim.get("diffraction_lit_region", True)), seed=int(sim["seed"]),
        )
        centers = to_numpy(result.cell_centers)
        metric_values = selected_metric_map(result, metric)
        association = tx_association_map(result, metric, metric_values)
        rows, linear, db = build_layer_rows(
            frame, centers, metric_values, association, metric, float(layer_z)
        )
        all_rows.extend(rows)
        centers_layers.append(np.asarray(centers, dtype=np.float32))
        values_layers.append(np.asarray(linear, dtype=np.float32))
        db_layers.append(np.asarray(db, dtype=np.float32))
        association_layers.append(np.asarray(association, dtype=np.int32))

    output = frame.get("output", {})
    keep_external = bool(runtime.get("output", {}).get("keep_external_results", True))
    linear_key, db_key = METRIC_COLUMNS[metric]
    linear_layers = np.asarray(values_layers, dtype=np.float32)
    logarithmic_layers = np.asarray(db_layers, dtype=np.float32)
    association_array = np.asarray(association_layers, dtype=np.int32)
    coverage_valid, metric_norm = metric_volume_display_data(
        linear_layers, logarithmic_layers, association_array
    )
    # Keep the flattened CSV representation numerically consistent with the
    # canonical HDF5 volume: normalization is computed over the whole 3D
    # volume, not independently per Z slice.
    valid_flat = np.asarray(coverage_valid).reshape(-1)
    norm_flat = np.asarray(metric_norm).reshape(-1)
    if len(all_rows) == len(valid_flat):
        for row, valid_value, norm_value in zip(all_rows, valid_flat, norm_flat):
            row["coverage_valid"] = int(valid_value)
            row["metric_norm"] = float(norm_value)

    if keep_external and output.get("results_npz"):
        archive = {
            "layer_heights": np.asarray(heights, dtype=np.float32),
            "cell_centers": np.asarray(centers_layers, dtype=np.float32),
            "metric": np.asarray(metric),
            "metric_linear_attribute": np.asarray(linear_key),
            "metric_db_attribute": np.asarray(db_key),
            "values": linear_layers,
            "values_db": logarithmic_layers,
            linear_key: linear_layers,
            db_key: logarithmic_layers,
            "associated_tx": association_array,
            "coverage_valid": np.asarray(coverage_valid, dtype=np.int32),
            "metric_norm": np.asarray(metric_norm, dtype=np.float32),
            "dimension_order": np.asarray("z,y,x"),
            "grid_shape_zyx": np.asarray(linear_layers.shape, dtype=np.int32),
        }
        np.savez_compressed(output["results_npz"], **archive)
    frame_result = {
        "frame": int(frame["frame"]), "simulation": dict(sim),
        "radio_map_3d": dict(volume), "transmitters": list(frame["transmitters"]),
        "materials": material_summary,
        "metric": metric, "metric_label": METRIC_METADATA[metric]["label"],
        "metric_unit": METRIC_METADATA[metric]["unit"],
        "metric_linear_attribute": linear_key, "metric_db_attribute": db_key,
        "metric_attributes": [linear_key, db_key],
        "association_metric": metric,
        "association_tx_names": list(scene.transmitters.keys()),
        "point_count": len(all_rows), "layer_count": len(heights),
        "layer_heights": [float(v) for v in heights],
        "volume_shape_zyx": [int(v) for v in linear_layers.shape],
        "dimension_order": "z,y,x",
        "valid_voxel_count": int(np.count_nonzero(coverage_valid)),
        "voxel_count": int(coverage_valid.size),
        "coverage_fraction": (
            float(np.count_nonzero(coverage_valid)) / float(coverage_valid.size)
            if coverage_valid.size else 0.0
        ),
        "results_json": output.get("results_json", ""), "results_npz": output.get("results_npz", ""),
    }
    if keep_external and output.get("results_json"):
        write_json(output["results_json"], {"schema_version": 6, "created_utc": now_utc(), "scene_xml_sha256": runtime["scene_xml_sha256"], **frame_result})
    if keep_external and output.get("status_json"):
        write_status_json(output["status_json"], {"state": "finished", "updated_utc": now_utc(), **frame_result})
    return frame_result, all_rows


def main(config_path):
    config_path = Path(config_path).resolve()
    with open(config_path, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    output = config["output"]
    status_path = Path(output["status_json"])
    payloads = [merged_frame(config, item) for item in frame_payloads(config)]
    if not payloads:
        raise RuntimeError("The 3D radio-map config contains no frames")
    write_status_json(status_path, {"state": "starting", "created_utc": now_utc(), "config": str(config_path), "frame_count": len(payloads)})

    import mitsuba as mi
    from sionna.rt import (
        load_scene, PlanarArray, RadioMapSolver, Transmitter,
        RadioMaterial, ITURadioMaterial, LambertianPattern,
        DirectivePattern, BackscatteringPattern,
    )
    runtime = dict(config)
    runtime.update({
        "PlanarArray": PlanarArray,
        "Transmitter": Transmitter,
        "RadioMaterial": RadioMaterial,
        "ITURadioMaterial": ITURadioMaterial,
        "LambertianPattern": LambertianPattern,
        "DirectivePattern": DirectivePattern,
        "BackscatteringPattern": BackscatteringPattern,
    })
    scene = None
    current_scene_xml = None
    solver = RadioMapSolver()

    frame_results, all_rows = [], []
    for index, frame in enumerate(payloads, start=1):
        frame_scene_xml = str(frame.get("scene_xml") or config["scene_xml"])
        if scene is None or frame_scene_xml != current_scene_xml:
            write_status_json(status_path, {
                "state": "loading_scene", "updated_utc": now_utc(),
                "frame": int(frame["frame"]), "frame_index": index,
                "frame_count": len(payloads), "scene_xml": frame_scene_xml,
            })
            scene = load_scene(frame_scene_xml, merge_shapes=True)
            current_scene_xml = frame_scene_xml
        frame_runtime = dict(runtime)
        frame_runtime["scene_xml"] = frame_scene_xml
        frame_runtime["scene_xml_sha256"] = frame.get("scene_xml_sha256", config.get("scene_xml_sha256", ""))
        frame_result, rows = solve_frame(scene, solver, frame_runtime, frame, status_path, index, len(payloads))
        frame_results.append(frame_result)
        all_rows.extend(rows)

    combined_csv = Path(output["results_csv"])
    write_csv(combined_csv, all_rows)
    manifest_path = Path(output.get("frames_manifest_json") or output["results_json"])
    metrics = sorted({item["metric"] for item in frame_results})
    manifest = {
        "schema_version": 6, "created_utc": now_utc(), "scene_xml": config["scene_xml"],
        "scene_xml_sha256": config["scene_xml_sha256"], "frame_count": len(frame_results),
        "point_count": len(all_rows), "metrics": metrics, "results_csv": str(combined_csv),
        "frames": frame_results, "procedural_scene": bool(config.get("procedural_scene", False)),
        "sionna_rt_version": package_version(),
        "mitsuba_version": getattr(mi, "__version__", "unknown"),
    }
    write_json(manifest_path, manifest)
    if Path(output["results_json"]) != manifest_path:
        write_json(output["results_json"], manifest)
    from result_export_worker import export_completed_run
    export_status = export_completed_run(
        config_path=config_path,
        manifest_path=manifest_path,
        csv_path=combined_csv,
        output=output,
    )
    write_status_json(status_path, {
        "state": "finished", "updated_utc": now_utc(), "frame_count": len(frame_results),
        "completed_frames": len(frame_results), "point_count": len(all_rows), "metrics": metrics,
        "results_csv": str(combined_csv), "results_json": str(manifest_path), "frames": frame_results,
        **export_status,
    })
    print(json.dumps({"ok": True, "frame_count": len(frame_results), "point_count": len(all_rows), "metrics": metrics, "results_csv": str(combined_csv), **export_status}))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    exit_code = 1
    try:
        exit_code = main(args.config)
    except Exception as exc:
        traceback.print_exc()
        try:
            with open(Path(args.config).resolve(), "r", encoding="utf-8") as handle:
                config = json.load(handle)
            write_status_json(config["output"]["status_json"], {"state": "failed", "updated_utc": now_utc(), "error": str(exc), "traceback": traceback.format_exc()})
        except Exception:
            pass
    finally:
        try:
            import sys
            sys.stdout.flush(); sys.stderr.flush()
        finally:
            os._exit(int(exit_code))
