# Verification: SionnaRT-Bridge 2.1.0

Tested on 30 September 2026 with Blender 5.2.0 LTS (`fbe6228777e7`), Windows 11, NVIDIA RTX 4070 Ti SUPER (16 GB, driver 591.86), CUDA polarized backend, Python 3.13.13, Sionna RT 2.1.0, Mitsuba 3.9.1, Dr.Jit 1.5.0, NumPy 2.5.2 and h5py 3.16.0. Optional sensing plots use Matplotlib 3.11.1.

## Coverage

| Area | Verification |
| --- | --- |
| Pure functions | 52 Python tests: metadata serialization, identity checks, statistics, material models, vegetation geometry, worker services, empty-channel values, exit-code preservation and planar rotation contracts |
| Offline report | JavaScript syntax and statistics checks, CSV escaping, link identity and changing-vegetation selector |
| Blender registration and panels | Register/unregister/re-register, all four simulation modes, property/operator references and bundled node groups |
| Evaluated scene data | Animated/driver/nested/disabled Geometry Nodes, material assignment through nodes, instances, nonuniform/mirrored scale, frame restoration and export scope |
| Vegetation | Known-area leaves and wood box, explicit IDs, object and scene totals, two different RX corridors, export and HDF5 round trips |
| Native materials | Three frequencies, paths/2D/3D workers, actual solver dielectric/thickness values and analytical normal-incidence slab comparison (absolute gain error below 0.001 dB) |
| Public run/import cycle | Paths + 2D + 3D HDF5 batch; CSV and embedded-only modes; multiple TX/RX; multi-element arrays; all planar/stacked map metrics; projected mesh cells |
| Oriented 2D maps | Native XY/XZ/YZ/custom Sionna maps; vertical RSS/SINR; independently sized rectangular cells; world centers and normals; evaluated Geometry Nodes tile corners and dimensions; CSV/HDF5 orientation and local/world coordinates; AUTO selection of keyframed custom rotation; save/reopen; in-plane TX centering |
| Analysis persistence | Channel summaries before visualization limits, parameter/reference imports, reports, dashboards and Blender save/reopen |
| Motion | Grid and PointCloud trajectories, animated Doppler, first live RX movement, automatic result replacement while retaining manual results |
| Interactions/runtime | Reflection/refraction material checks; Lambertian/directive/backscattering with diffuse and diffraction options enabled; both external Python and Blender Python worker execution |
| Valid empty result | Zero paths remain a completed observation with missing gain/delay and a usable parameter report |
| Optional curves | Curve import retains embedded results and parameter analysis |
| Lifecycle | Stop operator, queued-output cancellation, run-lock cleanup, disabling while running and file-load cancellation hook |
| Failure behavior | All three workers exit 1 with failed receipts for invalid configurations; failed batch component stays visible after successful queued output; diagnostic files retained |
| Optional sensing | Self-contained two-frame skinned rig, explicit human proxy, pose labels, CIR/CSI exports and plots, file checksums and camera overlay |

The packaged code is tested again after extraction. Release evidence identifies the archive hash and test commands. Successful native runs must exit 0; output existence alone is insufficient. Failure fixtures deliberately produce error messages and must exit nonzero.

## Reproduce

The tests use generated analytical fixtures and do not require private scene assets. Supply Blender, a Python environment containing the pinned Sionna stack, Node.js, and an output folder to `tests/run_release_checks.py`. Run that script with a normal Python interpreter. It runs the dependent fixture/export/import checks in order and writes a JSON receipt plus individual logs. The script does not change Blender preferences or enable the add-on in the user's regular installation.

## Limits

These tests verify defined software workflows and numerical/data-transfer contracts. They are not exhaustive for every setting combination, scene size or third-party Geometry Nodes system. Windows/CUDA was exercised; CPU-only, Linux and macOS operation were not. Panel references and evaluated result geometry were checked in background Blender; interactive viewport appearance and long-duration user sessions were not manually inspected.

Small analytic fixtures do not establish electromagnetic accuracy for a real canopy, biological correctness of leaf counts, numerical convergence at a chosen scene budget or uncertainty across plant realizations. Those remain experiment-specific checks.

Blender emitted a thumbnail-cache warning during background save operations. Saved `.blend` files reopened correctly; no preference files were changed.

## Vegetation archive checks

The [reproducibility verification summary](../reproducibility/vegetation/verification_summary.json) covers 50 original foliage arrays, the 30 matched numerical calculations, native-route evidence, fresh reruns of all 50 reconstructed generator states, and a complete packaged-model export/worker/import check. This evidence is distinct from small software regression fixtures. Notebook code cells were checked sequentially in Python; a separate Jupyter front-end was not launched.
