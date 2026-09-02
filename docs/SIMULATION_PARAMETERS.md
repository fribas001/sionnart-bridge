# SionnaRT-Bridge Simulation Parameters

This document explains the main physical, numerical, antenna, timeline, and radio-map parameters exposed by SionnaRT-Bridge.

The names and default values below follow the Blender add-on interface.

> **Important:** Default values are starting values for the user interface. They are not universal recommendations for every propagation scenario. Scientific studies should justify solver settings and, where relevant, perform convergence or sensitivity checks.

---

## 1. Core simulation settings

| Interface control | Default | Meaning |
|---|---:|---|
| Frequency | 28 GHz | Carrier frequency used by Sionna RT |
| Bandwidth | 1 MHz | Noise bandwidth used for SINR calculations |
| Temperature | 293 K | Scene temperature used for thermal-noise calculations |
| Max Depth | 3 | Maximum propagation interaction depth |
| Samples / Source | 100000 | Solver sampling budget per source |
| Max Paths / Source | 10000 | Maximum number of paths retained per source |
| Seed | 42 | Random seed used by stochastic solver operations |
| Simulation ID | 0 | Numeric identifier written to exported result rows |
| Timeline | Auto Detect Animation | Determines which Blender frames are solved |
| Frame Step | 1 | Samples every Nth frame when a range is solved |
| Mobility / Doppler | Enabled | Estimates animated TX/RX velocities and path-wise Doppler |

---

## 2. Frequency

**Interface:** `Frequency`  
**Unit:** GHz  
**Default:** `28.0`

The carrier frequency determines the electromagnetic wavelength

```text
lambda = c / f
```

where:

- `lambda` is wavelength in meters;
- `c` is the speed of light;
- `f` is carrier frequency in hertz.

Frequency affects several parts of the simulation, including:

- wavelength-relative antenna-array spacing;
- frequency-dependent radio-material properties;
- propagation behavior;
- the physical interpretation of scene dimensions.

### Example

At 28 GHz, the wavelength is approximately 10.7 mm.

A planar-array spacing of `0.5` therefore corresponds to approximately half a wavelength, or about 5.35 mm.

### Scientific recommendation

Record the frequency used in every experiment.

If frequency changes across Blender frames, document how frame index maps to frequency.

---

## 3. Bandwidth

**Interface:** `Bandwidth (MHz)`  
**Unit:** MHz  
**Default:** `1.0`

Bandwidth is used for thermal-noise calculations required by SINR workflows.

For thermal noise, the general dependence is

```text
noise power ~ k * T * B
```

where:

- `k` is Boltzmann's constant;
- `T` is temperature;
- `B` is bandwidth.

Increasing bandwidth increases integrated thermal-noise power.

### Important

Bandwidth does not directly change geometric propagation paths.

Its main effect in the bridge is on noise-dependent metrics such as SINR.

---

## 4. Temperature

**Interface:** `Temperature (K)`  
**Unit:** kelvin  
**Default:** `293.0`

Temperature is used together with bandwidth to determine thermal noise for SINR calculations.

`293 K` corresponds approximately to room temperature.

For reproducible work, record the temperature assumption when SINR is reported.

---

## 5. Maximum propagation depth

**Interface:** `Max Depth`  
**Default:** `3`

Maximum depth limits how many propagation interactions may occur along a path.

Higher depth can allow higher-order multipath components but generally increases:

- computation time;
- memory requirements;
- number of candidate paths;
- output complexity.

### Practical interpretation

A low depth may be sufficient for simple line-of-sight or first-order reflection studies.

Complex indoor, urban, or obstructed environments may require higher interaction depths.

### Scientific recommendation

Do not automatically maximize this value.

Instead, test whether the quantities of interest change materially when Max Depth is increased.

---

## 6. Samples per source

**Interface:** `Samples / Source`  
**Default:** `100000`

This controls the sampling budget used by the Sionna RT solver for each source.

A larger sampling budget can improve discovery of difficult propagation paths but also increases computational cost.

The required value depends on:

- scene complexity;
- number of transmitters;
- number of receivers;
- enabled propagation mechanisms;
- geometry;
- antenna configuration;
- frequency;
- required precision.

### Scientific recommendation

For publication-grade studies, evaluate whether the result is stable when the number of samples is increased.

Do not describe the default value as universally converged.

---

## 7. Maximum paths per source

**Interface:** `Max Paths / Source`  
**Default:** `10000`

This limits the number of paths retained per source.

A smaller limit can reduce:

- memory usage;
- exported file size;
- Blender geometry density;
- visualization complexity.

However, an aggressive limit may discard weaker valid paths.

If the complete multipath structure is required, ensure that this value is sufficiently high for the scenario.

---

## 8. Seed

**Interface:** `Seed`  
**Default:** `42`

The seed controls stochastic solver operations where applicable.

A fixed seed improves repeatability.

However, users should not assume that GPU-parallel numerical execution will always produce bit-for-bit identical floating-point values across:

- different GPUs;
- different drivers;
- different backends;
- different library versions.

For validation, use documented numerical tolerances rather than requiring binary-identical files.

---

## 9. Simulation ID

**Interface:** `Simulation ID`  
**Default:** `0`

This numeric identifier is written to exported Geometry Nodes CSV rows and can be used to distinguish simulation campaigns.

Examples:

```text
0 = baseline
1 = modified material model
2 = increased transmitter power
3 = alternate antenna configuration
```

For large parameter studies, define a consistent simulation-ID convention and document it.

---

## 10. Timeline mode

**Interface:** `Timeline`

Available modes are:

### Auto Detect Animation

Uses the current frame when devices and solver settings are static.

When relevant animation or frame-dependent state is detected, the scene frame range is solved.

This is the default mode.

### Current Frame Only

Solves only the currently selected Blender frame.

Recommended for:

- setup;
- debugging;
- testing;
- interactive exploration.

### Scene Frame Range

Always solves Blender's configured start-to-end frame range.

Recommended for explicit sweeps and reproducible parameter studies.

---

## 11. Frame step

**Interface:** `Frame Step`  
**Default:** `1`

When a frame range is evaluated, this parameter controls the sampling interval.

Example:

```text
Scene range: 1-10
Frame Step: 2

Solved frames:
1, 3, 5, 7, 9
```

### Scientific recommendation

Document the relationship between frame number and the physical parameter being varied.

Examples:

```text
Frame 1  -> TX power 20 dBm
Frame 2  -> TX power 21 dBm
...
Frame 41 -> TX power 60 dBm
```

or

```text
Frame 1  -> UAV altitude 10 m
Frame 2  -> UAV altitude 12 m
...
```

---

## 12. Mobility / Doppler

**Interface:** `Mobility / Doppler`  
**Default:** Enabled

When enabled, SionnaRT-Bridge estimates animated transmitter and receiver world-space velocities from adjacent Blender frames and allows Sionna RT to compute path-wise Doppler shifts.

### Important

Blender frames only represent physical time if a time mapping is defined.

If Doppler or velocity is scientifically interpreted, document:

- Blender frame rate or frame-to-time mapping;
- trajectory definition;
- device positions;
- any assumptions used to convert animation into physical motion.

Do not interpret frame index as seconds unless this has been explicitly defined.

---

# 13. Propagation mechanisms

The add-on exposes the following solver switches.

| Mechanism | Default |
|---|---:|
| Line of Sight | Enabled |
| Specular Reflection | Enabled |
| Diffuse Reflection | Disabled |
| Refraction | Enabled |
| Diffraction | Disabled |
| Edge Diffraction | Disabled |
| Diffraction in Lit Region | Enabled |

---

## 14. Line of Sight

**Interface:** `Line of Sight`  
**Default:** Enabled

Includes direct unobstructed propagation between transmitter and receiver.

Disable this only when the experiment intentionally excludes the direct path.

---

## 15. Specular reflection

**Interface:** `Specular Reflection`  
**Default:** Enabled

Includes mirror-like reflections from radio-material surfaces.

Specular reflections are important in many:

- indoor;
- urban;
- industrial;
- mmWave

propagation environments.

The quality of reflected paths depends strongly on the geometry and assigned radio materials.

---

## 16. Diffuse reflection

**Interface:** `Diffuse Reflection`  
**Default:** Disabled

Enables diffuse scattering from radio-material surfaces.

Diffuse scattering can be relevant when surfaces exhibit significant roughness or when non-specular energy is important.

Its usefulness depends on the material scattering parameters.

Enabling diffuse reflection can substantially increase computational complexity.

---

## 17. Refraction

**Interface:** `Refraction`  
**Default:** Enabled

Allows supported transmission/refraction behavior through compatible radio materials.

The result depends on:

- material properties;
- material thickness;
- frequency;
- solver assumptions.

Do not assume that every mesh should be treated as transmissive simply because refraction is enabled.

---

## 18. Diffraction

**Interface:** `Diffraction`  
**Default:** Disabled

Enables diffraction contributions associated with eligible edges.

Diffraction can be important in obstructed environments, for example around building edges.

It can also increase solver cost.

---

## 19. Edge diffraction

**Interface:** `Edge Diffraction`  
**Default:** Disabled

Includes free-floating edges when diffraction is enabled.

This option only has an effect when diffraction itself is enabled.

---

## 20. Diffraction in lit region

**Interface:** `Diffraction in Lit Region`  
**Default:** Enabled

Allows diffraction contributions within geometrically illuminated regions.

The interpretation should follow the Sionna RT diffraction model used by the installed version.

---

# 21. Transmitter and receiver antenna arrays

SionnaRT-Bridge exposes shared Sionna RT transmitter and receiver array configurations.

The available antenna patterns are:

- Isotropic;
- Dipole;
- Half-wave Dipole;
- 3GPP TR 38.901.

The default pattern is `Isotropic`.

---

## 22. Array rows and columns

**TX defaults**

```text
TX Rows:    1
TX Columns: 1
```

**RX defaults**

```text
RX Rows:    1
RX Columns: 1
```

Increasing rows or columns creates a larger planar array.

The resulting antenna response depends on:

- element pattern;
- element spacing;
- polarization;
- array geometry;
- orientation.

---

## 23. Antenna spacing

**Default vertical spacing:** `0.5 wavelengths`  
**Default horizontal spacing:** `0.5 wavelengths`

Array spacing is specified in wavelengths rather than meters.

The physical spacing is

```text
physical spacing = wavelength-relative spacing * lambda
```

This means that changing carrier frequency changes the physical spacing represented by the same wavelength-relative value.

---

## 24. Polarization

Available polarization selections are:

- `V` - vertical;
- `H` - horizontal;
- `VH` - dual vertical/horizontal;
- `Cross` - cross-polarized.

The default is `V`.

Available polarization models include:

- TR 38.901 model 2;
- TR 38.901 model 1.

The default is TR 38.901 model 2.

Record polarization settings when reporting antenna configurations.

---

# 25. Per-device orientation

Radio devices support three orientation modes.

## Blender Object / Blender Rotation

Uses the evaluated Blender world rotation.

This is useful when the antenna orientation is controlled visually in the Blender scene.

## Look At Target

Points the Sionna device local `+X` boresight toward a selected Blender object.

Useful for:

- tracking;
- directional antennas;
- UAV links;
- controlled demonstrations.

## Fixed Sionna Euler

Uses explicitly entered Sionna Euler angles:

- Alpha about Z;
- Beta about Y;
- Gamma about X.

Use fixed orientation when exact numerical orientation is more important than the Blender object's visual rotation.

---

# 26. Per-transmitter power

**Interface:** `Transmit Power (dBm)`  
**Default:** `44 dBm`

The power is stored per transmitter and is used by RSS and SINR radio-map calculations.

### Path gain vs transmit power

Path gain describes the propagation channel.

Transmit power is required to convert propagation gain into an absolute received-power quantity.

Therefore:

```text
Path Gain != RSS
```

Changing transmit power changes RSS and can change SINR-based transmitter association, while the underlying geometric paths can remain the same.

---

# 27. Radio-material parameters

SionnaRT-Bridge supports:

- ITU presets;
- custom radio materials.

Custom material controls include:

| Parameter | Default |
|---|---:|
| Thickness | 0.1 m |
| Relative Permittivity | 5.24 |
| Conductivity | 0.0462 S/m |
| Scattering Coefficient | 0 |
| XPD Coefficient | 0 |
| Scattering Pattern | Lambertian |

These defaults are interface starting values and should not be interpreted as universal physical properties.

---

## 28. Material thickness

**Interface:** `Thickness`  
**Unit:** m  
**Default:** `0.1`

Equivalent slab thickness used for reflection and transmission.

Use a value consistent with the represented physical material where applicable.

---

## 29. Relative permittivity

**Interface:** `Relative Permittivity`  
**Default:** `5.24`

Used for custom constant radio materials.

For scientific studies, custom values should be traceable to measurements, literature, standards, or explicitly stated assumptions.

---

## 30. Conductivity

**Interface:** `Conductivity`  
**Unit:** S/m  
**Default:** `0.0462`

Electrical conductivity used by custom radio materials.

As with permittivity, the appropriate value depends strongly on material composition and frequency.

---

## 31. Scattering coefficient

**Interface:** `Scattering Coefficient`  
**Range:** 0 to 1  
**Default:** `0`

Controls effective-roughness scattering strength.

A value of zero disables material diffuse-scattering contribution from this coefficient.

---

## 32. XPD coefficient

**Interface:** `XPD Coefficient`  
**Range:** 0 to 1  
**Default:** `0`

Controls the material cross-polarization discrimination coefficient.

Use non-zero values only when justified by the intended material/scattering model.

---

## 33. Scattering patterns

Available patterns include:

- Lambertian;
- Directive;
- Backscattering.

Additional pattern-specific parameters are exposed when relevant.

Material scattering parameters should be documented together with the simulation.

---

# 34. 2D radio-map settings

SionnaRT-Bridge supports two measurement-surface modes:

- Planar Grid;
- Projected Mesh.

---

## 35. Planar Grid

A regular horizontal XY measurement grid.

Default geometry:

```text
Center X:    0 m
Center Y:    0 m
Height:      1.5 m
Area Size X: 100 m
Area Size Y: 100 m
Cell Size X: 1 m
Cell Size Y: 1 m
```

### Resolution trade-off

Reducing cell size increases spatial resolution but also increases:

- number of map cells;
- runtime;
- memory;
- output size;
- Blender point-cloud density.

Select resolution based on the physical spatial scale of interest.

---

## 36. Projected Mesh

Uses an evaluated Blender mesh as the Sionna measurement surface.

Each eligible non-degenerate triangle represents a radio-map cell.

This is useful for radio maps on:

- inclined surfaces;
- irregular terrain;
- building facades;
- other non-horizontal surfaces.

### Current limitation

In the current add-on implementation, Projected Mesh radio maps support **Path Gain only**.

---

# 37. Radio-map metrics

Available map metrics are:

- Path Gain;
- RSS;
- SINR.

---

## 38. Path Gain

Path Gain represents propagation gain and is independent of absolute transmitter power.

Use it when the primary question concerns the propagation environment itself.

---

## 39. RSS

RSS represents received signal strength / received power.

It depends on transmitter power and propagation gain.

The add-on stores appropriate linear and dB/dBm representations depending on the output.

---

## 40. SINR

SINR compares the desired received signal with interference and thermal noise.

It depends on:

- transmitter powers;
- competing transmitters;
- propagation conditions;
- bandwidth;
- temperature/noise assumptions.

High RSS does not necessarily imply high SINR.

---

# 41. 3D / stacked-height radio maps

The 3D radio-map workflow evaluates horizontal Sionna RT radio maps at multiple heights and combines them into a structured point volume.

> This is a stack of planar Sionna RT calculations, not a separate volumetric electromagnetic solver.

Available metrics are:

- Path Gain;
- RSS;
- SINR.

Default geometry:

```text
Center X: 0 m
Center Y: 0 m
Center Z: 5 m

Size X: 50 m
Size Y: 50 m
Size Z: 10 m

Cell X: 1 m
Cell Y: 1 m
Cell Z: 1 m
```

For regular HDF5 output, the logical organization is:

```text
[frame, z, y, x]
```

---

# 42. Dynamic Mode

Dynamic Mode is a master switch for movement-driven automatic simulations.

When disabled, the add-on does not schedule movement-triggered background simulations.

When enabled, output-specific automatic update options can be used for:

- propagation paths;
- 2D radio maps;
- 3D radio maps.

Dynamic Mode is useful for exploration and demonstrations.

For final scientific sweeps, explicit frame-defined simulations are generally easier to archive and reproduce.

---

# 43. Procedural geometry settings

The add-on exposes:

### Procedural Geometry per Frame

Evaluates Geometry Nodes and modifiers and creates a distinct exported scene for every sampled frame.

Default: disabled.

Enable this when environmental geometry actually changes between frames.

### Capture Geometry Statistics

Stores compact per-frame evaluated mesh descriptors for procedural analytics.

Default: enabled.

### Skip Incompatible Frames

Allows the remaining timeline to continue when one procedural frame cannot be converted successfully.

Default: enabled.

For validation studies, always inspect the procedural export report so that skipped frames are not silently interpreted as completed results.

---

# 44. Practical parameter-selection strategy

For a new scene:

1. Begin with one transmitter and one receiver.
2. Use the current frame only.
3. Start with Line of Sight and Specular Reflection.
4. Use a moderate Max Depth.
5. Test the default sample budget.
6. Inspect the returned paths.
7. Increase Max Depth and Samples / Source separately.
8. Compare the quantities relevant to your study.
9. Add diffraction or diffuse scattering only when physically justified.
10. Add timeline sweeps only after a single frame works correctly.
11. Add radio maps only after the underlying scene/material/device configuration is verified.
12. Record the final parameter set used for published results.

---

# 45. Minimum parameters to report in a publication

At minimum, archive or report:

- carrier frequency;
- bandwidth and temperature for SINR;
- transmitter powers;
- TX/RX antenna patterns;
- array rows and columns;
- array spacing;
- polarization;
- orientation method;
- radio materials;
- Max Depth;
- Samples / Source;
- Max Paths / Source if path truncation is relevant;
- seed;
- enabled propagation mechanisms;
- Blender frame interpretation;
- map size and cell size;
- SionnaRT-Bridge version;
- Blender version;
- Sionna / Sionna RT version;
- Mitsuba version;
- DrJit version;
- compute backend/hardware.

This information makes comparison and reproduction substantially easier.
