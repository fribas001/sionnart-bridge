# SoftwareX code metadata values for v1.8.2

Use these values for the SoftwareX code-metadata table for the published `v1.8.2` release and archival record.

> **Before submission:** verify that the GitHub release URL and version-specific DOI remain consistent with the published v1.8.2 Zenodo record.

- **C1 — Current code version:** SionnaRT-Bridge v1.8.2
- **C2 — Permanent link to code/repository:** GitHub `v1.8.2` release URL and the version-specific archival DOI
- **C3 — Reproducible capsule / additional archive:** `N/A` if the manuscript examples are included in the tagged repository/release; otherwise provide the persistent identifier for any separately archived large reproducibility assets
- **C4 — Legal code license:** GPL-3.0-or-later
- **C5 — Code versioning system:** Git
- **C6 — Software code languages, tools, and services used:** Python; Blender Python API; Blender Geometry Nodes; Sionna; Sionna RT; Mitsuba 3; DrJit; h5py
- **C7 — Compilation requirements, operating environments, and dependencies:** Blender 5.2; Blender Python 3.13; Sionna 2.0.1; Sionna RT 2.0.1; Mitsuba 3.8.0; DrJit 1.3.1; h5py 3.16.0; Windows 11 x64 for the SoftwareX reference environment; supported Mitsuba/DrJit CPU or GPU backend as documented by the project
- **C8 — Installation requirements and guidance:** repository `README.md`, `docs/installation.md`, `docs/SIONNA_2_BLENDER_5_2_WINDOWS.md`, `docs/USER_GUIDE.md`, `docs/SIMULATION_PARAMETERS.md`, and `docs/WORKFLOWS.md`
- **C9 — Support email:** felipe.oliveiraribas@ugent.be

## Release and archive identifiers

The v1.8.2 GitHub release and Zenodo archival record are published:

```text
GitHub release:
https://github.com/fribas001/sionnart-bridge/releases/tag/v1.8.2

Version DOI:
10.5281/zenodo.20125209

Archive record:
https://zenodo.org/records/20125209
```

## Consistency checks before submission

Confirm that the values above match:

- `src/sionnart_bridge/blender_manifest.toml`
- `src/sionnart_bridge/__init__.py`
- `CITATION.cff`
- `README.md`
- the Git tag and GitHub release
- the SoftwareX manuscript metadata table
- the archival DOI record

Do not update the repository to `v1.8.2` piecemeal. Perform the final version bump across all release metadata together after documentation and release checks are complete.
