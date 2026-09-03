# SionnaRT-Bridge User Guide

SionnaRT-Bridge connects Blender scene authoring, procedural modeling, simulation control, scientific visualization, and structured data export with NVIDIA Sionna RT.

Blender is used to define geometry, radio materials, transmitters, receivers, antenna configuration, simulation settings, timeline states, parameter sweeps, and result visualization. Numerical propagation calculations run in a dedicated Sionna RT Python environment using Mitsuba 3 and DrJit.

> **Important:** SionnaRT-Bridge does not replace Sionna RT and does not implement a separate electromagnetic solver. It is an experiment-authoring, automation, data-management, and visualization layer around Sionna RT.

---

## 1. Typical workflow

1. Configure and test the Sionna runtime.
2. Create or repair the controlled simulation hierarchy.
3. Add static or procedural geometry.
4. Assign radio materials.
5. Create or mark transmitters and receivers.
6. Configure antenna arrays and device orientations.
7. Configure carrier frequency and solver settings.
8. Select propagation mechanisms.
9. Enable propagation paths, 2D radio maps, 3D stacked-height radio maps, or a combination.
10. Select the result-export mode.
11. Run the simulation.
12. Inspect Blender geometry and/or exported CSV results.

For scientific experiments, record the software versions, scene-generation rules, solver settings, random seed, and the meaning of Blender frames together with the results.

---

## 2. Sionna Runtime

The **Sionna Runtime** section configures the external Python environment used by the Sionna RT workers.

The SoftwareX release is tested with:

- Blender 5.2
- Blender Python 3.13
- Sionna 2.0.1
- Sionna RT 2.0.1
- Mitsuba 3.8.0
- DrJit 1.3.1
- h5py 3.16.0
- Windows 11 x64

### Runtime

Selects or identifies the Python runtime used by the external workers.

### Sionna Packages

Points to the environment containing Sionna, Sionna RT, Mitsuba, DrJit, and related dependencies.

### LLVM

LLVM may be required by DrJit's CPU backend. A compatible CUDA backend is preferred when supported NVIDIA hardware and drivers are available.

### Workspace

The workspace stores temporary exports, worker inputs/outputs, logs, and persistent results when enabled. For reproducible projects, use a stable project-specific location.

### Runtime Test

Use the runtime test before troubleshooting simulation failures. It checks whether the external environment and required scientific packages can be located and imported.

---

## 3. Workflow and Scene Preparation

SionnaRT-Bridge manages radio-propagation geometry through a controlled Blender hierarchy.

### Static geometry

Use for geometry whose evaluated mesh does not change during the experiment, for example buildings, walls, terrain, or fixed infrastructure.

### Procedural geometry

Use when Geometry Nodes, modifiers, animation, drivers, or other frame-dependent operations change the evaluated mesh.

Examples include growing vegetation, moving obstacles, deforming objects, and parametric scene variants.

> Moving only a transmitter or receiver does not necessarily require regeneration of environmental geometry.

---

## 4. Simulation Settings

These settings define the main physical and numerical parameters shared by enabled simulations. There is no single solver configuration that is optimal for every scene.

### Carrier frequency

Carrier frequency affects wavelength, wavelength-relative antenna-array geometry, frequency-dependent radio-material behavior, and the physical interpretation of the scenario.

### Bandwidth and temperature

Bandwidth and temperature contribute to thermal-noise calculations used in SINR workflows. Increasing bandwidth increases integrated thermal-noise power.

### Random seed

Record the random seed for reproducible studies. A fixed seed improves repeatability, but parallel floating-point calculations are not guaranteed to be bit-identical across all hardware and execution backends. Use documented numerical tolerances for scientific comparisons.

### Maximum depth

Controls the permitted interaction depth. Larger values allow higher-order multipath components but generally increase computation time, memory use, and result complexity.

### Samples per source

Controls the ray-sampling budget. Higher values can improve path discovery in difficult scenes but increase computational cost. For scientific work, check convergence for the specific scenario instead of assuming one value is universally sufficient.

---

## 5. Propagation Mechanisms

SionnaRT-Bridge exposes propagation mechanisms implemented by Sionna RT.

### Line of sight

Direct unobstructed propagation between transmitter and receiver.

### Specular reflection

Mirror-like reflection from surfaces. Important in many indoor, urban, industrial, and mmWave environments.

### Refraction / transmission

Propagation through compatible materials according to the configured material and Sionna RT model.

### Diffraction

Propagation associated with eligible geometric edges. It can be important when direct paths are obstructed.

### Diffuse scattering

Non-specular redistribution of energy from surfaces. Enable it only when appropriate to the material model and study assumptions.

> Enabling every available mechanism does not automatically make a simulation more accurate. Results also depend on geometry, material parameters, antenna configuration, sampling, scene scale, and solver settings.

---

## 6. Radio Materials

Radio materials describe how electromagnetic waves interact with scene surfaces and are conceptually different from Blender visual materials.

Depending on the model, relevant properties can include relative permittivity, conductivity, thickness, scattering parameters, and cross-polarization properties.

Changing an object's visible color or Blender shader does not automatically change its radio-propagation properties.

For scientific studies, custom material parameters should be supported by measurements, literature, manufacturer data, standards, or a clearly documented modeling assumption.

---

## 7. Devices and Orientation

Transmitters and receivers are Blender objects associated with Sionna RT radio devices.

Relevant properties can include position, orientation, transmit power, antenna-array configuration, and trajectory information.

Antenna orientation affects the relationship between the antenna response and the scene. Directional antennas should be checked carefully.

Target-based orientation can be useful for directional links, UAV antennas, tracking demonstrations, and orientation sweeps.

---

## 8. Antenna Arrays

Typical array parameters include rows, columns, horizontal spacing, vertical spacing, antenna pattern, polarization, and polarization model.

Array spacing is typically specified relative to wavelength:

```text
d = s * lambda
lambda = c / f
```

where `s` is wavelength-relative spacing. A value of `0.5` represents half-wavelength spacing.

Changing carrier frequency while keeping `s = 0.5` preserves half-wavelength spacing but changes the physical array size.

---

## 9. Timeline-Based Experiments

The Blender timeline can be used as an experiment dimension. A frame may represent geometry state, transmitter or receiver position, transmit power, carrier frequency, antenna orientation, or another parameter.

### Current frame

Useful while configuring and debugging a simulation.

### Frame range

Runs multiple Blender states sequentially. For example:

```text
Start: 1
End:   100
Step:  5
```

runs frames:

```text
1, 6, 11, ..., 96
```

Always document what frame number means in a scientific experiment. For example: `Frames 1-41 correspond to transmitter powers from 20 dBm to 60 dBm in 1 dB increments.`

---

## 10. PointCloud Device Trajectories

Transmitters and receivers can follow Blender PointCloud positions. This supports UAV trajectories, receiver mobility, candidate base-station locations, spatial grids, routes, and large location sweeps without creating a keyframe for every position.

A sequence of PointCloud positions should be interpreted as a sequence of evaluated scene states unless a physical time mapping is explicitly defined.

---

## 11. Simulation Execution and Dynamic Mode

Before a large run, verify runtime configuration, geometry, radio materials, device positions, antenna orientation, frequency, solver settings, enabled mechanisms, requested outputs, frame range, and export mode.

Test one or a few representative frames before launching a long procedural sweep.

Dynamic Mode is primarily intended for interactive exploration. For publication-grade experiments, explicit runs and defined frame sweeps are generally easier to archive and reproduce.

---

## 12. Propagation Paths

For each valid transmitter-receiver path, Sionna RT can provide transmitter/receiver identifiers, ordered interaction locations, interaction types, propagation delay, propagation distance, and a complex path coefficient.

SionnaRT-Bridge can convert this information into attributed Blender geometry.

Path gain is expressed as:

```text
G_path = 10*log10(|a|^2) = 20*log10(|a|)
```

where `a` is the complex path coefficient.

Path gain should not be confused with absolute received power, which also depends on transmitter power, antenna response, and other system assumptions.

Path-display or export limits can reduce Blender geometry and file size. For scientific analysis, ensure that such limits do not remove relevant multipath components.

---

## 13. 2D Radio Maps

A radio map evaluates propagation quantities across a spatial measurement surface. SionnaRT-Bridge supports planar and projected-mesh workflows.

Supported analysis can include path gain, received signal strength/power, and SINR.

### Path gain

Characterizes propagation independently of absolute transmitter power.

### RSS

Includes transmitter power and propagation conditions. Where applicable, received power is represented in dBm.

### SINR

Compares the desired received signal against interference and noise. SINR depends on transmitter powers, propagation conditions, bandwidth, and thermal-noise assumptions.

A location can have high received power while still having poor SINR when interference is strong.

### Resolution

Smaller map cells increase spatial sampling resolution but also increase computation time, memory use, output size, and Blender visualization density.

---

## 14. Projected-Mesh Radio Maps

Projected-mesh mode uses evaluated Blender mesh geometry as the measurement surface. It can follow inclined or irregular surfaces instead of being restricted to a horizontal plane.

Non-degenerate exported triangles define the eligible measurement geometry.

---

## 15. 3D / Stacked-Height Radio Maps

SionnaRT-Bridge creates height-resolved radio maps by evaluating a sequence of horizontal Sionna RT planar radio maps at different heights and combining the samples into a structured three-dimensional dataset.

> **Important:** This does not implement a new volumetric electromagnetic solver. It is a structured stack of established planar Sionna RT radio-map calculations.

---

## 16. Result Export

### No persistent file export

Useful for interactive inspection and quick testing, but generally not sufficient as the sole record of a publication-grade simulation.

### CSV with metadata

Useful for tabular inspection, path analysis, smaller datasets, and interoperability with common analysis tools.

---

## 17. Geometry Nodes Visualization and Analytics

Returned simulation results can be represented as attributed Blender geometry. Bundled Geometry Nodes can reconstruct propagation paths, filter results, apply thresholds, select frames or heights, visualize radio maps, color values, and animate simulation sequences.

Visualization supports exploration and communication but is not a substitute for numerical validation. For publication-grade quantitative analysis, retain and analyze exported numerical outputs.

---

## 18. Scope and Limitations

SionnaRT-Bridge does not:

- replace or modify the Sionna RT solver;
- guarantee that scene geometry or radio materials are physically correct;
- automatically determine appropriate solver parameters;
- convert Blender visual materials into validated electromagnetic materials;
- guarantee bit-identical output across every hardware/backend configuration;
- turn stacked-height maps into a full volumetric electromagnetic solver;
- replace convergence, sensitivity, or validation studies.

Meaningful results require appropriate choices for scene geometry, scale, radio materials, antenna models, transmitter powers, propagation mechanisms, solver settings, and sampling.

---

## 19. Recommended Reproducibility Information

For an archived or published experiment, record at least:

- SionnaRT-Bridge version and repository tag/DOI;
- Blender and Python versions;
- Sionna and Sionna RT versions;
- Mitsuba and DrJit versions;
- execution backend and GPU/CPU model;
- carrier frequency and transmitter powers;
- antenna pattern, array geometry, spacing, and orientation;
- radio materials;
- enabled propagation mechanisms;
- maximum depth and sampling settings;
- random seed;
- scene geometry or generation procedure;
- Blender frame interpretation;
- radio-map dimensions and cell sizes;
- exported result format.

---

## 20. Recommended First Experiment

New users should start with a minimal static scene:

1. Create the Sionna environment.
2. Add a simple wall or room.
3. Assign a radio material.
4. Add one transmitter.
5. Add one receiver.
6. Configure carrier frequency.
7. Enable line of sight and reflection.
8. Enable propagation paths.
9. Run only the current frame.
10. Inspect the returned paths.

After this works, progressively add diffraction, more complex materials, procedural geometry, timeline sweeps, radio maps, and PointCloud trajectories.

---

## 21. Further Documentation

See the other files in `docs/` for installation, radio materials, Geometry Nodes, result schemas, reproducibility, validation, and release procedures.
