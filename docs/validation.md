# Validation

This document describes the validation approach used for SionnaRT-Bridge and the checks recommended when reproducing or extending the SoftwareX results.

It distinguishes between:

- **scientific validation** of numerical results against direct Sionna RT workflows;
- **software tests** that verify implementation behavior and packaging;
- **workflow checks** that verify results are transferred into Blender without unintended modification.

> **Scope:** The repository documents the validation method and includes the example scenes used to exercise the workflow. It does not currently distribute the complete raw 70-frame comparison dataset or a standalone machine-readable validation package.

---

## Scientific validation principle

SionnaRT-Bridge is a workflow and integration layer around Sionna RT.

The central validation question is therefore:

> Does the bridge reproduce the same Sionna RT result as an equivalent direct Sionna RT workflow when geometry, devices, antenna configuration, radio materials, propagation mechanisms, and solver settings are held constant?

The bridge should not be expected to produce a different physical solution from direct Sionna RT when both workflows use the same numerical configuration.

---

## Propagation-path comparison

For a numerical equivalence study, run equivalent scenes and solver settings through:

1. a direct Sionna RT reference workflow; and
2. SionnaRT-Bridge.

Compare, where applicable:

- number of returned paths;
- transmitter and receiver indices;
- interaction-type sequence;
- ordered interaction coordinates;
- path gain;
- propagation delay.

Corresponding paths should be matched using stable identifiers derived from the TX/RX pair and the ordered propagation interactions rather than relying only on output row order.

---

## SoftwareX propagation-path validation

The SoftwareX manuscript reports a 70-frame procedural-vegetation comparison between the automated bridge workflow and an independently prepared direct Sionna RT reference workflow.

The reported comparison uses the following absolute tolerances:

| Quantity | Absolute tolerance |
|---|---:|
| Interaction coordinates | 0.01 m |
| Path gain | 0.002 dB |
| Propagation delay | 0.2 ns |

The manuscript reports an overall agreement of **99.9%**, calculated from the category-level agreement percentages used in that study.

The complete raw 70-frame comparison files are not required for normal installation or use of SionnaRT-Bridge and are not currently included in this Git repository.

The procedural vegetation example scene is available under:

```text
examples/procedural-vegetation-paths/
```

---

## Interpreting numerical differences

Small floating-point differences may occur between runs because of:

- GPU-parallel execution;
- driver changes;
- backend changes;
- dependency-version changes;
- hardware differences;
- stochastic solver operations.

For this reason, scientific comparisons should use documented numerical tolerances rather than requiring byte-for-byte identical result files.

A fixed solver seed should be used when repeatability is important.

---

## External-file-to-Blender agreement

Numerical values written by the external worker should be imported into Blender without unintended changes.

When validating the import layer, compare retained result files against the corresponding Blender geometry attributes for applicable quantities such as:

- coordinates;
- delays;
- path gains;
- interaction types;
- transmitter and receiver indices;
- radio-map values;
- transmitter association;
- stacked-height layer indices.

This check validates data transport and reconstruction inside Blender rather than the Sionna RT solver itself.

---

## Result serialization checks

For CSV output, verify that:

- frame indices are preserved;
- TX/RX indices are preserved;
- path identifiers remain stable within the documented schema;
- units match the output-schema documentation;
- missing or invalid values are represented consistently;
- multidimensional radio-map ordering matches the documented dimensions.

See:

```text
docs/output-schemas/
```

---

## Radio-map validation

For planar radio maps, comparisons may include:

- grid dimensions;
- cell-center coordinates;
- path gain;
- RSS;
- SINR;
- transmitter association.

When comparing numerical radio-map values, report both an aggregate error measure and the maximum absolute difference.

Examples of useful measures include:

- RMSE;
- mean absolute error;
- maximum absolute difference.

The comparison should use identical:

- map center;
- map extent;
- cell size;
- measurement height;
- transmit powers;
- bandwidth and temperature for SINR;
- radio materials;
- solver settings.

---

## Projected-mesh radio-map validation

For Projected Mesh mode, verify:

- the same evaluated reference mesh is used;
- degenerate triangles are handled consistently;
- triangle ordering is stable or explicitly matched;
- returned values are associated with the correct measurement triangles.

The current projected-mesh workflow should be validated using the metric supported by the implementation.

---

## Stacked-height convention

The implementation and SoftwareX manuscript use the requested vertical spacing `cell_size_z` directly.

The requested vertical extent determines the number of sampled layers.

Adjacent layer centers remain separated by `cell_size_z`.

The final layer may therefore extend beyond the nominal upper boundary when the requested vertical extent is not an exact multiple of the requested spacing.

The following must remain consistent with this convention:

- implementation;
- user-interface wording;
- output schema;
- examples;
- manuscript description.

A stacked-height radio map is a set of planar Sionna RT evaluations at multiple heights. It is not a separate volumetric electromagnetic solver.

---

## Procedural-geometry validation

For procedural or Geometry Nodes scenes, verify that the geometry used by the worker is the evaluated Blender geometry for the intended frame.

Useful checks include:

- object count;
- vertex count;
- triangle count;
- evaluated bounding box;
- material assignment;
- frame number;
- procedural random seed;
- exported-scene checksum where practical.

Representative frames should be inspected manually before launching a large sweep.

If incompatible frames are skipped, the skipped-frame report must be retained and reviewed.

---

## Timeline and parameter-sweep validation

When Blender frames represent a scientific parameter rather than animation time, document the mapping explicitly.

Examples:

```text
frame -> transmitter power
frame -> UAV altitude
frame -> vegetation state
frame -> device position
```

Validation should confirm that the intended parameter value is applied before each frame is exported and simulated.

---

## Performance measurements

Performance measurements are useful for characterizing workflow overhead, but they should be reported separately from numerical-equivalence validation.

Possible stages include:

- evaluated-scene preparation;
- scene export;
- external-worker startup;
- Sionna RT scene loading;
- Sionna RT solve;
- result serialization;
- Blender result import;
- Geometry Nodes visualization preparation;
- total workflow time.

For reproducible benchmarks, record:

- scene;
- scene size;
- TX/RX count;
- path or radio-map sample count;
- operating system;
- CPU;
- GPU and driver;
- Mitsuba / DrJit backend;
- warm-up count;
- measured-run count.

Do not present performance numbers from different hardware or solver configurations as directly comparable without qualification.

---

## Automated tests

Automated repository tests serve a different purpose from scientific validation.

They may verify items such as:

- Python helper behavior;
- path-gain conversions;
- array handling;
- output serialization;
- manifest validity;
- packaging;
- syntax and import behavior.

Passing automated tests does not by itself establish scientific equivalence with a direct Sionna RT workflow.

Likewise, a scientific comparison does not replace normal software testing.

---

## Environment reporting

A reproducible validation report should record the exact environment used.

For the SoftwareX submission environment, record at least:

```text
SionnaRT-Bridge version
Git commit
Blender version
Blender Python version
Sionna version
Sionna RT version
Mitsuba version
DrJit version
h5py version
operating system
CPU
GPU
GPU driver
execution backend
solver seed
```

Do not infer exact environment versions from documentation when the validation machine can report them directly.

See also:

```text
docs/reproducibility.md
```

---

## Current repository scope

This repository contains:

- the SionnaRT-Bridge source code;
- installation documentation;
- user documentation;
- output-schema documentation;
- example Blender scenes;
- automated tests;
- the validation methodology described here.

The repository does **not** currently claim to include:

- the complete raw 70-frame reference dataset;
- the complete raw 70-frame bridge-result dataset;
- a dedicated `validation/` result archive;
- a machine-readable table containing every comparison used to obtain the manuscript's reported 99.9% value.

If those artifacts are archived separately in the future, the corresponding persistent identifier and checksum should be added to the release documentation.

---

## Manuscript consistency

Before creating a publication release, check that the repository and manuscript agree on:

- SionnaRT-Bridge version;
- Blender version;
- Sionna / Sionna RT versions;
- example-scene descriptions;
- propagation-path comparison tolerances;
- stacked-height convention;
- supported output formats;
- stated software scope and limitations.

Repository documentation should not claim that validation artifacts are distributed unless those artifacts are actually present in the tagged release.
