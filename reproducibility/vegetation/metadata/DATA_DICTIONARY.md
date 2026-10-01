# Data dictionary

All JSON and CSV files use UTF-8. Decimal separators are periods; JSON null means unavailable, not zero. Coordinates are Blender world coordinates interpreted in metres by the exporter. XML/PLY are open scene/mesh formats; NPZ is a NumPy container loaded with `allow_pickle=False`.

| Field | Meaning / unit |
|---|---|
| `study`, `run_id`, `frame` | Experiment identity, original run token, discrete configuration index |
| `geometry_seed` / `controls.Seed` | Integer seed used by the vegetation generator |
| `simulation.seed` | Sionna path-solver seed; a separate source of numerical randomness |
| `controls.Leaf Density` | Dimensionless generator input, not physical vegetation density |
| `controls.Add Leaves` | Whether the generator includes leaves |
| `leaf_component_count` | Connected leaf-mesh components; not independently measured biological leaves |
| `leaf_area_estimate_m2` | Mesh-derived leaf area, mÂ², using recorded area convention |
| `wood_surface_area_m2` | Mesh-derived woody surface area, mÂ² |
| `corridor_leaf_area_density_m_inv` | Leaf area inside the recorded square TXâ€“RX corridor / corridor volume, mÂ²/mÂ³; corridor width 1 m |
| `frequency_hz`, `bandwidth_hz`, `temperature_k` | Hz, Hz, K |
| device `position`, `look_at_target_position` | Cartesian metres |
| array `vertical_spacing`, `horizontal_spacing` | Fractions of wavelength |
| `samples_per_src`, `max_num_paths_per_src`, `max_depth` | Ray budget, candidate capacity, maximum path-interaction depth |
| `materials` | Exact recorded dielectric and surface-interaction inputs; conductivity S/m; dimensions m |
| `path_count`, `los_available` | Number of valid computed paths, direct-path presence |
| `total_power_db` | 10 log10(sum |a_p|Â²) over valid paths, first antenna pair; called summed path gain in the article |
| `strongest_path_gain_db` | 10 log10(max |a_p|Â²), first antenna pair |
| delay fields ending `_ns` | Nanoseconds |
| `rms_delay_spread_ns` | Power-weighted standard deviation of valid-path delays |
| `geometry_status`, `raw_array_status` | Whether a scene is original or reconstructed and whether the original full arrays were retained |
| `original_scene_sha256`, `portable_scene_sha256` | Original recorded XML hash and hash after rebasing file paths |

NPZ array shapes and names are recorded with each result; they include valid masks, complex coefficients represented by real/imaginary components, delays, vertices and interactions. Consult `run_vegetation.py:first_pair` and `summarize` for explicit antenna-axis selection. Interaction codes follow the tested Sionna RT version; a path may contain multiple interaction types. TX power (44 dBm) is recorded but is not added to path gain in dB.

`displayed_path_points.csv` is a spatial display export, potentially filtered to strongest paths. It is not the full raw channel. `source_metadata.json` preserves the original export, including historical file paths and background-object records; `configurations.json` identifies the intended tree and the portable scene references used by the rerun scripts.

In new verification records, `ARCHIVE_ROOT` denotes the extracted archive directory and replaces the original local machine prefix. These fields are provenance records. Use `data/<study>/native_configs/` or the provided launchers for runnable configurations.
