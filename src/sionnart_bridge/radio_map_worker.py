#!/usr/bin/env python3
"""External multi-frame Sionna RT 2D radio-map worker.

Only the point attributes required by Blender visualization are written. The
selected metric can be path gain, RSS, or SINR.
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
    "frame", "x", "y", "z", "cell_size_x", "cell_size_y",
    "is_projected", "cell_index", "primitive_index", "tx_count",
    "normal_x", "normal_y", "normal_z",
    "tangent_x", "tangent_y", "tangent_z",
    "bitangent_x", "bitangent_y", "bitangent_z",
    "triangle_v0_x", "triangle_v0_y", "triangle_v0_z",
    "triangle_v1_x", "triangle_v1_y", "triangle_v1_z",
    "triangle_v2_x", "triangle_v2_y", "triangle_v2_z",
    "edge_length_01", "edge_length_12", "edge_length_20",
    "cell_area", "associated_tx", "coverage_valid",
    "metric_linear", "metric_db", "metric_norm",
)
METRIC_COLUMNS = {
    "path_gain": ("path_gain", "path_gain_db"),
    "rss": ("rss", "rss_dbm"),
    "sinr": ("sinr", "sinr_db"),
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
    # Keep dynamically generated per-transmitter fields and future numeric
    # projected-map attributes instead of silently dropping them.
    columns.extend(sorted(present.difference(columns)))
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


def normalize_cell_centers(value):
    """Return Sionna cell centers with coordinates on the last axis.

    Mitsuba/Dr.Jit vector arrays may convert to NumPy in structure-of-arrays
    layout, e.g. ``(3, num_cells)``, while TensorXf values use the documented
    array-of-structures layout, e.g. ``(num_cells, 3)``. Planar maps can
    similarly appear as ``(3, ny, nx)`` instead of ``(ny, nx, 3)``.
    """
    centers = np.asarray(to_numpy(value), dtype=np.float64)
    centers = np.squeeze(centers)
    if centers.ndim not in {2, 3}:
        raise ValueError(f"Unexpected cell-centers shape: {centers.shape}")
    if centers.shape[-1] == 3:
        return centers
    if centers.shape[0] == 3:
        return np.moveaxis(centers, 0, -1)
    raise ValueError(f"Unexpected cell-centers shape: {centers.shape}")


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
        "radio_map": dict(config.get("radio_map", {})),
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
    radio = dict(config.get("radio_map", {}))
    radio.update(payload.get("radio_map", {}))
    return {
        "frame": int(payload.get("frame", config.get("frame", 0))),
        "simulation": simulation,
        "radio_map": radio,
        "transmitters": list(payload.get("transmitters", config.get("transmitters", []))),
        "materials": list(payload.get("materials", config.get("materials", []))),
        "scene_xml": str(payload.get("scene_xml") or config.get("scene_xml", "")),
        "scene_xml_sha256": str(payload.get("scene_xml_sha256") or config.get("scene_xml_sha256", "")),
        "output": dict(payload.get("output", {})),
    }


def metric_name(frame):
    metric = str(frame.get("radio_map", {}).get("metric", "path_gain")).lower()
    if metric not in METRIC_COLUMNS:
        raise ValueError(f"Unsupported radio-map metric: {metric}")
    return metric


def selected_metric_map(result, metric, centers):
    centers = np.asarray(centers)
    mesh_surface = centers.ndim == 2
    try:
        values = result.transmitter_radio_map(metric=metric, tx=None)
        values = to_numpy(values)
        expected_shape = centers.shape[:-1]
        if values.shape == expected_shape:
            return values
    except Exception:
        pass
    values = to_numpy(getattr(result, metric))
    if mesh_surface:
        if values.ndim == 1:
            return values
        if values.ndim == 2:
            finite = np.where(np.isfinite(values), values, -np.inf)
            return np.max(finite, axis=0)
    else:
        if values.ndim == 2:
            return values
        if values.ndim == 3:
            finite = np.where(np.isfinite(values), values, -np.inf)
            return np.max(finite, axis=0)
    raise ValueError(
        f"Unexpected {metric} tensor shape {values.shape} for cell centers {centers.shape}"
    )


def metric_maps_by_tx(result, metric, centers):
    """Return one metric array per transmitter.

    Mesh radio maps are documented as ``[num_tx, num_primitives]`` and planar
    maps as ``[num_tx, ny, nx]``. A one-transmitter result may occasionally be
    exposed without the leading transmitter dimension, so this function
    normalizes both layouts to ``[num_tx, ...cell_shape]``.
    """
    centers = np.asarray(centers)
    expected_shape = tuple(centers.shape[:-1])
    values = np.asarray(to_numpy(getattr(result, metric)), dtype=np.float64)
    # Remove only redundant wrapper dimensions. Preserve the documented
    # leading transmitter dimension even for the one-TX/one-cell edge case.
    while values.ndim > len(expected_shape) + 1 and 1 in values.shape:
        values = np.squeeze(values, axis=next(i for i, size in enumerate(values.shape) if size == 1))
    if tuple(values.shape) == expected_shape:
        return values.reshape((1,) + expected_shape)
    if values.ndim == len(expected_shape) + 1 and tuple(values.shape[1:]) == expected_shape:
        return values
    raise ValueError(
        f"Unexpected per-transmitter {metric} tensor shape {values.shape}; "
        f"expected [num_tx, {', '.join(map(str, expected_shape))}]"
    )


def tx_association_map(result, metric, selected_values, centers):
    """Return the zero-based TX index serving each cell for ``metric``.

    Sionna's :meth:`RadioMap.tx_association` is the source of truth. The
    NumPy fallback keeps the add-on compatible with minor API variations.
    Invalid cells are encoded as ``-1`` so Geometry Nodes can remove or
    style them without a second validity attribute.
    """
    selected_values = np.asarray(selected_values, dtype=np.float64)
    centers = np.asarray(centers)
    mesh_surface = centers.ndim == 2
    try:
        association = to_numpy(result.tx_association(metric)).astype(np.int32, copy=False)
    except Exception:
        all_values = to_numpy(getattr(result, metric))
        if mesh_surface and all_values.ndim == 1:
            association = np.zeros(all_values.shape, dtype=np.int32)
        elif mesh_surface and all_values.ndim == 2:
            finite = np.where(np.isfinite(all_values), all_values, -np.inf)
            association = np.argmax(finite, axis=0).astype(np.int32, copy=False)
        elif not mesh_surface and all_values.ndim == 2:
            association = np.zeros(all_values.shape, dtype=np.int32)
        elif not mesh_surface and all_values.ndim == 3:
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
    """Return the Sionna metric in linear and logarithmic units.

    Path gain and SINR are unitless in linear scale and use 10*log10 for dB.
    RSS is returned by Sionna in watts and is converted to dBm. Cells without
    coverage keep an exact linear zero and use -300 as a finite Blender-safe
    sentinel for the logarithmic attribute.
    """
    values = np.asarray(values, dtype=np.float64)
    valid = np.isfinite(values) & (values > 0.0)
    db = np.full(values.shape, -300.0, dtype=np.float64)
    if metric == "rss":
        db[valid] = 30.0 + 10.0 * np.log10(values[valid])
    else:
        db[valid] = 10.0 * np.log10(values[valid])
    clean = np.where(valid, values, 0.0)
    return clean, db


def metric_display_data(linear, db, association):
    """Create generic Geometry Nodes helpers and compact per-frame statistics.

    Blender's spreadsheet rounds very small linear path-gain values (commonly
    around 1e-8 to 1e-12) to ``0.000``. ``metric_db`` is the recommended
    visualization attribute, while ``metric_norm`` maps the valid per-frame dB
    range to [0, 1]. ``coverage_valid`` is one only when Sionna associates the
    cell with a transmitter and the selected metric is positive and finite.
    """
    linear = np.asarray(linear, dtype=np.float64)
    db = np.asarray(db, dtype=np.float64)
    association = np.asarray(association, dtype=np.int32)
    valid = (association >= 0) & np.isfinite(linear) & (linear > 0.0) & np.isfinite(db)
    normalized = np.zeros(db.shape, dtype=np.float64)
    valid_db = db[valid]
    if valid_db.size:
        db_min = float(np.min(valid_db))
        db_max = float(np.max(valid_db))
        span = db_max - db_min
        if span > 1e-12:
            normalized[valid] = np.clip((valid_db - db_min) / span, 0.0, 1.0)
        else:
            normalized[valid] = 1.0
        db_median = float(np.median(valid_db))
    else:
        db_min = -300.0
        db_max = -300.0
        db_median = -300.0
    valid_count = int(np.count_nonzero(valid))
    total_count = int(valid.size)
    stats = {
        "valid_cell_count": valid_count,
        "invalid_cell_count": total_count - valid_count,
        "coverage_fraction": (float(valid_count) / float(total_count)) if total_count else 0.0,
        "metric_db_min": db_min,
        "metric_db_max": db_max,
        "metric_db_median": db_median,
    }
    return valid.astype(np.int32), normalized, stats


def load_surface_cells(path):
    path = Path(path)
    if not path.is_file():
        raise RuntimeError(f"Projected measurement-surface metadata is missing: {path}")
    rows = []
    with open(path, "r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            def vector(prefix, default):
                values = []
                for axis, fallback in zip(("x", "y", "z"), default):
                    raw = row.get(f"{prefix}_{axis}", "")
                    values.append(float(raw) if raw not in (None, "") else float(fallback))
                return np.asarray(values, dtype=np.float64)

            rows.append({
                "primitive_index": int(row["primitive_index"]),
                "center": np.asarray([
                    float(row["center_x"]), float(row["center_y"]), float(row["center_z"])
                ], dtype=np.float64),
                "normal": vector("normal", (0.0, 0.0, 1.0)),
                "tangent": vector("tangent", (1.0, 0.0, 0.0)),
                "bitangent": vector("bitangent", (0.0, 1.0, 0.0)),
                "triangle_v0": vector("triangle_v0", (0.0, 0.0, 0.0)),
                "triangle_v1": vector("triangle_v1", (0.0, 0.0, 0.0)),
                "triangle_v2": vector("triangle_v2", (0.0, 0.0, 0.0)),
                "edge_length_01": float(row.get("edge_length_01", 0.0) or 0.0),
                "edge_length_12": float(row.get("edge_length_12", 0.0) or 0.0),
                "edge_length_20": float(row.get("edge_length_20", 0.0) or 0.0),
                "cell_area": float(row["cell_area"]),
            })
    if not rows:
        raise RuntimeError(f"Projected measurement-surface metadata has no cells: {path}")
    return rows


def build_rows(
    frame, centers, values, association, metric, surface_cells=None,
    values_by_tx=None,
):
    centers = np.asarray(centers, dtype=np.float64)
    values = np.asarray(values, dtype=np.float64)
    association = np.asarray(association, dtype=np.int32)
    if centers.ndim not in {2, 3} or centers.shape[-1] != 3:
        raise ValueError(f"Unexpected cell-centers shape: {centers.shape}")
    expected_shape = centers.shape[:-1]
    if values.shape != expected_shape:
        raise ValueError(f"Metric grid mismatch: metric={values.shape}, centers={centers.shape}")
    if association.shape != expected_shape:
        raise ValueError(
            f"TX-association grid mismatch: association={association.shape}, centers={centers.shape}"
        )
    linear, db = metric_db(values, metric)
    coverage_valid, metric_norm, metric_stats = metric_display_data(
        linear, db, association
    )
    linear_key, db_key = METRIC_COLUMNS[metric]
    tx_linear = None
    tx_db = None
    tx_count = 0
    if values_by_tx is not None:
        values_by_tx = np.asarray(values_by_tx, dtype=np.float64)
        if values_by_tx.ndim != len(expected_shape) + 1 or tuple(values_by_tx.shape[1:]) != tuple(expected_shape):
            raise ValueError(
                f"Per-transmitter metric mismatch: values_by_tx={values_by_tx.shape}, "
                f"cells={expected_shape}"
            )
        tx_count = int(values_by_tx.shape[0])
        tx_linear, tx_db = metric_db(values_by_tx, metric)

    def add_tx_fields(row, index):
        row["tx_count"] = tx_count
        if tx_linear is None:
            return row
        for tx_index in range(tx_count):
            token = f"{tx_index:03d}"
            row[f"{linear_key}_tx_{token}"] = float(tx_linear[(tx_index,) + index])
            row[f"{db_key}_tx_{token}"] = float(tx_db[(tx_index,) + index])
        return row

    radio = frame["radio_map"]
    rows = []
    if centers.ndim == 3:
        ny, nx, _ = centers.shape
        cell_area = float(radio["cell_size_x"]) * float(radio["cell_size_y"])
        for iy in range(ny):
            for ix in range(nx):
                p = centers[iy, ix]
                row = {
                    "frame": int(frame["frame"]),
                    "x": float(p[0]),
                    "y": float(p[1]),
                    "z": float(p[2]),
                    "cell_size_x": float(radio["cell_size_x"]),
                    "cell_size_y": float(radio["cell_size_y"]),
                    "is_projected": 0,
                    "cell_index": int(iy * nx + ix),
                    "primitive_index": -1,
                    "normal_x": 0.0,
                    "normal_y": 0.0,
                    "normal_z": 1.0,
                    "cell_area": cell_area,
                    "associated_tx": int(association[iy, ix]),
                    "coverage_valid": int(coverage_valid[iy, ix]),
                    "metric_linear": float(linear[iy, ix]),
                    "metric_db": float(db[iy, ix]),
                    "metric_norm": float(metric_norm[iy, ix]),
                    linear_key: float(linear[iy, ix]),
                    db_key: float(db[iy, ix]),
                }
                rows.append(add_tx_fields(row, (iy, ix)))
        return rows, linear, db, metric_stats

    count = centers.shape[0]
    if surface_cells is None or len(surface_cells) != count:
        raise ValueError(
            f"Projected surface-cell mismatch: metadata={0 if surface_cells is None else len(surface_cells)}, "
            f"radio_map={count}"
        )
    for index in range(count):
        p = centers[index]
        surface = surface_cells[index]
        normal = surface["normal"]
        tangent = surface["tangent"]
        bitangent = surface["bitangent"]
        v0 = surface["triangle_v0"]
        v1 = surface["triangle_v1"]
        v2 = surface["triangle_v2"]
        # The Sionna/Ply primitive order is expected to match the metadata. A
        # center-distance check catches accidental mesh reordering early.
        if float(np.linalg.norm(p - surface["center"])) > 1e-3:
            raise ValueError(
                f"Projected primitive {index} center does not match the Blender reference mesh"
            )
        row = {
            "frame": int(frame["frame"]),
            "x": float(p[0]),
            "y": float(p[1]),
            "z": float(p[2]),
            "cell_size_x": 0.0,
            "cell_size_y": 0.0,
            "is_projected": 1,
            "cell_index": int(index),
            "primitive_index": int(surface["primitive_index"]),
            "normal_x": float(normal[0]),
            "normal_y": float(normal[1]),
            "normal_z": float(normal[2]),
            "tangent_x": float(tangent[0]),
            "tangent_y": float(tangent[1]),
            "tangent_z": float(tangent[2]),
            "bitangent_x": float(bitangent[0]),
            "bitangent_y": float(bitangent[1]),
            "bitangent_z": float(bitangent[2]),
            "triangle_v0_x": float(v0[0]),
            "triangle_v0_y": float(v0[1]),
            "triangle_v0_z": float(v0[2]),
            "triangle_v1_x": float(v1[0]),
            "triangle_v1_y": float(v1[1]),
            "triangle_v1_z": float(v1[2]),
            "triangle_v2_x": float(v2[0]),
            "triangle_v2_y": float(v2[1]),
            "triangle_v2_z": float(v2[2]),
            "edge_length_01": float(surface["edge_length_01"]),
            "edge_length_12": float(surface["edge_length_12"]),
            "edge_length_20": float(surface["edge_length_20"]),
            "cell_area": float(surface["cell_area"]),
            "associated_tx": int(association[index]),
            "coverage_valid": int(coverage_valid[index]),
            "metric_linear": float(linear[index]),
            "metric_db": float(db[index]),
            "metric_norm": float(metric_norm[index]),
            linear_key: float(linear[index]),
            db_key: float(db[index]),
        }
        rows.append(add_tx_fields(row, (index,)))
    return rows, linear, db, metric_stats


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


def solve_frame(scene, solver, runtime, frame):
    material_summary = configure_frame(scene, frame, runtime)
    sim = frame["simulation"]
    radio = frame["radio_map"]
    metric = metric_name(frame)
    surface_mode = str(radio.get("surface_mode", "PLANAR")).upper()
    solver_kwargs = dict(
        scene=scene,
        samples_per_tx=int(sim["samples_per_src"]),
        max_depth=int(sim["max_depth"]),
        los=bool(sim["los"]),
        specular_reflection=bool(sim["specular_reflection"]),
        diffuse_reflection=bool(sim["diffuse_reflection"]),
        refraction=bool(sim["refraction"]),
        diffraction=bool(sim["diffraction"]),
        edge_diffraction=bool(sim.get("edge_diffraction", False)),
        diffraction_lit_region=bool(sim.get("diffraction_lit_region", True)),
        seed=int(sim["seed"]),
    )
    surface_cells = None
    if surface_mode == "PROJECTED":
        mesh_path = Path(str(radio.get("measurement_surface_mesh", "")))
        if not mesh_path.is_file():
            raise RuntimeError(f"Projected measurement surface is missing: {mesh_path}")
        measurement_surface = runtime["load_mesh"](
            str(mesh_path), flip_normals=False
        )
        solver_kwargs["measurement_surface"] = measurement_surface
        surface_cells = load_surface_cells(
            radio.get("measurement_surface_cells_csv", "")
        )
    else:
        surface_mode = "PLANAR"
        solver_kwargs.update({
            "center": [
                float(radio["center_x"]),
                float(radio["center_y"]),
                float(radio["height"]),
            ],
            "orientation": [0.0, 0.0, 0.0],
            "size": [float(radio["size_x"]), float(radio["size_y"])],
            "cell_size": [
                float(radio["cell_size_x"]),
                float(radio["cell_size_y"]),
            ],
        })
    result = solver(**solver_kwargs)
    centers = normalize_cell_centers(result.cell_centers)
    metric_values = selected_metric_map(result, metric, centers)
    values_by_tx = metric_maps_by_tx(result, metric, centers)
    association = tx_association_map(result, metric, metric_values, centers)
    rows, linear, db, metric_stats = build_rows(
        frame, centers, metric_values, association, metric,
        surface_cells=surface_cells,
        values_by_tx=values_by_tx if surface_cells is not None else None,
    )
    output = frame.get("output", {})
    keep_external = bool(runtime.get("output", {}).get("keep_external_results", True))
    if keep_external and output.get("results_npz"):
        npz_payload = {
            "cell_centers": np.asarray(centers, dtype=np.float32),
            "metric": np.asarray(metric),
            "surface_mode": np.asarray(surface_mode.lower()),
            "values": np.asarray(linear, dtype=np.float32),
            "values_db": np.asarray(db, dtype=np.float32),
            "associated_tx": np.asarray(association, dtype=np.int32),
            "coverage_valid": np.asarray(
                [row["coverage_valid"] for row in rows], dtype=np.int32
            ).reshape(np.asarray(linear).shape),
            "metric_norm": np.asarray(
                [row["metric_norm"] for row in rows], dtype=np.float32
            ).reshape(np.asarray(linear).shape),
        }
        if surface_cells is not None:
            tx_linear, tx_db = metric_db(values_by_tx, metric)
            npz_payload.update({
                "primitive_index": np.asarray(
                    [item["primitive_index"] for item in surface_cells], dtype=np.int32
                ),
                "surface_normal": np.asarray(
                    [item["normal"] for item in surface_cells], dtype=np.float32
                ),
                "cell_area": np.asarray(
                    [item["cell_area"] for item in surface_cells], dtype=np.float32
                ),
                "triangle_vertices": np.asarray([
                    [item["triangle_v0"], item["triangle_v1"], item["triangle_v2"]]
                    for item in surface_cells
                ], dtype=np.float32),
                "values_by_tx": np.asarray(tx_linear, dtype=np.float32),
                "values_db_by_tx": np.asarray(tx_db, dtype=np.float32),
            })
        np.savez_compressed(output["results_npz"], **npz_payload)
    frame_result = {
        "frame": int(frame["frame"]),
        "simulation": dict(sim),
        "radio_map": dict(radio),
        "transmitters": list(frame["transmitters"]),
        "materials": material_summary,
        "metric": metric,
        "surface_mode": surface_mode,
        "reference_mesh_blender_name": radio.get("reference_mesh_blender_name", ""),
        "measurement_surface_triangle_count": int(
            radio.get("measurement_surface_triangle_count", 0) or 0
        ),
        "association_metric": metric,
        "association_tx_names": list(scene.transmitters.keys()),
        "tx_count": int(values_by_tx.shape[0]),
        "point_count": len(rows),
        **metric_stats,
        "results_json": output.get("results_json", ""),
        "results_npz": output.get("results_npz", ""),
    }
    if keep_external and output.get("results_json"):
        write_json(output["results_json"], {
            "schema_version": 7, "created_utc": now_utc(),
            "scene_xml_sha256": runtime["scene_xml_sha256"], **frame_result,
        })
    if keep_external and output.get("status_json"):
        write_status_json(output["status_json"], {"state": "finished", "updated_utc": now_utc(), **frame_result})
    return frame_result, rows


def main(config_path):
    config_path = Path(config_path).resolve()
    with open(config_path, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    output = config["output"]
    status_path = Path(output["status_json"])
    payloads = [merged_frame(config, item) for item in frame_payloads(config)]
    if not payloads:
        raise RuntimeError("The radio-map config contains no frames")
    write_status_json(status_path, {"state": "starting", "created_utc": now_utc(), "config": str(config_path), "frame_count": len(payloads)})

    import mitsuba as mi
    from sionna.rt import (
        load_scene, load_mesh, PlanarArray, RadioMapSolver, Transmitter,
        RadioMaterial, ITURadioMaterial, LambertianPattern,
        DirectivePattern, BackscatteringPattern,
    )
    runtime = dict(config)
    runtime.update({
        "PlanarArray": PlanarArray,
        "load_mesh": load_mesh,
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
        write_status_json(status_path, {
            "state": "solving", "updated_utc": now_utc(), "frame": int(frame["frame"]),
            "frame_index": index, "frame_count": len(payloads),
            "completed_frames": len(frame_results), "frequency_ghz": float(frame["simulation"]["frequency_ghz"]),
            "metric": metric_name(frame), "num_tx": len(frame["transmitters"]),
            "sionna_rt_version": package_version(), "mitsuba_version": getattr(mi, "__version__", "unknown"),
        })
        frame_runtime = dict(runtime)
        frame_runtime["scene_xml"] = frame_scene_xml
        frame_runtime["scene_xml_sha256"] = frame.get("scene_xml_sha256", config.get("scene_xml_sha256", ""))
        frame_result, rows = solve_frame(scene, solver, frame_runtime, frame)
        frame_results.append(frame_result)
        all_rows.extend(rows)

    combined_csv = Path(output["results_csv"])
    write_csv(combined_csv, all_rows)
    manifest_path = Path(output.get("frames_manifest_json") or output["results_json"])
    metrics = sorted({item["metric"] for item in frame_results})
    valid_db = [
        float(row["metric_db"]) for row in all_rows
        if int(row.get("coverage_valid", 0) or 0) != 0
        and np.isfinite(float(row.get("metric_db", -300.0)))
    ]
    valid_count = len(valid_db)
    combined_stats = {
        "valid_cell_count": valid_count,
        "invalid_cell_count": max(0, len(all_rows) - valid_count),
        "coverage_fraction": (float(valid_count) / float(len(all_rows))) if all_rows else 0.0,
        "metric_db_min": min(valid_db) if valid_db else -300.0,
        "metric_db_max": max(valid_db) if valid_db else -300.0,
        "metric_db_median": float(np.median(valid_db)) if valid_db else -300.0,
    }
    manifest = {
        "schema_version": 7, "created_utc": now_utc(), "scene_xml": config["scene_xml"],
        "scene_xml_sha256": config["scene_xml_sha256"], "frame_count": len(frame_results),
        "point_count": len(all_rows), "metrics": metrics, "results_csv": str(combined_csv),
        **combined_stats,
        "frames": frame_results, "procedural_scene": bool(config.get("procedural_scene", False)),
    }
    write_json(manifest_path, manifest)
    if Path(output["results_json"]) != manifest_path:
        write_json(output["results_json"], manifest)
    write_status_json(status_path, {
        "state": "finished", "updated_utc": now_utc(), "frame_count": len(frame_results),
        "completed_frames": len(frame_results), "point_count": len(all_rows), "metrics": metrics,
        **combined_stats,
        "results_csv": str(combined_csv), "results_json": str(manifest_path), "frames": frame_results,
    })
    print(json.dumps({"ok": True, "frame_count": len(frame_results), "point_count": len(all_rows), "metrics": metrics, "results_csv": str(combined_csv)}))
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
