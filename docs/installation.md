# Installation

## 1. Install Blender

Install Blender 4.5 LTS. The extension manifest declares Blender 4.5.0 as the
minimum supported version.

## 2. Install the scene-export compatibility component

Install **Mitsuba-Blender 4.5 Compatibility v0.4.8** from its separate
repository and archived release:

`https://github.com/fribas001/mitsuba-blender-4.5-compatibility`

Use the release asset `mitsuba_blender_45_compatibility-0.4.8.zip` and verify
its published SHA-256 checksum.

## 3. Create the external Sionna RT environment

Use Python 3.11:

```bash
python3.11 -m venv .venv-sionna
source .venv-sionna/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-external.txt
```

On Windows, activate with `.venv-sionna\Scripts\activate`.

For CPU execution, install the LLVM/runtime components required by Mitsuba and
Dr.Jit. GPU execution additionally requires a backend and driver combination
supported by those projects.

## 4. Install SionnaRT-Bridge

Download `sionnart_bridge-1.0.0.zip` from the v1.0.0 GitHub release. In Blender,
open **Edit → Preferences → Get Extensions → Install from Disk**, select the
ZIP file, and enable the extension if needed.

## 5. Configure and test

In the 3D View sidebar, open **Sionna RT**. Set:

- the external Python executable;
- a writable workspace directory;
- the scene-export compatibility extension.

Run **Test Environment** and record the reported Python, Sionna RT, and Mitsuba
versions in the validation log.

## Troubleshooting

Attach the worker log, status JSON, version report, and a minimal example when
opening an issue. Failed runs retain their run directory for diagnosis.
