#!/usr/bin/env python3
"""Run frozen vegetation scenes with the native Sionna RT 2.1.0 API.

No Blender or SionnaRT-Bridge imports. Edit experiment.json, then run:
    python run_vegetation.py experiment.json --check
    python run_vegetation.py experiment.json --output results
Use --inspect scene.xml to print material IDs before configuring bindings.
"""

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


SOLVER_KEYS = {
    "max_depth", "max_num_paths_per_src", "samples_per_src", "synthetic_array",
    "los", "specular_reflection", "diffuse_reflection", "refraction",
    "diffraction", "edge_diffraction", "diffraction_lit_region", "seed",
}
MATERIAL_KEYS = {
    "relative_permittivity", "conductivity", "thickness",
    "scattering_coefficient", "xpd_coefficient", "scattering_pattern",
}
METRICS = (
    "path_count", "los_available", "total_power_db", "strongest_path_gain_db",
    "first_arrival_ns", "mean_excess_delay_ns", "rms_delay_spread_ns",
)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False) + "\n",
                          encoding="utf-8")


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def resolve(base, value):
    p = Path(value).expanduser()
    return (base / p).resolve() if not p.is_absolute() else p.resolve()


def scene_inventory(path):
    """Audit explicit XML/mesh inputs; never modify geometry or its materials.

    The reproducibility runner deliberately accepts the flat PLY/OBJ scene
    format used in this experiment. Untracked includes/instances are rejected.
    """
    path = Path(path).resolve()
    root = ET.parse(path).getroot()
    if root.tag != "scene" or root.findall(".//include") or root.findall(".//default"):
        raise ValueError(f"Use a self-contained scene XML without includes/defaults: {path}")
    shapes = root.findall(".//shape")
    if any(s.get("type") not in ("ply", "obj") for s in shapes):
        raise ValueError("Use evaluated PLY/OBJ meshes; expand instances before this comparison.")
    mats = {}
    for mat in root.findall("bsdf"):
        name = mat.get("id")
        if not name or name in mats:
            raise ValueError("Each top-level material needs a unique XML ID.")
        mats[name] = {"type": mat.get("type"), "shape_count": 0}
    files = [{"path": str(path), "sha256": sha256(path)}]
    seen = {path}
    for shape in shapes:
        refs = [r.get("id") for r in shape.findall("ref") if r.get("id") in mats]
        if len(refs) != 1 or shape.findall("bsdf"):
            raise ValueError("Each shape must reference exactly one top-level radio material.")
        mats[refs[0]]["shape_count"] += 1
        filename = shape.find("string[@name='filename']")
        if filename is None:
            raise ValueError("A mesh shape has no filename.")
        mesh = resolve(path.parent, filename.get("value", ""))
        if mesh not in seen:
            files.append({"path": str(mesh), "sha256": sha256(mesh)})
            seen.add(mesh)
    if not shapes:
        raise ValueError("No mesh shapes found in the scene.")
    return {"materials": mats, "shape_count": len(shapes), "files": files}


def load_experiment(path):
    path = Path(path).resolve()
    cfg = read_json(path)
    required = {"schema_version", "required_sionna_rt", "runtime_variant", "scene",
                "arrays", "devices", "solver", "deterministic", "materials",
                "comparison", "scenes"}
    if set(cfg) != required or cfg["schema_version"] != 1:
        raise ValueError(f"Invalid configuration keys/schema; expected {sorted(required)}")
    if cfg["required_sionna_rt"] != "2.1.0":
        raise ValueError("This comparison is pinned to Sionna RT 2.1.0.")
    if cfg["runtime_variant"] not in (None, "cuda_ad_mono_polarized", "llvm_ad_mono_polarized"):
        raise ValueError("Use null (Sionna default) or a supported polarized Mitsuba variant.")
    if set(cfg["solver"]) != SOLVER_KEYS:
        raise ValueError("The solver block must specify every supported solver option explicitly.")
    for key in SOLVER_KEYS - {"max_depth", "max_num_paths_per_src", "samples_per_src", "seed"}:
        if type(cfg["solver"][key]) is not bool:
            raise ValueError(f"solver.{key} must be a JSON boolean.")
    for key in ("max_depth", "max_num_paths_per_src", "samples_per_src", "seed"):
        value = cfg["solver"][key]
        if type(value) is not int or value < (1 if key in ("max_num_paths_per_src", "samples_per_src") else 0):
            raise ValueError(f"Invalid solver.{key}")
    if type(cfg["deterministic"]) is not bool:
        raise ValueError("deterministic must be a JSON boolean.")
    if set(cfg["scene"]) != {"frequency_hz", "bandwidth_hz", "temperature_k", "merge_shapes"}:
        raise ValueError("Invalid scene settings.")
    if cfg["scene"]["frequency_hz"] != 26e9:
        raise ValueError("These material values are evaluated at 26 GHz; frequency sweeps need new values.")
    if cfg["scene"]["bandwidth_hz"] <= 0 or cfg["scene"]["temperature_k"] <= 0:
        raise ValueError("Bandwidth and temperature must be positive.")
    if type(cfg["scene"]["merge_shapes"]) is not bool:
        raise ValueError("merge_shapes must be a JSON boolean.")
    for group in ("devices", "arrays"):
        if set(cfg[group]) != {"tx", "rx"}:
            raise ValueError("This experiment uses exactly one TX and one RX.")
    for role, d in cfg["devices"].items():
        expected = {"name", "position", "look_at", "velocity"} | ({"power_dbm"} if role == "tx" else set())
        if set(d) != expected:
            raise ValueError(f"Invalid {role} device keys.")
        for key in ("position", "look_at", "velocity"):
            if len(d[key]) != 3 or not np.all(np.isfinite(d[key])):
                raise ValueError(f"Invalid {role}.{key}")
        if np.linalg.norm(np.array(d["position"]) - d["look_at"]) == 0:
            raise ValueError("A device cannot look at its own position.")
    for name, mat in cfg["materials"].items():
        if set(mat) != MATERIAL_KEYS or mat["scattering_pattern"] != "lambertian":
            raise ValueError(f"Invalid material {name}; this experiment uses Lambertian scattering.")
        if not all(math.isfinite(mat[k]) for k in MATERIAL_KEYS - {"scattering_pattern"}):
            raise ValueError(f"Non-finite material value in {name}")
        if mat["relative_permittivity"] < 1 or min(mat["conductivity"], mat["thickness"]) < 0:
            raise ValueError(f"Invalid dielectric/thickness for {name}")
        if not all(0 <= mat[k] <= 1 for k in ("scattering_coefficient", "xpd_coefficient")):
            raise ValueError(f"Invalid scattering/XPD for {name}")
    if set(cfg["comparison"]) != {"gain_tolerance_db", "delay_tolerance_ns"}:
        raise ValueError("Specify gain_tolerance_db and delay_tolerance_ns.")
    if any(not math.isfinite(v) or v < 0 for v in cfg["comparison"].values()):
        raise ValueError("Comparison tolerances must be finite and nonnegative.")
    if not cfg["scenes"]:
        raise ValueError("The scenes list is empty.")
    names = set()
    for item in cfg["scenes"]:
        if not {"id", "xml", "material_bindings"} <= set(item):
            raise ValueError("Each scene needs id, xml and material_bindings.")
        extra = set(item) - {"id", "xml", "material_bindings", "frame", "geometry_seed",
                             "reference_npz", "reference_metrics", "notes"}
        if extra:
            raise ValueError(f"Unknown scene options: {extra}")
        name = item["id"]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", name) or name in names:
            raise ValueError(f"Use a unique simple scene ID: {name}")
        names.add(name)
        item["xml"] = str(resolve(path.parent, item["xml"]))
        if item.get("reference_npz"):
            item["reference_npz"] = str(resolve(path.parent, item["reference_npz"]))
            if not Path(item["reference_npz"]).is_file():
                raise FileNotFoundError(item["reference_npz"])
        inv = scene_inventory(item["xml"])
        used = {k for k, v in inv["materials"].items() if v["shape_count"]}
        bindings = item["material_bindings"]
        if not used <= set(bindings) or not set(bindings) <= set(inv["materials"]):
            raise ValueError(f"{name}: bind all used material IDs. Found: {sorted(inv['materials'])}")
        for key, preset in bindings.items():
            normalized = material_name(key)
            if normalized.startswith(("itu_", "itu-")) or normalized == "wood":
                raise ValueError(f"{key}: reserved ITU material name; use a custom ID such as plant_wood.")
            if preset not in cfg["materials"]:
                raise ValueError(f"Unknown material preset {preset}")
            if inv["materials"][key]["type"] != "radio-material":
                raise ValueError(f"{key}: use a radio-material BSDF, not an optical Blender material; see README.")
        item["input_inventory"] = inv
    return cfg


def first_pair(array, name, leading=0):
    """Select RX0/RX antenna0/TX0/TX antenna0, preserving every path."""
    array = np.asarray(array)
    n = array.ndim - leading
    if n == 3:
        idx = (slice(None),) * leading + (0, 0, slice(None))
    elif n == 5:
        idx = (slice(None),) * leading + (0, 0, 0, 0, slice(None))
    else:
        raise ValueError(f"Unsupported {name} shape {array.shape}")
    return array[idx]


def summarize(arrays):
    valid = first_pair(arrays["valid"], "valid").astype(bool)
    real = first_pair(arrays["a_real"], "a_real").astype(np.float64)
    imag = first_pair(arrays["a_imag"], "a_imag").astype(np.float64)
    tau = first_pair(arrays["tau"], "tau").astype(np.float64)
    interactions = first_pair(arrays["interactions"], "interactions", leading=1)
    if real.shape != valid.shape or imag.shape != valid.shape or tau.shape != valid.shape:
        raise ValueError("Coefficient, delay and validity path dimensions do not match.")
    if interactions.shape[1:] != valid.shape:
        raise ValueError("Interaction path dimension does not match validity.")
    p = real[valid] ** 2 + imag[valid] ** 2
    delay_ns = tau[valid] * 1e9
    if not (np.all(np.isfinite(p)) and np.all(np.isfinite(delay_ns))) or np.any(delay_ns < 0):
        raise ValueError("Non-finite coefficients or invalid delays on valid paths.")
    count = int(valid.sum())
    total = float(p.sum())
    result = dict.fromkeys(METRICS, None)
    result.update(path_count=count, los_available=bool(np.any(np.all(interactions[:, valid] == 0, axis=0))),
                  total_power_linear=total)
    if count:
        first = float(delay_ns.min())
        result["first_arrival_ns"] = first
        if total > 0:
            excess = delay_ns - first
            mean = float(np.dot(p, excess) / total)
            result.update(total_power_db=10 * math.log10(total),
                          strongest_path_gain_db=10 * math.log10(float(p.max())),
                          mean_excess_delay_ns=mean,
                          rms_delay_spread_ns=math.sqrt(float(np.dot(p, (excess - mean) ** 2) / total)))
    return result


def compare_metrics(result, reference, tolerances):
    rows = []
    for metric in METRICS:
        if metric not in reference:
            raise ValueError(f"Reference is missing {metric}.")
        new, old = result[metric], reference[metric]
        tol = (0 if metric in ("path_count", "los_available") else
               tolerances["delay_tolerance_ns"] if metric.endswith("_ns") else
               tolerances["gain_tolerance_db"])
        if new is None or old is None:
            delta, matched = None, new is None and old is None
        else:
            if not math.isfinite(float(old)):
                raise ValueError(f"Non-finite reference {metric}")
            delta = float(new) - float(old)
            matched = abs(delta) <= tol
        rows.append({"metric": metric, "native": new, "reference": old,
                     "difference": delta, "absolute_tolerance": tol, "within_tolerance": matched})
    all_match = all(r["within_tolerance"] for r in rows)
    meaningful = result["total_power_db"] is not None and reference["total_power_db"] is not None
    status = "within_tolerances" if all_match and meaningful else "no_comparable_power" if all_match else "different"
    return {"status": status, "metrics": rows,
            "scope": "First-antenna-pair aggregate metrics; not path-by-path or physical validation."}


def to_numpy(value):
    return np.asarray(value.numpy() if hasattr(value, "numpy") else value).copy()


def scalar(value):
    return float(to_numpy(value).reshape(-1)[0])


def material_name(value):
    return value[4:] if value.startswith("mat-") else value


def configure_materials(scene, item, cfg, LambertianPattern):
    """Update loaded radio-materials in place to preserve merged-mesh bindings."""
    resolved, matched = [], set()
    for xml_id, preset in item["material_bindings"].items():
        candidates = []
        for key, material in scene.radio_materials.items():
            aliases = [str(key), str(material.name), str(material.id())]
            if material_name(xml_id) in {material_name(a) for a in aliases}:
                candidates.append(material)
        if len(candidates) != 1:
            raise ValueError(f"Cannot uniquely match material {xml_id}; loaded: {list(scene.radio_materials)}")
        material = candidates[0]
        if id(material) in matched:
            raise ValueError("Multiple XML bindings resolve to the same loaded material.")
        matched.add(id(material))
        spec = cfg["materials"][preset]
        for key in MATERIAL_KEYS - {"scattering_pattern"}:
            setattr(material, key, spec[key])
        material.scattering_pattern = LambertianPattern()
        resolved.append({"xml_id": xml_id, "runtime_name": material.name, "preset": preset,
                         **{k: scalar(getattr(material, k)) for k in MATERIAL_KEYS - {"scattering_pattern"}},
                         "scattering_pattern": "lambertian"})
    for name, obj in scene.objects.items():
        if id(obj.radio_material) not in matched:
            raise ValueError(f"Object {name} has no explicitly configured radio material.")
    return resolved


def runtime_imports(cfg):
    installed = importlib.metadata.version("sionna-rt")
    if installed != cfg["required_sionna_rt"]:
        raise RuntimeError(f"Expected sionna-rt==2.1.0, found {installed}. Use the same runtime as the recorded runs.")
    import mitsuba as mi
    if cfg["runtime_variant"]:
        mi.set_variant(cfg["runtime_variant"])
    import sionna.rt as rt
    import drjit as dr
    if cfg["runtime_variant"] and mi.variant() != cfg["runtime_variant"]:
        raise RuntimeError("Sionna changed the requested Mitsuba variant.")
    versions = {}
    for name in ("sionna-rt", "mitsuba", "drjit", "numpy"):
        versions[name] = importlib.metadata.version(name)
    return rt, dr, {"packages": versions, "python": sys.version, "executable": sys.executable,
                    "platform": platform.platform(), "mitsuba_variant": mi.variant()}


def solve_one(rt, dr, cfg, item, directory):
    start = time.perf_counter()
    scene = rt.load_scene(item["xml"], merge_shapes=cfg["scene"]["merge_shapes"])
    scene.frequency = cfg["scene"]["frequency_hz"]
    scene.bandwidth = cfg["scene"]["bandwidth_hz"]
    scene.temperature = cfg["scene"]["temperature_k"]
    scene.tx_array = rt.PlanarArray(**cfg["arrays"]["tx"])
    scene.rx_array = rt.PlanarArray(**cfg["arrays"]["rx"])
    materials = configure_materials(scene, item, cfg, rt.LambertianPattern)
    for name in list(scene.transmitters) + list(scene.receivers):
        scene.remove(name)
    for role, cls in (("tx", rt.Transmitter), ("rx", rt.Receiver)):
        spec = cfg["devices"][role]
        device = cls(name=spec["name"], position=spec["position"], orientation=[0., 0., 0.])
        scene.add(device)
        device.look_at(spec["look_at"])
        device.velocity = spec["velocity"]
        if role == "tx":
            device.power_dbm = spec["power_dbm"]
    # Fresh solver and scene per frozen geometry, matching procedural frame runs.
    solver = rt.PathSolver(deterministic=cfg["deterministic"])
    dr.sync_thread()
    setup_seconds = time.perf_counter() - start
    start = time.perf_counter()
    paths = solver(scene=scene, **cfg["solver"])
    dr.sync_thread()
    solver_seconds = time.perf_counter() - start
    arrays = {k: to_numpy(getattr(paths, k)) for k in
              ("valid", "tau", "interactions", "vertices", "objects", "sources", "targets", "doppler")}
    arrays["a_real"], arrays["a_imag"] = (to_numpy(v) for v in paths.a)
    metrics = summarize(arrays)
    np.savez_compressed(directory / "paths.npz", **arrays)
    valid = first_pair(arrays["valid"], "valid").astype(bool)
    ar = first_pair(arrays["a_real"], "a_real")
    ai = first_pair(arrays["a_imag"], "a_imag")
    tau = first_pair(arrays["tau"], "tau")
    interactions = first_pair(arrays["interactions"], "interactions", leading=1)
    with (directory / "paths_first_pair.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["path_index", "coefficient_real", "coefficient_imag", "delay_s", "path_gain_db", "interaction_codes"])
        for i in np.flatnonzero(valid):
            power = float(ar[i]) ** 2 + float(ai[i]) ** 2
            codes = [int(v) for v in interactions[:, i] if v != 0]
            writer.writerow([int(i), float(ar[i]), float(ai[i]), float(tau[i]),
                             10 * math.log10(power) if power > 0 else "", json.dumps(codes)])
    result = {"id": item["id"], "frame": item.get("frame"), "geometry_seed": item.get("geometry_seed"),
              "metrics": metrics, "resolved_materials": materials,
              "tensor_shapes": {k: list(v.shape) for k, v in arrays.items()},
              "setup_seconds": setup_seconds, "solver_seconds": solver_seconds,
              "metric_definition": "All valid paths for RX0/antenna0, TX0/antenna0; incoherent sum |a|^2."}
    reference = item.get("reference_metrics")
    if item.get("reference_npz"):
        with np.load(item["reference_npz"], allow_pickle=False) as previous:
            raw_reference = summarize(previous)
        result["reference_npz_sha256"] = sha256(item["reference_npz"])
        if reference is not None:
            result["reference_export_check"] = compare_metrics(raw_reference, reference, cfg["comparison"])
        else:
            reference = raw_reference
    if reference is not None:
        result["comparison"] = compare_metrics(metrics, reference, cfg["comparison"])
    write_json(directory / "result.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("configuration", nargs="?", help="JSON configuration containing a scenes list")
    parser.add_argument("--inspect", metavar="SCENE_XML", help="List XML material IDs and mesh hashes; no simulation")
    parser.add_argument("--check", action="store_true", help="Validate configuration and input files; no simulation")
    parser.add_argument("--output", default="native_results", help="Parent folder for a new timestamped batch")
    args = parser.parse_args(argv)
    if args.inspect:
        print(json.dumps(scene_inventory(args.inspect), indent=2))
        return 0
    if not args.configuration:
        parser.error("Provide a configuration JSON or --inspect SCENE_XML.")
    cfg = load_experiment(args.configuration)
    print(f"Validated {len(cfg['scenes'])} scenes; solver seed {cfg['solver']['seed']}; "
          f"{cfg['solver']['samples_per_src']:,} samples per source.", flush=True)
    if args.check:
        print("Input checks complete. Sionna has not been imported or run.")
        return 0
    rt, dr, runtime = runtime_imports(cfg)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    batch = Path(args.output).resolve() / stamp
    batch.mkdir(parents=True, exist_ok=False)
    write_json(batch / "resolved_configuration.json", cfg)
    write_json(batch / "runtime.json", {**runtime, "created_utc": stamp,
                                       "script_sha256": sha256(__file__),
                                       "configuration_sha256": sha256(args.configuration)})
    completed, failures = [], []
    for number, item in enumerate(cfg["scenes"], 1):
        print(f"[{number}/{len(cfg['scenes'])}] {item['id']}", flush=True)
        directory = batch / item["id"]
        directory.mkdir()
        try:
            # Stop if an input changed between preflight and execution.
            for entry in item["input_inventory"]["files"]:
                if sha256(entry["path"]) != entry["sha256"]:
                    raise RuntimeError(f"Input changed after preflight: {entry['path']}")
            result = solve_one(rt, dr, cfg, item, directory)
            completed.append(result)
            print(f"  summed gain: {result['metrics']['total_power_db']} dB; "
                  f"comparison: {result.get('comparison', {}).get('status', 'not requested')}", flush=True)
        except Exception as exc:
            failure = {"id": item["id"], "error": str(exc), "traceback": traceback.format_exc()}
            failures.append(failure)
            write_json(directory / "error.json", failure)
            print(f"  ERROR: {exc}", file=sys.stderr, flush=True)
            break  # Fail fast: avoid repeating an invalid experiment.
        finally:
            write_json(batch / "batch_summary.json", {"completed": completed, "failures": failures,
                       "requested_scene_count": len(cfg["scenes"]),
                       "not_run_count": len(cfg["scenes"]) - len(completed) - len(failures)})
    with (batch / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["id", "frame", "geometry_seed", *METRICS, "comparison"])
        writer.writeheader()
        for row in completed:
            writer.writerow({"id": row["id"], "frame": row["frame"], "geometry_seed": row["geometry_seed"],
                             **{k: row["metrics"][k] for k in METRICS},
                             "comparison": row.get("comparison", {}).get("status", "not_requested")})
    print(f"Saved: {batch}", flush=True)
    if failures:
        return 1
    if any(c.get("comparison", {}).get("status") in ("different", "no_comparable_power") or
           c.get("reference_export_check", {}).get("status") in ("different", "no_comparable_power") for c in completed):
        return 2
    return 0


def cli_exit(code):
    # The tested Windows Mitsuba/Dr.Jit stack can fail during DLL finalization
    # after successful work. All output files are already closed here. End only
    # this CLI process, preserving its real success/error/comparison exit code.
    # Imported/notebook use never invokes this function.
    if os.name == "nt" and "sionna.rt" in sys.modules:
        import ctypes
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.flush()
            except OSError:
                code = code or 1
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        kernel.TerminateProcess.restype = ctypes.c_int
        if not kernel.TerminateProcess(kernel.GetCurrentProcess(), code):
            raise ctypes.WinError(ctypes.get_last_error())
    raise SystemExit(code)


if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        exit_code = 1
    cli_exit(exit_code)
