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
- HDF5 schema v5 export.
- Tile_spacial_dataset spatial integration.
- Automatic bundled Geometry Nodes.
- PointCloud-driven TX/RX motion.
- Dynamic simulation mode.
- Blender 5.2 setup documentation.

### Changed
- Updated minimum Blender version to 5.2.
- Updated simulation and radio-map worker architecture.
- Coverage exports support frame-stacked 2D and 3D tensors.
