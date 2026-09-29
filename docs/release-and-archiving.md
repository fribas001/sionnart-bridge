# Release and archiving

Build 2.0.0 with `python scripts/build_extension.py`, run `scripts/check_release.py`, and verify the archive using Blender's extension validator. Run the packaged regression suite on the stated native environment and retain its receipt and archive checksum.

Review the source changes before merging the release branch. Tag the exact release commit and publish the corresponding ZIP/checksum. Preserve existing tags and archives. Archive the new release with matching authors, license, source commit, environment and version; add its assigned DOI to citation metadata only when that record exists. The v1.8.2 DOI is historical and must not be relabeled as 2.0.0.

Before manuscript submission, record the exact software version/commit and experimental settings, include reproducible scene assets where licensed, and distinguish software verification from the new scientific results. Repository CI alone does not replace Blender/Sionna integration testing.
