# 2.0.0

This release consolidates procedural simulation, vegetation measurement and parameter analysis with a broader workflow regression suite.

## Reliability fixes

- Isolated Windows workers now flush their streams and exit through a shared process-exit routine. This avoids the reproducible Mitsuba/Dr.Jit DLL-detach crash while preserving success/failure codes. Runtime probes use the same routine.
- Nonzero worker exits are rejected and diagnostic files retained.
- Completed workers remain owned until their outputs have been consumed; all run operators check every simulation category.
- Added Stop Simulation. Cancellation clears queued outputs, retains partial files and releases the owned run lock. File loading and extension disabling stop owned workers.
- Zero-path solutions retain an empty embedded result and complete parameter observations; gain is unavailable rather than an invented finite floor.
- Optional curve import no longer removes the embedded paths result or unrelated objects in its collection.
- A later successful batch output no longer hides an earlier output failure. Failed/cancelled receipts are never recovered as successful.
- Live movement detection now uses original Blender object identities consistently, fixing a missed first movement when dependency-graph updates contain evaluated IDs.
- New scenes refresh static geometry by default; intentional cache reuse has a visible reminder.

## Included scientific workflow

Per-frame Geometry Nodes metadata, parameter plots and descriptive statistics, vegetation measurements, reference leaf/wood materials, 2D/projected/stacked radio maps, antenna arrays, device motion and Doppler are retained. Optional sensing is retained, disabled by default and covered by a self-contained test. RIS and crowd integrations remain excluded.

The extension identifier and existing result schemas remain compatible with the preceding release. No existing simulation data or Blender project is modified by installing this ZIP. Defaults stored in an older project retain their saved values.


---

# Changelog

All notable changes to SionnaRT-Bridge are documented here.

The project uses semantic versioning for publication releases.

## 1.8.2 - 2026-09-03

### Documentation

- Added SoftwareX-oriented user guide, simulation-parameter reference, workflows, validation, reproducibility, installation, Geometry Nodes, and release documentation.
- Updated the documented reference environment to Blender 5.2, Python 3.13, Sionna 2.0.1, Sionna RT 2.0.1, Mitsuba 3.8.0, DrJit 1.3.1, and h5py 3.16.0.
- Clarified that the current workflow uses the integrated Mitsuba scene exporter and bundled Geometry Nodes library.
- Updated SoftwareX metadata, third-party software references, release checklist, and archival workflow.

### Changed

- Updated release metadata and documentation for SionnaRT-Bridge 1.8.2.
- Removed obsolete v1.0.0 publication planning and stale Blender 4.5 references.
- Documented the reserved version-specific Zenodo DOI: 10.5281/zenodo.20125209.

## 1.8.1 - 2026-09-01

### Documentation

- Added step-by-step installation instructions for Sionna 2.0.1 with Blender 5.2.
- Documented the dedicated `blender52-sionna` environment.
- Added Sionna RT, Mitsuba, DrJit and CUDA verification commands.
- Clarified that Sionna is required separately and is not bundled with the extension.

### Added
- Blender 5.2 and Python 3.13 workflow.
- Integrated Mitsuba scene exporter.
- Automatic bundled Geometry Nodes.
- PointCloud-driven TX/RX motion.
- Dynamic simulation mode.
- Blender 5.2 setup documentation.

### Changed
- Updated minimum Blender version to 5.2.
- Updated simulation and radio-map worker architecture.
- Coverage exports support frame-stacked 2D and 3D tensors.
