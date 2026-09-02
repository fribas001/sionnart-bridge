# SionnaRT-Bridge

**SionnaRT-Bridge** is a Blender 5.2+ extension for configuring, executing,
exporting, and visualizing NVIDIA Sionna RT radio-propagation simulations.

Blender is used for scene authoring, procedural geometry, transmitter and
receiver placement, animation, Geometry Nodes visualization, and interaction
with the simulation workflow.

Numerical radio-propagation computations are performed with **NVIDIA
Sionna 2.0.1 / Sionna RT 2.0.1** through a dedicated Python environment that
is compatible with Blender 5.2's Python runtime.

The current extension version is **SionnaRT-Bridge 1.8.1**.

The installable Blender extension is built from:

```text
src/sionnart_bridge/
```

---

## Main capabilities

- Sionna RT propagation-path simulations
- Attributed propagation-path geometry in Blender
- Planar 2D radio maps
- Projected radio maps
- 3D / stacked-height radio maps
- Path gain, RSS, SINR, and related radio-map workflows
- Blender timeline simulation sweeps
- Procedural Geometry Nodes parameter sweeps
- PointCloud-driven transmitter and receiver trajectories
- Dynamic TX/RX movement support
- Transmitter and receiver array configuration
- Antenna orientation configuration
- Sionna radio-material configuration
- Integrated Mitsuba scene exporter
- Scene caching and subprocess worker execution
- CSV + metadata export
- Structured HDF5 + metadata export
- Frame-stacked 2D and 3D coverage tensors
- `Tile_spacial_dataset` HDF5 integration
- Spatial joins between coverage cells and tile information
- Mobility and Doppler support
- Automatic bundled Sionna Geometry Nodes
- Headless Blender execution support

---

## Requirements

The current tested configuration is:

```text
Operating system : Windows 11 x64
Blender          : 5.2
Blender Python   : 3.13.13
Sionna           : 2.0.1
Sionna RT        : 2.0.1
Mitsuba          : 3.8.0
DrJit            : 1.3.1
h5py             : 3.16.0
CUDA backend     : cuda_ad_mono_polarized
```

An NVIDIA GPU and compatible NVIDIA driver are recommended for CUDA-accelerated
Sionna RT ray tracing.

---

## Important: Sionna 2.0.1 must be installed separately

SionnaRT-Bridge does **not** bundle NVIDIA Sionna.

Installing the Blender extension by itself is therefore **not enough to run
Sionna RT simulations**.

Before running simulations, install **Sionna 2.0.1** in a dedicated Python
environment created with Blender 5.2's own Python interpreter.

For Windows, the recommended environment is:

```text
C:\Users\<username>\blender52-sionna
```

SionnaRT-Bridge is designed to detect the corresponding Python packages at:

```text
C:\Users\<username>\blender52-sionna\Lib\site-packages
```

The complete installation procedure is available here:

**[Install Sionna 2.0.1 for Blender 5.2 on Windows](docs/SIONNA_2_BLENDER_5_2_WINDOWS.md)**

---

## Quick Sionna 2.0.1 installation on Windows

Open Windows PowerShell.

First locate Blender 5.2's Python interpreter:

```powershell
$BlenderPython = "C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe"

& $BlenderPython --version
```

A Blender 5.2 installation should report Python 3.13.x. The tested
configuration uses:

```text
Python 3.13.13
```

Create the dedicated environment:

```powershell
& $BlenderPython -m venv "$HOME\blender52-sionna"
```

Upgrade pip and the Python packaging tools:

```powershell
& "$HOME\blender52-sionna\Scripts\python.exe" `
    -m pip install --upgrade pip setuptools wheel
```

Install Sionna 2.0.1:

```powershell
& "$HOME\blender52-sionna\Scripts\python.exe" `
    -m pip install "sionna==2.0.1"
```

Install HDF5 support:

```powershell
& "$HOME\blender52-sionna\Scripts\python.exe" `
    -m pip install h5py
```

Verify Sionna:

```powershell
& "$HOME\blender52-sionna\Scripts\python.exe" `
    -c "import sionna; print('Sionna:', sionna.__version__)"
```

Expected:

```text
Sionna: 2.0.1
```

Verify Sionna RT:

```powershell
& "$HOME\blender52-sionna\Scripts\python.exe" `
    -c "import sionna.rt; print('Sionna RT import: OK')"
```

Expected:

```text
Sionna RT import: OK
```

Verify Mitsuba and DrJit:

```powershell
& "$HOME\blender52-sionna\Scripts\python.exe" `
    -c "import mitsuba as mi, drjit as dr; print('Mitsuba:', mi.__version__); print('DrJit:', dr.__version__)"
```

The tested configuration reports:

```text
Mitsuba: 3.8.0
DrJit: 1.3.1
```

Check available Mitsuba variants:

```powershell
& "$HOME\blender52-sionna\Scripts\python.exe" `
    -c "import mitsuba as mi; print(mi.variants())"
```

On a compatible NVIDIA system, the output should include CUDA variants such
as:

```text
cuda_ad_rgb
cuda_ad_mono
cuda_ad_mono_polarized
cuda_ad_spectral
cuda_ad_spectral_polarized
```

Test the CUDA backend used by the verified SionnaRT-Bridge configuration:

```powershell
& "$HOME\blender52-sionna\Scripts\python.exe" `
    -c "import mitsuba as mi; mi.set_variant('cuda_ad_mono_polarized'); print('Mitsuba variant:', mi.variant())"
```

Expected on a compatible NVIDIA system:

```text
Mitsuba variant: cuda_ad_mono_polarized
```

For more information and troubleshooting, see:

**[Sionna 2.0.1 installation for Blender 5.2](docs/SIONNA_2_BLENDER_5_2_WINDOWS.md)**

---

## PyTorch CUDA note

Sionna RT performs its ray tracing through **Mitsuba and DrJit**.

For this reason:

```python
torch.cuda.is_available()
```

is not the definitive test of whether Sionna RT can use the GPU.

A Python environment may report:

```text
False
```

for PyTorch CUDA while Mitsuba successfully uses:

```text
cuda_ad_mono_polarized
```

For SionnaRT-Bridge ray tracing, the important GPU test is whether the required
Mitsuba CUDA variant can be selected successfully.

---

## Installation of SionnaRT-Bridge

### 1. Install Sionna first

Before installing or running the Blender extension, follow:

**[Install Sionna 2.0.1 for Blender 5.2 on Windows](docs/SIONNA_2_BLENDER_5_2_WINDOWS.md)**

### 2. Install the Blender extension

Download the release ZIP:

```text
sionnart_bridge-1.8.1.zip
```

In Blender 5.2:

1. Open **Edit → Preferences**
2. Open **Get Extensions**
3. Choose **Install from Disk**
4. Select `sionnart_bridge-1.8.1.zip`
5. Enable **SionnaRT-Bridge**

The standard Blender 5.2 workflow automatically looks for the recommended
environment:

```text
~/blender52-sionna
```

On Windows this normally resolves to:

```text
C:\Users\<username>\blender52-sionna
```

The packages are loaded from:

```text
C:\Users\<username>\blender52-sionna\Lib\site-packages
```

Sionna does not need to be copied into Blender's installation directory.

---

## Verify Sionna from inside Blender

Open Blender's Python Console and run:

```python
import sys
from pathlib import Path

site_packages = (
    Path.home()
    / "blender52-sionna"
    / "Lib"
    / "site-packages"
)

if str(site_packages) not in sys.path:
    sys.path.insert(0, str(site_packages))

import sionna
import sionna.rt
import mitsuba as mi

print("Sionna:", sionna.__version__)
print("Mitsuba variants:", mi.variants())
```

To verify the tested CUDA backend:

```python
mi.set_variant("cuda_ad_mono_polarized")
print("Mitsuba variant:", mi.variant())
```

Expected:

```text
Sionna: 2.0.1
Mitsuba variant: cuda_ad_mono_polarized
```

---

## Quick start

After Sionna and SionnaRT-Bridge are installed:

1. Open Blender 5.2.
2. Open the **Sionna RT** sidebar.
3. Create or prepare the simulation environment.
4. Place scene geometry under the Sionna scene hierarchy.
5. Assign Sionna radio materials.
6. Create or mark transmitter and receiver objects.
7. Configure carrier frequency, arrays, solver settings, and propagation
   mechanisms.
8. Choose the desired simulation mode.
9. Choose the desired export mode: no durable export, CSV + metadata, or
   HDF5 + metadata.
10. Run the simulation.
11. Inspect propagation paths or radio maps through the bundled Geometry Nodes
    visualization groups.

---

## Integrated Mitsuba exporter

SionnaRT-Bridge 1.8.1 includes its own integrated Mitsuba scene exporter:

```text
src/sionnart_bridge/integrated_mitsuba_exporter.py
```

The legacy **Mitsuba-Blender 4.5 Compatibility** package is **not required**
for the standard Blender 5.2 workflow.

The integrated exporter converts the Blender simulation scene into the scene
representation required by Sionna RT workers.

---

## Geometry Nodes visualization library

SionnaRT-Bridge 1.8.1 bundles its Geometry Nodes library directly inside the
extension:

```text
src/sionnart_bridge/assets/sionnart_geometry_nodes.blend
```

The extension automatically loads missing Sionna Geometry Nodes groups.

The bundled library includes visualization groups for propagation paths and
2D/3D radio maps.

Current bundled groups include:

```text
Sionna_Paths
Sionna_radio_map_pathgain_node
Sionna_radio_map_projected_pathgain_node
Sionna_radio_map_rss_node
Sionna_radio_map_sinr_node
Sionna_radio_map_3d_pathgain_node
Sionna_radio_map_3d_rss_node
Sionna_radio_map_3d_sinr_node
```

Existing node groups with the same name are preserved so that Blender does not
create unnecessary `.001` duplicates.

Manual appending of the standard Sionna visualization node groups is not
normally required.

---

## PointCloud TX/RX trajectories

SionnaRT-Bridge supports PointCloud-driven transmitter and receiver movement.

When a PointCloud path is connected, the transmitter or receiver position is
updated from the point corresponding to the current Blender frame.

This allows trajectories generated by external or procedural spatial datasets
to drive Sionna RT simulations directly from the Blender timeline.

The Tile Dataset workflow can, for example, provide:

```text
Tile_TX_Path_Points
```

for transmitter sampling and motion.

---

## Tile spatial dataset integration

SionnaRT-Bridge can integrate with a Blender PointCloud object named exactly:

```text
Tile_spacial_dataset
```

When HDF5 export is enabled and this object exists, its numeric attributes can
be embedded into the simulation HDF5 output.

The dataset is stored under:

```text
/spatial_datasets/Tile_spacial_dataset
```

Coverage maps can include a spatial join between coverage cells and tile
indices.

For 2D coverage this enables relationships between simulated radio coverage
and tile-level information such as:

```text
building information
statistical-sector information
population information
base-station information
ROI / buffer classification
other numeric tile attributes
```

The exact spelling `Tile_spacial_dataset` is retained for compatibility with
the Tile Dataset Blender workflow.

---

## HDF5 result export

SionnaRT-Bridge supports structured HDF5 export.

Current HDF5 output supports simulation categories including:

```text
/simulations/paths
/simulations/coverage_2d
/simulations/coverage_3d
```

For compatible regular radio-map grids, coverage values are stored as dense
time-series tensors.

Typical 2D coverage layout:

```text
[frame, y, x]
```

Typical 3D coverage layout:

```text
[frame, z, y, x]
```

The HDF5 output also stores metadata describing dimensions, simulation
configuration, source datasets, and available spatial joins.

---

## Dynamic simulations

The extension supports dynamic transmitter and receiver workflows.

When Dynamic Mode and trajectory controls are used, Blender frame changes can
drive TX/RX positions before Sionna RT simulations are launched.

This enables frame-by-frame radio-propagation studies for mobility,
trajectory sampling, UAV studies, and other dynamic network scenarios.

---

## Headless Blender execution

SionnaRT-Bridge can also be used with Blender in background/headless mode.

A typical Blender command follows the form:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" `
    -b "project.blend" `
    -P "run_sionna_headless.py"
```

Scripts using Blender's `bpy` API must be executed by Blender's Python runtime,
not by a normal standalone Python interpreter.

---

## Build the Blender extension

The extension source is located at:

```text
src/sionnart_bridge
```

Using Blender 5.2 on Windows, validate the extension with:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" `
    --command extension validate `
    ".\src\sionnart_bridge"
```

A successful validation reports:

```text
Success parsing TOML in ".\src\sionnart_bridge"
```

Build the extension with:

```powershell
New-Item -ItemType Directory -Force ".\dist" | Out-Null

& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" `
    --command extension build `
    --source-dir ".\src\sionnart_bridge" `
    --output-dir ".\dist"
```

The expected release asset for version 1.8.1 is:

```text
dist\sionnart_bridge-1.8.1.zip
```

The extension manifest is:

```text
src\sionnart_bridge\blender_manifest.toml
```

and currently declares:

```text
version = "1.8.1"
blender_version_min = "5.2.0"
```

---

## Tests

The repository includes source and metadata tests that can run without a full
interactive Blender session.

Install development requirements as documented by the repository and run:

```bash
pytest
```

Scientific validation should additionally verify the complete Blender,
Sionna RT, Mitsuba, DrJit, GPU, scene-export, and result-export workflow.

See:

[Validation protocol](docs/validation.md)

---

## Reproducibility

For reproducible simulation studies, record at minimum:

```text
SionnaRT-Bridge version
Blender version
Blender Python version
Sionna version
Sionna RT version
Mitsuba version
DrJit version
GPU model
NVIDIA driver
Mitsuba execution variant
carrier frequency
TX power
antenna configuration
solver settings
propagation mechanisms
random seed
simulation scene
simulation frame / trajectory state
```

For the currently tested SionnaRT-Bridge 1.8.1 environment:

```text
Blender          5.2
Python           3.13.13
Sionna           2.0.1
Sionna RT        2.0.1
Mitsuba          3.8.0
DrJit            1.3.1
Mitsuba backend  cuda_ad_mono_polarized
```

See:

[Reproducibility documentation](docs/reproducibility.md)

---

## Documentation

- [User guide](docs/USER_GUIDE.md) - complete overview of the Blender workflow and interface
- [Simulation parameter reference](docs/SIMULATION_PARAMETERS.md) - physical, solver, antenna, material, and radio-map settings
- [Example workflows](docs/WORKFLOWS.md) - step-by-step propagation-path, trajectory, procedural, 2D, and 3D examples

- [Sionna 2.0.1 installation for Blender 5.2 on Windows](docs/SIONNA_2_BLENDER_5_2_WINDOWS.md)
- [Installation](docs/installation.md)
- [Reproducibility](docs/reproducibility.md)
- [Validation protocol](docs/validation.md)
- [Antenna naming](docs/antenna-naming.md)
- [Radio materials](docs/radio-materials.md)
- [Output schemas](docs/output-schemas/)
- [Geometry Nodes](docs/geometry-nodes.md)
- [Release and Zenodo archiving](docs/release-and-archiving.md)
- [Third-party software and citations](THIRD_PARTY_SOFTWARE.md)

---

## Citation

Citation metadata are provided in:

[`CITATION.cff`](CITATION.cff)

If a DOI is assigned through Zenodo or another archive, cite the archived
release corresponding to the exact SionnaRT-Bridge version used in the
simulation study.

---

## Third-party software and citations

SionnaRT-Bridge depends on separately distributed scientific software,
including:

```text
Blender
NVIDIA Sionna
Sionna RT
Mitsuba
DrJit
PyTorch
NumPy
h5py
```

These projects remain separate dependencies and are distributed according to
their respective licenses.

See:

[THIRD_PARTY_SOFTWARE.md](THIRD_PARTY_SOFTWARE.md)

for dependency, provenance, licensing, and citation information.

---

## License

SionnaRT-Bridge is distributed under the GNU General Public License,
version 3 or later:

```text
GPL-3.0-or-later
```

See:

[LICENSE](LICENSE)

Sionna, Sionna RT, Mitsuba, DrJit, Blender, PyTorch, and other dependencies
are separate software projects distributed under their own licenses.

---

## Support

Use the GitHub issue tracker for reproducible bug reports and feature requests.

For publication-related questions, contact:

```text
Felipe Oliveira Ribas
felipe.oliveiraribas@ugent.be
```