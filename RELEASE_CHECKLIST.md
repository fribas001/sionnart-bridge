# SionnaRT-Bridge v1.0.0 release checklist

## Naming and version

- [x] Repository/add-on name is `SionnaRT-Bridge`
- [x] Semantic version is `1.0.0`
- [x] Blender extension ID is `sionnart_bridge`
- [x] GitHub repository is named `sionnart-bridge`
- [x] SoftwareX manuscript C1 identifies v1.0.0

## Legal, authorship, and attribution

- [x] Full GPL-3.0-or-later license text is present
- [x] Third-party software and citation requirements are documented
- [x] Munich/OpenStreetMap attribution is included
- [ ] Confirm institutional copyright ownership
- [ ] Confirm final CRediT roles
- [ ] Add and verify author ORCIDs
- [ ] Confirm final funding and acknowledgement statements
- [ ] Publish and archive Mitsuba-Blender 4.5 Compatibility v0.4.8
- [ ] Record the compatibility component DOI and SHA-256

## Documentation

- [x] Repair Markdown formatting and UTF-8 encoding
- [x] Document installation and external-environment setup
- [x] Document Geometry Nodes assets and append procedure
- [x] Update the examples index
- [x] Update the reproducibility-package description
- [x] Update the validation and performance protocol
- [ ] Verify every relative Markdown link
- [ ] Remove all remaining release placeholders
- [ ] Ensure README instructions reference assets that exist in the release

## Reproducibility assets

- [x] Add Geometry Nodes reference library
- [x] Add Geometry Nodes SHA-256 checksum
- [x] Add procedural-vegetation Blender example
- [x] Add procedural-vegetation checksums
- [x] Add Munich stacked-height Blender example
- [x] Add Munich example checksum and attribution
- [x] Reconcile the stacked-height spacing convention
- [ ] Add direct Sionna RT reference scripts or documented reference commands
- [ ] Add compact machine-readable validation results
- [ ] Add validation environment metadata
- [ ] Add validation-artifact SHA-256 checksums

## Scientific validation

- [ ] Run propagation-path numerical-equivalence tests
- [ ] Run planar radio-map numerical-equivalence tests
- [ ] Run projected-map numerical-equivalence tests
- [ ] Run stacked-height numerical-equivalence tests
- [ ] Run coordinate-transfer tests
- [ ] Verify external-file-to-Blender attribute agreement
- [ ] Record all tolerances and pass/fail results
- [ ] Add the final validation summary to the SoftwareX manuscript

## Performance measurements

- [ ] Record evaluated-scene preparation time
- [ ] Record scene-export time
- [ ] Record external-worker startup time
- [ ] Record Sionna RT scene-loading and solve times
- [ ] Record serialization and Blender-import times
- [ ] Record total bridge-workflow time
- [ ] Record hardware, driver, backend, and software versions
- [ ] Report repetitions, warm-up runs, mean, standard deviation, minimum, and maximum

## Clean-install verification

- [ ] Build the extension from the release commit
- [ ] Verify the built ZIP checksum
- [ ] Validate the extension with Blender 4.5 LTS
- [ ] Install the ZIP in a clean Blender profile
- [ ] Configure a clean Python 3.11 external environment
- [ ] Run Test Environment successfully
- [ ] Open and inspect both distributed `.blend` examples
- [ ] Verify that all example resources are packed or documented
- [ ] Run one propagation-path simulation
- [ ] Run one radio-map simulation
- [ ] Save, close, and reopen an imported result

## Release and archiving

- [ ] CI passes on the final release commit
- [ ] All repository checks and tests pass
- [ ] Replace the changelog `Unreleased` marker with the release date
- [ ] Create annotated tag `v1.0.0`
- [ ] Create GitHub release
- [ ] Attach `sionnart_bridge-1.0.0.zip`
- [ ] Attach ZIP checksum
- [ ] Attach or reference the Geometry Nodes library and checksum
- [ ] Attach or reference the validation package
- [ ] Archive the release in Zenodo
- [ ] Add the version DOI to `CITATION.cff`
- [ ] Add the version DOI to the README
- [ ] Add the version DOI to the SoftwareX manuscript
- [ ] Verify that all release and DOI links resolve

## Manuscript submission

- [ ] Fill all numerical values in the validation table
- [ ] Fill all hardware and environment placeholders
- [ ] Verify example values directly from retained numerical results
- [ ] Remove “release candidate” and drafting notes
- [ ] Finalize funding, acknowledgements, and CRediT roles
- [ ] Confirm manuscript word count and SoftwareX template compliance
- [ ] Ensure the availability statement matches the archived release
- [ ] Complete the final author review
