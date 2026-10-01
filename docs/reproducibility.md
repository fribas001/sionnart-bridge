# Reproducible experiments

The current procedural vegetation study uses add-on **2.1.0** and has archive DOI **[10.5281/zenodo.23081848](https://doi.org/10.5281/zenodo.23081848)**. Its [scripts, notebooks and instructions](../reproducibility/vegetation/README.md) distinguish original raw outputs, reconstructed inputs and new verification runs. The archive stores the large Blender project and datasets; GitHub maintains the software and lightweight reproduction material.


Keep the source `.blend`, external assets, extension version/commit, solver environment and simulation-time exports. Use procedural mode when meshes vary; intentional static cache reuse does not track later edits.

Record geometry-generator inputs and seeds separately from solver seeds. Join completed observations by run ID, category, frame and device link. Optional full Geometry Nodes JSON retains more scene context; compact parameter records and vegetation measurements are embedded with paths results. Prepared inputs alone do not establish completion.

Use the [measurement definitions](../src/sionnart_bridge/VEGETATION_METRICS.md) and [material assumptions](../src/sionnart_bridge/PLANT_MATERIALS.md). Keep corridor width, area convention, frequency, arrays, materials and device geometry fixed when they are not experimental factors. One generator input can change multiple physical quantities.

Solver convergence, sensitivity to controlled inputs and uncertainty across scene realizations require different comparisons. Descriptive statistics from one sweep do not establish all three. Preserve missing no-path gains and explicit sample counts. A no-leaf reference requires verified absence of leaves, not merely a generator socket set to zero.

The full release tests and tested platform are in [validation](validation.md). The original repository examples remain available with their existing provenance; rerun the chosen examples with the released version before reporting new scientific findings.
