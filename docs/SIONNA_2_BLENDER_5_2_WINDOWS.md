# Installing Sionna 2.0.1 for Blender 5.2 on Windows

SionnaRT-Bridge requires NVIDIA Sionna RT to perform radio-propagation
simulations.

Sionna is **not bundled with SionnaRT-Bridge** and must be installed
separately before running simulations.

This guide documents the Windows configuration tested with
SionnaRT-Bridge 1.8.2.

## Tested configuration

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

---

## Installation architecture

Do **not** install Sionna directly into Blender's installation directory:

```text
C:\Program Files\Blender Foundation\
```

Instead, create a dedicated Python virtual environment using the Python
interpreter bundled with Blender 5.2.

The recommended environment location is:

```text
C:\Users\<username>\blender52-sionna
```

Its Python packages are stored under:

```text
C:\Users\<username>\blender52-sionna\Lib\site-packages
```

SionnaRT-Bridge is designed to detect this environment automatically.

This approach keeps Blender's installation directory clean while ensuring
that the external Sionna packages use a Python version compatible with
Blender 5.2.

---

# Step-by-step installation

## Step 1 — Open Windows PowerShell

Open a normal Windows PowerShell terminal.

You do not need to run PowerShell as Administrator.

---

## Step 2 — Locate Blender 5.2 Python

The default Blender 5.2 Python executable is:

```text
C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe
```

Define it in PowerShell:

```powershell
$BlenderPython = "C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe"
```

Check the Python version:

```powershell
& $BlenderPython --version
```

Expected output should be similar to:

```text
Python 3.13.x
```

The tested Blender 5.2 installation reports:

```text
Python 3.13.13
```

---

## Step 3 — Create the Sionna environment

Create a virtual environment using Blender's own Python interpreter:

```powershell
& $BlenderPython -m venv "$HOME\blender52-sionna"
```

This creates:

```text
C:\Users\<username>\blender52-sionna
```

The environment's Python executable is:

```text
C:\Users\<username>\blender52-sionna\Scripts\python.exe
```

The corresponding site-packages directory is:

```text
C:\Users\<username>\blender52-sionna\Lib\site-packages
```

---

## Step 4 — Upgrade pip, setuptools, and wheel

Run:

```powershell
& "$HOME\blender52-sionna\Scripts\python.exe" `
    -m pip install --upgrade pip setuptools wheel
```

This ensures the environment has current Python packaging tools.

---

## Step 5 — Install Sionna 2.0.1

Run:

```powershell
& "$HOME\blender52-sionna\Scripts\python.exe" `
    -m pip install "sionna==2.0.1"
```

This installs NVIDIA Sionna and its dependencies.

For the tested environment, this includes:

```text
Sionna       2.0.1
Sionna RT    2.0.1
Mitsuba      3.8.0
DrJit        1.3.1
PyTorch      2.13.0
NumPy
SciPy
Matplotlib
```

The exact dependency versions installed by pip may change over time except
where they are constrained by Sionna 2.0.1.

---

## Step 6 — Install HDF5 support

SionnaRT-Bridge supports structured HDF5 simulation-result export.

Install `h5py`:

```powershell
& "$HOME\blender52-sionna\Scripts\python.exe" `
    -m pip install h5py
```

Sionna 2.0.1 may already install a compatible version of `h5py`, but running
this command ensures it is available.

The tested environment uses:

```text
h5py 3.16.0
```

---

# Verify the installation

## Step 7 — Verify Sionna

Run:

```powershell
& "$HOME\blender52-sionna\Scripts\python.exe" `
    -c "import sionna; print('Sionna:', sionna.__version__)"
```

Expected output:

```text
Sionna: 2.0.1
```

---

## Step 8 — Verify Sionna RT

Run:

```powershell
& "$HOME\blender52-sionna\Scripts\python.exe" `
    -c "import sionna.rt; print('Sionna RT import: OK')"
```

Expected output:

```text
Sionna RT import: OK
```

---

## Step 9 — Verify Mitsuba and DrJit

Run:

```powershell
& "$HOME\blender52-sionna\Scripts\python.exe" `
    -c "import mitsuba as mi, drjit as dr; print('Mitsuba:', mi.__version__); print('DrJit:', dr.__version__)"
```

The tested environment reports:

```text
Mitsuba: 3.8.0
DrJit: 1.3.1
```

---

## Step 10 — List available Mitsuba execution variants

Run:

```powershell
& "$HOME\blender52-sionna\Scripts\python.exe" `
    -c "import mitsuba as mi; print(mi.variants())"
```

The tested NVIDIA system reports variants including:

```text
scalar_rgb
scalar_spectral
scalar_spectral_polarized
llvm_ad_rgb
llvm_ad_mono
llvm_ad_mono_polarized
llvm_ad_spectral
llvm_ad_spectral_polarized
cuda_ad_rgb
cuda_ad_mono
cuda_ad_mono_polarized
cuda_ad_spectral
cuda_ad_spectral_polarized
```

For CUDA-accelerated Sionna RT operation, at least one appropriate
`cuda_*` variant should be available.

---

## Step 11 — Test the CUDA backend

The tested SionnaRT-Bridge configuration uses:

```text
cuda_ad_mono_polarized
```

Test it with:

```powershell
& "$HOME\blender52-sionna\Scripts\python.exe" `
    -c "import mitsuba as mi; mi.set_variant('cuda_ad_mono_polarized'); print('Mitsuba variant:', mi.variant())"
```

Expected output on the tested NVIDIA system:

```text
Mitsuba variant: cuda_ad_mono_polarized
```

If this succeeds, Mitsuba/DrJit can access the CUDA backend required by the
tested Sionna RT workflow.

---

# Important PyTorch CUDA note

Sionna RT performs its ray tracing through **Mitsuba and DrJit**.

Therefore:

```python
torch.cuda.is_available()
```

is not the definitive test of whether Sionna RT can use the GPU.

For example, PyTorch may report:

```text
False
```

while Mitsuba successfully uses:

```text
cuda_ad_mono_polarized
```

For SionnaRT-Bridge ray tracing, the relevant GPU verification is whether
the required Mitsuba CUDA variant can be selected successfully.

---

# Install SionnaRT-Bridge

## Step 12 — Obtain the extension ZIP

Download the SionnaRT-Bridge release ZIP or build it from the repository.

For version 1.8.2, the expected extension package is:

```text
sionnart_bridge-1.8.2.zip
```

---

## Step 13 — Install the extension in Blender

Open Blender 5.2.

Then:

1. Open **Edit → Preferences**
2. Open **Get Extensions**
3. Choose **Install from Disk**
4. Select `sionnart_bridge-1.8.2.zip`
5. Enable **SionnaRT-Bridge**

Sionna itself remains in the external environment:

```text
C:\Users\<username>\blender52-sionna
```

It does not need to be copied into:

```text
C:\Program Files\Blender Foundation\
```

---

# Verify Sionna from inside Blender

## Step 14 — Open Blender's Python Console

Open Blender and switch to the Python Console.

The following code manually exposes the tested Sionna site-packages
directory to Blender:

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

Expected Sionna version:

```text
Sionna: 2.0.1
```

---

## Step 15 — Test CUDA inside Blender

After the Sionna environment has been made available to Blender, run:

```python
import mitsuba as mi

mi.set_variant("cuda_ad_mono_polarized")

print("Mitsuba variant:", mi.variant())
```

Expected on the tested NVIDIA system:

```text
Mitsuba variant: cuda_ad_mono_polarized
```

---

# Troubleshooting

## `ModuleNotFoundError: No module named 'sionna'`

Check whether Sionna is installed in the dedicated environment:

```powershell
& "$HOME\blender52-sionna\Scripts\python.exe" `
    -m pip show sionna
```

Check the installed Sionna package directories:

```powershell
Get-ChildItem "$HOME\blender52-sionna\Lib\site-packages\sionna*"
```

You should see the Sionna packages inside:

```text
C:\Users\<username>\blender52-sionna\Lib\site-packages
```

---

## Blender uses the wrong Python version

Create the environment using Blender 5.2's bundled Python interpreter:

```text
C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe
```

Do not create the Sionna environment with an unrelated Conda or system
Python installation.

The external packages need to be compatible with Blender's Python runtime.

---

## CUDA variants are unavailable

List the Mitsuba variants:

```powershell
& "$HOME\blender52-sionna\Scripts\python.exe" `
    -c "import mitsuba as mi; print(mi.variants())"
```

If no `cuda_*` variants are available, check:

- NVIDIA GPU availability
- NVIDIA driver installation
- Mitsuba installation
- DrJit installation

---

## Sionna RT imports but CUDA fails

First verify the CPU/LLVM and CUDA variants returned by:

```powershell
& "$HOME\blender52-sionna\Scripts\python.exe" `
    -c "import mitsuba as mi; print(mi.variants())"
```

Then explicitly test:

```powershell
& "$HOME\blender52-sionna\Scripts\python.exe" `
    -c "import mitsuba as mi; mi.set_variant('cuda_ad_mono_polarized'); print(mi.variant())"
```

If the CUDA variant cannot initialize, investigate the NVIDIA driver and
Mitsuba/DrJit installation independently of PyTorch.

---

## HDF5 export is unavailable

Check `h5py`:

```powershell
& "$HOME\blender52-sionna\Scripts\python.exe" `
    -c "import h5py; print('h5py:', h5py.__version__)"
```

The tested environment reports:

```text
h5py: 3.16.0
```

If `h5py` is missing:

```powershell
& "$HOME\blender52-sionna\Scripts\python.exe" `
    -m pip install h5py
```

---

# Verified runtime

This workflow was validated with:

```text
Windows           11 x64
Blender           5.2
Blender Python    3.13.13
Sionna            2.0.1
Sionna RT         2.0.1
Mitsuba           3.8.0
DrJit             1.3.1
h5py              3.16.0
Mitsuba backend   cuda_ad_mono_polarized
```

The Sionna environment is intentionally kept separate from the Blender
installation so that dependencies can be inspected, reproduced, upgraded,
or replaced without modifying Blender's program files.

---

# Next steps

After the environment passes the tests above:

1. Start Blender 5.2.
2. Enable SionnaRT-Bridge.
3. Open the **Sionna RT** sidebar.
4. Prepare a Sionna simulation scene.
5. Create transmitter and receiver objects.
6. Configure antennas, materials, propagation mechanisms, and solver settings.
7. Run a path or radio-map simulation.
8. Inspect the generated Blender visualization.
9. Optionally export simulation results as CSV or HDF5.