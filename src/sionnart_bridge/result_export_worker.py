#!/usr/bin/env python3
"""Durable result exporters for SionnaRT-Bridge.

Simulation workers always create short-lived artifacts needed by Blender to
validate/embed results. This module turns a completed run into the user-selected
export: a traceable CSV + metadata JSON, or a structured HDF5 + metadata JSON.
It runs in the simulation worker process, never on Blender's UI thread.

HDF5 schema v5 stores dense coverage maps as explicit time-series tensors and
validates their spatial axes before stacking:
2D planar maps use (frame, y, x), 3D maps use (frame, z, y, x), and projected
surface maps use (frame, cell). Ragged propagation paths remain per-frame while
a derived, columnar path-point table provides convenient analysis access.
"""

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


HDF5_SCHEMA_VERSION = 5
EXPORT_METADATA_SCHEMA_VERSION = 5


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def load_json(path):
    path = Path(path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def json_safe(value):
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def json_text(value):
    return json.dumps(json_safe(value), ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(json_safe(payload), handle, indent=2, ensure_ascii=False, allow_nan=False)
    temporary.replace(path)


def build_category_metadata(config, manifest, *, category, source_csv):
    schemas = {
        "paths": "sionna_path_points_v3_mobility",
        "coverage_2d": "sionna_coverage_2d_v2_dense_frames",
        "coverage_3d": "sionna_coverage_3d_v3_4d_volume_time_series",
    }
    return {
        "simulation_category": category,
        "simulation_data_schema": schemas.get(category, "unknown"),
        "hdf5_schema_version": HDF5_SCHEMA_VERSION,
        "created_utc": config.get("created_utc"),
        "bridge_version": config.get("bridge_version", "unknown"),
        "blend_file": config.get("blend_file"),
        "scene_name": config.get("scene_name"),
        "scene_xml_sha256": config.get("scene_xml_sha256", ""),
        "procedural_scene": bool(config.get("procedural_scene", False)),
        "source_csv_columns_file": Path(source_csv).name if source_csv else "",
        "parameters": config,
        "results_summary": manifest,
    }


def build_export_metadata(existing, category_metadata, *, export_format, export_file, run_id):
    payload = dict(existing or {})
    if payload.get("schema") != "sionna_rt_bridge_export_metadata":
        payload = {}
    payload.update({
        "schema": "sionna_rt_bridge_export_metadata",
        "schema_version": EXPORT_METADATA_SCHEMA_VERSION,
        "hdf5_schema_version": HDF5_SCHEMA_VERSION if export_format == "HDF5" else None,
        "export_format": export_format,
        "run_id": run_id,
        "exported_utc": now_utc(),
        "export_file": str(Path(export_file).name),
    })
    categories = dict(payload.get("categories") or {})
    category = str(category_metadata.get("simulation_category") or "unknown")
    categories[category] = category_metadata
    payload["categories"] = categories
    payload["simulation_categories"] = sorted(categories)
    created_values = [
        str(item.get("created_utc")) for item in categories.values()
        if item.get("created_utc")
    ]
    payload["created_utc"] = min(created_values) if created_values else None
    first = categories[sorted(categories)[0]] if categories else {}
    payload["bridge_version"] = first.get("bridge_version", "unknown")
    payload["blend_file"] = first.get("blend_file")
    payload["scene_name"] = first.get("scene_name")
    return payload


def _string_dtype(h5py):
    return h5py.string_dtype(encoding="utf-8")


def _compression_kwargs(data):
    data = np.asarray(data)
    if data.ndim > 0 and data.size > 32 and data.dtype.kind not in {"U", "O"}:
        return {"compression": "gzip", "shuffle": True}
    return {}


def _safe_dataset(group, name, value, h5py, *, labels=None, scales=None):
    data = np.asarray(value)
    if data.dtype.kind in {"U", "O"}:
        if data.ndim == 0:
            ds = group.create_dataset(name, data=str(data.item()), dtype=_string_dtype(h5py))
        else:
            strings = np.asarray([str(item) for item in data.reshape(-1)], dtype=object).reshape(data.shape)
            ds = group.create_dataset(name, data=strings, dtype=_string_dtype(h5py))
    else:
        ds = group.create_dataset(name, data=data, **_compression_kwargs(data))
    _label_dimensions(ds, labels, scales)
    return ds


def _label_dimensions(dataset, labels=None, scales=None):
    if not labels:
        return
    scales = scales or {}
    for axis, label in enumerate(labels):
        if axis >= dataset.ndim:
            break
        dataset.dims[axis].label = str(label)
        scale = scales.get(label)
        if scale is not None and getattr(scale, "ndim", 0) == 1:
            if int(scale.shape[0]) == int(dataset.shape[axis]):
                try:
                    dataset.dims[axis].attach_scale(scale)
                except (RuntimeError, ValueError):
                    pass


def _make_scale(group, name, values, h5py, label=None):
    ds = _safe_dataset(group, name, values, h5py)
    try:
        ds.make_scale(label or name)
    except (RuntimeError, ValueError):
        pass
    return ds


def _replace_group(parent, name):
    if name in parent:
        del parent[name]
    return parent.create_group(name)


def _looks_int(values):
    found = False
    for value in values:
        value = value.strip()
        if value == "":
            continue
        found = True
        if re.fullmatch(r"[+-]?\d+", value) is None:
            return False
    return found


def _looks_float(values):
    found = False
    for value in values:
        value = value.strip()
        if value == "":
            continue
        found = True
        try:
            float(value)
        except ValueError:
            return False
    return found


def write_csv_table(parent, csv_path, h5py, *, group_name="table"):
    """Store the category CSV as compressed columnar HDF5 datasets."""
    csv_path = Path(csv_path)
    if not csv_path.exists():
        return None

    with open(csv_path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        preview = []
        for _ in range(512):
            try:
                preview.append(next(reader))
            except StopIteration:
                break

    table = parent.create_group(group_name)
    table.attrs["source_csv_name"] = csv_path.name
    table.attrs["column_order_json"] = json.dumps(columns)
    table.attrs["representation"] = "derived_columnar_table"
    if not columns:
        table.attrs["row_count"] = 0
        return table

    kinds = {}
    datasets = {}
    for name in columns:
        values = [row.get(name, "") for row in preview]
        if _looks_int(values):
            kinds[name], dtype = "int", np.int64
        elif _looks_float(values):
            kinds[name], dtype = "float", np.float64
        else:
            kinds[name], dtype = "string", _string_dtype(h5py)
        datasets[name] = table.create_dataset(
            name, shape=(0,), maxshape=(None,), chunks=(4096,),
            compression="gzip", shuffle=(kinds[name] != "string"), dtype=dtype,
        )
        datasets[name].attrs["logical_type"] = kinds[name]
        datasets[name].dims[0].label = "row"

    def append_batch(batch):
        if not batch:
            return 0
        start = datasets[columns[0]].shape[0]
        end = start + len(batch)
        for name in columns:
            ds = datasets[name]
            ds.resize((end,))
            values = [row.get(name, "") for row in batch]
            kind = kinds[name]
            if kind == "int":
                ds[start:end] = [int(value) if value.strip() else 0 for value in values]
            elif kind == "float":
                ds[start:end] = [float(value) if value.strip() else np.nan for value in values]
            else:
                ds[start:end] = values
        return len(batch)

    row_count = 0
    with open(csv_path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        batch = []
        for row in reader:
            batch.append(row)
            if len(batch) >= 4096:
                row_count += append_batch(batch)
                batch = []
        row_count += append_batch(batch)
    table.attrs["row_count"] = row_count
    return table


def frame_manifest_map(manifest):
    return {int(item.get("frame", 0)): item for item in (manifest.get("frames") or [])}


def _frame_records(config, manifest):
    manifest_frames = frame_manifest_map(manifest)
    records = []
    for frame in config.get("frames") or []:
        frame_number = int(frame.get("frame", 0))
        records.append((frame_number, frame, manifest_frames.get(frame_number, {})))
    return records


def _frame_npz_path(frame):
    return Path(str((frame.get("output") or {}).get("results_npz") or ""))


def _array_digest(value):
    arr = np.asarray(value)
    digest = hashlib.sha256()
    digest.update(str(arr.dtype).encode("utf-8"))
    digest.update(str(tuple(arr.shape)).encode("utf-8"))
    if arr.dtype.kind in {"U", "O"}:
        digest.update(json_text(arr.tolist()).encode("utf-8"))
    else:
        digest.update(np.ascontiguousarray(arr).tobytes())
    return digest.hexdigest()


def write_frame_metadata(sim_group, config, manifest, h5py, *, frame_scale=None):
    """Write one column per frame instead of hiding metadata in frame groups."""
    records = _frame_records(config, manifest)
    group = sim_group.create_group("frame_metadata")
    frame_numbers = np.asarray([item[0] for item in records], dtype=np.int32)
    times = np.asarray([float(item[1].get("time_seconds", np.nan)) for item in records], dtype=np.float64)
    if frame_scale is None:
        frame_scale = _make_scale(group, "frame", frame_numbers, h5py, "frame")
    else:
        group["frame"] = frame_scale
    _safe_dataset(group, "time_seconds", times, h5py, labels=["frame"], scales={"frame": frame_scale})
    _safe_dataset(
        group, "input_json", [json_text(item[1]) for item in records], h5py,
        labels=["frame"], scales={"frame": frame_scale},
    )
    _safe_dataset(
        group, "result_metadata_json", [json_text(item[2]) for item in records], h5py,
        labels=["frame"], scales={"frame": frame_scale},
    )
    _safe_dataset(
        group, "scene_xml_sha256",
        [str(item[1].get("scene_xml_sha256") or config.get("scene_xml_sha256") or "") for item in records],
        h5py, labels=["frame"], scales={"frame": frame_scale},
    )
    _safe_dataset(
        group, "geometry_signature",
        [str((item[1].get("procedural_geometry_stats") or {}).get("geometry_signature") or "") for item in records],
        h5py, labels=["frame"], scales={"frame": frame_scale},
    )
    _safe_dataset(
        group, "scene_xml",
        [str(item[1].get("scene_xml") or config.get("scene_xml") or "") for item in records],
        h5py, labels=["frame"], scales={"frame": frame_scale},
    )
    _safe_dataset(
        group, "configured_materials_json",
        [json_text(item[1].get("materials") or []) for item in records],
        h5py, labels=["frame"], scales={"frame": frame_scale},
    )
    _safe_dataset(
        group, "evaluated_materials_json",
        [json_text(item[2].get("materials") or []) for item in records],
        h5py, labels=["frame"], scales={"frame": frame_scale},
    )

    def device_matrix(key, prefix):
        lists = [item[1].get(key) or [] for item in records]
        if not lists:
            return
        names = [[str(dev.get("name") or dev.get("base_name") or "") for dev in devices] for devices in lists]
        if not names or any(row != names[0] for row in names[1:]):
            group.create_dataset(f"{prefix}_devices_json", data=np.asarray([json_text(v) for v in lists], dtype=object), dtype=_string_dtype(h5py))
            return
        count = len(names[0])
        if count == 0:
            return
        name_ds = _make_scale(group, f"{prefix}_name", names[0], h5py, f"{prefix}")
        positions = np.asarray([[dev.get("position", [np.nan] * 3) for dev in devices] for devices in lists], dtype=np.float64)
        velocities = np.asarray([[dev.get("velocity_m_s", [0.0] * 3) for dev in devices] for devices in lists], dtype=np.float64)
        xyz = _make_scale(group, f"{prefix}_xyz", ["x", "y", "z"], h5py, "xyz")
        scales = {"frame": frame_scale, prefix: name_ds, "xyz": xyz}
        _safe_dataset(group, f"{prefix}_positions_m", positions, h5py, labels=["frame", prefix, "xyz"], scales=scales)
        _safe_dataset(group, f"{prefix}_velocities_m_s", velocities, h5py, labels=["frame", prefix, "xyz"], scales=scales)

    device_matrix("transmitters", "tx")
    device_matrix("receivers", "rx")
    return group


def write_path_frame_payloads(sim_group, config, manifest, h5py):
    records = _frame_records(config, manifest)
    frames_group = sim_group.create_group("frames")
    for frame_number, frame, result_meta in records:
        group = frames_group.create_group(f"frame_{frame_number:06d}")
        group.attrs["frame"] = frame_number
        group.create_dataset("input_json", data=json_text(frame), dtype=_string_dtype(h5py))
        group.create_dataset("result_metadata_json", data=json_text(result_meta), dtype=_string_dtype(h5py))
        npz_path = _frame_npz_path(frame)
        if npz_path.exists():
            raw = group.create_group("raw")
            with np.load(npz_path, allow_pickle=False) as archive:
                for key in archive.files:
                    _safe_dataset(raw, key, archive[key], h5py)


def write_schema_metadata(meta_group, h5py):
    schema = _replace_group(meta_group, "schema")
    schema.attrs["hdf5_schema_version"] = HDF5_SCHEMA_VERSION
    schema.attrs["coverage_2d_dimensions"] = "frame,y,x (planar) or frame,cell (projected)"
    schema.attrs["coverage_3d_dimensions"] = "frame,z,y,x"
    schema.attrs["coverage_3d_rank"] = 4
    schema.attrs["coverage_3d_primary_dataset"] = "/simulations/coverage_3d/data/values_db"
    schema.attrs["coverage_3d_optional_per_tx_dimensions"] = "frame,tx,z,y,x"
    schema.attrs["paths_layout"] = "derived_path_points plus ragged per-frame raw tensors"
    schema.attrs["tile_spatial_dataset_path"] = "/spatial_datasets/Tile_spacial_dataset"
    schema.attrs["coverage_tile_join"] = (
        "Coverage cell-center XY is mapped to Tile_spacial_dataset; spatial_join/tile_index "
        "links coverage cells to the complete tile attribute table."
    )
    enums = schema.create_group("enums")
    _safe_dataset(enums, "point_role_id", [0, 1, 2, 3], h5py)
    _safe_dataset(enums, "point_role_name", ["none", "tx", "interaction", "rx"], h5py)
    _safe_dataset(enums, "interaction_type_id", [0, 1, 2, 3, 4, 5, 6], h5py)
    _safe_dataset(
        enums, "interaction_type_name",
        ["endpoint_none", "los_reserved", "specular", "diffuse", "refraction", "diffraction", "mixed"], h5py,
    )


def _coverage_dimension_labels(category, key, shape, *, framed):
    shape = tuple(shape)
    prefix = ["frame"] if framed else []
    if category == "coverage_2d":
        if key in {
            "values", "values_db", "associated_tx", "coverage_valid", "metric_norm",
            "path_gain", "path_gain_db", "rss", "rss_dbm", "sinr", "sinr_db",
        }:
            if len(shape) == 2:
                return prefix + ["y", "x"]
            if len(shape) == 1:
                return prefix + ["cell"]
        if key in {"values_by_tx", "values_db_by_tx"}:
            if len(shape) == 3:
                return prefix + ["tx", "y", "x"]
            if len(shape) == 2:
                return prefix + ["tx", "cell"]
        if key == "cell_centers":
            if len(shape) == 3:
                return prefix + ["y", "x", "xyz"]
            if len(shape) == 2:
                return prefix + ["cell", "xyz"]
        if key in {"primitive_index", "cell_area"} and len(shape) == 1:
            return prefix + ["cell"]
        if key == "surface_normal" and len(shape) == 2:
            return prefix + ["cell", "xyz"]
        if key == "triangle_vertices" and len(shape) == 3:
            return prefix + ["cell", "triangle_vertex", "xyz"]
    elif category == "coverage_3d":
        if key in {
            "values", "values_db", "associated_tx", "coverage_valid", "metric_norm",
            "path_gain", "path_gain_db", "rss", "rss_dbm", "sinr", "sinr_db",
        }:
            if len(shape) == 3:
                return prefix + ["z", "y", "x"]
        if key in {"values_by_tx", "values_db_by_tx"}:
            if len(shape) == 4:
                return prefix + ["tx", "z", "y", "x"]
        if key == "cell_centers" and len(shape) == 4:
            return prefix + ["z", "y", "x", "xyz"]
        if key == "layer_heights" and len(shape) == 1:
            return prefix + ["z"]
    return prefix + [f"dim_{index}" for index in range(len(shape))]


def _rectilinear_coordinates(category, centers):
    centers = np.asarray(centers)
    if category == "coverage_2d" and centers.ndim == 3 and centers.shape[-1] == 3:
        x = centers[0, :, 0]
        y = centers[:, 0, 1]
        if np.allclose(centers[:, :, 0], x[None, :]) and np.allclose(centers[:, :, 1], y[:, None]):
            z = centers[:, :, 2]
            return {"x": x, "y": y, "z_plane": np.asarray(float(np.nanmean(z)))}
    if category == "coverage_3d" and centers.ndim == 4 and centers.shape[-1] == 3:
        x = centers[0, 0, :, 0]
        y = centers[0, :, 0, 1]
        z = centers[:, 0, 0, 2]
        if (
            np.allclose(centers[..., 0], x[None, None, :])
            and np.allclose(centers[..., 1], y[None, :, None])
            and np.allclose(centers[..., 2], z[:, None, None])
        ):
            return {"x": x, "y": y, "z": z}
    return {}


def _inspect_coverage_archives(config, category):
    """Inspect frame NPZ files without retaining all maps in memory."""
    records = []
    coordinate_keys = {
        "coverage_2d": {"cell_centers", "primitive_index", "surface_normal", "cell_area", "triangle_vertices"},
        "coverage_3d": {"cell_centers", "layer_heights"},
    }[category]
    for frame in config.get("frames") or []:
        path = _frame_npz_path(frame)
        item = {"frame": int(frame.get("frame", 0)), "path": path, "specs": {}, "digests": {}, "scalars": {}}
        if path.exists():
            with np.load(path, allow_pickle=False) as archive:
                for key in archive.files:
                    value = np.asarray(archive[key])
                    item["specs"][key] = (tuple(value.shape), str(value.dtype), value.dtype.kind)
                    if value.ndim == 0:
                        try:
                            item["scalars"][key] = value.item()
                        except ValueError:
                            item["scalars"][key] = str(value)
                    elif key in coordinate_keys:
                        item["digests"][key] = _array_digest(value)
        records.append(item)
    return records


def _consistent_shape(records, key):
    specs = [item["specs"].get(key) for item in records]
    if not specs or any(spec is None for spec in specs):
        return None
    shape = specs[0][0]
    if any(spec[0] != shape for spec in specs[1:]):
        return None
    return shape


def _shared_coordinate(records, key):
    shape = _consistent_shape(records, key)
    if shape is None:
        return False
    digests = [item["digests"].get(key) for item in records]
    return bool(digests and all(value is not None for value in digests) and len(set(digests)) == 1)


def _coverage_3d_expected_shape(records, inspections):
    """Return a validated common (z, y, x) shape for dense 3D coverage.

    The worker writes each frame as a Z stack of horizontal Y/X maps. We only
    expose the canonical 4D HDF5 tensor when all frames agree on that shape and
    the coordinate arrays are compatible with it.
    """
    shape = _consistent_shape(inspections, "values_db") or _consistent_shape(inspections, "values")
    if shape is None or len(shape) != 3:
        return None
    z_count, y_count, x_count = map(int, shape)
    for item in inspections:
        centers = item["specs"].get("cell_centers")
        if centers is not None and tuple(centers[0]) != (z_count, y_count, x_count, 3):
            return None
        heights = item["specs"].get("layer_heights")
        if heights is not None and tuple(heights[0]) != (z_count,):
            return None
    return (z_count, y_count, x_count)


def _annotate_coverage_dataset(dataset, *, category, key, labels):
    """Add machine-readable tensor semantics in addition to HDF5 dim labels."""
    if not labels:
        return
    dataset.attrs["dimension_order"] = ",".join(labels)
    dataset.attrs["rank"] = int(dataset.ndim)
    if category == "coverage_3d" and labels[:4] == ["frame", "z", "y", "x"]:
        dataset.attrs["representation"] = "dense_4d_volume_time_series"
        dataset.attrs["spatial_rank"] = 3
        dataset.attrs["time_axis"] = 0
        dataset.attrs["z_axis"] = 1
        dataset.attrs["y_axis"] = 2
        dataset.attrs["x_axis"] = 3
    elif category == "coverage_3d" and labels[:5] == ["frame", "tx", "z", "y", "x"]:
        dataset.attrs["representation"] = "dense_5d_per_tx_volume_time_series"
        dataset.attrs["spatial_rank"] = 3
        dataset.attrs["time_axis"] = 0
        dataset.attrs["tx_axis"] = 1
        dataset.attrs["z_axis"] = 2
        dataset.attrs["y_axis"] = 3
        dataset.attrs["x_axis"] = 4
    elif category == "coverage_2d" and labels[:3] == ["frame", "y", "x"]:
        dataset.attrs["representation"] = "dense_3d_planar_time_series"
        dataset.attrs["spatial_rank"] = 2


def _create_stacked_dataset(group, key, first, frame_count, h5py, labels, scales, *, category=None):
    first = np.asarray(first)
    shape = (frame_count,) + tuple(first.shape)
    dtype = first.dtype
    if dtype.kind in {"U", "O"}:
        return group.create_dataset(key, shape=shape, dtype=_string_dtype(h5py))
    ds = group.create_dataset(
        key, shape=shape, dtype=dtype, chunks=True,
        compression="gzip" if first.size > 8 else None,
        shuffle=bool(first.size > 8),
    )
    _label_dimensions(ds, labels, scales)
    if category is not None:
        _annotate_coverage_dataset(ds, category=category, key=key, labels=labels)
    return ds


def write_coverage_tensor_payloads(sim_group, config, manifest, h5py, category):
    """Write dense coverage frames along an explicit frame dimension.

    If an individual raw array changes shape between frames, only that array
    falls back to ``frame_extras/frame_x/raw``. Main maps remain stacked when
    their grid shape is stable.
    """
    records = _frame_records(config, manifest)
    inspections = _inspect_coverage_archives(config, category)
    if not records or len(inspections) != len(records) or any(not item["path"].exists() for item in inspections):
        sim_group.attrs["layout"] = "per_frame_fallback_v1"
        write_path_frame_payloads(sim_group, config, manifest, h5py)
        return

    if category == "coverage_3d":
        expected_zyx = _coverage_3d_expected_shape(records, inspections)
        if expected_zyx is None:
            sim_group.attrs["layout"] = "per_frame_3d_grid_fallback"
            sim_group.attrs["dimension_order"] = "per_frame:z,y,x"
            sim_group.attrs["canonical_4d_available"] = False
            write_path_frame_payloads(sim_group, config, manifest, h5py)
            return
        sim_group.attrs["canonical_4d_available"] = True
        sim_group.attrs["grid_shape_zyx"] = expected_zyx
        sim_group.attrs["dimension_order"] = "frame,z,y,x"
        sim_group.attrs["spatial_rank"] = 3

    coords = sim_group.create_group("coordinates")
    frame_numbers = np.asarray([item[0] for item in records], dtype=np.int32)
    frame_scale = _make_scale(coords, "frame", frame_numbers, h5py, "frame")
    times = np.asarray([float(item[1].get("time_seconds", np.nan)) for item in records], dtype=np.float64)
    _safe_dataset(coords, "time_seconds", times, h5py, labels=["frame"], scales={"frame": frame_scale})
    xyz_scale = _make_scale(coords, "xyz", ["x", "y", "z"], h5py, "xyz")

    # Inspect the first frame for grid coordinates and transmitter count.
    with np.load(inspections[0]["path"], allow_pickle=False) as first_archive:
        first_centers = np.asarray(first_archive["cell_centers"]) if "cell_centers" in first_archive.files else None
        centers_are_shared = _shared_coordinate(inspections, "cell_centers")
        rect = (
            _rectilinear_coordinates(category, first_centers)
            if first_centers is not None and centers_are_shared else {}
        )
        for axis in ("x", "y", "z"):
            if axis in rect:
                _make_scale(coords, axis, rect[axis], h5py, axis)
        if "z_plane" in rect:
            _safe_dataset(coords, "z_plane", rect["z_plane"], h5py)
        if category == "coverage_2d" and first_centers is not None and first_centers.ndim == 2:
            _make_scale(coords, "cell", np.arange(first_centers.shape[0], dtype=np.int32), h5py, "cell")
        if category == "coverage_3d" and "layer_heights" in first_archive.files and "z" not in coords:
            _make_scale(coords, "z", np.asarray(first_archive["layer_heights"]), h5py, "z")

    # TX names provide a useful scale for values_by_tx when the count is stable.
    tx_lists = [frame.get("transmitters") or [] for _, frame, _ in records]
    tx_names = [[str(item.get("name") or item.get("base_name") or "") for item in items] for items in tx_lists]
    if tx_names and all(row == tx_names[0] for row in tx_names[1:]) and tx_names[0]:
        _make_scale(coords, "tx", tx_names[0], h5py, "tx")

    scale_map = {name: coords[name] for name in ("frame", "x", "y", "z", "cell", "tx", "xyz") if name in coords}
    for axis in ("x", "y", "z"):
        if axis in coords:
            coords[axis].attrs["units"] = "m"
    coords["time_seconds"].attrs["units"] = "s"
    data_group = sim_group.create_group("data")
    if category == "coverage_3d":
        data_group.attrs["dimension_order"] = "frame,z,y,x"
        data_group.attrs["canonical_rank"] = 4
        data_group.attrs["primary_dataset"] = "values_db"
        data_group.attrs["description"] = "Animated 3D coverage volumes; select one frame to obtain a z,y,x volume."
    coordinate_keys = {
        "coverage_2d": {"cell_centers", "primitive_index", "surface_normal", "cell_area", "triangle_vertices"},
        "coverage_3d": {"cell_centers", "layer_heights"},
    }[category]

    all_keys = sorted(set().union(*(set(item["specs"]) for item in inspections)))
    stacked_datasets = {}
    shared_keys = set()
    fallback_keys = set()
    scalar_values = {}

    # Scalar raw values become attributes when constant, otherwise frame metadata.
    scalar_keys = sorted(set().union(*(set(item["scalars"]) for item in inspections)))
    for key in scalar_keys:
        values = [item["scalars"].get(key) for item in inspections]
        if all(value == values[0] for value in values):
            sim_group.attrs[f"raw_{key}"] = str(values[0])
        else:
            scalar_values[key] = values

    # Create shared coordinates or stacked data arrays.
    with np.load(inspections[0]["path"], allow_pickle=False) as first_archive:
        for key in all_keys:
            if key in scalar_keys:
                continue
            shape = _consistent_shape(inspections, key)
            if shape is None:
                fallback_keys.add(key)
                continue
            first = np.asarray(first_archive[key])
            if key in coordinate_keys and _shared_coordinate(inspections, key):
                labels = _coverage_dimension_labels(category, key, first.shape, framed=False)
                _safe_dataset(coords, key, first, h5py, labels=labels, scales=scale_map)
                shared_keys.add(key)
                continue
            destination = coords if key in coordinate_keys else data_group
            labels = _coverage_dimension_labels(category, key, first.shape, framed=True)
            stacked_datasets[key] = _create_stacked_dataset(
                destination, key, first, len(records), h5py, labels, scale_map, category=category,
            )

    extras = None
    # Fill stacked arrays one frame at a time, keeping peak memory near one NPZ.
    for index, inspection in enumerate(inspections):
        with np.load(inspection["path"], allow_pickle=False) as archive:
            for key, ds in stacked_datasets.items():
                ds[index] = archive[key]
            if fallback_keys:
                if extras is None:
                    extras = sim_group.create_group("frame_extras")
                frame_group = extras.create_group(f"frame_{inspection['frame']:06d}")
                raw = frame_group.create_group("raw")
                for key in sorted(fallback_keys):
                    if key in archive.files:
                        _safe_dataset(raw, key, archive[key], h5py)

    frame_meta = write_frame_metadata(sim_group, config, manifest, h5py, frame_scale=frame_scale)
    for key, values in scalar_values.items():
        _safe_dataset(frame_meta, f"raw_{key}", values, h5py, labels=["frame"], scales={"frame": frame_scale})

    main_shape = _consistent_shape(inspections, "values_db") or _consistent_shape(inspections, "values")
    if category == "coverage_2d":
        if main_shape and len(main_shape) == 2:
            sim_group.attrs["layout"] = "dense_time_series"
            sim_group.attrs["dimension_order"] = "frame,y,x"
        elif main_shape and len(main_shape) == 1:
            sim_group.attrs["layout"] = "projected_surface_time_series"
            sim_group.attrs["dimension_order"] = "frame,cell"
        else:
            sim_group.attrs["layout"] = "mixed_time_series"
    else:
        sim_group.attrs["layout"] = "dense_4d_volume_time_series"
        sim_group.attrs["dimension_order"] = "frame,z,y,x"
        sim_group.attrs["canonical_4d_available"] = True
        sim_group.attrs["primary_dataset_path"] = "data/values_db"
    sim_group.attrs["stacked_frame_count"] = len(records)
    sim_group.attrs["fallback_raw_keys_json"] = json.dumps(sorted(fallback_keys))



_TILE_CONTEXT_ATTRIBUTES = (
    "is_roi",
    "is_buffer",
    "is_building",
    "building_hit_ratio",
    "neighborhood_id",
    "neighborhood_population_total",
    "neighborhood_population_roi",
    "neighborhood_population_analysis",
    "neighborhood_population_density_km2",
    "fraction_population",
    "population_estimate_cell",
    "population_valid",
    "has_base_station",
    "base_station_count",
    "base_station_distinct_operator_count",
    "base_station_primary_operator_id",
    "cell_area_m2",
    "longitude",
    "latitude",
)


def _tile_snapshot_paths(config):
    descriptor = config.get("tile_spatial_dataset") or {}
    npz_path = Path(str(descriptor.get("snapshot_npz") or ""))
    json_path = Path(str(descriptor.get("snapshot_json") or ""))
    if not npz_path.is_file() or not json_path.is_file():
        return descriptor, None, None
    return descriptor, npz_path, json_path


def write_tile_spatial_dataset(h5, config, h5py):
    """Embed Tile_spacial_dataset once and return its HDF5 group.

    The snapshot is produced by Blender before the Sionna worker starts, so the
    HDF5 export contains a self-contained copy of the tile grid and all numeric
    POINT-domain attributes even after temporary worker files are deleted.
    """
    descriptor, npz_path, json_path = _tile_snapshot_paths(config)
    if npz_path is None:
        return None
    metadata = load_json(json_path)
    dataset_name = str(metadata.get("object_name") or descriptor.get("object_name") or "Tile_spacial_dataset")
    root = h5.require_group("spatial_datasets")

    # Use the canonical group name requested by Tile_dataset. If a future object
    # is discovered through metadata under a different name, keep the source name
    # as an attribute but preserve a stable HDF5 path.
    group_name = "Tile_spacial_dataset"
    snapshot_hash = str(descriptor.get("snapshot_sha256") or "")
    if group_name in root:
        existing = root[group_name]
        if snapshot_hash and str(existing.attrs.get("snapshot_sha256", "")) == snapshot_hash:
            return existing
        del root[group_name]
    group = root.create_group(group_name)
    group.attrs["source_object_name"] = dataset_name
    group.attrs["schema"] = str(metadata.get("schema") or "sionna_tile_spatial_dataset_snapshot")
    group.attrs["schema_version"] = int(metadata.get("schema_version") or 1)
    group.attrs["snapshot_sha256"] = snapshot_hash
    group.attrs["point_count"] = int(metadata.get("point_count") or descriptor.get("point_count") or 0)
    group.attrs["coordinate_system"] = "Blender world coordinates, meters"
    group.attrs["relation_key"] = "tile_index (row index); tile_id is preserved as a source attribute"

    meta_group = group.create_group("metadata")
    meta_group.create_dataset("snapshot_json", data=json_text(metadata), dtype=_string_dtype(h5py))
    object_props = metadata.get("object_properties") or {}
    meta_group.create_dataset("object_properties_json", data=json_text(object_props), dtype=_string_dtype(h5py))

    coordinates = group.create_group("coordinates")
    attributes = group.create_group("attributes")
    attr_meta = {str(item.get("npz_key")): item for item in (metadata.get("attributes") or [])}

    with np.load(npz_path, allow_pickle=False) as archive:
        if "positions_world_m" not in archive.files:
            return group
        positions = np.asarray(archive["positions_world_m"], dtype=np.float64)
        point_count = int(positions.shape[0])
        tile_scale = _make_scale(
            coordinates, "tile_index", np.arange(point_count, dtype=np.int64), h5py, "tile"
        )
        xyz_scale = _make_scale(coordinates, "xyz", ["x", "y", "z"], h5py, "xyz")
        pos_ds = _safe_dataset(
            coordinates, "position_world_m", positions, h5py,
            labels=["tile", "xyz"], scales={"tile": tile_scale, "xyz": xyz_scale},
        )
        pos_ds.attrs["units"] = "m"
        if "positions_local_m" in archive.files:
            local_ds = _safe_dataset(
                coordinates, "position_local_m", np.asarray(archive["positions_local_m"]), h5py,
                labels=["tile", "xyz"], scales={"tile": tile_scale, "xyz": xyz_scale},
            )
            local_ds.attrs["units"] = "m"

        for npz_key, item in attr_meta.items():
            if npz_key not in archive.files:
                continue
            name = str(item.get("name") or npz_key)
            value = np.asarray(archive[npz_key])
            if value.ndim < 1 or int(value.shape[0]) != point_count:
                continue
            labels = ["tile"] + [f"component_{i}" for i in range(1, value.ndim)]
            ds = _safe_dataset(
                attributes, name, value, h5py, labels=labels, scales={"tile": tile_scale}
            )
            ds.attrs["blender_data_type"] = str(item.get("data_type") or "")
            ds.attrs["blender_domain"] = str(item.get("domain") or "POINT")
            ds.attrs["source_attribute_name"] = name

    return group


def _tile_axis_table(index_values, centers, sizes):
    index_values = np.asarray(index_values, dtype=np.int64)
    centers = np.asarray(centers, dtype=np.float64)
    sizes = np.asarray(sizes, dtype=np.float64)
    ids = np.unique(index_values)
    rows = []
    for value in ids:
        mask = index_values == value
        center = float(np.nanmedian(centers[mask]))
        size = float(np.nanmedian(sizes[mask])) if np.any(np.isfinite(sizes[mask])) else 0.0
        rows.append((int(value), center, max(0.0, size)))
    rows.sort(key=lambda item: item[1])
    axis_ids = np.asarray([item[0] for item in rows], dtype=np.int64)
    axis_centers = np.asarray([item[1] for item in rows], dtype=np.float64)
    axis_sizes = np.asarray([item[2] for item in rows], dtype=np.float64)
    left = axis_centers - 0.5 * axis_sizes
    right = axis_centers + 0.5 * axis_sizes
    return axis_ids, axis_centers, left, right


def _tile_grid_index(tile_group):
    attrs = tile_group.get("attributes")
    coords = tile_group.get("coordinates")
    if attrs is None or coords is None or "position_world_m" not in coords:
        return None
    positions = np.asarray(coords["position_world_m"], dtype=np.float64)
    point_count = int(positions.shape[0])
    if point_count == 0:
        return None

    def attr(name, default=None):
        if name in attrs:
            return np.asarray(attrs[name])
        return default

    grid_ix = attr("grid_ix")
    grid_iy = attr("grid_iy")
    if grid_ix is None or grid_iy is None:
        return None
    grid_ix = np.asarray(grid_ix, dtype=np.int64)
    grid_iy = np.asarray(grid_iy, dtype=np.int64)
    if len(grid_ix) != point_count or len(grid_iy) != point_count:
        return None

    cell_x = attr("cell_size_x_m")
    cell_y = attr("cell_size_y_m")
    if cell_x is None:
        cell_x = np.full(point_count, float(np.nanmedian(np.diff(np.unique(positions[:, 0])))) if point_count > 1 else 0.0)
    if cell_y is None:
        cell_y = np.full(point_count, float(np.nanmedian(np.diff(np.unique(positions[:, 1])))) if point_count > 1 else 0.0)

    x_ids, x_centers, x_left, x_right = _tile_axis_table(grid_ix, positions[:, 0], cell_x)
    y_ids, y_centers, y_left, y_right = _tile_axis_table(grid_iy, positions[:, 1], cell_y)
    x_id_to_pos = {int(value): index for index, value in enumerate(x_ids)}
    y_id_to_pos = {int(value): index for index, value in enumerate(y_ids)}
    lookup = np.full((len(y_ids), len(x_ids)), -1, dtype=np.int64)
    for tile_index, (ix, iy) in enumerate(zip(grid_ix, grid_iy)):
        xp = x_id_to_pos.get(int(ix))
        yp = y_id_to_pos.get(int(iy))
        if xp is not None and yp is not None:
            lookup[yp, xp] = int(tile_index)
    return {
        "lookup": lookup,
        "x_centers": x_centers, "x_left": x_left, "x_right": x_right,
        "y_centers": y_centers, "y_left": y_left, "y_right": y_right,
        "positions": positions,
    }


def _map_centers_to_tiles(centers, tile_indexer):
    centers = np.asarray(centers, dtype=np.float64)
    if centers.ndim < 2 or centers.shape[-1] < 2 or tile_indexer is None:
        return None, None
    shape = centers.shape[:-1]
    flat = centers.reshape(-1, centers.shape[-1])
    x = flat[:, 0]
    y = flat[:, 1]
    xr = tile_indexer["x_right"]
    yr = tile_indexer["y_right"]
    xp = np.searchsorted(xr, x, side="left")
    yp = np.searchsorted(yr, y, side="left")
    valid = (xp >= 0) & (yp >= 0) & (xp < len(xr)) & (yp < len(yr))
    safe_x = np.clip(xp, 0, max(0, len(xr) - 1))
    safe_y = np.clip(yp, 0, max(0, len(yr) - 1))
    tol = 1e-6
    valid &= x >= tile_indexer["x_left"][safe_x] - tol
    valid &= x <= tile_indexer["x_right"][safe_x] + tol
    valid &= y >= tile_indexer["y_left"][safe_y] - tol
    valid &= y <= tile_indexer["y_right"][safe_y] + tol

    tile = np.full(flat.shape[0], -1, dtype=np.int64)
    if np.any(valid):
        candidate = tile_indexer["lookup"][safe_y[valid], safe_x[valid]]
        tile[valid] = candidate
        valid_indices = np.flatnonzero(valid)
        valid[valid_indices[candidate < 0]] = False
        tile[~valid] = -1

    distance = np.full(flat.shape[0], np.nan, dtype=np.float32)
    mapped = tile >= 0
    if np.any(mapped):
        tile_positions = tile_indexer["positions"][tile[mapped], :2]
        delta = flat[mapped, :2] - tile_positions
        distance[mapped] = np.sqrt(np.sum(delta * delta, axis=1)).astype(np.float32)
    return tile.reshape(shape), distance.reshape(shape)


def _reduce_3d_xy_join(tile_index, distance):
    """3D coverage uses the same tile grid for every Z layer when XY is fixed."""
    if tile_index is None or tile_index.ndim != 3 or tile_index.shape[0] <= 1:
        return tile_index, distance
    first = tile_index[0]
    if np.all(tile_index == first[None, ...]):
        first_distance = distance[0] if distance is not None else None
        return first, first_distance
    return tile_index, distance


def _join_labels(category, array, *, framed):
    ndim = int(np.asarray(array).ndim)
    prefix = ["frame"] if framed else []
    spatial_ndim = ndim - len(prefix)
    if category == "coverage_2d":
        if spatial_ndim == 2:
            return prefix + ["y", "x"]
        if spatial_ndim == 1:
            return prefix + ["cell"]
    if category == "coverage_3d":
        if spatial_ndim == 3:
            return prefix + ["z", "y", "x"]
        if spatial_ndim == 2:
            return prefix + ["y", "x"]
    return prefix + [f"dim_{i}" for i in range(spatial_ndim)]


def _indexed_tile_context(source, tile_index):
    source = np.asarray(source)
    tile_index = np.asarray(tile_index, dtype=np.int64)
    valid = tile_index >= 0
    if source.ndim != 1:
        return None
    if source.dtype.kind == "b":
        result = np.zeros(tile_index.shape, dtype=np.bool_)
    elif source.dtype.kind in {"i", "u"}:
        result = np.full(tile_index.shape, -1, dtype=np.int64)
    else:
        result = np.full(tile_index.shape, np.nan, dtype=np.float32)
    if np.any(valid):
        result[valid] = source[tile_index[valid]]
    return result


def write_coverage_tile_join(sim_group, config, h5py, category, tile_group):
    """Link coverage cells/voxels to Tile_spacial_dataset by XY containment."""
    if tile_group is None:
        return None
    tile_indexer = _tile_grid_index(tile_group)
    if tile_indexer is None:
        return None
    frame_records = config.get("frames") or []
    if not frame_records:
        return None

    joins = []
    distances = []
    for frame in frame_records:
        npz_path = _frame_npz_path(frame)
        if not npz_path.is_file():
            return None
        with np.load(npz_path, allow_pickle=False) as archive:
            if "cell_centers" not in archive.files:
                return None
            centers = np.asarray(archive["cell_centers"])
        tile_index, distance = _map_centers_to_tiles(centers, tile_indexer)
        if category == "coverage_3d":
            tile_index, distance = _reduce_3d_xy_join(tile_index, distance)
        if tile_index is None:
            return None
        joins.append(tile_index)
        distances.append(distance)

    shapes = {tuple(item.shape) for item in joins}
    if len(shapes) != 1:
        return None
    shared = all(np.array_equal(joins[0], item) for item in joins[1:])
    if shared:
        tile_index = joins[0]
        distance = distances[0]
        framed = False
    else:
        tile_index = np.stack(joins, axis=0)
        distance = np.stack(distances, axis=0)
        framed = True

    join_group = sim_group.create_group("spatial_join")
    join_group.attrs["source_dataset_path"] = "/spatial_datasets/Tile_spacial_dataset"
    join_group.attrs["method"] = "coverage cell-center XY contained by Tile_dataset grid cell"
    join_group.attrs["invalid_tile_index"] = -1
    join_group.attrs["shared_across_frames"] = bool(shared)
    join_group.attrs["join_axes"] = ",".join(_join_labels(category, tile_index, framed=framed))
    if category == "coverage_3d" and tile_index.ndim - int(framed) == 2:
        join_group.attrs["broadcast_over_z"] = True
        join_group.attrs["coverage_relation"] = "tile context is y,x and broadcasts over frame,z in coverage data"
    elif category == "coverage_2d":
        join_group.attrs["coverage_relation"] = "tile context aligns to coverage y,x (or projected cell) axes"

    coords = sim_group.get("coordinates")
    scale_map = {}
    if coords is not None:
        for name in ("frame", "x", "y", "z", "cell"):
            if name in coords:
                scale_map[name] = coords[name]
    labels = _join_labels(category, tile_index, framed=framed)
    tile_ds = _safe_dataset(join_group, "tile_index", tile_index, h5py, labels=labels, scales=scale_map)
    tile_ds.attrs["description"] = "Row index into /spatial_datasets/Tile_spacial_dataset"
    distance_ds = _safe_dataset(
        join_group, "distance_to_tile_center_m", distance, h5py, labels=labels, scales=scale_map
    )
    distance_ds.attrs["units"] = "m"
    _safe_dataset(join_group, "inside_tile_dataset", tile_index >= 0, h5py, labels=labels, scales=scale_map)

    attrs = tile_group.get("attributes")
    if attrs is None:
        return join_group
    if "tile_id" in attrs:
        joined_tile_id = _indexed_tile_context(np.asarray(attrs["tile_id"]), tile_index)
        if joined_tile_id is not None:
            ds = _safe_dataset(join_group, "tile_id", joined_tile_id, h5py, labels=labels, scales=scale_map)
            ds.attrs["source_attribute_path"] = "/spatial_datasets/Tile_spacial_dataset/attributes/tile_id"

    context = join_group.create_group("tile_context")
    context.attrs["description"] = (
        "Convenience views of commonly used Tile_dataset attributes. The complete source table "
        "is stored once under /spatial_datasets/Tile_spacial_dataset/attributes."
    )
    for name in _TILE_CONTEXT_ATTRIBUTES:
        if name not in attrs:
            continue
        joined = _indexed_tile_context(np.asarray(attrs[name]), tile_index)
        if joined is None:
            continue
        ds = _safe_dataset(context, name, joined, h5py, labels=labels, scales=scale_map)
        ds.attrs["source_attribute_path"] = f"/spatial_datasets/Tile_spacial_dataset/attributes/{name}"
    return join_group


def export_hdf5(config, manifest, csv_path, export_file, metadata, category):
    import h5py

    export_file = Path(export_file)
    temporary = export_file.with_name(export_file.name + ".tmp")
    if temporary.exists():
        temporary.unlink()
    if export_file.exists():
        shutil.copy2(export_file, temporary)
        mode = "a"
    else:
        mode = "w"

    with h5py.File(temporary, mode) as h5:
        h5.attrs["schema"] = "sionna_rt_bridge_results"
        h5.attrs["schema_version"] = HDF5_SCHEMA_VERSION
        h5.attrs["bridge_version"] = str(metadata.get("bridge_version", "unknown"))
        h5.attrs["run_id"] = str(metadata.get("run_id", ""))
        h5.attrs["created_utc"] = str(metadata.get("created_utc") or "")
        h5.attrs["exported_utc"] = str(metadata.get("exported_utc") or "")
        h5.attrs["simulation_categories_json"] = json.dumps(metadata.get("simulation_categories") or [])

        meta_group = h5.require_group("metadata")
        if "export_json" in meta_group:
            del meta_group["export_json"]
        meta_group.create_dataset("export_json", data=json_text(metadata), dtype=_string_dtype(h5py))
        write_schema_metadata(meta_group, h5py)
        configs = meta_group.require_group("configs")
        summaries = meta_group.require_group("results_summaries")
        if category in configs:
            del configs[category]
        if category in summaries:
            del summaries[category]
        configs.create_dataset(category, data=json_text(config), dtype=_string_dtype(h5py))
        summaries.create_dataset(category, data=json_text(manifest), dtype=_string_dtype(h5py))

        simulations = h5.require_group("simulations")
        if category in simulations:
            del simulations[category]
        sim_group = simulations.create_group(category)
        sim_group.attrs["category"] = category
        sim_group.attrs["frame_count"] = len(config.get("frames") or [])
        sim_group.attrs["hdf5_schema_version"] = HDF5_SCHEMA_VERSION

        if category == "paths":
            sim_group.attrs["layout"] = "ragged_paths_with_derived_table"
            write_csv_table(sim_group, csv_path, h5py, group_name="derived_path_points")
            write_frame_metadata(sim_group, config, manifest, h5py)
            write_path_frame_payloads(sim_group, config, manifest, h5py)
        elif category in {"coverage_2d", "coverage_3d"}:
            # Keep a columnar representation as a convenience, but dense data lives
            # under /data with an explicit frame axis.
            write_csv_table(sim_group, csv_path, h5py, group_name="derived_cells")
            write_coverage_tensor_payloads(sim_group, config, manifest, h5py, category)
            tile_group = write_tile_spatial_dataset(h5, config, h5py)
            if tile_group is not None:
                join_group = write_coverage_tile_join(sim_group, config, h5py, category, tile_group)
                sim_group.attrs["tile_spatial_dataset_embedded"] = True
                sim_group.attrs["tile_spatial_join_available"] = bool(join_group is not None)
            else:
                sim_group.attrs["tile_spatial_dataset_embedded"] = False
                sim_group.attrs["tile_spatial_join_available"] = False
        else:
            raise RuntimeError(f"Unsupported HDF5 simulation category: {category}")
    temporary.replace(export_file)


def export_completed_run(*, config_path, manifest_path, csv_path, output):
    """Create the durable export requested by ``config['output']``.

    Returns a small status dictionary. ``NONE`` intentionally creates nothing.
    """
    export_format = str(output.get("export_format", "NONE") or "NONE").upper()
    if export_format == "NONE":
        return {"export_format": "NONE", "export_file": "", "export_metadata_json": ""}

    config = load_json(config_path)
    manifest = load_json(manifest_path)
    category = str(output.get("export_category") or "paths")
    run_id = str(output.get("export_run_id") or "unknown")
    export_file = Path(output["export_file"]).resolve()
    metadata_path = Path(output["export_metadata_json"]).resolve()
    export_file.parent.mkdir(parents=True, exist_ok=True)

    category_metadata = build_category_metadata(
        config, manifest, category=category, source_csv=csv_path,
    )
    existing_metadata = load_json(metadata_path) if metadata_path.exists() and export_format == "HDF5" else {}
    metadata = build_export_metadata(
        existing_metadata, category_metadata, export_format=export_format,
        export_file=export_file, run_id=run_id,
    )

    if export_format == "CSV":
        shutil.copy2(csv_path, export_file)
    elif export_format == "HDF5":
        export_hdf5(config, manifest, csv_path, export_file, metadata, category)
    else:
        raise RuntimeError(f"Unsupported export format: {export_format}")

    write_json(metadata_path, metadata)
    return {
        "export_format": export_format,
        "export_file": str(export_file),
        "export_metadata_json": str(metadata_path),
        "export_category": category,
        "export_run_id": run_id,
    }


def main(args):
    output = {
        "export_format": args.format,
        "export_category": args.category,
        "export_run_id": args.run_id,
        "export_file": args.output,
        "export_metadata_json": args.metadata_out,
    }
    result = export_completed_run(
        config_path=args.config,
        manifest_path=args.manifest,
        csv_path=args.csv,
        output=output,
    )
    print(json.dumps({"ok": True, **result}))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--metadata-out", required=True)
    parser.add_argument("--category", required=True, choices=("paths", "coverage_2d", "coverage_3d"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--format", required=True, choices=("CSV", "HDF5"))
    raise SystemExit(main(parser.parse_args()))
