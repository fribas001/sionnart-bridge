# Upgrade to 2.0.0

The extension identifier stays `sionnart_bridge`. Restart Blender after replacing an enabled older extension. Preserve a copy of project files. Existing scene settings retain their saved values; new scenes refresh static geometry by default. New vegetation measurements require new runs. Earlier saved parameter reports remain supported.

RIS and crowd integrations are excluded; ordinary geometry and result objects in older projects are not deleted. See [changes](CHANGELOG.md) and [the current guide](src/sionnart_bridge/README.md).

---

# Migration notes from the development ZIP

Source archive SHA-256: `1309a93f92bc1757b63b0cb8817d050e4432abe50ce2a71dcda70983517630c4`

The uploaded development archive contained 12 top-level files: four Python
modules, five Markdown documents, a Blender manifest, a short license notice,
and a README. It compiled successfully with Python syntax checks, but did not
contain automated tests, CI, reproducible example scenes, citation metadata,
a full GPL license text, or an archival release workflow.

This repository scaffold preserves the four runtime Python modules while:

- standardizing the public name to `SionnaRT-Bridge`;
- introducing semantic versioning for publication releases;
- correcting the Blender manifest maintainer, website, package ID, permission
  text, and build paths;
- replacing the short license notice with the full GPL-3.0 text;
- separating user documentation, schemas, tests, examples, and release tools;
- adding CITATION.cff, GitHub CI, issue templates, and a release checklist.

No scientific solver result was generated or validated during this repository
migration. This statement describes the migration step only; subsequent
validation and release preparation are documented separately.
