# Releasing and archiving SionnaRT-Bridge v1.8.2

This document describes the publication-release procedure for the SoftwareX version of SionnaRT-Bridge.

The objective is to keep the following synchronized:

- source code;
- installable Blender extension;
- Git tag;
- GitHub release;
- `CITATION.cff`;
- SoftwareX metadata;
- archival DOI record;
- manuscript.

> **Important:** Do not rewrite or move the final `v1.8.2` tag after publication.

---

## Recommended archive strategy

For the SoftwareX release, use **one** Zenodo software record for `v1.8.2`.

The recommended workflow is to create a **Zenodo draft manually before the final Git tag** and reserve its DOI.

This avoids a circular workflow in which the DOI is only known after the immutable release has already been created.

Do not simultaneously create a manual Zenodo software record and enable automatic Zenodo GitHub archiving for the same release unless you intentionally want two distinct records.

---

## 1. Finish the repository changes

Before reserving the DOI:

1. complete documentation cleanup;
2. update example documentation;
3. confirm the intended SoftwareX environment;
4. resolve stale release metadata;
5. run automated tests;
6. perform the required Blender/Sionna RT smoke tests;
7. confirm the repository working tree is clean.

Do not bump all release-version files until the final release-preparation step.

---

## 2. Prepare the Zenodo draft

Create a new Zenodo upload with resource type:

```text
Software
```

Use the final release title:

```text
SionnaRT-Bridge v1.8.2
```

Populate the draft metadata using the final author, license, description, keywords, repository URL, and related project information.

Keep the record as a **draft** at this stage.

Do not publish it yet.

---

## 3. Reserve the version DOI

In the Zenodo draft, reserve a DOI before publication.

Record the reserved version-specific DOI.

Example placeholder:

```text
10.5281/zenodo.XXXXXXXX
```

The DOI is not registered publicly until the Zenodo record is published, but the reserved identifier can be inserted into release metadata before the final software archive is created.

Do not delete the Zenodo draft after reserving the DOI, because the reservation belongs to that draft.

---

## 4. Perform the final v1.8.2 version bump

Update the release version consistently across the repository.

At minimum check:

```text
src/sionnart_bridge/blender_manifest.toml
src/sionnart_bridge/__init__.py
CITATION.cff
README.md
docs/softwarex-metadata.md
docs/SIONNA_2_BLENDER_5_2_WINDOWS.md
CHANGELOG.md
RELEASE_CHECKLIST.md
```

Use:

```text
1.8.2
```

for package/version fields and:

```text
v1.8.2
```

for Git tag / release references where appropriate.

Add the reserved version DOI to the publication-facing metadata where appropriate.

---

## 5. Update citation metadata

Update `CITATION.cff` so that it contains the final:

- software title;
- version `1.8.2`;
- release date;
- repository URL;
- author information;
- license;
- version DOI if represented by the selected CFF fields.

Validate the CFF file before release.

If `.zenodo.json` is retained, ensure it contains current metadata.

If both `CITATION.cff` and `.zenodo.json` are present and Zenodo GitHub integration is used, Zenodo gives `.zenodo.json` precedence.

For the recommended manual Zenodo-deposit workflow, maintain only metadata files that are useful to repository users and keep them mutually consistent.

---

## 6. Run final software checks

Run the repository tests and release checks.

At minimum:

```powershell
pytest
python scripts/check_release.py
```

Also run any repository-specific packaging checks.

Then perform a Blender 5.2 smoke test using the same installation workflow documented for users.

The smoke test should verify at least:

- extension installation;
- add-on activation;
- external runtime detection;
- runtime test;
- opening a representative example;
- one propagation-path run;
- result import into Blender.

If practical, also test one radio-map workflow.

Scientific validation methodology is documented separately in:

```text
docs/validation.md
```

The release process does not require adding a standalone raw 70-frame validation package when that package is not part of the repository.

---

## 7. Build the installable extension

Build the final extension archive:

```text
dist/sionnart_bridge-1.8.2.zip
```

Confirm that the archive contains the intended extension files and does not contain development-only material that should be excluded.

Install this exact ZIP in a clean Blender 5.2 profile.

Do not rebuild the ZIP after computing its final checksum unless the checksum is regenerated.

---

## 8. Generate release checksums

Generate SHA-256 checksums for the final release assets.

Example:

```powershell
Get-FileHash ".\dist\sionnart_bridge-1.8.2.zip" -Algorithm SHA256
```

Record the checksum in the release notes or a checksum file.

If example `.blend` files or additional archives are distributed separately, compute their checksums as well.

---

## 9. Review the final release candidate

Before tagging, verify:

```powershell
git status
git diff --check
```

The working tree should be clean.

Confirm that no publication-facing file still contains unintended references to:

```text
v1.0.0
v1.8.1
Blender 4.5
Mitsuba 3.5.0
Python 3.11
```

Historical changelog entries and schema-version fields are exceptions when they intentionally describe older releases or external schemas.

---

## 10. Commit the final release metadata

Create the final release-preparation commit.

Example:

```powershell
git add -A
git commit -m "release: prepare v1.8.2"
```

Record the resulting commit hash.

This commit should correspond to the exact source state intended for publication.

---

## 11. Create the annotated Git tag

Create:

```powershell
git tag -a v1.8.2 -m "SionnaRT-Bridge v1.8.2"
```

Verify:

```powershell
git show v1.8.2 --stat
```

Do not move or rewrite this tag after it is published.

---

## 12. Push the branch and tag

Push the final branch:

```powershell
git push origin softwarex-v1.8.2
```

After the branch has been reviewed/merged as appropriate, push the final tag:

```powershell
git push origin v1.8.2
```

Confirm that the tag points to the intended final release commit on GitHub.

---

## 13. Create the GitHub release

Create a GitHub release for:

```text
v1.8.2
```

Recommended title:

```text
SionnaRT-Bridge v1.8.2
```

Attach:

```text
sionnart_bridge-1.8.2.zip
```

and any checksum file prepared for the release.

The release notes should summarize:

- SoftwareX publication release;
- supported Blender/Sionna environment;
- major workflow capabilities;
- documentation additions;
- important limitations;
- archival DOI.

Do not claim that raw validation files are included if they are not actually attached or present in the tagged repository.

---

## 14. Upload the immutable release to the Zenodo draft

Upload the final release artifact(s) to the already-created Zenodo draft.

Recommended minimum archive content:

- final installable ZIP;
- optionally a GitHub-generated source archive or separately generated source snapshot;
- checksum file where useful.

Confirm that the Zenodo metadata identifies:

```text
SionnaRT-Bridge v1.8.2
```

and links back to:

```text
https://github.com/fribas001/sionnart-bridge
```

and the version-specific GitHub release.

---

## 15. Publish the Zenodo record

Only after the GitHub tag and release are final should the prepared Zenodo draft be published.

Publishing registers the previously reserved DOI.

After publication, verify:

- DOI resolves correctly;
- title is correct;
- version is `1.8.2`;
- creators are correct;
- license is correct;
- files match the final release;
- repository/release links are correct.

Record the final version DOI exactly as published.

---

## 16. Synchronize the manuscript

Before SoftwareX submission, verify that the manuscript references:

- SionnaRT-Bridge v1.8.2;
- the final GitHub repository/release;
- the version-specific archival DOI;
- the same software environment documented by the repository.

Do not cite an unpublished placeholder DOI.

---

## 17. Concept DOI and version DOI

Zenodo may expose both:

- a version-specific DOI for the `v1.8.2` record;
- a concept DOI representing the software across versions.

For a manuscript describing a specific immutable software version, prefer the **version-specific DOI**.

The repository may additionally provide the concept DOI for users who want to cite the evolving software project.

---

## 18. After publication

Preserve:

- the `v1.8.2` Git tag;
- the GitHub release assets;
- the Zenodo v1.8.2 record;
- the release checksum;
- the commit referenced by the paper.

Future corrections should normally be made in a new patch release rather than by rewriting `v1.8.2`.

Example:

```text
v1.8.3
```

---

## Release completion checklist

- [ ] Documentation finalized
- [ ] SoftwareX metadata finalized
- [ ] Zenodo draft created
- [ ] Version DOI reserved
- [ ] Final `1.8.2` version bump completed
- [ ] `CITATION.cff` finalized
- [ ] Automated tests pass
- [ ] Release check passes
- [ ] Blender 5.2 smoke test passes
- [ ] Final extension ZIP built
- [ ] SHA-256 checksum recorded
- [ ] Working tree clean
- [ ] Final release commit created
- [ ] `v1.8.2` annotated tag created
- [ ] Branch/tag pushed
- [ ] GitHub release published
- [ ] Final artifacts uploaded to Zenodo draft
- [ ] Zenodo record published
- [ ] DOI resolves
- [ ] Manuscript references synchronized
