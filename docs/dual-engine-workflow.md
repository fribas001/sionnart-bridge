# Comparing Sionna RT and DiffeRT in Blender

[DiffeRT-Bridge](https://github.com/fribas001/differt-bridge) is a separately installable GPL companion derived from SionnaRT-Bridge 2.1.0. Both extensions can remain enabled in Blender 5.2, using independent external Python environments and result collections. This addition does not replace the existing Sionna extension or change its native radio-material formulas.

## Setup

1. Keep the [Sionna installation](../src/sionnart_bridge/README.md) and its dedicated external interpreter.
2. Install the DiffeRT-Bridge prerelease and create its separate environment from that repository's pinned requirements.
3. In DiffeRT, select **Copy Sionna Setup**. Geometry is shared; device objects and radio settings are copied.
4. Set different results folders and select the correct interpreter in each extension.
5. Start with isotropic antennas, LoS/specular paths and depth 1. Use **Run Both — Paths**, then inspect the actual-input and geometry checks before interpreting the deltas.

Refresh the copied setup after changing static settings, constraints or animation assignments. Do not treat point-receiver DiffeRT coverage as the same estimator as Sionna's surface-area radio maps. Sionna edge/lit-region controls also have no exact mapping to DiffeRT.

## Windows CPU runtime workaround

The existing CUDA validation remains separate. For **Windows x64, Sionna RT 2.1.0, Mitsuba 3.9.1, Dr.Jit 1.5.0 and LLVM 22.1.8**, the optional [LLVM adapter](../tools/windows_llvm_adapter/README.md) addresses the observed continuous-batch linking failures and unsafe LLVM unloading. It changes the JIT object format and module lifetime, not ray geometry, material coefficients, numerical precision or solver formulas.

The candidate completed 306 fixture executions before installation. The installed configuration completed 408 Sionna executions across four continuous processes; 102 fresh DiffeRT runs were also completed. Physical records matched the prior evidence exactly after ignoring solver-owned path-slot ordering. The adapter rejects different binary hashes and versions and includes a backup/restore path. It is not an upstream compiler release or a generic fix for every CPU configuration.

## Scientific findings

The [diffraction report and evidence](https://github.com/fribas001/differt-bridge/releases/tag/v0.6.3) records 496 requested executions: 486 numerical completions and 10 configured DiffeRT candidate-budget rejections. These are not 496 successful physical comparisons.

- Native DiffeRT passes 40/40 nonzero signed PEC-limit checks at a 0.1% threshold; the tested installed Sionna assembly does not.
- Isolated Sionna field-assembly corrections pass those checks and restore the tested reflection-boundary cancellation signs.
- A separate isolated distance correction removes approximately 1.295 dB of dependence on unused maximum path depth for a fixed diffraction→reflection route.
- Material reciprocity and dielectric boundary differences remain. Matching PEC asymptotics or a shared LoS/specular room does not establish general diffraction equivalence.

The field candidates are **not installed by either Blender extension or the LLVM adapter**. They require an explicit diagnostic option in the companion repository and exist only inside the child process. The report relates them to upstream issues [#84](https://github.com/NVlabs/sionna-rt/issues/84), [#85](https://github.com/NVlabs/sionna-rt/issues/85), and [#87](https://github.com/NVlabs/sionna-rt/issues/87); upstream endorsement is not implied.

The historical workstation shared-profile control has 1,299 matched paths and zero exported phase difference. That experiment includes opt-in arithmetic/material/geometry alignment and must not be presented as the default behavior of two fresh native runtimes. Keep engine versions, source hashes, actual inputs and active profiles with every comparison.
