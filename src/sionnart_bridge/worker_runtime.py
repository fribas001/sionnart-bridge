"""Shared external-worker services; no Blender or eager Sionna imports.

Caches are bounded to the current scene and worker invocation. They never cache
propagation results, device poses, or evaluated procedural geometry.
"""
import copy
import inspect
import importlib.metadata
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

if __package__:
    from . import plant_materials
else:
    import plant_materials

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

def _apply_radio_materials_uncached(scene, frame, runtime):
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
        elif model == "VEGETATION":
            eta_r, sigma = plant_materials.dielectric(spec.get("plant_model"), _scalar_float(scene.frequency))
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
        if model == "VEGETATION":
            summaries[-1]["plant_reference"] = plant_materials.reference(spec["plant_model"], _scalar_float(scene.frequency), spec)
        summaries[-1]["scattering_pattern"] = spec.get("scattering_pattern", "lambertian")
    return summaries

def apply_radio_materials(scene, frame, runtime):
    """Reuse unchanged setup; invalidate for frequency, topology or material edits."""
    signature = (_scalar_float(scene.frequency),
                 json.dumps(frame_materials(runtime, frame), sort_keys=True),
                 tuple((key, id(value)) for key, value in scene.radio_materials.items()),
                 tuple((key, id(obj.radio_material)) for key, obj in scene.objects.items()))
    cached = runtime.get("_bridge_material_cache")
    if cached is not None and cached[0] is scene and cached[1] == signature:
        return copy.deepcopy(cached[2])
    summary = _apply_radio_materials_uncached(scene, frame, runtime)
    runtime["_bridge_material_cache"] = (scene, signature, copy.deepcopy(summary))
    return summary


def ensure_tx_array(scene, runtime, factory, profile):
    """Reuse a role array only while scene, profile and array identity agree."""
    signature = json.dumps(profile, sort_keys=True)
    cached = runtime.get("_bridge_tx_array_cache")
    if (cached is None or cached[0] is not scene or cached[1] != signature
            or scene.tx_array is not cached[2]):
        scene.tx_array = factory(runtime, runtime["PlanarArray"])
        runtime["_bridge_tx_array_cache"] = (scene, signature, scene.tx_array)


def make_path_solver(factory, deterministic=True):
    """2.1 reproducibility support, without masking solver construction errors."""
    parameters = inspect.signature(factory).parameters
    if "deterministic" in parameters:
        return factory(deterministic=bool(deterministic))
    if deterministic:
        print("WARNING: this PathSolver lacks deterministic execution support", flush=True)
    return factory()



def exit_worker(code):
    """Finish an isolated worker after its files have been closed.

    Windows' CRT exit invokes DLL detach callbacks that crash in the tested
    Mitsuba/Dr.Jit build, even after a plain import. Terminate only this worker
    after flushing Python streams; preserve the actual success/failure code.
    Never call this from Blender or another embedding application.
    """
    import sys
    code = int(code)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except (OSError, ValueError):
            code = code or 1
    if os.name == "nt":
        import ctypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        kernel.TerminateProcess.restype = ctypes.c_int
        if not kernel.TerminateProcess(kernel.GetCurrentProcess(), code):
            raise ctypes.WinError(ctypes.get_last_error())
    os._exit(code)
