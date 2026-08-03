# Reproducibility package

The SoftwareX v1.0.0 archive provides the installable SionnaRT-Bridge
extension, the Geometry Nodes reference library, two self-contained
illustrative Blender scenes, and compact numerical validation results.

## Illustrative Blender examples

The distributed examples are:

- `examples/procedural-vegetation-paths/`
- `examples/urban-stacked-height-map/`

### Procedural vegetation paths

The procedural-vegetation example contains the animated plant geometry,
transmitter and receiver configuration, simulation settings, imported
propagation-path results, Geometry Nodes visualization, materials, camera,
preview image, and file-integrity checksums.

### Munich stacked-height radio map

The Munich example contains the urban environment, transmitter and receiver
configuration, simulation settings, imported stacked-height radio-map results,
Geometry Nodes visualization, materials, camera, animation, attribution, and
a file-integrity checksum.

These scenes are illustrative examples used for the SoftwareX manuscript.
They are not substitutes for the compact numerical validation package.

## Geometry Nodes reference library

Reusable visualization node groups are distributed in:

`assets/blender/sionnart_geometry_nodes_1.0.0.blend`

The accompanying SHA-256 file allows users to verify the library before
appending the node groups into another Blender scene.

## Numerical validation package

Numerical validation is distributed separately under:

`validation/`

The final v1.0.0 package should contain:

- `validation/README.md`
- `validation/results-v1.0.0.csv`
- `validation/environment-v1.0.0.json`
- `validation/SHA256SUMS`

The validation results should report:

- direct Sionna RT versus bridge path-count agreement;
- maximum path-coordinate difference;
- maximum path-delay difference;
- maximum path-gain difference;
- planar radio-map RMSE and maximum absolute difference;
- transmitter-association agreement;
- external-file-to-Blender attribute agreement;
- scene-export, worker-startup, solver, serialization, and import runtimes.

## Environment record

For every validation run, retain:

- operating system and architecture;
- Blender and SionnaRT-Bridge versions;
- Python, Sionna RT, Mitsuba, and Dr.Jit versions;
- CPU and GPU models;
- GPU driver and selected backend;
- exact Git commit and release tag;
- input-file checksums;
- random seed and solver parameters;
- scene-export, solve, serialization, and import runtimes;
- warm-up count and number of measured repetitions.

## Large assets

Large reproducibility assets may be stored in a DOI-backed archive rather
than duplicated in Git history.

The GitHub repository and archived release must provide:

- exact filenames;
- SHA-256 checksums;
- retrieval instructions;
- version-specific release or archive links.

The exact Blender files and validation results cited by the SoftwareX
manuscript must remain immutable after the v1.0.0 archive is published.
