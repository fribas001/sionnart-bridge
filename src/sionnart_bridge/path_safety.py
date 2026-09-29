"""Portable path-budget helpers for the mixed Python/native Windows toolchain.

The 240 UTF-16-unit ceiling is a conservative bridge policy, not a claim that
all Windows APIs have the same limit. Keeping ordinary absolute paths short
also protects native readers that do not support Python's extended paths.
No system settings, drive mappings, junctions or file redirection are changed.
"""
from __future__ import annotations

import hashlib
import ntpath
import os
from pathlib import PureWindowsPath
import re

WINDOWS_PLATFORM = os.name == "nt"
WINDOWS_SAFE_PATH_UNITS = 240
# Covers snapshot/scene/meshes, bounded asset names and atomic-JSON temp suffixes.


class PathLengthError(ValueError):
    """A generated path would exceed the bridge's Windows compatibility budget."""


def absolute_path_text(path) -> str:
    text = os.fspath(path)
    # Also allow exact Windows paths to be examined in portable regression tests.
    if PureWindowsPath(text).is_absolute():
        return ntpath.normpath(text)
    return os.path.abspath(text)


def windows_path_units(path) -> int:
    """Length in UTF-16 code units, excluding the terminating NUL."""
    return len(absolute_path_text(path).encode("utf-16-le", errors="surrogatepass")) // 2


def validate_path_budget(path, *, reserve=0, purpose="file", windows=None) -> int:
    reserve = int(reserve)
    if reserve < 0:
        raise ValueError("Path-length reserve must be nonnegative")
    units = windows_path_units(path)
    windows = WINDOWS_PLATFORM if windows is None else bool(windows)
    if windows and units + reserve > WINDOWS_SAFE_PATH_UNITS:
        tail = f" plus {reserve} reserved units for generated files" if reserve else ""
        raise PathLengthError(
            f"Windows path budget exceeded for {purpose}: {units} UTF-16 units{tail}; "
            f"the bridge's compatibility limit is {WINDOWS_SAFE_PATH_UNITS}. "
            "Choose a shorter Results folder (for example D:\\Sionna_runs) or workspace, "
            "then start a NEW run; Resume keeps the old saved paths. "
            f"Path: {absolute_path_text(path)}"
        )
    return units






def mesh_asset_filename(mesh_dir, label: str, ordinal: int, *, prefix="", windows=None) -> str:
    """Bounded, deterministic ASCII PLY name; ordinal prevents case collisions.

    Original object/material names are retained in the exported asset-name
    map. Prefixes (used by ordinary animation export) enter the hash instead of
    lengthening the on-disk path without limit.
    """
    ordinal = int(ordinal)
    if ordinal < 0:
        raise ValueError("Mesh ordinal must be nonnegative")
    identity = f"{prefix}\0{label}\0{ordinal}"
    digest = hashlib.sha256(identity.encode("utf-8", errors="replace")).hexdigest()[:10]
    suffix = f"_{digest}_{ordinal:06d}.ply"
    readable = re.sub(r"[^A-Za-z0-9._-]+", "_", str(label)).strip("._-") or "mesh"
    windows = WINDOWS_PLATFORM if windows is None else bool(windows)
    available = 24
    if windows:
        available = min(available, WINDOWS_SAFE_PATH_UNITS - windows_path_units(mesh_dir) - 1 - len(suffix))
    if available < 1:
        # Raise the same actionable exception used by the early run preflight.
        validate_path_budget(mesh_dir, reserve=1 + 1 + len(suffix),
                             purpose="mesh export directory", windows=windows)
    name = readable[:max(1, available)] + suffix
    # Use ntpath for Windows-style examples without changing host file semantics.
    full_path = (ntpath.join(str(mesh_dir), name) if PureWindowsPath(str(mesh_dir)).is_absolute()
                 else os.path.join(os.fspath(mesh_dir), name))
    validate_path_budget(full_path, purpose="PLY mesh export", windows=windows)
    return name
