# SionnaRT-Bridge v1.8.2 release checklist

## Naming and version

- [x] Repository/add-on name is `SionnaRT-Bridge`
- [ ] Final semantic version is `1.8.2` everywhere required
- [x] Blender extension ID is `sionnart_bridge`
- [x] GitHub repository is named `sionnart-bridge`
- [x] SoftwareX metadata targets `v1.8.2`
- [ ] Final Git tag is `v1.8.2`

## Legal, authorship, and attribution

- [x] Full GPL-3.0-or-later license text is present
- [x] Third-party software and citation requirements are documented
- [x] Munich/OpenStreetMap attribution is included
- [ ] Confirm institutional copyright ownership if required
- [ ] Confirm final CRediT roles
- [ ] Add and verify author ORCIDs where applicable
- [ ] Confirm final funding and acknowledgement statements
- [ ] Confirm author names and affiliations in `CITATION.cff`
- [ ] Confirm author names and affiliations in the Zenodo draft

## Documentation

- [x] Repair Markdown formatting and UTF-8 encoding issues encountered during cleanup
- [x] Document installation and external-environment setup
- [x] Add user guide
- [x] Add simulation-parameter reference
- [x] Add practical workflow documentation
- [x] Update examples index
- [x] Update reproducibility guidance
- [x] Update validation methodology
- [x] Update SoftwareX metadata guidance
- [x] Update release and archiving procedure
- [ ] Verify every relative Markdown link
- [ ] Remove unintended release placeholders
- [ ] Ensure README instructions reference assets that exist in the release
- [ ] Ensure example READMEs match the final supported environment
- [ ] Check publication-facing docs for unintended references to old environments or versions

## Reproducibility assets

- [x] Procedural-vegetation Blender example is included
- [x] Munich stacked-height Blender example is included
- [x] Munich example attribution is included
- [x] Stacked-height spacing convention is documented consistently
- [x] Validation methodology is documented
- [ ] Verify example-file checksums that are intended to ship
- [ ] Verify any Geometry Nodes reference assets that are intended to ship
- [ ] Confirm large external assets, if any, have retrieval instructions and checksums
- [ ] Confirm repository documentation does not claim that a standalone raw validation package is included

## Scientific validation and smoke checks

The SoftwareX manuscript contains the scientific validation description. The release repository does not require a separate raw 70-frame validation archive unless one is intentionally added later.

Before release:

- [ ] Re-run at least one representative propagation-path case
- [ ] Confirm returned paths import correctly into Blender
- [ ] Verify external-file-to-Blender attributes for the smoke-test case
- [ ] Verify one procedural-geometry frame sequence or representative sampled frames
- [ ] Run one planar or stacked-height radio-map case if practical
- [ ] Record the exact software environment used for final smoke testing
- [ ] Confirm manuscript-reported validation wording matches `docs/validation.md`

## Performance reporting

Performance measurements are optional unless they are explicitly reported in the final manuscript.

If reported, record:

- [ ] scene preparation time
- [ ] scene export time
- [ ] external-worker startup time
- [ ] Sionna RT scene-loading and solve time
- [ ] result serialization time
- [ ] Blender result-import time
- [ ] total bridge-workflow time
- [ ] hardware, driver, backend, and software versions
- [ ] warm-up count and measured-run count
- [ ] mean, standard deviation, minimum, and maximum where relevant

## Clean-install verification

- [x] Build the extension from the final release candidate
- [x] Verify the built ZIP checksum
- [x] Validate the extension with Blender 5.2
- [x] Install the ZIP in a clean Blender 5.2 profile
- [ ] Configure a clean external Sionna RT runtime using the documented environment
- [x] Run the add-on runtime/environment test successfully
- [x] Open and inspect both distributed `.blend` examples
- [ ] Verify that required example resources are packed or documented
- [ ] Run one propagation-path simulation
- [ ] Run one radio-map simulation if practical
- [ ] Save, close, and reopen an imported result if applicable

## Automated repository checks

- [x] `pytest` passes
- [x] `python scripts/check_release.py` passes
- [x] `git diff --check` reports no errors
- [ ] Repository-specific packaging checks pass
- [x] Working tree is clean after the final release-preparation commit
- [x] CI passes on the final release commit if CI is configured

## Zenodo draft and DOI

Use the manual Zenodo draft workflow described in `docs/release-and-archiving.md`.

- [x] Create a Zenodo software draft for `SionnaRT-Bridge v1.8.2`
- [x] Confirm title, creators, affiliations, license, description, and keywords
- [x] Reserve the version-specific DOI
- [x] Record the reserved DOI in release-preparation notes
- [x] Keep the Zenodo draft unpublished until the GitHub tag and release are final
- [ ] Do not enable a duplicate automatic Zenodo GitHub archive for the same release unless intentionally creating a separate record

## Final version synchronization

After the Zenodo DOI has been reserved, update the release metadata together.

Check at minimum:

- [x] `src/sionnart_bridge/blender_manifest.toml` -> `1.8.2`
- [x] `src/sionnart_bridge/__init__.py` -> `1.8.2`
- [x] `CITATION.cff` -> `1.8.2`
- [x] `README.md` -> `1.8.2` release/install references
- [x] `docs/SIONNA_2_BLENDER_5_2_WINDOWS.md` -> `1.8.2` package references
- [x] `docs/softwarex-metadata.md` -> final release URL/DOI values
- [x] `CHANGELOG.md` -> add/finalize `1.8.2` release entry
- [x] `RELEASE_CHECKLIST.md` -> final target remains `v1.8.2`
- [x] Any version-specific filenames -> `1.8.2`
- [x] Reserved DOI is inserted where appropriate
- [x] Release date is synchronized where applicable

## Release build

- [x] Build `dist/sionnart_bridge-1.8.2.zip`
- [x] Install that exact ZIP in a clean Blender 5.2 profile
- [x] Run final smoke test using that exact ZIP
- [x] Compute SHA-256 for `dist/sionnart_bridge-1.8.2.zip`
- [x] Record the checksum
- [x] Do not rebuild the final ZIP without regenerating the checksum

## Git release

- [x] Create the final release-preparation commit
- [x] Record the final commit hash
- [x] Create annotated tag `v1.8.2`
- [x] Verify the tag points to the intended commit
- [x] Push the final branch
- [x] Push tag `v1.8.2`
- [x] Create GitHub release `SionnaRT-Bridge v1.8.2`
- [x] Attach `sionnart_bridge-1.8.2.zip`
- [x] Attach or publish the SHA-256 checksum
- [ ] Ensure release notes describe the supported environment and important limitations
- [ ] Ensure release notes do not claim unavailable validation artifacts are included

## Zenodo publication

- [x] Upload the final immutable release artifact(s) to the existing Zenodo draft
- [x] Confirm uploaded release ZIP matches the corresponding GitHub release asset
- [x] Confirm the reserved version DOI is unchanged
- [x] Confirm metadata version is `1.8.2`
- [ ] Confirm repository and release links
- [x] Publish the Zenodo record
- [x] Verify that the DOI resolves
- [ ] Verify title, creators, license, version, and files after publication
- [x] Record the final version DOI
- [ ] Record the concept DOI separately if useful

## Manuscript submission

- [ ] Update manuscript code version to `v1.8.2`
- [ ] Add the final GitHub release URL
- [ ] Add the final version-specific DOI
- [ ] Ensure the software/data availability statement matches what is actually archived
- [ ] Ensure validation wording matches the repository scope
- [ ] Ensure software environment matches the tagged release documentation
- [ ] Verify example values directly from retained numerical results where applicable
- [ ] Remove drafting notes and release-candidate wording
- [ ] Finalize funding, acknowledgements, and CRediT roles
- [ ] Confirm SoftwareX template requirements
- [ ] Complete final author review

## Final immutability check

After publication:

- [ ] Do not move or rewrite tag `v1.8.2`
- [ ] Do not replace the published Zenodo `v1.8.2` files with different content
- [ ] Keep the GitHub release asset and checksum unchanged
- [ ] Make future corrections in a new patch release, for example `v1.8.3`
