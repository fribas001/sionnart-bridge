# Geometry Nodes CSV Schema v2

The generated `paths_frame_####.csv` contains one numeric row for every TX
endpoint, interaction point, and RX endpoint. Coordinates use evaluated
Blender/Sionna world space in meters.

## Blender position limitation

Blender 5.2 Import CSV supports only scalar integer and float columns and
initializes native point positions to zero. It cannot parse a vector-valued CSV
column into the built-in `position` field.

Coordinates are therefore stored as three scalar attributes:

- `x`
- `y`
- `z`

Use Named Attribute ×3 → Combine XYZ → Set Position.

## Animation

- `frame`: Blender frame number used to evaluate TX/RX positions.
- File naming: `paths_frame_0001.csv`, `paths_frame_0002.csv`, etc.
- Pattern: `paths_frame_{:04}.csv` for Blender's Format String node.

## Point roles

- `point_role_id = 1`: TX
- `point_role_id = 2`: interaction
- `point_role_id = 3`: RX

## Interaction categories

- `interaction_type_id = 0`: endpoint / no event
- `interaction_type_id = 1`: reserved for LoS categorization
- `interaction_type_id = 2`: specular reflection
- `interaction_type_id = 3`: diffuse reflection
- `interaction_type_id = 4`: refraction
- `interaction_type_id = 5`: diffraction
- `interaction_type_id = 6`: mixed Sionna bit mask

`interaction_id` preserves Sionna's native bit flags: specular `1`, diffuse `2`,
refraction `4`, and diffraction `8`.

## Path grouping

Use `path_uid_num` to identify a path and `point_order` to identify its ordered
points. Each animation frame is a separate CSV, and `frame` is also included as
an attribute.


## v0.6.0 frame-evaluated simulation columns

`frequency_ghz`, `frequency_hz`, `max_depth`, `max_num_paths_per_src`, `samples_per_src`, `seed`, `los_enabled`, `specular_reflection_enabled`, `diffuse_reflection_enabled`, `refraction_enabled`, `diffraction_enabled`, `edge_diffraction_enabled`, and `diffraction_lit_region_enabled` are sampled per frame and repeated on every path-point row for that frame.


## 2D radio-map surface modes (v0.18.3)

`radio_map_all_frames.csv` contains every sampled 2D radio-map frame. Filter
with the integer `frame` attribute in Geometry Nodes.

### Planar Grid

Planar points are located at Sionna's cell centers on the configured horizontal
XY plane. The generated carrier has identity transforms. Planar rows contain:

- `is_projected = 0`
- `primitive_index = -1`
- `normal_x = 0`, `normal_y = 0`, `normal_z = 1`
- `cell_area = cell_size_x * cell_size_y`

### Projected Mesh

The selected Blender mesh is evaluated with modifiers, triangulated, transformed
to world space, and supplied to Sionna as a mesh measurement surface. Every
non-degenerate triangle is one radio-map cell. Projected rows contain:

| Attribute | Type | Meaning |
|---|---|---|
| `is_projected` | Integer | Always `1` for projected mesh rows. |
| `primitive_index` | Integer | Zero-based triangle index in the exported measurement surface. |
| `x`, `y`, `z` | Float | Sionna cell center in world coordinates. |
| `normal_x`, `normal_y`, `normal_z` | Float | World-space triangle unit normal. |
| `surface_normal` | Vector | Blender-only vector attribute assembled from the three normal columns. |
| `cell_area` | Float | Triangle area in square meters. |
| `path_gain` | Float | Unitless path gain in linear scale; often too small for fixed-decimal spreadsheet display. |
| `path_gain_db` | Float | Path gain in dB; recommended for color mapping. |
| `metric_linear` | Float | Generic alias of the active linear metric. |
| `metric_db` | Float | Generic dB/dBm alias of the active metric. |
| `metric_norm` | Float | Per-frame valid dB range mapped to `[0, 1]`. |
| `coverage_valid` | Integer | `1` when Sionna reports coverage, otherwise `0`. |
| `associated_tx` | Integer | Serving transmitter index, or `-1` when invalid. |

Projected Path Gain uses
`Sionna_radio_map_projected_pathgain_node`. The node group consumes the embedded
Geometry input and does not require an Object socket. The selected Reference
Mesh is used only during the Sionna solve. The generated object prefix is
`Sionna_CoverageMap_Projected_PathGain_…`.

The per-frame and combined result JSON files retain the reference-mesh name,
measurement-surface hash, triangle count, and full solver configuration.

## Radio-map transmitter association (v0.18.1)

2D and 3D radio-map point data include:

| Attribute | Type | Meaning |
|---|---|---|
| `associated_tx` | Integer | Zero-based index of the transmitter providing the highest selected map metric. `-1` means invalid/unassociated. |

The index uses Sionna RT's `tx_association(metric)` result, where `metric` is
the selected `path_gain`, `rss`, or `sinr` map metric. The Blender result object
stores a JSON custom property named `sionna_tx_index_map` that maps each index
to the transmitter name.

## 3D coverage-map mode routing

Stacked-height 3D coverage maps are assigned automatically to the Geometry
Nodes group matching the selected metric:

- Path Gain: `Sionna_radio_map_3d_pathgain_node`, using `path_gain` and `path_gain_db`
- RSS: `Sionna_radio_map_3d_rss_node`, using `rss` and `rss_dbm`
- SINR: `Sionna_radio_map_3d_sinr_node`, using `sinr` and `sinr_db`

The generated object is named with a `Sionna_CoverageMap3D_<Mode>_…` prefix and
contains only the selected metric pair, in addition to position, frame, voxel
size, and `associated_tx`.


## Mobility and Doppler columns 

Propagation-path CSV rows and embedded Blender point attributes also include:

| Column / attribute | Unit | Description |
| --- | --- | --- |
| `doppler_hz` | Hz | Signed Sionna Doppler shift of the propagation path |
| `doppler_abs_hz` | Hz | Absolute path Doppler shift |
| `tx_velocity_x/y/z` | m/s | Animated transmitter world-space velocity |
| `rx_velocity_x/y/z` | m/s | Animated receiver world-space velocity |
| `relative_velocity_x/y/z` | m/s | Receiver velocity minus transmitter velocity |
| `tx_speed_m_s` | m/s | Transmitter speed |
| `rx_speed_m_s` | m/s | Receiver speed |
| `relative_speed_m_s` | m/s | Magnitude of the relative velocity vector |

Blender additionally combines the scalar components into `tx_velocity`,
`rx_velocity`, and `relative_velocity` POINT-domain vector attributes.
