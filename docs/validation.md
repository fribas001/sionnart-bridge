# Validation and performance protocol

This document defines the minimum scientific and performance evidence required
for the SoftwareX v1.0.0 release.

It is a protocol, not a claim that the current development version has already
passed every listed test. Completed results must be recorded in the
machine-readable validation package before the final release is tagged.

## Numerical equivalence

Run identical scenes and simulation settings through:

1. a direct Sionna RT reference script; and
2. SionnaRT-Bridge.

Use identical scene geometry, transmitter and receiver configurations,
frequencies, antenna arrays, solver settings, propagation mechanisms, random
seeds, and numerical backends.

### Propagation paths

Compare:

- path count for every transmitter-receiver link;
- transmitter and receiver identifiers;
- ordered interaction coordinates;
- interaction-object identifiers;
- path delays;
- complex path coefficients;
- path gains;
- line-of-sight and interaction-type classifications.

Report the maximum absolute and relative differences and the tolerance used
for every quantity.

### Planar radio maps

Compare:

- cell-center coordinates;
- path-gain values;
- transmitter association;
- invalid or masked cells;
- grid dimensions and cell spacing.

Report RMSE, maximum absolute difference, transmitter-association agreement,
and the number of compared cells.

### Projected radio maps

Compare:

- projected cell-center coordinates;
- surface normals;
- cell areas;
- path-gain values;
- transmitter association;
- source-map indices.

### Stacked-height radio maps

Compare:

- number of layers;
- layer-center positions;
- horizontal cell centers;
- path-gain values;
- transmitter association;
- imported Blender attribute values.

## Coordinate transfer

Use a compact synthetic scene with known transforms to test:

- object translation;
- object rotation;
- parent transforms;
- uniform and nonuniform scaling;
- evaluated modifiers;
- evaluated Geometry Nodes geometry;
- transmitter and receiver orientation modes;
- exported and re-imported world-space coordinates.

For every case, retain the expected coordinates, bridge-produced coordinates,
absolute difference, tolerance, and pass/fail status.

## External-file-to-Blender agreement

Verify that numerical values written by the external worker are imported into
Blender without unintended changes.

Compare the retained result files against the corresponding Blender geometry
attributes for:

- coordinates;
- delays;
- path gains;
- interaction types;
- transmitter and receiver indices;
- radio-map values;
- transmitter association;
- stacked-height layer indices.

## Performance measurements

Measure the following stages separately:

- evaluated-scene preparation;
- scene export;
- external-worker startup;
- Sionna RT scene loading;
- Sionna RT solve;
- result serialization;
- Blender result import;
- Geometry Nodes visualization preparation;
- total bridge workflow time.

For every benchmark, report:

- scene name and checksum;
- scene size;
- transmitter and receiver count;
- path count or radio-map cell count;
- peak memory use where available;
- operating system;
- CPU;
- GPU and driver;
- selected Mitsuba or Dr.Jit backend;
- warm-up-run count;
- measured-run count;
- mean, standard deviation, minimum, and maximum runtime.

## Stacked-height convention

The implementation and SoftwareX manuscript use the requested vertical spacing
`cell_size_z` directly.

The requested vertical extent determines the number of sampled layers.
Adjacent layer centers remain separated by `cell_size_z`. The final layer may
therefore extend beyond the nominal upper boundary when the requested extent
is not an exact multiple of the spacing.

The implementation, user-interface label, output schema, validation results,
and manuscript must retain this same convention.

## Validation package

Completed evidence must be stored under:

`validation/`

The final v1.0.0 repository should contain:

- `validation/README.md`
- `validation/results-v1.0.0.csv`
- `validation/environment-v1.0.0.json`
- `validation/SHA256SUMS`

Additional per-case numerical files may be stored under:

`validation/cases/`

The CSV summary must contain, at minimum:

- validation-case identifier;
- compared quantity;
- reference value;
- bridge value;
- absolute error;
- relative error;
- tolerance;
- pass/fail status.

The environment JSON must record the exact software versions, hardware,
backend, Git commit, random seed, solver configuration, and measurement
procedure.

The SHA-256 file must cover every machine-readable validation artifact used to
produce the SoftwareX manuscript results.

## Manuscript reporting

The SoftwareX manuscript must report a concise summary of:

- path-count agreement;
- maximum coordinate difference;
- maximum delay difference;
- maximum path-gain difference;
- radio-map RMSE and maximum absolute difference;
- transmitter-association agreement;
- external-file-to-Blender agreement;
- export, import, and total bridge overhead.

The complete machine-readable evidence remains in the versioned repository and
DOI-backed release archive.
