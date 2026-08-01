# Lean 3D radio-map point attributes

A 3D coverage map is sampled as stacked horizontal radio-map layers. Every
voxel becomes one point in the generated loose-vertex mesh and receives the
following point-domain attributes.

## Always stored

- `frame`
- `x`, `y`, `z`
- `cell_size_x`, `cell_size_y`, `cell_size_z`
- `associated_tx`

`associated_tx` is the zero-based transmitter index providing the highest
selected metric at that voxel. `-1` marks an invalid or unassociated voxel.
Each horizontal layer is associated independently.

## Mode-specific data

Exactly one metric pair is stored per run and embedded on the Blender mesh:

| Mode | Linear attribute | Logarithmic attribute | Unit | Geometry Nodes group |
|---|---|---|---|---|
| Path Gain | `path_gain` | `path_gain_db` | dB | `Sionna_radio_map_3d_pathgain_node` |
| RSS | `rss` | `rss_dbm` | dBm | `Sionna_radio_map_3d_rss_node` |
| SINR | `sinr` | `sinr_db` | dB | `Sionna_radio_map_3d_sinr_node` |

Generated mesh names use the corresponding prefixes:

- `Sionna_CoverageMap3D_PathGain_…`
- `Sionna_CoverageMap3D_RSS_…`
- `Sionna_CoverageMap3D_SINR_…`

The result object also records the active metric, unit, attribute names, and
Geometry Nodes group in custom properties. NPZ files retain the generic
`values`/`values_db` arrays for compatibility and additionally expose the
mode-specific array keys listed above.

Run settings such as frequency, seed, depth, enabled mechanisms, transmitter
powers, bandwidth, and temperature remain in object/run metadata rather than
being duplicated on every voxel.
