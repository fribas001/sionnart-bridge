# SionnaRT-Bridge 2.1.0

Blender scene preparation, procedural sweeps, Sionna RT simulation, spatial visualization and parameter analysis.

## Install and check

1. Keep a copy of your project before upgrading. Install the release ZIP through Blender **Preferences > Add-ons > Install from Disk**, replacing the extension with identifier `sionnart_bridge`, then restart Blender.
2. Sionna RT is installed separately. The tested stack is Blender 5.2.0 LTS, Python 3.13.13, Sionna RT 2.1.0, Mitsuba 3.9.1, Dr.Jit 1.5.0 and h5py 3.16.0 on Windows 11 with a CUDA GPU. See `TEST_REPORT.md` for exact versions and coverage.
3. Open the **Sionna RT** sidebar. Under **Setup**, select Blender Python plus compatible Sionna site-packages, or an external Python environment with Sionna installed. Click **Test Runtime**.
4. Select a writable workspace. Use a short local path, such as `D:\Sionna_runs`, for projects with long names.

For a new environment, use Blender 5.2's Python to create a virtual environment, then install `sionna-rt==2.1.0`, `mitsuba==3.9.1`, `drjit==1.5.0`, `numpy==2.5.2` and `h5py==3.16.0`. The optional sensing plots use `matplotlib==3.11.1`. Point the extension to that environment's Python executable or site-packages. These packages are not included in the extension ZIP. No package installation runs automatically.

## Basic simulation

1. Click **Create / Repair Env**. Place propagation geometry in `sionna_env > scene`, including any desired subcollections.
2. Create the material library and assign explicit radio materials to the exported surfaces. Blender preview colors do not define the radio response.
3. Add TX and RX devices. Paths require both; radio maps require transmitters. Array settings are shared by device role. Device orientations and TX powers are configurable.
4. Select **Paths**, **2D Radio Map**, **3D Radio Map** or **Combined Outputs**. Set frequency, solver interactions, sampling budget and the frame selection.
5. Click **Run Simulation**. Outputs are embedded in Blender and can be saved with the project. **Stop Simulation** stops the current worker and queued outputs, pauses live updates and retains partial files for inspection.

New scenes refresh static geometry before each run. Turn off **Refresh Scene Before Run** only when intentionally reusing an unchanged scene cache. Cached geometry does not follow subsequent mesh edits. Procedural mode exports evaluated geometry for each sampled frame regardless of this switch.

Opening another Blender file or disabling the extension stops workers owned by the extension. Failed runs retain their files and logs. Successful worker completion is checked before result import; a failed batch component remains reported as a failure even if another output succeeds.

## Procedural experiments

Place changing meshes under `scene > procedural_geometry`, enable **Procedural Geometry**, animate the relevant Geometry Nodes inputs and select a frame range/step. The whole evaluated modifier stack and supported instances are exported. Ordinary object and device animation are supported too.

Use separate runs for solver convergence, input sensitivity and random-seed ensembles. The timeline schedules samples; the extension does not choose a scientific experimental design. Keep settings fixed unless they are part of the intended variation.

Grid and PointCloud motion templates can drive device trajectories. With **Dynamic Mode** enabled, device movement can trigger a current-frame recalculation after a short delay. RX movement affects paths; TX movement can affect paths and maps. Automatically refreshed results replace the previous automatic result while retaining manual runs.

## Vegetation

The material library includes leaf and wood reference presets. Select a preset, assign it to the corresponding geometry and review the frequency range, slab thickness and scattering settings. The default scattering coefficient is an explicit baseline assumption, not a calibrated canopy value. See `PLANT_MATERIALS.md`.

**Measure Vegetation** records measurements per generating object and frame. They include leaf-area estimates, connected leaf-component counts, optional supplied leaf IDs, envelope-based density and area indices, direct TX-RX crossings and density inside a configurable corridor. **Inspect Vegetation** previews these without running the solver. Definitions, units and limitations are in `VEGETATION_METRICS.md`.

These are measurements of the represented mesh. Connected components are not guaranteed biological leaf identities. Envelope density includes empty space within the bounds. Link measurements refer to the direct TX-RX segment/corridor, not every multipath ray or radio-map cell.

## Data and plots

- **Export Geometry Nodes Parameters**: optional full JSON per sampled frame with evaluated inputs and accompanying scene/device/material/simulation records; retained independently of result-file export.
- **Prepare Parameter Analysis**: stores compact inputs, vegetation measurements and channel summaries with the paths result. It works even when external result export is disabled.
- **Export Results**: choose embedded-only, CSV plus metadata, or HDF5 plus metadata. A batch HDF5 retains distinct output categories.
- **Open Parameter Plots**: select a TX/RX link, X parameter or vegetation descriptor, and Y channel metric. Import another simulation metadata JSON/ZIP as a reference. Reports are self-contained HTML; plots, observations and statistics can be downloaded as SVG, CSV and JSON.

Path gain in parameter reports is the incoherent sum of valid path powers, `10 log10(sum(abs(a_k)**2))`. Summaries use the first TX/RX antenna pair for each device link, before visualization limits. They are not full-array beamforming gain or received power in dBm. Zero-path runs are retained with path count zero and unavailable gain/delay values.

Statistics describe the sampled observations: range, mean, median, population standard deviation, first-to-last change and descriptive correlation. Across-frame spread is not automatically uncertainty; correlation is not proof of causality. Lines connect points in frame order. Reports list changing inputs and differences between compared runs.

Match data by run ID, frame, output category and TX/RX identity. Prepared input records alone do not certify a completed simulation. Save the `.blend` and required external assets to retain the procedural model. Existing reports cannot acquire newly introduced measurements without a new simulation.

## Visualization scope

Planar and stacked-height maps support path gain, RSS and SINR. The 3D result is a stack of horizontal samples. Projected maps use mesh triangles as measurement cells and support path gain. Bundled Geometry Nodes groups are loaded automatically; existing user-edited groups are preserved. Optional curve paths coexist with embedded results and parameter analysis.

### Oriented 2D radio maps

Under **2D Radio Map**, choose **Map Surface: Planar Grid** and **Map Plane**:

- **XY (Horizontal)** is the default, including for projects saved with earlier releases.
- **XZ (Vertical)** uses local X/Z axes; position the slice with Center Y.
- **YZ (Vertical)** uses local Y/Z axes; position the slice with Center X.
- **Custom Rotation** exposes Blender XYZ Euler angles. At zero rotation the map is XY. All three angles can be keyframed; AUTO timeline detection includes their animation.

Center X/Y/Z always use world coordinates. For XY, Center Z is labelled Height. Area and cell sizes follow the selected plane axes; custom planes label these U/V. For example, an XZ map with Area Size X = 50 m and Area Size Z = 20 m is a vertical 50-by-20-m slice. Position its center halfway up the desired vertical extent. Keep the TX outside the measurement plane to avoid a coplanar sampling configuration.

The worker passes Sionna `(alpha, beta, gamma) = (Rotation Z, Rotation Y, Rotation X)` in radians, using `Rz(alpha) Ry(beta) Rx(gamma)`. This is the convention in the [official Sionna radio-map documentation](https://nvlabs.github.io/sionna/rt/api/radio_maps.html) and the installed Sionna RT 2.1.0 implementation. Orientation rotates the measurement grid, not the antennas or scene geometry. Map values retain the selected antenna configuration.

New planar visualizers use rectangular tiles at the computed world positions, with their full in-plane rotation and independently sized sides. Frame filtering, metric threshold, color and opacity remain available through Geometry Nodes. New `*_oriented_node` groups are separate from legacy groups so saved results and user edits are preserved; new simulations select the oriented groups automatically. Existing simulated data is not rotated or recalculated when settings change: run the simulation again.

CSV contains world `x/y/z`, world normal/tangent/bitangent components, and Blender `rotation_x/y/z` in radians. Metadata records the orientation per frame. HDF5 retains `frame,y,x` tensor order for compatibility: here y/x index local V/U, not necessarily world Y/X. `plane_center`, `plane_orientation`, `plane_basis` (rows U/V/normal), and `plane_u/plane_v` describe the plane; `cell_centers` supplies authoritative world positions. Coordinates that change across frames retain their frame axis. Projected Mesh continues to use the selected mesh's orientation; 3D maps remain horizontal slice stacks.

With automatic TX centering enabled, the 2D center follows the transmitter within the measurement plane and preserves the plane's position along its normal. For XY this keeps the existing behavior: X/Y follow the TX and Height stays fixed.

## Optional sensing workflow

The existing CIR/CSI and human-pose export remains optional and disabled by default. It exports ideal simulated channels and synthetic pose labels; it does not provide measured Wi-Fi packets or articulated-body micro-Doppler. Human-material presets are homogeneous proxies evaluated when assigned; reapply them when changing frequency. `ISAC_DATA_DICTIONARY.md` defines the export.

RIS and crowd/JuPedSim integrations are excluded. Existing saved project objects are not deleted during an upgrade.

## Verification and support

See `TEST_REPORT.md`, `CHANGELOG.md` and the included `tests` folder. The release was checked on the stated Windows/CUDA stack. Other operating systems, CPU-only execution and arbitrary third-party node setups require separate validation. Software verification does not establish predictive accuracy for a real vegetation canopy or site.

Source and issues: https://github.com/fribas001/sionnart-bridge
License: GPL-3.0-or-later; see `LICENSE`.
