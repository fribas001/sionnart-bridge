# SionnaRT-Bridge 2.1.0

A Blender extension for procedural scene preparation, Sionna RT simulation, spatial visualization and parameter-linked analysis.

## Start here

- [Install and run](src/sionnart_bridge/README.md)
- [Tested environment and release verification](docs/validation.md)
- [Vegetation material presets](src/sionnart_bridge/PLANT_MATERIALS.md)
- [Vegetation measurements: definitions and units](src/sionnart_bridge/VEGETATION_METRICS.md)
- [Reproducible experiments](docs/reproducibility.md)
- [Changes in 2.1](CHANGELOG.md)
- [Vegetation study, scripts and notebooks](reproducibility/vegetation/README.md)
- [Reproducibility archive: DOI 10.5281/zenodo.23081848](https://doi.org/10.5281/zenodo.23081848)
- [Examples](examples/README.md)

## Capabilities

- Evaluated Blender scenes, Geometry Nodes and supported instances.
- Timeline sweeps, device motion and Doppler.
- Propagation paths; XY (default), XZ, YZ and arbitrarily oriented planar maps; projected mesh maps and stacked-height maps.
- Per-frame Geometry Nodes inputs, materials, device settings and vegetation descriptors.
- Parameter-versus-channel plots, descriptive statistics and comparison of saved runs.
- Embedded Blender results, CSV/JSON and HDF5 exports.
- Optional simulated CIR/CSI and human-pose exports, disabled by default.

RIS and crowd integrations are excluded. Existing example assets are preserved; their historical results are distinct from the current vegetation validation dataset.

## Tested stack

Blender 5.2.0 LTS, Python 3.13.13, Sionna RT 2.1.0, Mitsuba 3.9.1, Dr.Jit 1.5.0 and h5py 3.16.0 on Windows 11/CUDA. The extension does not bundle Sionna. See the installation guide before running simulations.

Version 2.1.0 extends the software verification with planar-map orientation, animation, rectangular tiles and export/persistence checks. The exact archived code also underlies the native comparison and vegetation reproducibility checks linked above. CPU-only and other operating systems have not been validated by that sequence. Scientific accuracy remains specific to the model and experiment.

## Build and test

```text
python -m pip install -r requirements-dev.txt
python -m pytest
python -m unittest discover -s src/sionnart_bridge/tests -p "test_*.py"
node src/sionnart_bridge/tests/test_report_math.cjs
python scripts/check_release.py
python scripts/build_extension.py
```

The deterministic build writes the installable ZIP and SHA-256 under `dist/`. The full local Blender/Sionna regression runner is `src/sionnart_bridge/tests/run_release_checks.py`; use `--help` for explicit runtime/output arguments. Portable CI runs source, unit, report and packaging checks without claiming native GPU coverage.

## Cite and archive

Use `CITATION.cff` for the software. The procedural vegetation study has a separate [reproducibility archive, DOI 10.5281/zenodo.23081848](https://doi.org/10.5281/zenodo.23081848), containing the exact tested 2.1.0 source, installable extension, editable model and simulation evidence. See [the dataset citation](reproducibility/vegetation/CITATION.cff) and [reproduction instructions](reproducibility/vegetation/README.md). Publication of the reserved Zenodo record is managed separately by the authors.

The earlier [v1.8.2 DOI 10.5281/zenodo.20125209](https://doi.org/10.5281/zenodo.20125209) remains historical. Use a versioned software tag and the matching dataset DOI when reporting these experiments. See [release and archiving](docs/release-and-archiving.md).

GPL-3.0-or-later. See [LICENSE](LICENSE), [AUTHORS.md](AUTHORS.md) and [third-party attribution](THIRD_PARTY_SOFTWARE.md).
