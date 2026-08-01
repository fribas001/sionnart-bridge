\# Third-party software and citations



SionnaRT-Bridge interfaces with separately distributed scientific software.

Unless explicitly stated otherwise, these projects are not bundled with

SionnaRT-Bridge and retain their own copyrights, trademarks, licenses, and

citation requirements.



\## Dependency overview



| Software | Tested version | Role | License | Official project |

|---|---:|---|---|---|

| Blender | 4.5 LTS | Scene authoring, procedural modeling, add-on host, and visualization | GPL-3.0-or-later | https://www.blender.org/ |

| Sionna RT | 2.0.1 | Radio-propagation path and radio-map solver | Apache-2.0 | https://github.com/NVlabs/sionna-rt |

| Mitsuba 3 | 3.5.0 | Ray-tracing and scene infrastructure used by Sionna RT | BSD-3-Clause | https://github.com/mitsuba-renderer/mitsuba3 |

| Dr.Jit | Installed with the tested Mitsuba/Sionna RT environment | JIT-compiled CPU and GPU computation | BSD-3-Clause | https://github.com/mitsuba-renderer/drjit |

| Mitsuba-Blender 4.5 Compatibility | 0.4.8 | Blender-to-Mitsuba scene export | BSD-3-Clause | https://github.com/fribas001/mitsuba-blender-4.5-compatibility |



The compatibility component is a downstream adaptation of the official

Mitsuba-Blender add-on:



https://github.com/mitsuba-renderer/mitsuba-blender



Its exact upstream commit, license notices, and downstream modifications are

documented in the compatibility repository.



\## Sionna RT



Sionna RT is developed by NVIDIA and distributed under the Apache-2.0

license. SionnaRT-Bridge uses the separately installed `sionna-rt` package

and does not redistribute Sionna RT source code.



Official citation guidance is provided by the Sionna RT repository. For the

tested release, the recommended software citation is:



```bibtex

@software{sionna,

&#x20; title   = {Sionna},

&#x20; author  = {Hoydis, Jakob and Cammerer, Sebastian and

&#x20;            {Ait Aoudia}, Fayçal and Nimier-David, Merlin and

&#x20;            Maggi, Lorenzo and Marcus, Guillermo and

&#x20;            Vem, Avinash and Keller, Alexander},

&#x20; note    = {https://nvlabs.github.io/sionna/},

&#x20; year    = {2022},

&#x20; version = {2.0.1}

}

