# Reproducibility

This document describes the information and repository resources needed to reproduce SionnaRT-Bridge workflows and to report experiments performed with the software.

The publication release should make it possible to identify:

- the exact SionnaRT-Bridge version;
- the Blender and Sionna RT environment;
- the scene and simulation configuration;
- the mapping between Blender frames and experiment states;
- the result format and schema;
- the software and hardware environment used to generate reported results.

> **Scope:** The repository provides the software, documentation, example scenes, output-schema documentation, and validation methodology. It does not currently distribute a standalone machine-readable archive of the complete 70-frame SoftwareX validation comparison.

---

## Repository resources

The repository contains the main resources required to reproduce normal SionnaRT-Bridge workflows:

```text
README.md
docs/
examples/
src/
tests/
```

Important documentation includes:

```text
docs/installation.md
docs/SIONNA_2_BLENDER_5_2_WINDOWS.md
docs/USER_GUIDE.md
docs/SIMULATION_PARAMETERS.md
docs/WORKFLOWS.md
docs/validation.md
docs/output-schemas/
```

Users reproducing a published experiment should begin from the tagged software release associated with that experiment rather than an arbitrary development commit.

---

## Software version

Every reproducibility record should identify:

```text
SionnaRT-Bridge version
Git tag
Git commit
```

For the planned SoftwareX submission release, the target version is:

```text
v1.8.2
```

Do not create or cite the final publication tag until the release contents, manuscript, and archival metadata are synchronized.

---

## Software environment

Record the exact software environment used to run the experiment.

At minimum record:

```text
Blender version
Blender Python version
Sionna version
Sionna RT version
Mitsuba version
DrJit version
h5py version
operating system
```

The SoftwareX manuscript environment should be kept consistent with the final tagged release documentation.

When possible, obtain versions directly from the environment used for the experiment instead of copying them from an example configuration.

---

## Hardware and execution backend

For computational results, record:

```text
CPU
GPU
GPU driver
Mitsuba / DrJit execution backend
```

Hardware and driver differences may cause small floating-point differences even when the same scene, solver configuration, and random seed are used.

Reproducibility therefore means agreement within scientifically justified numerical tolerances, not necessarily byte-identical result files across different systems.

---

## Scene provenance

For each experiment, retain the Blender scene or document exactly how it can be reconstructed.

Record:

- Blender filename;
- file checksum where practical;
- scene units;
- relevant collections;
- static geometry;
- procedural geometry;
- Geometry Nodes configuration;
- radio-material assignments;
- transmitter objects;
- receiver objects;
- antenna configuration;
- device orientation method;
- any external geometry or data dependencies.

If an example scene is used directly, record the exact path inside the tagged repository.

---

## Example scenes

Example Blender scenes are provided under:

```text
examples/
```

The procedural-vegetation propagation-path example is located under:

```text
examples/procedural-vegetation-paths/
```

Example scenes are intended to demonstrate complete workflows and manuscript use cases.

They should not be interpreted as a substitute for independently archived raw validation data.

---

## Simulation configuration

A reproducible propagation experiment should record the relevant solver settings.

At minimum, where applicable:

```text
carrier frequency
bandwidth
temperature
Max Depth
Samples / Source
Max Paths / Source
seed
Line of Sight
Specular Reflection
Diffuse Reflection
Refraction
Diffraction
Edge Diffraction
```

Also record:

- transmitter powers;
- TX/RX array rows and columns;
- array spacing;
- antenna element pattern;
- polarization;
- orientation mode.

See:

```text
docs/SIMULATION_PARAMETERS.md
```

---

## Radio materials

Record every radio material used by the simulation.

For ITU materials, record the preset identifier and frequency.

For custom materials, record the applicable parameters, including:

- relative permittivity;
- conductivity;
- thickness;
- scattering coefficient;
- XPD coefficient;
- scattering pattern.

Do not assume that a Blender visual material fully specifies the corresponding radio material.

---

## Timeline and parameter sweeps

Blender frames may represent:

- physical time;
- procedural geometry states;
- transmitter or receiver positions;
- transmitter power;
- UAV altitude;
- another experiment parameter.

For every multi-frame experiment, document the mapping explicitly.

Examples:

```text
frame 1  -> TX power 20 dBm
frame 2  -> TX power 21 dBm
...
```

or:

```text
frame 1  -> procedural vegetation state 1
frame 70 -> procedural vegetation state 70
```

If frame index represents physical time, record the frame-to-time conversion.

---

## Procedural geometry

For experiments using Geometry Nodes or other frame-dependent evaluated geometry, record:

- Blender frame range;
- frame step;
- procedural random seed;
- controlling node-group parameters;
- relevant modifier settings;
- whether `Procedural Geometry per Frame` is enabled;
- whether incompatible frames are allowed to be skipped.

Where practical, retain evaluated-geometry statistics such as:

- object count;
- vertex count;
- triangle count;
- bounding box.

Skipped or failed frames must be reported rather than silently omitted from the scientific interpretation.

---

## Propagation-path results

For propagation-path experiments, retain enough information to identify:

- frame;
- transmitter;
- receiver;
- path;
- interaction sequence;
- ordered interaction coordinates;
- path gain;
- propagation delay.

Use the documented output schema rather than relying on visual inspection of Blender curves alone.

See:

```text
docs/output-schemas/propagation-paths.md
```

---

## Radio-map results

For 2D radio maps, record:

- surface mode;
- center;
- extent;
- measurement height;
- cell size;
- selected metric;
- transmitter powers for RSS/SINR;
- bandwidth and temperature for SINR.

For projected-mesh workflows, record the reference mesh and the supported metric used.

For stacked-height radio maps, also record:

```text
Center Z
Size Z
Cell Z
number of layers
```

The stacked-height workflow is a set of planar Sionna RT evaluations at different heights. It is not a separate volumetric electromagnetic solver.

---

## Stacked-height convention

The implementation uses the requested vertical spacing `cell_size_z` directly.

The requested vertical extent determines the number of sampled layers.

Adjacent layer centers remain separated by `cell_size_z`.

When the requested vertical extent is not an exact multiple of the spacing, the final layer may extend beyond the nominal upper boundary.

The following should use the same convention:

- implementation;
- interface wording;
- output schemas;
- examples;
- manuscript.

---

## Output formats

SionnaRT-Bridge can retain structured outputs for later analysis.

When publishing results, record:

- output format;
- filename;
- schema version if applicable;
- relevant dataset/group names;
- checksum for archived files where practical.

See:

```text
docs/output-schemas/
```

HDF5 or CSV output is preferable to relying only on Blender visualization when the results will be analyzed quantitatively.

---

## Geometry Nodes visualization

Geometry Nodes visualization is a downstream representation of imported numerical results.

A reproducibility record should distinguish between:

1. the numerical simulation result; and
2. the Blender visualization generated from that result.

Visual attributes such as color mapping, geometry scale, camera position, and render settings may affect the figure appearance without changing the underlying propagation result.

Where reusable Geometry Nodes assets are distributed under `assets/`, use the exact asset from the tagged release and record its filename.

---

## Validation

The scientific validation methodology is documented in:

```text
docs/validation.md
```

The SoftwareX manuscript reports a 70-frame procedural-vegetation comparison against an independently prepared direct Sionna RT reference workflow.

The repository currently documents that validation method and its manuscript-reported tolerances but does not include a standalone `validation/` archive containing every raw comparison used for the reported overall agreement.

This distinction should remain explicit in the publication release.

---

## Automated tests

Automated software tests are provided under:

```text
tests/
```

They are useful for checking implementation behavior, helper functions, serialization, packaging, and related software properties.

Automated tests are complementary to, but distinct from, scientific numerical validation.

---

## Checksums

For files cited directly in a publication or external archive, SHA-256 checksums are recommended.

Useful candidates include:

- Blender experiment files;
- external input datasets;
- exported result files;
- release archives;
- separately archived large assets.

Example command in PowerShell:

```powershell
Get-FileHash <FILE> -Algorithm SHA256
```

Record the checksum together with the filename and software version.

---

## Large assets and external archives

Large reproducibility assets do not need to be stored directly in Git history.

If large files are archived externally, the release documentation should provide:

- persistent archive identifier or DOI;
- exact archive filename;
- archive version;
- SHA-256 checksum;
- retrieval instructions.

Do not claim that a DOI-backed validation archive exists until it has actually been created and published.

---

## Archival release

For a publication release, the recommended sequence is:

1. finalize source code and documentation;
2. finalize example scenes and small reproducibility assets;
3. run release and software checks;
4. synchronize version numbers;
5. create the archival software record;
6. record the DOI or persistent identifier where applicable;
7. create the final Git tag and GitHub release;
8. ensure the manuscript references the same immutable release.

The exact archival procedure is documented separately in the repository release documentation.

---

## Minimum reproducibility checklist

For each reported SionnaRT-Bridge experiment, retain or report:

- [ ] SionnaRT-Bridge version
- [ ] Git tag or commit
- [ ] Blender version
- [ ] Sionna / Sionna RT version
- [ ] Mitsuba and DrJit versions
- [ ] operating system
- [ ] CPU and GPU
- [ ] execution backend
- [ ] Blender scene or scene-reconstruction instructions
- [ ] radio-material definitions
- [ ] TX/RX positions and orientations
- [ ] antenna arrays
- [ ] transmitter powers
- [ ] solver settings
- [ ] random seed
- [ ] timeline/frame interpretation
- [ ] output format
- [ ] result-file checksum where practical
- [ ] analysis script or documented analysis procedure

A publication-quality result should be traceable from software version and scene configuration through simulation output and final analysis.
