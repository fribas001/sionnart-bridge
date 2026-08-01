# Validation and performance protocol

This document defines the minimum evidence required for the SoftwareX v1.0.0
release. It is a protocol, not a claim that the uploaded development archive
has already passed these tests.

## Numerical equivalence

Run the same scene and settings through a native Sionna RT script and through
SionnaRT-Bridge. Compare:

- path count and TX/RX link identifiers;
- ordered interaction coordinates and object identifiers;
- delays, complex coefficients, and path gains;
- planar radio-map values and transmitter association;
- projected-map cell centers, normals, areas, and path gains;
- stacked-height layer positions and values.

Report absolute and relative tolerances and explain any nondeterminism.

## Coordinate transfer

Use a synthetic scene to test translations, rotations, parent transforms,
nonuniform scale, evaluated modifiers, Geometry Nodes geometry, and device
orientation modes.

## Performance

Separate the measured time into scene evaluation/export, worker startup,
Sionna RT solve, result serialization, Blender import, and visualization. Report
scene size, path count or map-cell count, memory use, hardware, and backend.

## Release evidence

Store machine-readable results under `examples/*/expected/` and a concise
summary table under `validation/results-v1.0.0.csv`. Add the final table to the
SoftwareX manuscript.

## Known paper/code item to reconcile

The current uploaded development worker spaces stacked-height layers using the
requested `cell_size_z` directly. The revised manuscript defines an effective
spacing `size_z / ceil(size_z / maximum_spacing)`. The implementation, schema,
UI label, tests, and paper must use one identical convention before release.
