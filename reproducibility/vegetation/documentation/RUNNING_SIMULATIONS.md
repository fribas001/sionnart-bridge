# Native simulation and route comparison

Create an isolated environment with Python 3.13.13 and the package versions in `requirements-simulation.txt`. Install/configure a compatible Mitsuba/Dr.Jit backend following the official Sionna RT documentation: https://nvlabs.github.io/sionna/rt/ . The recorded Windows system used CUDA. The environment specification is a record of the tested stack, not a guarantee of driver compatibility on every operating system.

For notebook 02, install `requirements-notebook-simulation.txt` in the simulation environment. The analysis-only notebook requirements pin a different tested NumPy version; keep these environments separate.

## Native Sionna: one or more scenes

```text
python scripts/run_study.py foliage_r1 --frames 1,9,10 --output ../my_native_foliage
python scripts/run_study.py seed_ensemble --frames 1,27,33,35 --output ../my_native_seeds
```

Use `--frames all` for the full selected study. Use `--check` to validate configuration and files without importing Sionna. Every command requires a new empty output directory. `scripts/build_native_configs.py` creates one explicit JSON configuration per observation; `scripts/run_vegetation.py` can also accept a user-created list of scenes under common settings, as shown by `studies/native_comparison/native_aligned.json`.

The packaged seed/exploratory scenes are reconstructed and labeled accordingly. To regenerate geometry yourself, first use `configure_blender.py` and inspect its `reconstruction.json`. Native solver settings remain in the generated JSON; geometry seeds belong to scene generation and solver seeds belong to ray tracing.

The native runner writes the full returned arrays, scalar summaries, configuration snapshots, runtime versions and comparison outcomes. Summaries use the first TX/RX antenna pair. Comparisons use 0.01 dB gain and 0.01 ns delay tolerances with exact path-count and LoS checks, and report actual errors. These are practical regression thresholds, not claims of physical accuracy. Floating-point/platform changes or nondeterministic runs can change outcomes. The exploratory ray sweep explicitly has deterministic mode disabled; new values should not be assumed bitwise repeatable.

## Reproduce the Blender/native timing protocol

```text
python scripts/run_blender_comparison.py --blender /path/to/blender --sionna-python /path/to/sionna/python --output ../new_comparison
```

This copies the harness into a new directory, appends the recorded realization-1 tree, exports frames 1/9/10, and runs one warm-up plus three measured pairs per state. Routes alternate order. It invokes the add-on's cached-run operator and a separate native process. The source model is hash-checked before/after and never saved. Initial geometry export is measured separately and excluded from cached-run timings. Array synchronization is included in both solver measurements. Close competing GPU workloads before interpreting timings.

`--prepare-only` writes the local configuration without executing; `--quick` runs one warm-up pair at frame 1 as an integration check, not a performance study. The original publication measurements remain under `studies/native_comparison/`. Do not merge newly generated timing observations into that dataset without documenting a new experiment/version.

## Matched numerical checks

The 30-case schedule is `studies/numerical_stability/schedule.json`. To prepare a fresh run without old completion logs:

```text
python scripts/run_stability.py --output ../new_stability
```

Use `--check` to validate all inputs without simulation, or `--limit 1` for one case. This copies only the required configurations, scenes and runner into a new directory, then executes the recorded schedule. The original completed results remain untouched.
