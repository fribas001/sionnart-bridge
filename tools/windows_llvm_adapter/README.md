# Windows CPU LLVM compatibility adapter

Optional workaround for the tested **Sionna RT 2.1.0 / Mitsuba 3.9.1 / Dr.Jit 1.5.0 / LLVM 22.1.8, Windows x64 CPU** combination. It is not needed for the existing CUDA workflow and is not an upstream Dr.Jit release.

The adapter forwards 1,226 LLVM exports unchanged and overrides only the default target triple to `x86_64-pc-windows-msvc-elf`. The Windows/MSVC ABI is retained while the JIT emits ELF objects. Both LLVM modules stay mapped until normal process exit. A separate `sionna-llvm-elf-v1` kernel-cache namespace prevents reuse of incompatible COFF cache entries. Solver formulas, numeric types, optimization flags and scene visibility are unchanged.

## Install in a dedicated environment

Install the pinned Sionna packages and the official LLVM 22.1.8 Windows x64 distribution, including `clang-cl`, `lld-link`, `llvm-dlltool`, and `llvm-readobj`. Start with a fresh environment, not one whose Dr.Jit initializer has already been customized.

```powershell
py -3.13 -m venv .venv-sionna
.\.venv-sionna\Scripts\python.exe -m pip install sionna-rt==2.1.0 mitsuba==3.9.1 drjit==1.5.0
python tools/windows_llvm_adapter/manage.py --python .venv-sionna/Scripts/python.exe --llvm-bin 'C:/Program Files/LLVM/bin'
# After a successful read-only preflight:
python tools/windows_llvm_adapter/manage.py --python .venv-sionna/Scripts/python.exe --llvm-bin 'C:/Program Files/LLVM/bin' --apply
```

The installer rejects different package versions, LLVM/core hashes, modified initializers and a non-identical rebuilt adapter. It keeps the original initializer and an installation receipt. Start a new worker after installation. Configure the bridge to use this environment; do not enable the separate experimental diffraction physics candidates.

## Restore

```powershell
python tools/windows_llvm_adapter/manage.py --python .venv-sionna/Scripts/python.exe --llvm-bin 'C:/Program Files/LLVM/bin' --restore
```

Restore verifies both the current initializer and backup before writing. Inert adapter files and the backup remain available for inspection. `SIONNA_LLVM_BATCH_ADAPTER=off` temporarily disables the hook for diagnostic comparisons; doing so restores the original runtime behavior, including the observed batch-failure risk.

## Evidence and limits

The workstation candidate passed 306 continuous fixture executions before installation. The installed runtime then passed 408 executions in four continuous processes; 102 fresh DiffeRT cases were also completed. Physical path records matched the preceding isolated-worker evidence exactly after ignoring solver-owned path-slot ordering. Independent float32/float64 value/gradient arithmetic probes were bit-identical. The [dual-engine guide](../../docs/dual-engine-workflow.md) distinguishes this runtime repair from remaining diffraction physics discrepancies.

This is evidence for the exact checked binaries and CPU workload, not universal compatibility. Disk-cache persistence was not certified because the workstation sandbox denied native cache-file linking. CUDA, other operating systems/compiler builds and later dependency versions need separate validation. Do not bypass the hash checks.
