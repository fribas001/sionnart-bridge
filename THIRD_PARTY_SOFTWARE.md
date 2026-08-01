# Third-party software and citations

SionnaRT-Bridge interfaces with separately distributed scientific software.
These projects are not bundled with SionnaRT-Bridge and retain their own
copyrights, trademarks, licenses, and citation requirements.

## Dependency overview

| Software | Tested version | Role | License |
|---|---:|---|---|
| Blender | 4.5 LTS | Scene authoring, add-on host, and visualization | GNU GPL |
| Sionna RT | 2.0.1 | Radio-propagation solver | Apache-2.0 |
| Mitsuba 3 | 3.5.0 | Ray-tracing infrastructure | BSD-3-Clause |
| Dr.Jit | Installed with Mitsuba | CPU/GPU JIT computation | BSD-3-Clause |
| Mitsuba-Blender 4.5 Compatibility | 0.4.8 | Blender-to-Mitsuba scene export | BSD-3-Clause |

## Sionna RT

Official project:

https://github.com/NVlabs/sionna-rt

Sionna RT is developed by NVIDIA and distributed under the Apache-2.0
license. SionnaRT-Bridge uses a separately installed `sionna-rt` package
and does not redistribute its source code.

The citation recommended by the official repository is:

```bibtex
@software{sionna,
  title = {Sionna},
  author = {Hoydis, Jakob and Cammerer, Sebastian and
            {Ait Aoudia}, Fayçal and Nimier-David, Merlin and
            Maggi, Lorenzo and Marcus, Guillermo and
            Vem, Avinash and Keller, Alexander},
  note = {https://nvlabs.github.io/sionna/},
  year = {2022},
  version = {2.0.1}
}
```

## Mitsuba 3

Official project:

https://github.com/mitsuba-renderer/mitsuba3

Mitsuba 3 is separately distributed under the BSD-3-Clause license.
Scientific publications should follow the citation guidance provided by
the official Mitsuba 3 project and report the version used.

## Dr.Jit

Official project:

https://github.com/mitsuba-renderer/drjit

For academic use, cite:

Wenzel Jakob, Sébastien Speierer, Nicolas Roussel, and Delio Vicini,
“Dr.Jit: A Just-In-Time Compiler for Differentiable Rendering,”
ACM Transactions on Graphics, volume 41, number 4, 2022.

DOI: https://doi.org/10.1145/3528223.3530099

## Blender

Official project:

https://www.blender.org/

Official source repository:

https://github.com/blender/blender

Blender is the host application for SionnaRT-Bridge and is not bundled
with this repository.

## Mitsuba-Blender 4.5 Compatibility

Tested compatibility component:

https://github.com/fribas001/mitsuba-blender-4.5-compatibility

This component is derived from the official Mitsuba-Blender project:

https://github.com/mitsuba-renderer/mitsuba-blender

Its repository documents the pinned upstream commit, BSD-3-Clause license,
downstream modifications, and release provenance.

## Citing SionnaRT-Bridge

The repository's `CITATION.cff` file describes how to cite SionnaRT-Bridge
itself. Third-party projects are not authors of SionnaRT-Bridge and should
be cited separately in publications using them.