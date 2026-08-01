# Reproducibility package

The SoftwareX v1.0.0 archive should contain enough material for a reviewer to
install the extension, reproduce at least one path simulation and one radio-map
simulation, and compare the results with expected numerical outputs.

## Required example assets

Add the following before tagging v1.0.0:

- `examples/minimal-path/minimal-path.blend`
- `examples/minimal-path/reference-native-sionna.py`
- `examples/minimal-path/expected/` with JSON/CSV/NPZ results
- `examples/planar-radio-map/` with an equivalent native reference
- `examples/procedural-vegetation/` used for the paper figure
- `examples/urban-stacked-height-map/` used for the paper figure
- a README in each example with coordinates, materials, arrays, frequency,
  mechanisms, depth, samples, seed, expected runtime, and hardware

Large assets may be stored in a DOI-backed data repository, but the GitHub
repository must contain a manifest with checksums and retrieval instructions.

## Environment record

For every validation run, retain:

- operating system and architecture;
- Blender and extension versions;
- Python, Sionna RT, Mitsuba, and Dr.Jit versions;
- CPU/GPU model and driver/backend;
- exact git commit and release tag;
- input file checksums;
- random seed and all solver parameters;
- export, solve, and import runtimes.
