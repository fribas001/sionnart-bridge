# SionnaRT-Bridge

**SionnaRT-Bridge** is a Blender 4.5 LTS add-on for configuring, executing,
and analyzing Sionna RT radio-propagation simulations. Blender is used for
scene authoring, procedural geometry, device placement, animation, and
visualization. Numerical computations run in a separate Python environment
with Sionna RT.

This repository is the publication-facing source tree for **version 1.0.0**.
The installable Blender extension is built from `src/sionnart\_bridge/`.

## Main capabilities

* Propagation-path simulations with attributed path geometry
* Planar and projected-mesh radio maps
* Stacked-height radio maps
* Blender timeline and procedural-geometry parameter sweeps
* Transmitter and receiver array/orientation configuration
* Radio-material configuration
* Scene caching, external worker monitoring, and retained numerical outputs
* Path, coverage, mobility, and Doppler analytics

## Requirements

* Blender 4.5 LTS
* Python 3.11 for the external simulation environment
* Sionna RT 2.0.1
* Mitsuba-Blender 4.5 Compatibility v0.4.8
* CPU backend supported by Mitsuba/Dr.Jit, or a supported GPU backend

The exact tested dependency is maintained separately as **Mitsuba-Blender 4.5
Compatibility v0.4.8** in the repository
`fribas001/mitsuba-blender-4.5-compatibility`. Install its archived release and
verify its SHA-256 before installing SionnaRT-Bridge.

## Installation

1. Download `sionnart\_bridge-1.0.0.zip` from the GitHub release assets.
2. In Blender, open **Edit → Preferences → Get Extensions → Install from Disk**
and select the downloaded ZIP file.
3. Create a Python 3.11 virtual environment for Sionna RT and install the
external dependency:

```bash
   python3.11 -m venv .venv-sionna
   source .venv-sionna/bin/activate   # Windows: .venv-sionna\\Scripts\\activate
   python -m pip install --upgrade pip
   python -m pip install -r requirements-external.txt
   ```

4. In Blender, open the **Sionna RT** sidebar, set the external Python
executable and workspace, and run **Test Environment**.

See [docs/installation.md](docs/installation.md) for the complete procedure.

## Quick start

1. Use **Create / Repair Env** to create the controlled `sionna\_env` hierarchy.
2. Place simulation geometry under `sionna\_env/scene`.
3. Assign radio materials and create or mark transmitter and receiver objects.
4. Configure the external environment, antenna arrays, solver settings, and
desired output type.
5. Run the simulation and inspect the imported attributed geometry.

Detailed attribute definitions are in [docs/output-schemas](docs/output-schemas/).

## Build the Blender extension

Using Blender 4.5 LTS:

```bash
blender --command extension validate --source-dir src/sionnart\_bridge
blender --command extension build \\
  --source-dir src/sionnart\_bridge \\
  --output-dir dist
```

A Python-only deterministic build helper is also provided:

```bash
python scripts/build\_extension.py
```

The expected release asset is `dist/sionnart\_bridge-1.0.0.zip`.

## Tests

The repository includes source/metadata tests that can run without Blender:

```bash
python -m pip install -r requirements-dev.txt
pytest
python scripts/check\_release.py
```

Full scientific validation requires Blender 4.5 LTS, the exact Mitsuba export
component, and Sionna RT. The validation protocol is described in
[docs/validation.md](docs/validation.md).

## Reproducibility and examples

Publication example scenes, configurations, expected numerical outputs, and
hardware/runtime metadata must be placed under `examples/` before the archival
v1.0.0 release. See [examples/README.md](examples/README.md) and
[docs/reproducibility.md](docs/reproducibility.md).

## Documentation

* [Installation](docs/installation.md)
* [Reproducibility](docs/reproducibility.md)
* [Validation protocol](docs/validation.md)
* [Antenna naming](docs/antenna-naming.md)
* [Radio materials](docs/radio-materials.md)
* [Output schemas](docs/output-schemas/)
* [Release and Zenodo archiving](docs/release-and-archiving.md)

## Citation

Citation metadata are provided in [`CITATION.cff`](CITATION.cff). After the
v1.0.0 GitHub release is archived in Zenodo, add the version DOI to both
`CITATION.cff` and the SoftwareX manuscript.

## License

SionnaRT-Bridge is distributed under the GNU General Public License,
version 3 or later (`GPL-3.0-or-later`). See [LICENSE](LICENSE).

Sionna RT and Mitsuba are separate dependencies distributed under their own
licenses. Mitsuba-Blender 4.5 Compatibility is a separate BSD-3-Clause downstream
component with its own provenance, release archive, and citation metadata.

## Support

Use the GitHub issue tracker for reproducible bug reports and feature requests.
For publication-related questions, contact Felipe Oliveira Ribas at
`felipe.oliveiraribas@ugent.be`.

