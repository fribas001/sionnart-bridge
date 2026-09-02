# SionnaRT-Bridge 1.8.0 — Blender 5.2 LTS

## Sionna installation required

SionnaRT-Bridge does not bundle NVIDIA Sionna.

Sionna 2.0.1 must be installed separately before running simulations.

The recommended Windows environment is:

`C:\Users\<username>\blender52-sionna`

For the complete installation procedure, see:

`docs/SIONNA_2_BLENDER_5_2_WINDOWS.md`

## PointCloud motion: live frame-index follower

PointCloud motion no longer bakes one keyframe per point and no longer uses a Copy Location constraint. At each Blender frame the add-on reads `point_index = frame - Start Frame`, evaluates that PointCloud point in world space, and places the chosen TX/RX directly at that world position. This keeps visible points and devices aligned and scales to very large PointCloud paths. The handler is registered only while at least one PointCloud path is connected and runs only when the Blender frame changes.


This build targets **Blender 5.2 LTS / Python 3.13** and defaults to the Blender-Python runtime.


## Tile_dataset spatial linkage (1.8.0)

When HDF5 export is selected and a PointCloud named `Tile_spacial_dataset` is present, coverage-map runs automatically snapshot the complete numeric tile dataset and embed it at:

```text
/spatial_datasets/Tile_spacial_dataset
```

2D and 3D coverage simulations then add `/simulations/<coverage>/spatial_join`. `tile_index` maps each coverage cell center in XY to the containing Tile_dataset point. The complete tile attributes remain stored once under the spatial dataset, while `tile_context` exposes convenient aligned views for common fields such as building mask, neighborhood ID/population, ROI/buffer membership, and base-station counts. For regular 3D volumes the tile join is stored as `(y,x)` and broadcasts over the coverage `(frame,z,y,x)` tensor.

No Tile_dataset object is required for normal Sionna export; the linkage is automatic only when the compatible PointCloud is found.

## PointCloud TX/RX motion paths (1.7.2)

**Devices → Generate Template Paths → Style → PointCloud** drives a marked TX or RX from any Blender PointCloud selected with the object picker/eyedropper. The source PointCloud is never modified.

The mapping is deterministic: point index `0` → `Start Frame`, point index `1` → `Start Frame + 1`, and point index `i` → `Start Frame + i`.

Version 1.7.2 uses a live frame-index follower instead of a baked hidden anchor. On every Blender frame change it evaluates the chosen PointCloud sample in world space and writes the TX/RX world translation directly. This avoids coordinate/constraint offsets and avoids creating hundreds of thousands of animation keyframes for large SUMO point clouds. Source edits and transforms are therefore reflected live without rebuilding the path.

The frame handler exists only while at least one PointCloud path is connected and only runs when the frame changes; it is not a continuous background timer. The UI reports the current point index and alignment error in meters.


## Runtime

You do **not** need to select an external Python interpreter in the normal workflow. The bridge launches isolated worker processes with Blender 5.2's bundled `python.exe` so heavy Mitsuba/Dr.Jit/CUDA solves do not block the Blender UI.

Sionna can be either directly importable by Blender or installed in a dedicated environment such as `C:\Users\<user>\blender52-sionna\Lib\site-packages`. The latter is the tested configuration. The add-on auto-detects `~/blender52-sionna` and exposes those packages to Blender's worker Python.

The runtime test now also reports **h5py**, which is used for HDF5 exports.

## Dynamic Mode

**Simulation → Dynamic Mode** is the master switch for movement-driven background work.

- OFF: TX/RX movement listeners and queued auto-compute timers are disabled. Manual **Run Simulation** still works normally.
- ON: moving a marked TX/RX can trigger the enabled live outputs after the configured debounce delay.
- Worker processes remain short-lived and start only for an actual manual or dynamic simulation.

## Result export modes (new in 1.4.0)

**Simulation → Export Results** is now one dropdown:

- **No File Export** — result data is embedded in Blender and temporary worker files are deleted.
- **CSV + Metadata** — keeps one category-specific CSV and one `.metadata.json` file for each enabled simulation category. Files from the same **Run Simulation** batch share one timestamp/run ID and one export folder.
- **HDF5 + Metadata** — keeps one `.h5` file and one `.metadata.json` file for the whole **Run Simulation** batch. If paths, 2D coverage, and 3D coverage are selected together, all three categories are stored in that same HDF5 file.

Intermediate worker CSV/JSON/NPZ/config/log files are removed after Blender has verified and embedded the result. Exported filenames include the blend/project name, simulation category (CSV) or simulation batch (HDF5), UTC timestamp, and run ID, for example:

`campus__paths__20260830T003215_123456Z__a1b2c3d4.csv`

`campus__simulation__20260830T003318_654321Z__e5f6a7b8.h5`

The metadata JSON records the run ID, timestamps, Blender source file, scene name, bridge version, scene hash, full simulation parameters, TX/RX/material input data, and result summary.

### CSV schemas

Each simulation category keeps its own table shape:

- **Propagation paths** — point/path records including frame, path ID/rank, XYZ vertices, interactions, object IDs, path gain, delay, amplitude/phase, Doppler, velocities, distances, and TX/RX coordinates.
- **2D coverage** — coverage cells including frame, XYZ, cell geometry/surface information, associated TX, validity, normalized metric, and selected path-gain/RSS/SINR values.
- **3D coverage** — volume samples including frame, XYZ, voxel cell sizes, associated TX, and selected path-gain/RSS/SINR values.

### HDF5 schema v5

HDF5 exports use category-specific layouts rather than forcing every simulation into the same per-frame tree.

```text
/
├── metadata/
│   ├── export_json
│   ├── schema/
│   │   └── enums/
│   ├── configs/
│   └── results_summaries/
└── simulations/
    ├── paths/
    ├── coverage_2d/
    └── coverage_3d/
```

Coverage maps are stored as explicit time-series tensors whenever their grid shape is stable:

- 2D planar coverage: `simulations/coverage_2d/data/values_db` -> `(frame, y, x)`
- 2D projected coverage: `(frame, cell)`
- 3D coverage: `simulations/coverage_3d/data/values_db` -> **`(frame, z, y, x)`**, validated as the canonical 4D representation

Their `coordinates/` groups contain the frame scale and shared x/y/z/cell coordinates where available. HDF5 dimension labels/scales are attached to the dense datasets. Per-frame configuration lives in `frame_metadata/`, including scene XML hashes, geometry signatures, TX/RX positions and velocities, plus configured and evaluated material metadata. If one raw array changes shape during an animation, only that array falls back to `frame_extras/`; stable map arrays remain stacked.

Propagation paths remain ragged by nature. `simulations/paths/derived_path_points` contains the flattened columnar analysis table, while native Sionna path tensors remain under `frames/frame_XXXXXX/raw`. `metadata/schema/enums` documents the path point-role and interaction-type IDs.

A convenience `derived_cells` table remains available for coverage exports, but the dense `data/` tensors are the preferred representation for numerical analysis.

For 3D coverage, schema v4 makes the 4D contract explicit. `data/values`, `data/values_db`, `data/associated_tx`, `data/coverage_valid`, and `data/metric_norm` all use `(frame, z, y, x)` when the volume grid is stable. The datasets carry `dimension_order`, rank, axis-index, and representation attributes; `coordinates/x`, `coordinates/y`, and `coordinates/z` are HDF5 dimension scales in meters. Optional per-transmitter arrays, when available, use `(frame, tx, z, y, x)`. If any frame has an incompatible Z/Y/X grid, the exporter refuses to mis-stack it and falls back to per-frame raw volume groups.

## Blender 5.2 compatibility

The bridge uses Blender 5.2's Geometry Nodes modifier RNA API (`modifier.properties.inputs`) with the older ID-property form retained only as a fallback. The extension manifest requires Blender 5.2.0 or newer.

## Workspace behavior

For an unsaved `.blend`, `//sionna_runs` falls back to `~/sionna_runs` instead of Blender's protected installation directory. After the `.blend` is saved, normal Blender-relative `//sionna_runs` behavior resumes.

With CSV/HDF5 export enabled, temporary worker run folders are removed and only the clean export bundle folder remains. With No File Export, completed worker run folders are removed entirely.


## 1.6.1 registration fix

Blender 5.2 can register extensions while `bpy.data` is temporarily exposed as `_RestrictData`.
Version 1.6.1 defers all scene-dependent Dynamic Mode and device-representation initialization to a timer after registration. This avoids `'_RestrictData' object has no attribute 'scenes'` during installation/reload.

## Bundled Geometry Nodes (1.8.1+)

The extension ships `assets/sionnart_geometry_nodes.blend`. All node groups in
that file are appended automatically when the extension is enabled and whenever
a different `.blend` project is loaded. Existing node groups with the same exact
name are preserved, so Blender does not create `.001` duplicates and local edits
are not overwritten. If a required bundled group is deleted during a session,
the bridge restores missing bundled groups automatically the next time that group
is requested by a Sionna operator.

