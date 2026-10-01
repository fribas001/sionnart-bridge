# Release and archiving

Build 2.1.0 with `python scripts/build_extension.py`, run `scripts/check_release.py`, and verify the archive using Blender's extension validator. Run the packaged regression suite on the stated native environment and retain its receipt and archive checksum.

Review the source changes before merging the release branch. Tag the exact release commit and publish the corresponding ZIP/checksum. Preserve existing tags and archives. Archive the new release with matching authors, license, source commit, environment and version; add its assigned DOI to citation metadata only when that record exists. The v1.8.2 DOI is historical and must not be relabeled as 2.1.0.

Before manuscript submission, record the exact software version/commit and experimental settings, include reproducible scene assets where licensed, and distinguish software verification from the new scientific results. Repository CI alone does not replace Blender/Sionna integration testing.

The vegetation reproducibility archive is identified by DOI [10.5281/zenodo.23081848](https://doi.org/10.5281/zenodo.23081848). It includes the tested extension archive with SHA-256 `15149afdfdb899f2a2df3bb54ccd0c4fd961080c94e340cab1b1322d235043f4`. A deterministic repository build may use different ZIP timestamps/compression: compare the extracted files to establish source identity. Preserve the archive ZIP as the original tested distribution. The research archive DOI should be cited as a dataset, not mislabeled as a standalone software-only record.
