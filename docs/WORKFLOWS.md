# SionnaRT-Bridge Example Workflows

This document provides task-oriented examples for the main SionnaRT-Bridge workflows.

The examples use the control names shown in the Blender add-on interface.

> **Recommendation:** Start with a minimal current-frame simulation before launching long timeline sweeps or dense radio maps.

---

# 1. Basic propagation-path simulation

## Goal

Create a minimal static scene with one transmitter and one receiver, run Sionna RT, and inspect the returned propagation paths.

## Step 1 — Test the runtime

Open the **Sionna RT** sidebar in Blender.

Expand:

```text
Sionna Runtime
```

Click:

```text
Test Runtime
```

Do not continue until the runtime test succeeds.

A successful runtime test confirms that the bridge can locate the required Sionna RT / Mitsuba / DrJit environment.

---

## Step 2 — Create the simulation hierarchy

Expand:

```text
Workflow
```

Click:

```text
Create / Repair Env
```

This creates or repairs the Blender collections used by SionnaRT-Bridge.

---

## Step 3 — Add static scene geometry

Create or select geometry representing the propagation environment.

For a first test, a simple floor and wall are sufficient.

Select the geometry and click:

```text
Move to Static Scene
```

Use static geometry when its evaluated mesh does not change between simulation frames.

---

## Step 4 — Assign radio materials

Expand:

```text
Radio Materials
```

For a quick test, click:

```text
Create Default Materials
```

Select the desired material.

If needed, use:

```text
Enable / Prefix itu_
```

Then select the Blender objects that should use the material and click:

```text
Assign to Selected
```

### Important

A Blender visual material is not automatically a radio material.

The radio material controls electromagnetic properties used by Sionna RT.

---

## Step 5 — Add a transmitter

Expand:

```text
Devices
```

Click:

```text
Add TX
```

Move the created transmitter to the desired position.

For example:

```text
TX = (0 m, 0 m, 1.5 m)
```

Select the TX and expand:

```text
Per-device Orientation
```

Set the desired:

```text
Transmit Power (dBm)
Orientation
```

For a first test, the default orientation and antenna configuration are sufficient.

---

## Step 6 — Add a receiver

Click:

```text
Add RX
```

Move the receiver to another location, for example:

```text
RX = (5 m, 0 m, 1.5 m)
```

---

## Step 7 — Configure the solver

Expand:

```text
Simulation Settings
```

For a basic test, use:

```text
Frequency:            28 GHz
Max Depth:            3
Samples / Source:     100000
Seed:                  42
Timeline:              Current Frame Only
Line of Sight:         Enabled
Specular Reflection:   Enabled
Diffuse Reflection:    Disabled
Diffraction:           Disabled
```

These are starting settings, not universal scientific recommendations.

---

## Step 8 — Enable propagation paths

Enable:

```text
Propagation Paths
```

Choose the desired post-run representation.

For interactive Blender visualization, configure the path result to return/import curves or attributed geometry.

---

## Step 9 — Choose result persistence

Expand:

```text
Simulation
```

Set:

```text
Export Results
```

Available choices include:

```text
No persistent export
CSV
HDF5
```

For a first visual test, no persistent export is acceptable.

For scientific analysis, use a persistent structured output.

---

## Step 10 — Run

Click:

```text
Run Simulation
```

After the worker completes, inspect the returned path geometry in Blender.

---

## Expected result

The scene should contain reconstructed propagation paths between TX and RX.

Depending on geometry and enabled mechanisms, the result may contain:

- a direct line-of-sight path;
- reflected paths;
- transmitted/refracted paths;
- diffraction paths if enabled;
- diffuse-scattering contributions if enabled.

---

# 2. Propagation paths with procedural geometry

## Goal

Evaluate changing Blender geometry over a frame range and run one Sionna RT calculation for each evaluated state.

This workflow corresponds to use cases such as:

- growing vegetation;
- moving obstacles;
- changing building geometry;
- Geometry Nodes parameter sweeps.

---

## Step 1 — Prepare a working static simulation

First complete the basic propagation-path workflow above.

Verify that one current-frame simulation runs successfully before introducing procedural geometry.

---

## Step 2 — Create the procedural object

Create or select an object whose evaluated mesh changes with Blender frame.

Examples:

- Geometry Nodes vegetation growth;
- animated obstacle dimensions;
- modifier-driven geometry;
- frame-dependent procedural structures.

---

## Step 3 — Move it to procedural geometry

Select the object.

Under:

```text
Workflow
```

click:

```text
Move to Procedural Geometry
```

You can also use the corresponding control under:

```text
Procedural Geometry
```

---

## Step 4 — Enable procedural export

Expand:

```text
Procedural Geometry
```

Enable:

```text
Procedural Geometry per Frame
```

Recommended:

```text
Capture Geometry Statistics: Enabled
```

For exploratory sweeps you may keep:

```text
Skip Incompatible Frames: Enabled
```

For validation, inspect the procedural export report afterward so that skipped frames are not mistaken for completed calculations.

---

## Step 5 — Define the frame range

Configure Blender's scene start and end frames.

Then under:

```text
Simulation Settings
```

set:

```text
Timeline: Scene Frame Range
Frame Step: 1
```

Example:

```text
Start frame: 1
End frame:   70
Frame Step:   1
```

---

## Step 6 — Verify representative frames

Before launching the complete sweep:

1. inspect the first frame;
2. inspect a middle frame;
3. inspect the final frame;
4. verify that the procedural mesh evaluates as expected;
5. run one or two frames manually if necessary.

---

## Step 7 — Run the sequence

Enable:

```text
Propagation Paths
```

Then click:

```text
Run Simulation
```

For each sampled frame, the bridge evaluates the required Blender state before preparing the Sionna RT calculation.

---

## Step 8 — Interpret the output

Treat the Blender frame index as an experiment coordinate.

Document what changes with frame.

Example:

```text
Frames 1-70 represent successive procedural vegetation growth states.
```

If frame number represents physical time, document the frame-to-time conversion.

---

# 3. Transmitter or receiver location sweep using a Grid

## Goal

Evaluate many candidate TX or RX positions without manually creating keyframes for every device location.

---

## Step 1 — Create or mark the device

Under:

```text
Devices
```

create a TX or RX using:

```text
Add TX
Add RX
```

or select an existing Blender object and use:

```text
Mark TX
Mark RX
```

---

## Step 2 — Enable the motion path

Under:

```text
Devices
```

enable:

```text
TX / RX Motion Path
```

Set:

```text
Style: Grid
Associated TX / RX: <your device>
```

---

## Step 3 — Configure the grid

Set:

```text
Columns
Rows
Column Spacing
Row Spacing
Start Frame
```

Example:

```text
Columns:        10
Rows:           10
Column Spacing: 2 m
Row Spacing:    2 m
Start Frame:    1
```

This creates:

```text
100 positions
```

mapped to:

```text
frames 1-100
```

The grid uses serpentine ordering.

---

## Step 4 — Generate the grid

Click:

```text
Generate Grid
```

The generated grid can be moved, rotated, or scaled in Blender to reposition the sweep.

---

## Step 5 — Set the scene range

Enable:

```text
Set Scene Range to Path
```

or manually configure the Blender scene range.

Use:

```text
Timeline: Auto Detect Animation
```

or:

```text
Timeline: Scene Frame Range
```

to solve the complete sweep.

---

## Step 6 — Run

Enable the required output:

```text
Propagation Paths
Radio Maps
3D Radio Maps
```

Then:

```text
Run Simulation
```

---

## Scientific interpretation

A grid sweep represents a sequence of independently evaluated device locations.

Document:

- grid origin;
- row and column spacing;
- orientation;
- frame mapping;
- device role;
- solver settings.

---

# 4. Device trajectory from an existing PointCloud

## Goal

Drive a transmitter or receiver through positions stored in a Blender PointCloud.

This is useful for:

- UAV trajectories;
- mobility routes;
- candidate site lists;
- imported spatial samples.

---

## Step 1 — Prepare a PointCloud

Create or import a Blender PointCloud containing the desired ordered positions.

Point order determines the frame mapping.

---

## Step 2 — Select the device

Under:

```text
Devices
```

enable:

```text
TX / RX Motion Path
```

Set:

```text
Style: PointCloud
Associated TX / RX: <your TX or RX>
PointCloud Path: <your PointCloud>
Start Frame: 1
```

---

## Step 3 — Connect the trajectory

Click:

```text
Connect PointCloud Path
```

The mapping is:

```text
point index i -> frame Start + i
```

For example, with Start Frame = 1:

```text
point 0 -> frame 1
point 1 -> frame 2
point 2 -> frame 3
...
```

---

## Step 4 — Verify alignment

Scrub the Blender timeline.

The add-on displays the current point/frame relationship and can report the alignment error between the device and expected PointCloud position.

Verify that the device follows the intended trajectory before launching a simulation.

---

## Step 5 — Run the timeline

Set the timeline to:

```text
Auto Detect Animation
```

or:

```text
Scene Frame Range
```

Enable the desired simulation output and click:

```text
Run Simulation
```

---

# 5. Basic planar 2D radio map

## Goal

Generate a horizontal radio map around one or more transmitters.

---

## Step 1 — Prepare the environment and TX

Complete the runtime, environment, material, and TX setup from Workflow 1.

A receiver is not required for a radio-map-only workflow.

---

## Step 2 — Enable Radio Maps

Enable:

```text
Radio Maps
```

Set:

```text
Map Surface: Planar Grid
```

---

## Step 3 — Choose the metric

Available metrics include:

```text
Path Gain
RSS
SINR
```

### Path Gain

Use when studying propagation gain independently of absolute TX power.

### RSS

Use when absolute received power is required.

Verify each transmitter's:

```text
Transmit Power (dBm)
```

### SINR

Use when studying desired-signal quality in the presence of interference and noise.

Verify:

```text
TX powers
Bandwidth
Temperature
```

---

## Step 4 — Define the map

Example:

```text
Center X:    0 m
Center Y:    0 m
Height:      1.5 m
Area Size X: 50 m
Area Size Y: 50 m
Cell Size X: 1 m
Cell Size Y: 1 m
```

Smaller cell sizes produce finer spatial sampling but increase:

- number of cells;
- runtime;
- memory;
- export size;
- Blender visualization density.

---

## Step 5 — Run

Under:

```text
Simulation
```

choose the desired export mode.

Then click:

```text
Run Simulation
```

Inspect the returned radio-map point cloud / attributed Blender geometry.

---

# 6. Projected-Mesh radio map

## Goal

Evaluate a radio map on an irregular or inclined Blender mesh instead of a horizontal plane.

---

## Step 1 — Prepare the reference mesh

Create or select the Blender mesh that should act as the measurement surface.

Examples:

- sloped terrain;
- building facade;
- roof;
- irregular measurement surface.

---

## Step 2 — Configure Radio Maps

Enable:

```text
Radio Maps
```

Set:

```text
Map Surface: Projected Mesh
Reference Mesh: <your mesh>
```

---

## Step 3 — Select the metric

The current implementation supports:

```text
Path Gain
```

for Projected Mesh mode.

If another metric is selected, the interface warns that Projected Mesh currently supports Path Gain only.

---

## Step 4 — Run

Click:

```text
Run Simulation
```

The returned values are associated with eligible non-degenerate triangles of the evaluated reference mesh.

---

# 7. 3D stacked-height radio map

## Goal

Generate height-resolved coverage by stacking multiple horizontal Sionna RT radio maps.

This is useful for scenarios such as UAV coverage and vertical urban analysis.

> **Important:** This is not a separate volumetric electromagnetic solver. It is a structured stack of planar Sionna RT radio-map evaluations.

---

## Step 1 — Prepare the environment and transmitters

Complete the environment, materials, TX, antenna, power, and solver configuration.

---

## Step 2 — Enable 3D Radio Maps

Enable:

```text
3D Radio Maps
```

Choose:

```text
Path Gain
RSS
SINR
```

as required.

---

## Step 3 — Define the volume

Example:

```text
Center X: 0 m
Center Y: 0 m
Center Z: 10 m

Size X: 50 m
Size Y: 50 m
Size Z: 20 m

Cell X: 2 m
Cell Y: 2 m
Cell Z: 2 m
```

The vertical cell size determines the spacing between the evaluated horizontal radio-map layers.

---

## Step 4 — Estimate the computational size

Before running a dense volume, consider the approximate number of samples:

```text
Nx ~ Size X / Cell X
Ny ~ Size Y / Cell Y
Nz ~ Size Z / Cell Z
```

The complete result scales approximately with:

```text
Nx * Ny * Nz * number of frames
```

Use a coarse grid for initial testing.

---

## Step 5 — Run

Choose the persistent output format and click:

```text
Run Simulation
```

For structured HDF5 output, regular 3D coverage data are organized logically as:

```text
[frame, z, y, x]
```

---

# 8. SINR transmitter-power sweep

## Goal

Use Blender frames to represent a controlled transmitter-power sweep and evaluate SINR-based spatial association.

---

## Step 1 — Create two transmitters

Create:

```text
TX 1
TX 2
```

Set both initially to the same power.

Example:

```text
TX 1 = 20 dBm
TX 2 = 20 dBm
```

---

## Step 2 — Keep the intended TX fixed

Keep:

```text
TX 1 = 20 dBm
```

for the entire experiment.

---

## Step 3 — Animate the second TX power

Use Blender animation/keyframes or the supported parameter workflow so that the second transmitter changes with frame.

Example experiment definition:

```text
Frame 1  -> TX 2 = 20 dBm
Frame 2  -> TX 2 = 21 dBm
...
Frame 41 -> TX 2 = 60 dBm
```

Document this mapping explicitly.

---

## Step 4 — Configure SINR

Under:

```text
Simulation Settings
```

verify:

```text
Bandwidth
Temperature
```

Under:

```text
Radio Maps
```

or:

```text
3D Radio Maps
```

select:

```text
SINR
```

---

## Step 5 — Use a frame range

Set:

```text
Timeline: Scene Frame Range
Frame Step: 1
```

Configure the scene range to cover the complete sweep.

---

## Step 6 — Run

Click:

```text
Run Simulation
```

The resulting dataset can be analyzed frame-by-frame to determine how the serving / highest-SINR transmitter changes as TX power varies.

---

# 9. Dynamic interactive propagation paths

## Goal

Automatically recompute paths when a TX or RX is moved interactively in Blender.

This workflow is intended for exploration and demonstration.

---

## Step 1 — Enable Dynamic Mode

Under:

```text
Simulation
```

enable:

```text
Dynamic Mode
```

The interface should report:

```text
TX/RX movement watcher active
```

---

## Step 2 — Enable path auto-computation

Under:

```text
Propagation Paths
```

enable:

```text
Auto Compute on TX / RX Move
```

Set:

```text
Move Debounce
```

as needed.

---

## Step 3 — Move a device

Move the TX or RX in the Blender viewport.

The bridge schedules a current-frame path simulation after the movement debounce interval.

---

## Important

Dynamic Mode is primarily an exploratory feature.

For archived or publication-grade sweeps, explicit frame-based runs are usually easier to reproduce.

---

# 10. Dynamic radio map following a moving TX

## Goal

Recompute a planar radio map when the TX moves and optionally keep the map centered on the TX.

---

## Step 1 — Enable Dynamic Mode

Under:

```text
Simulation
```

enable:

```text
Dynamic Mode
```

---

## Step 2 — Enable Radio Maps

Enable:

```text
Radio Maps
```

Set:

```text
Map Surface: Planar Grid
```

---

## Step 3 — Enable automatic coverage

Enable:

```text
Auto Compute on TX Move
```

Optionally enable:

```text
Center Map on Moving TX
```

When enabled, automatic runs follow the moved TX in X/Y while keeping the configured map Height unchanged.

---

## Step 4 — Move the TX

Move the transmitter in Blender.

After the debounce interval, the current-frame coverage map is recomputed.

---

# 11. Recommended publication workflow

For a result that will be reported in a paper or archived dataset:

1. Verify one current-frame simulation manually.
2. Freeze the software version.
3. Record the complete environment versions.
4. Fix and record the solver seed.
5. Record radio-material definitions.
6. Record TX/RX antenna settings and powers.
7. Define exactly what Blender frame means.
8. Use explicit timeline ranges rather than only interactive Dynamic Mode.
9. Use persistent CSV or HDF5 output.
10. Retain simulation metadata together with results.
11. Record skipped or failed frames.
12. Archive scripts used to produce derived statistics.
13. Record the Git tag and archival DOI associated with the software version.

---

# 12. Troubleshooting checklist

If a simulation does not behave as expected, check in this order:

1. **Test Runtime** succeeds.
2. Scene geometry is inside the correct static/procedural hierarchy.
3. Simulation meshes have valid radio materials.
4. At least one TX exists.
5. A RX exists when propagation paths require one.
6. TX/RX orientation is correct.
7. Frequency and antenna-array settings are appropriate.
8. The intended propagation mechanisms are enabled.
9. The requested output toggle is enabled.
10. Timeline mode is correct.
11. Procedural geometry is enabled only when required.
12. Map dimensions and cell sizes are reasonable.
13. The **Status** section contains no worker errors.
14. Use **Open Last Run** to inspect the latest run directory.
15. Reduce the experiment to one frame and one output type before debugging a large sweep.
