# Installation

## 1. Install Blender 5.2

Install Blender 5.2 or newer. The extension manifest declares Blender 5.2.0
as the minimum supported version.

The SoftwareX reference environment uses Blender 5.2 with Blender Python 3.13.

## 2. Create the Sionna RT runtime environment

SionnaRT-Bridge does not bundle NVIDIA Sionna. On Windows, create the tested
runtime environment with Blender 5.2's bundled Python rather than an unrelated
Conda or system Python installation.

The default Blender 5.2 Python executable is:

```text
C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe
```

In PowerShell:

```powershell
$BlenderPython = "C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe"

& $BlenderPython -m venv "$HOME\blender52-sionna"

& "$HOME\blender52-sionna\Scripts\python.exe" `
    -m pip install --upgrade pip setuptools wheel

& "$HOME\blender52-sionna\Scripts\python.exe" `
    -m pip install -r requirements-external.txt
```

The SoftwareX reference environment uses:

- Sionna 2.0.1
- Sionna RT 2.0.1
- Mitsuba 3.8.0
- DrJit 1.3.1
- h5py 3.16.0

For detailed Windows setup, CUDA-backend checks, and troubleshooting, see
[`SIONNA_2_BLENDER_5_2_WINDOWS.md`](SIONNA_2_BLENDER_5_2_WINDOWS.md).

## 3. Install SionnaRT-Bridge

For the SoftwareX release, install the release asset:

```text
sionnart_bridge-1.8.2.zip
```

In Blender, open **Edit → Preferences → Get Extensions → Install from Disk**,
select the ZIP file, and enable the extension if needed.

The extension package does not require the former separate
Mitsuba-Blender 4.5 compatibility add-on.

## 4. Runtime behavior

In the normal Blender 5.2 workflow, you do not need to select a separate
external Python interpreter.

SionnaRT-Bridge launches isolated worker processes with Blender 5.2's bundled
`python.exe`. The tested configuration stores the Sionna packages in:

```text
C:\Users\<username>\blender52-sionna\Lib\site-packages
```

The add-on auto-detects `~/blender52-sionna` and exposes those packages to the
worker processes.

Configure a writable workspace directory in the Sionna RT interface as needed.

## 5. Test the environment

Run **Test Environment** from the Sionna RT interface.

For the SoftwareX reference environment, verify that the reported runtime is
consistent with:

```text
Blender            5.2
Blender Python     3.13
Sionna             2.0.1
Sionna RT          2.0.1
Mitsuba            3.8.0
DrJit              1.3.1
h5py               3.16.0
```

If using the tested GPU workflow, also verify that the required Mitsuba/DrJit
CUDA variant initializes successfully.

## Troubleshooting

For Windows-specific setup and diagnostics, see
[`SIONNA_2_BLENDER_5_2_WINDOWS.md`](SIONNA_2_BLENDER_5_2_WINDOWS.md).

When opening an issue, include the worker log, status JSON, version report, and
a minimal reproducible example where possible. Failed runs retain their run
directory for diagnosis.
