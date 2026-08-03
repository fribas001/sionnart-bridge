# Changelog

All notable changes to SionnaRT-Bridge are documented here.

The project uses semantic versioning for publication releases.

## [1.0.0] - Unreleased

First publication-facing release under the name **SionnaRT-Bridge**.

### Added

- Blender 4.5 LTS extension manifest and reproducible build process
- External Sionna RT worker architecture
- Propagation-path, planar-map, projected-map, and stacked-height-map workflows
- Attributed Geometry Nodes result representations
- Procedural frame sweeps, scene caching, status reporting, and analytics
- TX/RX antenna arrays, orientations, mobility, and Doppler attributes
- Versioned Geometry Nodes reference library and SHA-256 checksum
- Procedural-vegetation Blender example, preview image, and checksums
- Munich stacked-height Blender example, attribution, and checksum
- Reproducibility and validation protocols
- Versioned repository documentation, citation metadata, tests, and CI
- SoftwareX-oriented release and clean-install checklist

### Changed

- Standardized the product name to `SionnaRT-Bridge`
- Reset the public release version from the development sequence `0.18.8` to
  the semantic publication version `1.0.0`
- Standardized the stacked-height convention around the requested
  `cell_size_z` spacing
- Updated the reproducibility package to use two canonical Blender examples
  and a separate machine-readable validation package

### Release blockers

- Publish and archive Mitsuba-Blender 4.5 Compatibility v0.4.8 and record its
  DOI and SHA-256 checksum
- Add direct Sionna RT reference scripts or documented reference commands
- Add compact native-versus-bridge numerical validation results, environment
  metadata, and validation-artifact checksums
- Add performance measurements, hardware metadata, and clean-install
  verification results
- Confirm institutional copyright ownership, final CRediT roles, author
  ORCIDs, funding, and acknowledgements
- Create the final GitHub and Zenodo releases and replace the `Unreleased`
  marker with the release date and version DOI
