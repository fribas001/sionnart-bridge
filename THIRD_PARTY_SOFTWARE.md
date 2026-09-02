# Third-party software and citations

SionnaRT-Bridge interfaces with separately distributed scientific software.
These projects are not bundled with SionnaRT-Bridge unless explicitly stated
otherwise, and they retain their own copyrights, trademarks, licenses, and
citation requirements.

## SoftwareX reference environment

| Software | Reference version | Role | License / status |
|---|---:|---|---|
| Blender | 5.2 | Scene authoring, add-on host, and visualization | GNU GPL |
| Blender Python | 3.13 | Python runtime used by Blender 5.2 | Bundled with Blender |
| Sionna | 2.0.1 | Scientific communications framework containing Sionna RT | Apache-2.0 |
| Sionna RT | 2.0.1 | Radio-propagation solver | Apache-2.0 |
| Mitsuba 3 | 3.8.0 | Ray-tracing infrastructure used by Sionna RT | BSD-3-Clause |
| DrJit | 1.3.1 | CPU/GPU JIT computation used by Mitsuba | BSD-3-Clause |
| h5py | 3.16.0 | HDF5 result export | BSD-3-Clause |

Version numbers above describe the SoftwareX reference environment. Users
should follow the project-specific compatibility requirements documented in
the installation guide.

## Sionna and Sionna RT

Official project:

https://github.com/NVlabs/sionna

Documentation:

https://nvlabs.github.io/sionna/

Sionna and Sionna RT are developed by NVIDIA and distributed separately under
the Apache-2.0 license. SionnaRT-Bridge does not redistribute their source code.

The SoftwareX reference environment installs:

```text
sionna==2.0.1
```

and uses Sionna RT 2.0.1 from that installation.

For publications, follow the citation guidance provided by the official Sionna
project. The project documentation provides the recommended software citation.

## Mitsuba 3

Official project:

https://github.com/mitsuba-renderer/mitsuba3

Mitsuba 3 is separately distributed under the BSD-3-Clause license.

The SoftwareX reference environment uses:

```text
Mitsuba 3.8.0
```

Scientific publications should follow the citation guidance provided by the
official Mitsuba 3 project and report the version used.

## DrJit

Official project:

https://github.com/mitsuba-renderer/drjit

The SoftwareX reference environment uses:

```text
DrJit 1.3.1
```

For academic use, follow the citation guidance provided by the DrJit project.
A commonly cited publication is:

Wenzel Jakob, Sébastien Speierer, Nicolas Roussel, and Delio Vicini,
“Dr.Jit: A Just-In-Time Compiler for Differentiable Rendering,”
ACM Transactions on Graphics, volume 41, number 4, 2022.

DOI:

https://doi.org/10.1145/3528223.3530099

## h5py

Official project:

https://github.com/h5py/h5py

SionnaRT-Bridge uses h5py for structured HDF5 result export.

The SoftwareX reference environment uses:

```text
h5py 3.16.0
```

h5py is distributed separately and is not bundled with the extension.

## Blender

Official project:

https://www.blender.org/

Official source repository:

https://github.com/blender/blender

Blender is the host application for SionnaRT-Bridge and is not bundled with
this repository.

The extension manifest declares Blender 5.2.0 as the minimum supported Blender
version for the current SoftwareX release.

## Scene export

Current SionnaRT-Bridge releases use the integrated scene-export implementation
shipped with the extension.

The former separate **Mitsuba-Blender 4.5 Compatibility** component was used by
an older workflow and is not required by the current Blender 5.2 installation
procedure.

Its historical repository is:

https://github.com/fribas001/mitsuba-blender-4.5-compatibility

That component was derived from the official Mitsuba-Blender project:

https://github.com/mitsuba-renderer/mitsuba-blender

The historical repositories retain their own licensing and provenance
information. They should not be listed as active dependencies of
SionnaRT-Bridge v1.8.2.

## Citing SionnaRT-Bridge

The repository's `CITATION.cff` file describes how to cite SionnaRT-Bridge
itself.

Third-party projects are not authors of SionnaRT-Bridge and should be cited
separately where appropriate in publications using them.
