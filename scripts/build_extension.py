#!/usr/bin/env python3
from __future__ import annotations
import hashlib
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "sionnart_bridge"
DIST = ROOT / "dist"

with (SOURCE / "blender_manifest.toml").open("rb") as handle:
    manifest = tomllib.load(handle)
version = manifest["version"]
extension_id = manifest["id"]
paths = manifest["build"]["paths"]

DIST.mkdir(exist_ok=True)
out = DIST / f"{extension_id}-{version}.zip"
with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for relative in paths:
        source = SOURCE / relative
        if not source.is_file():
            raise FileNotFoundError(source)
        info = zipfile.ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, source.read_bytes())

digest = hashlib.sha256(out.read_bytes()).hexdigest()
checksum = out.with_suffix(out.suffix + ".sha256")
checksum.write_text(f"{digest}  {out.name}\n", encoding="utf-8")
print(out)
print(checksum)
