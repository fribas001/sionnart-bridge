#!/usr/bin/env python3

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "sionnart_bridge"

errors = []


with (SOURCE / "blender_manifest.toml").open("rb") as handle:
    manifest = tomllib.load(handle)


with (ROOT / "CITATION.cff").open("r", encoding="utf-8") as handle:
    citation = yaml.safe_load(handle)


init_text = (SOURCE / "__init__.py").read_text(encoding="utf-8")

match = re.search(
    r'^_ADDON_VERSION\s*=\s*"([^"]+)"',
    init_text,
    re.MULTILINE,
)

addon_version = match.group(1) if match else None


if manifest.get("id") != "sionnart_bridge":
    errors.append("manifest id must be sionnart_bridge")


if manifest.get("name") != "SionnaRT-Bridge":
    errors.append("manifest name must be SionnaRT-Bridge")


manifest_version = manifest.get("version")

if not manifest_version:
    errors.append("manifest version is missing")


if addon_version != manifest_version:
    errors.append(
        f"__init__.py version {addon_version!r} "
        f"!= manifest version {manifest_version!r}"
    )


if citation.get("version") != manifest_version:
    errors.append(
        f"CITATION.cff version {citation.get('version')!r} "
        f"!= manifest version {manifest_version!r}"
    )


if citation.get("title") != manifest.get("name"):
    errors.append("CITATION.cff title does not match manifest")


if not (ROOT / "LICENSE").is_file():
    errors.append("LICENSE is missing")


for relative in manifest.get("build", {}).get("paths", []):
    if not (SOURCE / relative).is_file():
        errors.append(f"build path is missing: {relative}")


for source in SOURCE.glob("*.py"):
    try:
        ast.parse(
            source.read_text(encoding="utf-8"),
            filename=str(source),
        )
    except SyntaxError as exc:
        errors.append(f"syntax error in {source.name}: {exc}")


if errors:
    print("Release check failed:")

    for error in errors:
        print(f"- {error}")

    sys.exit(1)


print("Release metadata and source checks passed")
print(f"Extension version: {manifest_version}")
