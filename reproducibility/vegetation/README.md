# Procedural vegetation reproducibility study

Archive DOI: **[10.5281/zenodo.23081848](https://doi.org/10.5281/zenodo.23081848)**.
Research package version 1.0.0 uses SionnaRT-Bridge 2.1.0, Blender 5.2.0 LTS and Sionna RT 2.1.0. The dataset DOI is separate from software version identifiers. The authors manage publication of the reserved Zenodo record separately.

This directory is a lightweight mirror of the analysis scripts, notebooks, input catalogue and instructions. The editable Blender project, meshes, raw arrays and full metadata are in the 1.5 GB Zenodo archive. The data are not embedded in this Git repository.

## Reproduce the study

Download and extract the complete Zenodo archive. Run the following commands **from its extracted root**, where `data/`, `studies/`, `software/` and `blender/` are present. The scripts and notebooks mirrored here also exist in that archive; running this mirror alone is insufficient.

```text
python scripts/verify_package.py
python -m pip install -r requirements-analysis.txt
python scripts/analyze_paper.py --output ../reproduced_analysis
```

The analysis environment needs NumPy and Matplotlib, not Blender or Sionna. Install dependencies in a dedicated environment. For notebook 01 use `requirements-notebook.txt`. For notebook 02 use a separate Sionna environment with `requirements-notebook-simulation.txt`, preserving the different tested NumPy version. Simulation is disabled by default in the notebooks.

For new native calculations, run from the extracted archive using the tested Sionna environment:

```text
python scripts/run_study.py foliage_r1 --frames 1,9,10 --output ../new_native_foliage
```

The [simulation guide](documentation/RUNNING_SIMULATIONS.md) covers all studies, clean Blender scene reconstruction and the paired Blender/native benchmark. The [data dictionary](metadata/DATA_DICTIONARY.md) defines units and metrics; the [claim map](metadata/claims.json) connects article findings to archived evidence.

## Evidence and limits

- Five foliage realizations × ten configurations, with original full arrays and frozen scene exports.
- Thirty matched numerical-stability calculations and 24 original paired-route calculations plus three material-alignment checks.
- Fifty original generator-ensemble summaries and reconstructed scenes; all 50 were rerun natively during archive verification, with identical path counts/LoS and maximum summed-gain difference 3.41e-6 dB.
- Forty earlier exploratory sweep records, with clearly identified reconstructed scenes. The ray sweep was nondeterministic.

The [verification summary](verification_summary.json) reports actual checks. Original records and newly generated verification runs remain separate. These results concern the tested setup and do not establish measured-channel accuracy, cross-platform performance or reduced user effort. Radio-map renders demonstrate visualization; the native equivalence study tests propagation paths.

Original data and documentation use CC BY 4.0. Software, node groups and textures retain the component licenses listed in [LICENSE.md](LICENSE.md); the complete third-party notices accompany the Zenodo archive. The repository itself remains GPL-3.0-or-later.
