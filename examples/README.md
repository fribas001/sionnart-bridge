# Reproducible examples

This directory contains the illustrative Blender examples and preview material distributed with SionnaRT-Bridge.

## Complete Blender examples

- [`procedural-vegetation-paths`](procedural-vegetation-paths/) — demonstrates frame-dependent procedural vegetation growth and its effect on propagation paths.
- [`urban-stacked-height-map`](urban-stacked-height-map/) — demonstrates an animated stacked-height radio-map visualization in the Munich urban scene.

Each complete example includes a Blender scene, usage instructions, visualization material, and file-integrity checksums where provided.

The two directories listed above are the canonical illustrative examples for the SoftwareX software package.

---

## Preview material

- [`03-animated-paths-and-stacked-height-map`](03-animated-paths-and-stacked-height-map/) contains earlier animation and preview material.

Preview material is useful for demonstration, but the complete example directories above should be preferred for reproducible workflows.

---

## Relationship to validation

These examples illustrate workflows described in the SoftwareX manuscript, but they are not a substitute for raw numerical validation data.

The validation methodology is documented in:

```text
docs/validation.md
```

The repository does not currently include a standalone `validation/` directory containing the complete raw 70-frame comparison dataset used for the manuscript-reported agreement value.

---

## Recommended use

For a reproducible example run:

1. use the tagged SionnaRT-Bridge release associated with the experiment;
2. follow the README inside the selected example directory;
3. verify the documented software environment;
4. retain the exact Blender scene used;
5. record solver settings and random seed;
6. retain CSV or HDF5 output for quantitative analysis where applicable;
7. record checksums for archived result files when practical.

See also:

```text
docs/reproducibility.md
docs/USER_GUIDE.md
docs/SIMULATION_PARAMETERS.md
docs/WORKFLOWS.md
```
