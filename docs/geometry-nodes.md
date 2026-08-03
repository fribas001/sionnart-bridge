# Geometry Nodes reference library

SionnaRT-Bridge imports Sionna RT simulation results as attributed Blender
geometry. Visualization is performed with user-editable Geometry Nodes groups.

The reference library is available at:

`assets/blender/sionnart_geometry_nodes_1.0.0.blend`

The groups must retain their exact Blender datablock names.

## Included node groups

| Node group | Purpose |
|---|---|
| `Sionna_Paths` | Visualizes radio-propagation paths and their interactions. |
| `Sionna_radio_map_pathgain_node` | Visualizes planar Path Gain radio maps. |
| `Sionna_radio_map_rss_node` | Visualizes planar RSS radio maps. |
| `Sionna_radio_map_sinr_node` | Visualizes planar SINR radio maps. |
| `Sionna_radio_map_projected_pathgain_node` | Projects Path Gain values onto reference geometry. |
| `Sionna_radio_map_3d_pathgain_node` | Visualizes three-dimensional Path Gain maps. |
| `Sionna_radio_map_3d_rss_node` | Visualizes three-dimensional RSS maps. |
| `Sionna_radio_map_3d_sinr_node` | Visualizes three-dimensional SINR maps. |
| `Sionna_device_text` | Creates optional camera-facing TX and RX labels. |

## Append the node groups

1. Download `sionnart_geometry_nodes_1.0.0.blend`.
2. In Blender 4.5 LTS, select **File → Append**.
3. Open the downloaded `.blend` file.
4. Open the **NodeTree** directory.
5. Select the required node groups, or press `A` to select all.
6. Select **Append**.
7. Save the destination Blender file.

Do not rename the node groups. A copied name such as
`Sionna_radio_map_3d_sinr_node.001` does not match the exact name expected
by the add-on.

## Requirements

- Blender 4.5 LTS
- Exact node-group names
- A `Geometry` input on result-visualization groups
- Fake User enabled for reusable node groups
- Required materials included in the reference library
- No project-specific absolute paths or simulation outputs

## Verify the downloaded file

A SHA-256 checksum is provided in:

`assets/blender/sionnart_geometry_nodes_1.0.0.blend.sha256`

On Windows PowerShell:

```powershell
Get-FileHash `
    .\sionnart_geometry_nodes_1.0.0.blend `
    -Algorithm SHA256

```
