from pathlib import Path
import re
import tomllib

import yaml


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "sionnart_bridge"


def test_manifest_and_citation_are_consistent():
    with (SOURCE / "blender_manifest.toml").open("rb") as handle:
        manifest = tomllib.load(handle)

    citation = yaml.safe_load(
        (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    )

    init_text = (SOURCE / "__init__.py").read_text(
        encoding="utf-8"
    )

    match = re.search(
        r'^_ADDON_VERSION\s*=\s*"([^"]+)"',
        init_text,
        re.MULTILINE,
    )

    assert match is not None, "_ADDON_VERSION not found in __init__.py"

    addon_version = match.group(1)

    assert manifest["id"] == "sionnart_bridge"
    assert manifest["name"] == "SionnaRT-Bridge"

    assert citation["title"] == manifest["name"]
    assert citation["version"] == manifest["version"]
    assert addon_version == manifest["version"]


def test_all_manifest_build_paths_exist():
    with (SOURCE / "blender_manifest.toml").open("rb") as handle:
        manifest = tomllib.load(handle)

    for relative in manifest["build"]["paths"]:
        assert (SOURCE / relative).is_file(), relative
