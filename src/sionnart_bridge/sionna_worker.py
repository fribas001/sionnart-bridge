#!/usr/bin/env python3
"""
Sionna RT propagation-path worker for the Blender SionnaRT-Bridge.

Blender 5.2 mode executes this file with Blender's bundled Python and exposes
the configured Sionna site-packages through PYTHONPATH. Legacy external-Python
mode is still supported.

Version 0.7 also derives Blender TX/RX velocities, assigns them to Sionna radio
devices, and embeds path-wise Doppler shifts and mobility attributes. The Sionna
scene is loaded once; devices, carrier frequency, and solver arguments are
updated for each frame.
"""

import argparse
import csv
import importlib.metadata
import json
import math
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


SPEED_OF_LIGHT_M_S = 299_792_458.0
INVALID_SHAPE = 0xFFFFFFFF
PATH_UID_STRIDE = 10_000_000

# Blender 4.5's Import CSV node supports scalar integer and float columns only.
# Coordinates therefore remain three scalar columns. Short x/y/z names replace
# point_x/point_y/point_z from schema v1.
GEOMETRY_NODES_CSV_COLUMNS = (
    "frame",
    "frequency_ghz",
    "frequency_hz",
    "max_depth",
    "max_num_paths_per_src",
    "samples_per_src",
    "seed",
    "los_enabled",
    "specular_reflection_enabled",
    "diffuse_reflection_enabled",
    "refraction_enabled",
    "diffraction_enabled",
    "edge_diffraction_enabled",
    "diffraction_lit_region_enabled",
    "sim_numeric_id",
    "pos_idx",
    "top_rank",
    "path_uid_num",
    "path_index",
    "point_order",
    "point_role_id",
    "x",
    "y",
    "z",
    "interaction_id",
    "interaction_type_id",
    "object_id",
    "num_events",
    "path_is_los",
    "path_num_specular",
    "path_num_diffuse",
    "path_num_refraction",
    "path_num_diffraction",
    "path_num_mixed",
    "path_gain_linear",
    "path_gain_db",
    "delay_s",
    "delay_ns",
    "amplitude",
    "phase_rad",
    "doppler_hz",
    "doppler_abs_hz",
    "tx_velocity_x",
    "tx_velocity_y",
    "tx_velocity_z",
    "tx_speed_m_s",
    "rx_velocity_x",
    "rx_velocity_y",
    "rx_velocity_z",
    "rx_speed_m_s",
    "relative_velocity_x",
    "relative_velocity_y",
    "relative_velocity_z",
    "relative_speed_m_s",
    "straight_distance_m",
    "path_length_m",
    "distance_from_delay_m",
    "excess_distance_m",
    "cumulative_distance_from_tx_m",
    "segment_to_next_length_m",
    "segment_from_prev_type_id",
    "segment_from_prev_object_id",
    "segment_to_next_type_id",
    "segment_to_next_object_id",
    "tx_x",
    "tx_y",
    "tx_z",
    "rx_x",
    "rx_y",
    "rx_z",
)


def package_version():
    for distribution in ("sionna-rt", "sionna_rt"):
        try:
            return importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            pass
    return "unknown"


def now_utc():
    return datetime.now(timezone.utc).isoformat()


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


def write_geometry_nodes_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.{time.time_ns()}.tmp")
    with open(temporary, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=GEOMETRY_NODES_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    _atomic_replace_with_retry(temporary, path)


def to_numpy(value):
    if hasattr(value, "numpy"):
        return value.numpy()
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

def safe_scalar(array, index, default=0.0):
    try:
        return float(array[index])
    except Exception:
        return float(default)


def path_tensor_index(array, rx_index, tx_index, path_index, *, leading=0, trailing=0):
    """Build an index for Sionna path tensors with optional edge dimensions.

    Synthetic topology is ``[rx, tx, path]`` and explicit-array topology is
    ``[rx, rx_ant, tx, tx_ant, path]``. Geometry tensors prepend depth and
    vertices also append XYZ.
    """
    core_rank = array.ndim - int(leading) - int(trailing)
    if core_rank == 3:
        core = (rx_index, tx_index, path_index)
    elif core_rank == 5:
        core = (rx_index, 0, tx_index, 0, path_index)
    else:
        raise ValueError(
            f"Unsupported path tensor layout: shape={array.shape}, "
            f"leading={leading}, trailing={trailing}"
        )
    return ((slice(None),) * int(leading)) + core + ((slice(None),) * int(trailing))


def distance(a, b):
    return math.sqrt(
        (float(b[0]) - float(a[0])) ** 2
        + (float(b[1]) - float(a[1])) ** 2
        + (float(b[2]) - float(a[2])) ** 2
    )


def public_object_id(value):
    value = int(value)
    return -1 if value < 0 or value == INVALID_SHAPE else value


def interaction_type_id(raw_value):
    """Map Sionna bit flags to compact CSV/GN category IDs.

    0 endpoint/none, 1 reserved for LoS, 2 specular, 3 diffuse,
    4 refraction, 5 diffraction, 6 mixed/combined bit mask.
    """
    raw_value = int(raw_value)
    return {
        0: 0,
        1: 2,
        2: 3,
        4: 4,
        8: 5,
    }.get(raw_value, 6)


def path_interaction_counts(raw_interactions):
    counts = {
        "path_num_specular": 0,
        "path_num_diffuse": 0,
        "path_num_refraction": 0,
        "path_num_diffraction": 0,
        "path_num_mixed": 0,
    }
    for raw_value in raw_interactions:
        raw_value = int(raw_value)
        if raw_value == 1:
            counts["path_num_specular"] += 1
        elif raw_value == 2:
            counts["path_num_diffuse"] += 1
        elif raw_value == 4:
            counts["path_num_refraction"] += 1
        elif raw_value == 8:
            counts["path_num_diffraction"] += 1
        elif raw_value != 0:
            counts["path_num_mixed"] += 1
    return counts



def frame_simulation(config, frame_payload):
    """Return a normalized per-frame solver configuration."""
    simulation = dict(config.get("simulation", {}))
    simulation.update(frame_payload.get("simulation", {}))
    if "frequency_hz" not in simulation and "frequency_ghz" in simulation:
        simulation["frequency_hz"] = float(simulation["frequency_ghz"]) * 1e9
    if "frequency_ghz" not in simulation and "frequency_hz" in simulation:
        simulation["frequency_ghz"] = float(simulation["frequency_hz"]) / 1e9
    simulation.setdefault("frequency_ghz", 28.0)
    simulation.setdefault("frequency_hz", float(simulation["frequency_ghz"]) * 1e9)
    simulation.setdefault("max_depth", 3)
    simulation.setdefault("max_num_paths_per_src", 10000)
    simulation.setdefault("samples_per_src", 100000)
    simulation.setdefault("synthetic_array", True)
    simulation.setdefault("los", True)
    simulation.setdefault("specular_reflection", True)
    simulation.setdefault("diffuse_reflection", False)
    simulation.setdefault("refraction", True)
    simulation.setdefault("diffraction", False)
    simulation.setdefault("edge_diffraction", False)
    simulation.setdefault("diffraction_lit_region", True)
    simulation.setdefault("seed", 42)
    simulation.setdefault("sim_numeric_id", 0)
    simulation.setdefault("mobility_doppler", True)
    simulation.setdefault("timeline_fps", 24.0)
    return simulation


def _path_type_label(record):
    if int(record.get("path_is_los", 0)) or len(record.get("interactions", [])) == 0:
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


def _segment_angles(start, end):
    dx = float(end[0]) - float(start[0])
    dy = float(end[1]) - float(start[1])
    dz = float(end[2]) - float(start[2])
    length = math.sqrt(dx*dx + dy*dy + dz*dz)
    if length <= 1e-20:
        return None, None
    azimuth = math.degrees(math.atan2(dy, dx)) % 360.0
    zenith = math.degrees(math.acos(max(-1.0, min(1.0, dz / length))))
    return azimuth, zenith


def _linear_to_db(value, floor_db=-600.0):
    value = float(value)
    if not math.isfinite(value) or value <= 0.0:
        return float(floor_db)
    return 10.0 * math.log10(value)


def _velocity_vector(item):
    values = list(item.get("velocity_m_s", [0.0, 0.0, 0.0]))
    values = (values + [0.0, 0.0, 0.0])[:3]
    return [float(value) for value in values]


def _vector_length(values):
    return math.sqrt(sum(float(value) ** 2 for value in values))


def _link_motion_payload(tx, rx):
    tx_velocity = _velocity_vector(tx)
    rx_velocity = _velocity_vector(rx)
    relative_velocity = [
        rx_velocity[index] - tx_velocity[index] for index in range(3)
    ]
    return {
        "tx_velocity_m_s": tx_velocity,
        "rx_velocity_m_s": rx_velocity,
        "relative_velocity_m_s": relative_velocity,
        "tx_speed_m_s": float(tx.get("speed_m_s", _vector_length(tx_velocity))),
        "rx_speed_m_s": float(rx.get("speed_m_s", _vector_length(rx_velocity))),
        "relative_speed_m_s": _vector_length(relative_velocity),
    }


def _channel_link_analytics(frame_number, pos_idx, tx, rx, pair_paths, config):
    """Build compact channel statistics before visualization-path truncation.

    The stored CIR components use the first antenna pair for explicit arrays,
    matching the point representation used by this bridge. Summary power and
    delay statistics include every valid path available to that pair.
    """
    analytics_cfg = dict(config.get("analytics", {}) or {})
    component_limit = max(8, min(512, int(analytics_cfg.get("cir_component_limit", 96))))
    pdp_bins = max(16, min(256, int(analytics_cfg.get("pdp_bins", 64))))
    significant_drop_db = max(0.0, float(
        analytics_cfg.get("significant_path_threshold_db", 20.0)
    ))
    motion = _link_motion_payload(tx, rx)

    if not pair_paths:
        return {
            "frame": int(frame_number), "pos_idx": int(pos_idx),
            "tx_name": tx.get("blender_name", tx.get("name", "TX")),
            "rx_name": rx.get("blender_name", rx.get("name", "RX")),
            "path_count": 0, "los_available": False,
            "total_power_linear": 0.0, "total_power_db": -600.0,
            "strongest_path_gain_db": -600.0,
            "dominant_to_rest_db": 0.0,
            "first_arrival_ns": None, "mean_excess_delay_ns": None,
            "rms_delay_spread_ns": None,
            "max_significant_excess_delay_ns": None,
            "path_type_counts": {}, "path_type_power_db": {},
            "doppler_mean_hz": 0.0, "rms_doppler_spread_hz": 0.0,
            "doppler_min_hz": 0.0, "doppler_max_hz": 0.0,
            "max_abs_doppler_hz": 0.0,
            **motion,
            "cir_components": [], "pdp_bins": [],
            "antenna_pair_note": "First antenna pair when explicit arrays are used",
        }

    ordered_delay = sorted(pair_paths, key=lambda item: float(item["delay_ns"]))
    first_arrival = float(ordered_delay[0]["delay_ns"])
    powers = [max(0.0, float(item["path_gain_linear"])) for item in pair_paths]
    total_power = sum(powers)
    strongest = max(pair_paths, key=lambda item: float(item["path_gain_linear"]))
    strongest_power = max(0.0, float(strongest["path_gain_linear"]))
    rest_power = max(0.0, total_power - strongest_power)
    dominant_to_rest_db = (
        _linear_to_db(strongest_power / rest_power)
        if rest_power > 0.0 else 300.0
    )

    if total_power > 0.0:
        excess_delays = [float(item["delay_ns"]) - first_arrival for item in pair_paths]
        mean_excess = sum(p*d for p, d in zip(powers, excess_delays)) / total_power
        rms_delay = math.sqrt(max(
            0.0,
            sum(p * (d - mean_excess) ** 2 for p, d in zip(powers, excess_delays))
            / total_power,
        ))
    else:
        excess_delays = [float(item["delay_ns"]) - first_arrival for item in pair_paths]
        mean_excess = 0.0
        rms_delay = 0.0

    dopplers = [float(item.get("doppler_hz", 0.0)) for item in pair_paths]
    if total_power > 0.0:
        doppler_mean = sum(p*d for p, d in zip(powers, dopplers)) / total_power
        rms_doppler = math.sqrt(max(
            0.0,
            sum(p * (d - doppler_mean) ** 2 for p, d in zip(powers, dopplers))
            / total_power,
        ))
    else:
        doppler_mean = 0.0
        rms_doppler = 0.0

    strongest_db = float(strongest["path_gain_db"])
    significant = [
        float(item["delay_ns"]) - first_arrival
        for item in pair_paths
        if float(item["path_gain_db"]) >= strongest_db - significant_drop_db
    ]

    type_counts = {}
    type_powers = {}
    for item in pair_paths:
        label = _path_type_label(item)
        type_counts[label] = type_counts.get(label, 0) + 1
        type_powers[label] = type_powers.get(label, 0.0) + max(
            0.0, float(item["path_gain_linear"])
        )

    strongest_components = sorted(
        pair_paths, key=lambda item: float(item["path_gain_linear"]), reverse=True
    )[:component_limit]
    components = []
    for item in strongest_components:
        aod_az, aod_ze = _segment_angles(item["points"][0], item["points"][1])
        # Geometric arrival direction follows the final propagation segment.
        aoa_az, aoa_ze = _segment_angles(item["points"][-2], item["points"][-1])
        components.append({
            "path_index": int(item["path_index"]),
            "delay_ns": float(item["delay_ns"]),
            "excess_delay_ns": float(item["delay_ns"]) - first_arrival,
            "coefficient_real": float(item["coefficient_real"]),
            "coefficient_imag": float(item["coefficient_imag"]),
            "amplitude": float(item["amplitude"]),
            "phase_rad": float(item["phase_rad"]),
            "path_gain_db": float(item["path_gain_db"]),
            "doppler_hz": float(item.get("doppler_hz", 0.0)),
            "path_type": _path_type_label(item),
            "aod_azimuth_deg": aod_az,
            "aod_zenith_deg": aod_ze,
            "aoa_azimuth_deg": aoa_az,
            "aoa_zenith_deg": aoa_ze,
        })

    max_excess = max(excess_delays) if excess_delays else 0.0
    if max_excess <= 1e-12:
        edges = [0.0, 1.0]
        bin_count = 1
    else:
        bin_count = pdp_bins
        edges = [max_excess * i / bin_count for i in range(bin_count + 1)]
    bin_power = [0.0] * bin_count
    for item, power in zip(pair_paths, powers):
        excess = max(0.0, float(item["delay_ns"]) - first_arrival)
        if max_excess <= 1e-12:
            index = 0
        else:
            index = min(bin_count - 1, int(excess / max_excess * bin_count))
        bin_power[index] += power
    pdp = []
    for index, power in enumerate(bin_power):
        center = 0.5 * (edges[index] + edges[index + 1])
        pdp.append({
            "excess_delay_ns": float(center),
            "power_linear": float(power),
            "power_db": _linear_to_db(power),
        })

    return {
        "frame": int(frame_number), "pos_idx": int(pos_idx),
        "tx_name": tx.get("blender_name", tx.get("name", "TX")),
        "rx_name": rx.get("blender_name", rx.get("name", "RX")),
        "path_count": len(pair_paths),
        "los_available": any(_path_type_label(item) == "LoS" for item in pair_paths),
        "total_power_linear": float(total_power),
        "total_power_db": _linear_to_db(total_power),
        "strongest_path_gain_db": strongest_db,
        "dominant_to_rest_db": float(dominant_to_rest_db),
        "first_arrival_ns": float(first_arrival),
        "mean_excess_delay_ns": float(mean_excess),
        "rms_delay_spread_ns": float(rms_delay),
        "doppler_mean_hz": float(doppler_mean),
        "rms_doppler_spread_hz": float(rms_doppler),
        "doppler_min_hz": min(dopplers) if dopplers else 0.0,
        "doppler_max_hz": max(dopplers) if dopplers else 0.0,
        "max_abs_doppler_hz": max((abs(value) for value in dopplers), default=0.0),
        **motion,
        "max_significant_excess_delay_ns": (
            max(significant) if significant else 0.0
        ),
        "significant_path_threshold_db": float(significant_drop_db),
        "path_type_counts": type_counts,
        "path_type_power_db": {
            key: _linear_to_db(value) for key, value in type_powers.items()
        },
        "cir_component_count": len(components),
        "cir_component_limit": component_limit,
        "cir_components": components,
        "pdp_bins": pdp,
        "antenna_pair_note": "First antenna pair when explicit arrays are used",
    }


def extract_path_records(
    config,
    frame_payload,
    vertices,
    interactions,
    objects,
    valid,
    tau,
    doppler,
    a_real,
    a_imag,
):
    """Convert one frame of Sionna tensors into ranked paths and CSV rows."""
    tx_items = frame_payload["transmitters"]
    rx_items = frame_payload["receivers"]
    top_paths_per_pair = int(config.get("output", {}).get("top_paths_per_pair", 50))
    simulation = frame_simulation(config, frame_payload)
    sim_numeric_id = int(simulation.get("sim_numeric_id", 0))
    frame_number = int(frame_payload.get("frame", config.get("frame", 0)))

    if valid.ndim not in (3, 5):
        raise ValueError(
            "Unsupported Paths.valid layout. Expected rank 3 for synthetic "
            f"arrays or rank 5 for explicit arrays, got {valid.shape}."
        )

    num_paths = int(valid.shape[-1]) if valid.ndim else 0
    exported_paths = []
    point_rows = []
    channel_links = []

    for rx_index, rx in enumerate(rx_items):
        for tx_index, tx in enumerate(tx_items):
            pos_idx = rx_index * len(tx_items) + tx_index
            pair_paths = []

            for path_index in range(num_paths):
                valid_index = path_tensor_index(valid, rx_index, tx_index, path_index)
                if not bool(valid[valid_index]):
                    continue

                raw_interaction_values = interactions[path_tensor_index(
                    interactions,
                    rx_index,
                    tx_index,
                    path_index,
                    leading=1,
                )]
                vertex_values = vertices[path_tensor_index(
                    vertices,
                    rx_index,
                    tx_index,
                    path_index,
                    leading=1,
                    trailing=1,
                )]
                raw_object_values = objects[path_tensor_index(
                    objects,
                    rx_index,
                    tx_index,
                    path_index,
                    leading=1,
                )]

                points = [list(map(float, tx["position"]))]
                compact_interactions = []
                compact_objects = []
                for depth_index, raw_interaction in enumerate(raw_interaction_values):
                    raw_interaction = int(raw_interaction)
                    if raw_interaction == 0:
                        continue
                    vertex = vertex_values[depth_index]
                    if not np.all(np.isfinite(vertex)):
                        continue
                    points.append([
                        float(vertex[0]),
                        float(vertex[1]),
                        float(vertex[2]),
                    ])
                    compact_interactions.append(raw_interaction)
                    compact_objects.append(public_object_id(raw_object_values[depth_index]))

                points.append(list(map(float, rx["position"])))

                coefficient_idx = path_tensor_index(a_real, rx_index, tx_index, path_index)
                delay_idx = path_tensor_index(tau, rx_index, tx_index, path_index)
                delay_s = safe_scalar(tau, delay_idx, 0.0)
                real = safe_scalar(a_real, coefficient_idx, 0.0)
                imag = safe_scalar(a_imag, coefficient_idx, 0.0)
                amplitude = math.hypot(real, imag)
                path_gain_linear = amplitude * amplitude
                path_gain_db = 10.0 * math.log10(max(path_gain_linear, 1e-60))
                phase_rad = math.atan2(imag, real)
                doppler_idx = path_tensor_index(
                    doppler, rx_index, tx_index, path_index
                )
                doppler_hz = safe_scalar(doppler, doppler_idx, 0.0)
                motion = _link_motion_payload(tx, rx)

                segment_lengths = [
                    distance(points[index], points[index + 1])
                    for index in range(len(points) - 1)
                ]
                path_length_m = sum(segment_lengths)
                straight_distance_m = distance(points[0], points[-1])
                distance_from_delay_m = delay_s * SPEED_OF_LIGHT_M_S

                record = {
                    "frame": frame_number,
                    "tx_name": tx["blender_name"],
                    "rx_name": rx["blender_name"],
                    "tx_sionna_name": tx["name"],
                    "rx_sionna_name": rx["name"],
                    "rx_index": rx_index,
                    "tx_index": tx_index,
                    "pos_idx": pos_idx,
                    "path_uid_num": pos_idx * PATH_UID_STRIDE + path_index,
                    "path_index": path_index,
                    "points": points,
                    "interactions": compact_interactions,
                    "interaction_type_ids": [
                        interaction_type_id(value) for value in compact_interactions
                    ],
                    "objects": compact_objects,
                    "delay_s": delay_s,
                    "delay_ns": delay_s * 1e9,
                    "coefficient_real": real,
                    "coefficient_imag": imag,
                    "amplitude": amplitude,
                    "phase_rad": phase_rad,
                    "doppler_hz": float(doppler_hz),
                    "doppler_abs_hz": abs(float(doppler_hz)),
                    **motion,
                    "path_gain_linear": path_gain_linear,
                    "path_gain_db": path_gain_db,
                    "straight_distance_m": straight_distance_m,
                    "path_length_m": path_length_m,
                    "distance_from_delay_m": distance_from_delay_m,
                    "excess_distance_m": path_length_m - straight_distance_m,
                    "segment_lengths": segment_lengths,
                }
                record.update(path_interaction_counts(compact_interactions))
                pair_paths.append(record)

            pair_paths.sort(
                key=lambda item: (item["path_gain_db"], -item["path_index"]),
                reverse=True,
            )
            channel_links.append(_channel_link_analytics(
                frame_number, pos_idx, tx, rx, pair_paths, config
            ))
            if top_paths_per_pair > 0:
                pair_paths = pair_paths[:top_paths_per_pair]

            for top_rank, record in enumerate(pair_paths, start=1):
                record["top_rank"] = top_rank
                exported_paths.append(record)
                point_rows.extend(path_record_to_point_rows(
                    record,
                    simulation=simulation,
                    sim_numeric_id=sim_numeric_id,
                ))

    return exported_paths, point_rows, channel_links


def path_record_to_point_rows(record, simulation=None, sim_numeric_id=0):
    simulation = dict(simulation or {})
    points = record["points"]
    raw_interactions = record["interactions"]
    type_ids = record["interaction_type_ids"]
    object_ids = record["objects"]
    num_events = len(raw_interactions)
    rows = []
    cumulative = 0.0
    counts = {
        key: int(record[key])
        for key in (
            "path_num_specular",
            "path_num_diffuse",
            "path_num_refraction",
            "path_num_diffraction",
            "path_num_mixed",
        )
    }
    tx = points[0]
    rx = points[-1]

    for point_order, point in enumerate(points):
        is_tx = point_order == 0
        is_rx = point_order == len(points) - 1
        event_index = point_order - 1

        if is_tx:
            point_role_id = 1
            raw_interaction = 0
            current_type_id = 0
            current_object_id = -1
        elif is_rx:
            point_role_id = 3
            raw_interaction = 0
            current_type_id = 0
            current_object_id = -1
        else:
            point_role_id = 2
            raw_interaction = int(raw_interactions[event_index])
            current_type_id = int(type_ids[event_index])
            current_object_id = int(object_ids[event_index])

        if point_order + 1 < len(points) - 1:
            next_event_index = point_order
            next_type_id = int(type_ids[next_event_index])
            next_object_id = int(object_ids[next_event_index])
        else:
            next_type_id = 0
            next_object_id = -1

        segment_to_next = (
            float(record["segment_lengths"][point_order])
            if point_order < len(record["segment_lengths"])
            else 0.0
        )

        row = {
            "frame": int(record.get("frame", 0)),
            "frequency_ghz": float(simulation.get("frequency_ghz", 0.0)),
            "frequency_hz": float(simulation.get("frequency_hz", 0.0)),
            "max_depth": int(simulation.get("max_depth", 0)),
            "max_num_paths_per_src": int(simulation.get("max_num_paths_per_src", 0)),
            "samples_per_src": int(simulation.get("samples_per_src", 0)),
            "seed": int(simulation.get("seed", 0)),
            "los_enabled": int(bool(simulation.get("los", False))),
            "specular_reflection_enabled": int(bool(simulation.get("specular_reflection", False))),
            "diffuse_reflection_enabled": int(bool(simulation.get("diffuse_reflection", False))),
            "refraction_enabled": int(bool(simulation.get("refraction", False))),
            "diffraction_enabled": int(bool(simulation.get("diffraction", False))),
            "edge_diffraction_enabled": int(bool(simulation.get("edge_diffraction", False))),
            "diffraction_lit_region_enabled": int(bool(simulation.get("diffraction_lit_region", False))),
            "sim_numeric_id": int(sim_numeric_id),
            "pos_idx": int(record["pos_idx"]),
            "top_rank": int(record["top_rank"]),
            "path_uid_num": int(record["path_uid_num"]),
            "path_index": int(record["path_index"]),
            "point_order": int(point_order),
            "point_role_id": int(point_role_id),
            "x": float(point[0]),
            "y": float(point[1]),
            "z": float(point[2]),
            "interaction_id": int(raw_interaction),
            "interaction_type_id": int(current_type_id),
            "object_id": int(current_object_id),
            "num_events": int(num_events),
            "path_is_los": int(num_events == 0),
            **counts,
            "path_gain_linear": float(record["path_gain_linear"]),
            "path_gain_db": float(record["path_gain_db"]),
            "delay_s": float(record["delay_s"]),
            "delay_ns": float(record["delay_ns"]),
            "amplitude": float(record["amplitude"]),
            "phase_rad": float(record["phase_rad"]),
            "doppler_hz": float(record.get("doppler_hz", 0.0)),
            "doppler_abs_hz": float(record.get("doppler_abs_hz", 0.0)),
            "tx_velocity_x": float(record.get("tx_velocity_m_s", [0.0, 0.0, 0.0])[0]),
            "tx_velocity_y": float(record.get("tx_velocity_m_s", [0.0, 0.0, 0.0])[1]),
            "tx_velocity_z": float(record.get("tx_velocity_m_s", [0.0, 0.0, 0.0])[2]),
            "tx_speed_m_s": float(record.get("tx_speed_m_s", 0.0)),
            "rx_velocity_x": float(record.get("rx_velocity_m_s", [0.0, 0.0, 0.0])[0]),
            "rx_velocity_y": float(record.get("rx_velocity_m_s", [0.0, 0.0, 0.0])[1]),
            "rx_velocity_z": float(record.get("rx_velocity_m_s", [0.0, 0.0, 0.0])[2]),
            "rx_speed_m_s": float(record.get("rx_speed_m_s", 0.0)),
            "relative_velocity_x": float(record.get("relative_velocity_m_s", [0.0, 0.0, 0.0])[0]),
            "relative_velocity_y": float(record.get("relative_velocity_m_s", [0.0, 0.0, 0.0])[1]),
            "relative_velocity_z": float(record.get("relative_velocity_m_s", [0.0, 0.0, 0.0])[2]),
            "relative_speed_m_s": float(record.get("relative_speed_m_s", 0.0)),
            "straight_distance_m": float(record["straight_distance_m"]),
            "path_length_m": float(record["path_length_m"]),
            "distance_from_delay_m": float(record["distance_from_delay_m"]),
            "excess_distance_m": float(record["excess_distance_m"]),
            "cumulative_distance_from_tx_m": float(cumulative),
            "segment_to_next_length_m": float(segment_to_next),
            "segment_from_prev_type_id": int(current_type_id),
            "segment_from_prev_object_id": int(current_object_id),
            "segment_to_next_type_id": int(next_type_id),
            "segment_to_next_object_id": int(next_object_id),
            "tx_x": float(tx[0]),
            "tx_y": float(tx[1]),
            "tx_z": float(tx[2]),
            "rx_x": float(rx[0]),
            "rx_y": float(rx[1]),
            "rx_z": float(rx[2]),
        }
        rows.append(row)
        cumulative += segment_to_next

    return rows


def _array_profile(config, role):
    antenna = config.get("antenna", {})
    if role in antenna:
        return antenna[role]
    # Compatibility with v0.11 and earlier single-array packages.
    return antenna or {
        "num_rows": 1, "num_cols": 1, "vertical_spacing": 0.5,
        "horizontal_spacing": 0.5, "pattern": "iso", "polarization": "V",
        "polarization_model": "tr38901_2",
    }


def _make_planar_array(profile, PlanarArray):
    return PlanarArray(
        num_rows=int(profile.get("num_rows", 1)),
        num_cols=int(profile.get("num_cols", 1)),
        vertical_spacing=float(profile.get("vertical_spacing", 0.5)),
        horizontal_spacing=float(profile.get("horizontal_spacing", 0.5)),
        pattern=str(profile.get("pattern", "iso")),
        polarization=str(profile.get("polarization", "V")),
        polarization_model=str(profile.get("polarization_model", "tr38901_2")),
    )


def _configure_scene(scene, config, PlanarArray):
    scene.tx_array = _make_planar_array(_array_profile(config, "tx"), PlanarArray)
    scene.rx_array = _make_planar_array(_array_profile(config, "rx"), PlanarArray)


def _lookup_device(scene, name):
    if not name:
        return None
    return scene.transmitters.get(name) or scene.receivers.get(name)


def _apply_device_orientation(scene, device, item):
    mode = str(item.get("orientation_mode", "BLENDER")).upper()
    if mode == "LOOK_AT":
        # Use the evaluated Blender target position. This also works when the
        # target is not a Sionna radio device (e.g. an Empty) and avoids stale
        # name lookups after compact device renaming.
        target_position = item.get("look_at_target_position")
        if target_position is None:
            target = _lookup_device(scene, item.get("look_at_target_name", ""))
            target_position = target.position if target is not None else None
        if target_position is None:
            raise RuntimeError(
                f"Device {item.get('blender_name', item['name'])} has LOOK_AT orientation but no target"
            )
        dx = float(target_position[0]) - float(item["position"][0])
        dy = float(target_position[1]) - float(item["position"][1])
        dz = float(target_position[2]) - float(item["position"][2])
        if dx*dx + dy*dy + dz*dz <= 1e-12:
            raise RuntimeError(f"Device {item.get('name')} cannot look at a coincident target")
        device.look_at(target_position)
        return
    device.orientation = item.get("orientation_sionna_rad", [0.0, 0.0, 0.0])


def _ensure_devices(scene, frame_payload, Transmitter, Receiver):
    """Create/update devices, then apply per-frame Blender/fixed/look-at orientation."""
    wanted_tx = {item["name"] for item in frame_payload["transmitters"]}
    wanted_rx = {item["name"] for item in frame_payload["receivers"]}

    for name in list(scene.transmitters):
        if name not in wanted_tx:
            scene.remove(name)
    for name in list(scene.receivers):
        if name not in wanted_rx:
            scene.remove(name)

    for item in frame_payload["transmitters"]:
        device = scene.transmitters.get(item["name"])
        if device is None:
            device = Transmitter(
                name=item["name"], position=item["position"], orientation=[0.0, 0.0, 0.0]
            )
            scene.add(device)
        else:
            device.position = item["position"]
        device.power_dbm = float(item.get("power_dbm", 44.0))
        device.velocity = item.get("velocity_m_s", [0.0, 0.0, 0.0])

    for item in frame_payload["receivers"]:
        device = scene.receivers.get(item["name"])
        if device is None:
            device = Receiver(
                name=item["name"], position=item["position"], orientation=[0.0, 0.0, 0.0]
            )
            scene.add(device)
        else:
            device.position = item["position"]
        device.velocity = item.get("velocity_m_s", [0.0, 0.0, 0.0])

    # Apply look-at only after all referenced TX/RX devices exist.
    for item in frame_payload["transmitters"]:
        _apply_device_orientation(scene, scene.transmitters.get(item["name"]), item)
    for item in frame_payload["receivers"]:
        _apply_device_orientation(scene, scene.receivers.get(item["name"]), item)


def _solve_frame(scene, solver, frame_runtime, frame_payload):
    config = frame_runtime
    simulation = frame_simulation(config, frame_payload)
    scene.frequency = float(simulation["frequency_hz"])
    scene.bandwidth = float(simulation.get("bandwidth_hz", 1e6))
    scene.temperature = float(simulation.get("temperature_k", 293.0))
    material_summary = apply_radio_materials(scene, frame_payload, config)
    paths = solver(
        scene=scene,
        max_depth=int(simulation["max_depth"]),
        max_num_paths_per_src=int(simulation["max_num_paths_per_src"]),
        samples_per_src=int(simulation["samples_per_src"]),
        synthetic_array=bool(simulation["synthetic_array"]),
        los=bool(simulation["los"]),
        specular_reflection=bool(simulation["specular_reflection"]),
        diffuse_reflection=bool(simulation["diffuse_reflection"]),
        refraction=bool(simulation["refraction"]),
        diffraction=bool(simulation["diffraction"]),
        edge_diffraction=bool(simulation.get("edge_diffraction", False)),
        diffraction_lit_region=bool(simulation.get("diffraction_lit_region", True)),
        seed=int(simulation["seed"]),
    )

    vertices = to_numpy(paths.vertices)
    interactions = to_numpy(paths.interactions)
    objects = to_numpy(paths.objects)
    valid = to_numpy(paths.valid)
    tau = to_numpy(paths.tau)
    try:
        doppler = to_numpy(paths.doppler)
        doppler_available = True
    except Exception:
        doppler = np.zeros_like(tau, dtype=np.float32)
        doppler_available = False
    sources = to_numpy(paths.sources)
    targets = to_numpy(paths.targets)

    # Sionna stores complex coefficients as separate real and imaginary tensors.
    a_real = to_numpy(paths.a[0])
    a_imag = to_numpy(paths.a[1])

    output = frame_payload["output"]
    keep_external = bool(config.get("output", {}).get("keep_external_results", True))
    if keep_external:
        np.savez_compressed(
            output["results_npz"],
            vertices=vertices,
            interactions=interactions,
            objects=objects,
            valid=valid,
            tau=tau,
            doppler=doppler,
            sources=sources,
            targets=targets,
            a_real=a_real,
            a_imag=a_imag,
        )

    exported_paths, point_rows, channel_links = extract_path_records(
        config=config,
        frame_payload=frame_payload,
        vertices=vertices,
        interactions=interactions,
        objects=objects,
        valid=valid,
        tau=tau,
        doppler=doppler,
        a_real=a_real,
        a_imag=a_imag,
    )
    tensor_shapes = {
        "vertices": list(vertices.shape),
        "interactions": list(interactions.shape),
        "objects": list(objects.shape),
        "valid": list(valid.shape),
        "tau": list(tau.shape),
        "doppler": list(doppler.shape),
        "a_real": list(a_real.shape),
        "a_imag": list(a_imag.shape),
    }

    results_payload = {
        "schema_version": 4,
        "geometry_nodes_csv_schema": "sionna_path_points_v3_mobility",
        "created_utc": now_utc(),
        "frame": int(frame_payload["frame"]),
        "simulation": simulation,
        "materials": material_summary,
        "scene_xml_sha256": config["scene_xml_sha256"],
        "sionna_rt_version": package_version(),
        "path_count": len(exported_paths),
        "point_count": len(point_rows),
        "doppler_available": bool(doppler_available),
        "mobility_doppler": bool(simulation.get("mobility_doppler", True)),
        "tensor_shapes": tensor_shapes,
        "geometry_nodes_csv": config["output"]["results_csv"],
        "paths": exported_paths,
        "channel_analytics": {
            "schema_version": 2,
            "source": "all_valid_paths_first_antenna_pair",
            "links": channel_links,
        },
    }
    if keep_external:
        write_json(output["results_json"], results_payload)
        write_status_json(output["status_json"], {
            "state": "finished",
            "updated_utc": now_utc(),
            "frame": int(frame_payload["frame"]),
            "simulation": simulation,
            "path_count": len(exported_paths),
            "point_count": len(point_rows),
            "tensor_shapes": tensor_shapes,
            "results_json": output["results_json"],
            "results_csv": config["output"]["results_csv"],
            "results_npz": output["results_npz"],
        })

    return {
        "frame": int(frame_payload["frame"]),
        "simulation": simulation,
        "materials": material_summary,
        "path_count": len(exported_paths),
        "point_count": len(point_rows),
        "doppler_available": bool(doppler_available),
        "mobility_doppler": bool(simulation.get("mobility_doppler", True)),
        "results_json": output["results_json"],
        "results_csv": config["output"]["results_csv"],
        "results_npz": output["results_npz"],
        "tensor_shapes": tensor_shapes,
        "channel_analytics": {
            "schema_version": 2,
            "source": "all_valid_paths_first_antenna_pair",
            "links": channel_links,
        },
    }, point_rows


def _legacy_frame_payload(config):
    """Accept v0.3 single-frame configs for easier upgrades/testing."""
    return {
        "frame": int(config.get("frame", 0)),
        "simulation": dict(config.get("simulation", {})),
        "transmitters": config["transmitters"],
        "receivers": config["receivers"],
        "materials": list(config.get("materials", [])),
        "output": {
            "results_npz": config["output"]["results_npz"],
            "results_json": config["output"]["results_json"],
            "results_csv": config["output"]["results_csv"],
            "status_json": config["output"]["status_json"],
        },
    }


def main(config_path):
    config_path = Path(config_path).resolve()
    with open(config_path, "r", encoding="utf-8") as handle:
        config = json.load(handle)

    output = config["output"]
    status_path = Path(output["status_json"])
    frame_payloads = list(config.get("frames") or [_legacy_frame_payload(config)])
    if not frame_payloads:
        raise RuntimeError("The run config contains no frames")

    write_status_json(status_path, {
        "state": "starting",
        "created_utc": now_utc(),
        "config": str(config_path),
        "frame_count": len(frame_payloads),
    })

    # Import here so startup errors are captured in status.json and sionna.log.
    import mitsuba as mi
    import sionna.rt
    from sionna.rt import (
        load_scene,
        PathSolver,
        PlanarArray,
        Receiver,
        Transmitter,
        RadioMaterial,
        ITURadioMaterial,
        LambertianPattern,
        DirectivePattern,
        BackscatteringPattern,
    )

    write_status_json(status_path, {
        "state": "loading_scene",
        "updated_utc": now_utc(),
        "frame_count": len(frame_payloads),
        "sionna_rt_version": package_version(),
        "mitsuba_version": getattr(mi, "__version__", "unknown"),
        "mitsuba_variant": mi.variant(),
    })

    scene = None
    current_scene_xml = None
    material_runtime = {
        "RadioMaterial": RadioMaterial,
        "ITURadioMaterial": ITURadioMaterial,
        "LambertianPattern": LambertianPattern,
        "DirectivePattern": DirectivePattern,
        "BackscatteringPattern": BackscatteringPattern,
    }
    frame_runtime = dict(config)
    frame_runtime.update(material_runtime)
    solver = PathSolver()

    frame_results = []
    all_point_rows = []
    for index, frame_payload in enumerate(frame_payloads, start=1):
        frame_number = int(frame_payload["frame"])
        simulation = frame_simulation(config, frame_payload)
        frame_scene_xml = str(frame_payload.get("scene_xml") or config["scene_xml"])
        if scene is None or frame_scene_xml != current_scene_xml:
            write_status_json(status_path, {
                "state": "loading_scene", "updated_utc": now_utc(),
                "frame": frame_number, "frame_index": index,
                "frame_count": len(frame_payloads), "scene_xml": frame_scene_xml,
            })
            scene = load_scene(frame_scene_xml, merge_shapes=True)
            frame_runtime = dict(config)
            frame_runtime.update(material_runtime)
            frame_runtime["scene_xml"] = frame_scene_xml
            frame_runtime["scene_xml_sha256"] = frame_payload.get(
                "scene_xml_sha256", config.get("scene_xml_sha256", "")
            )
            _configure_scene(scene, frame_runtime, PlanarArray)
            current_scene_xml = frame_scene_xml
        _ensure_devices(scene, frame_payload, Transmitter, Receiver)
        write_status_json(status_path, {
            "state": "solving",
            "updated_utc": now_utc(),
            "frame": frame_number,
            "frame_index": index,
            "frame_count": len(frame_payloads),
            "completed_frames": len(frame_results),
            "frequency_ghz": float(simulation["frequency_ghz"]),
            "max_depth": int(simulation["max_depth"]),
            "seed": int(simulation["seed"]),
            "num_tx": len(frame_payload["transmitters"]),
            "num_rx": len(frame_payload["receivers"]),
        })
        frame_result, point_rows = _solve_frame(scene, solver, frame_runtime, frame_payload)
        frame_results.append(frame_result)
        all_point_rows.extend(point_rows)

    combined_csv_path = Path(output.get("results_csv", status_path.parent / "paths_all_frames.csv"))
    write_geometry_nodes_csv(combined_csv_path, all_point_rows)

    manifest_path = Path(output.get("frames_manifest_json", status_path.parent / "frames_manifest.json"))
    manifest_payload = {
        "schema_version": 1,
        "created_utc": now_utc(),
        "scene_xml": config["scene_xml"],
        "scene_xml_sha256": config["scene_xml_sha256"],
        "procedural_scene": bool(config.get("procedural_scene", False)),
        "frame_count": len(frame_results),
        "results_csv": str(combined_csv_path),
        "frames": frame_results,
    }
    write_json(manifest_path, manifest_payload)

    from result_export_worker import export_completed_run
    export_status = export_completed_run(
        config_path=config_path,
        manifest_path=manifest_path,
        csv_path=combined_csv_path,
        output=output,
    )

    write_status_json(status_path, {
        "state": "finished",
        "updated_utc": now_utc(),
        "frame_count": len(frame_results),
        "completed_frames": len(frame_results),
        "frames_manifest_json": str(manifest_path),
        "results_csv": str(combined_csv_path),
        "point_count": len(all_point_rows),
        "frames": frame_results,
        **export_status,
    })

    print(json.dumps({
        "ok": True,
        "frame_count": len(frame_results),
        "frames_manifest_json": str(manifest_path),
        "last_results_csv": str(combined_csv_path),
        **export_status,
    }))
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
            config_path = Path(args.config).resolve()
            with open(config_path, "r", encoding="utf-8") as handle:
                config = json.load(handle)
            write_status_json(config["output"]["status_json"], {
                "state": "failed",
                "updated_utc": now_utc(),
                "error": str(exc),
                "traceback": traceback.format_exc(),
            })
        except Exception:
            pass
    finally:
        # Dr.Jit/Mitsuba can return a Windows-native shutdown status after all
        # output has been written. Flush and exit directly with our own code.
        try:
            import sys
            sys.stdout.flush()
            sys.stderr.flush()
        finally:
            os._exit(int(exit_code))
