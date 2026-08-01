# Releasing and archiving v1.0.0

1. Complete all items in `RELEASE_CHECKLIST.md`.
2. Ensure the repository default branch is public and has the final name
   `fribas001/sionnart-bridge`.
3. Run `pytest`, `python scripts/check_release.py`, and the full Blender/Sionna
   validation protocol.
4. Build `dist/sionnart_bridge-1.0.0.zip` and install it in a clean Blender 4.5
   profile.
5. Commit the final version, create the annotated tag `v1.0.0`, and push it.
6. Create a GitHub release titled `SionnaRT-Bridge v1.0.0` and attach the
   installable ZIP, checksums, validation results, and example manifest.
7. Connect the GitHub repository to Zenodo before or immediately after the
   release and archive tag `v1.0.0`.
8. Add the version-specific Zenodo DOI to `CITATION.cff`, the README, and the
   SoftwareX code-metadata table. Use the version DOI in the paper; the concept
   DOI may also be listed in the repository.
9. Preserve the exact accepted commit and release asset without rewriting the
   tag.
