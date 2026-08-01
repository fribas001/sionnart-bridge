# Projected Mesh Radio Map Schema — v0.18.6

Projected 2D radio maps use a Blender mesh as Sionna RT's measurement surface.
The bridge evaluates the selected object, applies its modifiers and world
transform, triangulates it, and exports a temporary PLY. One non-degenerate
triangle becomes one Sionna `MeshRadioMap` cell.

The worker accepts both NumPy layouts returned by Mitsuba/Dr.Jit for cell centers: `[cells_count, 3]` and the coordinate-first `[3, cells_count]`, normalizing both to `[cells_count, 3]` before CSV generation.

## User interface

1. Enable **Radio Map**.
2. Set **Map Surface** to **Projected Mesh**.
3. Select a mesh in **Reference Mesh**.
4. Use **Path Gain** as the metric.
5. Ensure `Sionna_radio_map_projected_pathgain_node` exists. Only its normal
   Geometry input is required; no Object socket is needed.

## Point attributes

| Name | Blender type | Description |
|---|---|---|
| Position | Built-in vector | Sionna cell center in world coordinates. |
| `x`, `y`, `z` | Float | Scalar copies of Position. |
| `surface_normal` | Float Vector | World-space unit normal of the source triangle. |
| `normal_x`, `normal_y`, `normal_z` | Float | Scalar normal components. |
| `surface_tangent` | Float Vector | Unit tangent from triangle vertex 0 toward vertex 1. |
| `surface_bitangent` | Float Vector | Unit in-plane vector perpendicular to the tangent. |
| `triangle_v0`, `triangle_v1`, `triangle_v2` | Float Vector | Exact world-space triangle corners, available for procedural triangle reconstruction. |
| `edge_length_01`, `edge_length_12`, `edge_length_20` | Float | Triangle edge lengths in meters. |
| `cell_index` | Integer | Sequential point/cell index in the returned map. |
| `primitive_index` | Integer | Triangle index in the exported measurement surface. |
| `cell_area` | Float | Triangle area in m². |
| `is_projected` | Integer | `1` for this mode. |
| `path_gain` | Float | Unitless linear path gain. Values are often very small and may display as `0.000` in Blender. |
| `path_gain_db` | Float | Path gain in dB; recommended for visualization. |
| `metric_linear` | Float | Generic alias of the selected linear metric. |
| `metric_db` | Float | Generic dB/dBm alias; equals `path_gain_db` in this mode. |
| `metric_norm` | Float | Valid per-frame dB range normalized to `[0, 1]`. |
| `coverage_valid` | Integer | `1` for a covered cell, otherwise `0`. |
| `associated_tx` | Integer | Serving TX index; `-1` means invalid. |
| `tx_count` | Integer | Number of transmitters represented by the projected map. |
| `path_gain_tx_000`, `path_gain_db_tx_000`, … | Float | Per-transmitter linear and dB path gain. The three-digit suffix is the zero-based TX index. |
| `frame` | Integer | Evaluated Blender frame. |
| `radius` | Float | Display radius configured in the add-on. |

The object also stores custom properties identifying the reference mesh,
Geometry Nodes group, measurement-surface triangle count, metric attribute
names, the transmitter-index map, and the list of per-transmitter metric
attributes.

## Geometry Nodes contract

The generated point object receives the
`Sionna_radio_map_projected_pathgain_node` modifier. The point geometry is
self-contained: its built-in Position is the Sionna `MeshRadioMap.cell_centers`
world-space position and `surface_normal` stores the corresponding triangle
normal. The Reference Mesh is a simulation input only and is not assigned to the
modifier. Geometry Nodes should read `path_gain_db` or `metric_db` for color
mapping and can use `metric_norm` directly for a `[0, 1]` display value. The
data block is stored as a loose-vertex mesh for compatibility across Blender
4.5 builds; the add-on injects a **Mesh to Points** helper so the node tree
receives a native point-cloud component.

## Resolution and animation

Triangle size determines map resolution. Subdivide or remesh the reference
object before simulation to increase resolution. In frame-range runs, the
reference mesh is re-evaluated and re-exported per frame, so animated transforms,
shape keys, modifiers, and Geometry Nodes output are reflected in the map.
Degenerate triangles are skipped.
