# Geometry Nodes

SionnaRT-Bridge ships its current Geometry Nodes library inside the Blender extension package.

The bundled library is:

```text
src/sionnart_bridge/assets/sionnart_geometry_nodes.blend
```

The extension loads missing SionnaRT node groups automatically during extension registration and when another `.blend` file is opened. In the normal Blender 5.2 workflow, users do **not** need to append these node groups manually.

The node groups must retain their exact Blender datablock names because the add-on looks them up by name.

## Included node groups

The SionnaRT workflow uses node groups including:

| Node group | Purpose |
|---|---|
| `Sionna_Paths` | Visualizes radio-propagation paths and their interactions. |
| `Sionna_radio_map_pathgain_node` | Visualizes planar Path Gain radio maps. |
| `Sionna_radio_map_rss_node` | Visualizes planar RSS radio maps. |
| `Sionna_radio_map_sinr_node` | Visualizes planar SINR radio maps. |
| `Sionna_radio_map_projected_pathgain_node` | Projects Path Gain values onto reference geometry. |
| `Sionna_radio_map_3d_pathgain_node` | Visualizes stacked-height Path Gain maps. |
| `Sionna_radio_map_3d_rss_node` | Visualizes stacked-height RSS maps. |
| `Sionna_radio_map_3d_sinr_node` | Visualizes stacked-height SINR maps. |
| `Sionna_device_text` | Creates optional camera-facing TX and RX labels. |

Do not rename these node groups. A copied name such as
`Sionna_radio_map_3d_sinr_node.001` does not match the exact name expected by
the add-on.

## Automatic loading

When SionnaRT-Bridge is registered, it checks the bundled library for the
required node groups and appends missing groups automatically.

The same recovery mechanism runs when a different Blender file is loaded, so
projects do not need to carry a manually appended copy of every group in
advance.

If a required group is missing from both the current Blender file and the
bundled library, the add-on reports an error rather than silently substituting
a differently named group.

## Blender requirements

The SoftwareX release targets:

- Blender 5.2 or newer;
- Blender Python 3.13 in the reference environment;
- exact node-group datablock names;
- a valid `Geometry` input on result-visualization groups where required.

The extension manifest declares Blender 5.2.0 as the minimum supported Blender
version.

## Bundled versus legacy reference library

The current extension library is:

```text
src/sionnart_bridge/assets/sionnart_geometry_nodes.blend
```

The repository also contains an older standalone reference asset:

```text
assets/blender/sionnart_geometry_nodes_1.0.0.blend
```

These files are not identical and should not be treated as interchangeable.

The `1.0.0` filename identifies that legacy reference asset; it is **not** the
current SionnaRT-Bridge release version. The current v1.8.2 extension uses the
bundled unversioned library under `src/sionnart_bridge/assets/`.

Unless reproducing an older workflow that explicitly depends on the legacy
reference file, use the Geometry Nodes library bundled with the installed
extension.

## Verification

To verify the current bundled library in a source checkout, run:

```powershell
Get-FileHash `
    ".\src\sionnart_bridge\assets\sionnart_geometry_nodes.blend" `
    -Algorithm SHA256
```

For a publication release, record the SHA-256 checksum from the exact final
release commit rather than copying a checksum from an older reference asset.

## Result data and Geometry Nodes

SionnaRT-Bridge writes or imports numerical simulation results and assigns the
corresponding Geometry Nodes group for visualization.

Depending on the workflow, Geometry Nodes are used for:

- propagation-path visualization;
- planar radio maps;
- projected radio maps;
- stacked-height radio maps;
- metric filtering and styling;
- optional transmitter and receiver labels.

Geometry Nodes are a Blender-side visualization and analysis layer. They do
not replace the Sionna RT propagation solver.
