# Vegetation measurements — SionnaRT-Bridge 1.25.0

## Use

1. Assign a vegetation radio material to the actual leaf or wood faces. The
   library's leaf and branch presets already identify these two roles. Material
   names alone, unused material slots and ordinary green viewport materials do
   not identify vegetation.
2. Leave **Measure Vegetation** enabled in the simulation controls. It is on by
   default. Measurements use the final evaluated mesh after Geometry Nodes and
   modifiers, with the same collection/instance scope as the scene exporter.
3. Set **Link Corridor Width (m)** for the scale of the region you want to study.
   The default is a 1 m wide square corridor. Keep this width fixed when comparing
   density across a parameter sweep.
4. Use **Inspect Vegetation** to inspect the current frame without running the
   radio solver. Blender opens a readable Text Editor report; its text data-block
   also stores the complete measurements in `vegetation_metrics_json`.
5. Run paths with **Prepare Parameter Analysis** enabled. In the report choose
   an X axis beginning with **Vegetation** and a channel metric such as summed
   path gain. The selected TX/RX link controls the link-specific measurements.
   **Include changing vegetation measurements in automatic plots** adds these
   descriptors to the automatic plots. SVG, plotted CSV and statistics JSON
   downloads work as before.

Measurements are captured once per sampled simulation frame. They are retained
in simulation metadata and the embedded parameter study; they also appear in
each Geometry Nodes JSON when that export is enabled. CSV result exports retain
them in the companion metadata JSON, rather than duplicating object/frame
measurements on every path point. HDF5 exports retain the same category metadata.
Radio-map runs capture the per-object and scene measurements; they do not create
a link measurement for every map cell. Explicit TX/RX link measurements are part
of paths runs. Previous reports do not acquire measurements retroactively.

## What the quantities mean

| Quantity | Definition | Scope and units |
|---|---|---|
| Leaf mesh surface area | Sum of world-space triangle areas assigned a leaf material | Object and scene, m² |
| One-sided leaf area estimate | Leaf surface area with the selected side convention | Object and scene, m² |
| Wood mesh surface area | Sum of triangles assigned a wood vegetation material | Object and scene, m² |
| Leaf count estimate | Number of vertex-connected components of leaf-material faces | Object and scene |
| Leaf count from supplied IDs | Distinct positive `sionna_leaf_id` values on leaf faces | Object and scene, unavailable if incomplete |
| Bounding-box leaf area density | One-sided leaf area estimate / vegetation box volume | Object and scene, m²/m³ |
| Bounding-box leaf area index | One-sided leaf area estimate / vegetation box XY footprint | Object and scene, m²/m² |
| Vegetation depth estimate | Length of the straight TX–RX segment inside vegetation object boxes | Link and object within link, m |
| Leaf/wood surface crossings | Distinct intersections of the straight segment with the respective surfaces | Link and object within link |
| Link corridor leaf area | Leaf triangles clipped to the square corridor, using the selected side convention | Link and object within link, m² |
| Link corridor leaf area density | Corridor leaf area / (corridor width² × TX–RX distance) | Link and object within link, m²/m³ |

The vegetation envelope is the world-axis-aligned bounding box of all vegetation
faces on an object, including wood. It can contain gaps and space below a crown.
It is not a fitted canopy volume. The scene envelope bounds all measured objects
and includes space between them. These denominators are exported explicitly.
A box with zero volume or XY footprint produces an unavailable density/index,
not an invented denominator. Envelope ratios are labelled estimates and are not
substitutes for field-measured canopy LAD or plot LAI. Keep object grouping and
orientation consistent when comparing these estimates.

Corridor density includes empty air between the antennas. Its denominator is the
entire corridor, not just the part inside tree envelopes. Partial triangles are
clipped to the corridor, rather than selected by triangle centre. The corridor
cross section is perpendicular to the link; its first axis is the normalized
cross product of link direction with world Z (world Y for near-vertical links).
It is a geometric sampling region, not a Fresnel zone. Vegetation depth uses the
union of object-box intervals, so overlapping boxes do not double-count length.

Surface crossings are not biological leaf counts: a closed leaf may have two
crossings. Shared-edge or coincident hits within 1 µm are merged. Coplanar tangent
segments and intersections within 0.1 µm of an endpoint are not counted. A
zero-length link has unavailable crossing and corridor-density values. None of
these quantities measures the vegetation encountered by an indirect Sionna ray.

## Leaf counts and area conventions

**Automatic by topology** uses full surface area for an open leaf component and
half surface area for a closed component. This accommodates single-sheet leaves
and thin closed leaves without assuming that material slab thickness gives the
geometrical volume. **Single surface** and **Half surface** allow an explicit
convention. Half the area of a thick leaf still includes half its edge area.
Duplicate sheets or disconnected front/back faces need a deliberate convention;
they cannot be recognized reliably as two sides of one biological leaf.

Mesh islands provide an automatic count estimate when each leaf is one component.
Split leaves, merged leaves, disconnected lobes, double-sided geometry and stems
incorrectly assigned a leaf material affect that estimate. Do not interpret the
number of triangles, vertices, material slots or Geometry Nodes instances as the
number of leaves.

If an object has no vegetation faces on a frame, it is absent from that frame's
object list. Its object-specific plot values are unavailable; scene totals still
record zero vegetation when the whole scene has none. Use scene totals when
studying complete disappearance of vegetation.

For a count based on generator-provided identities, store a **FACE-domain integer
attribute named `sionna_leaf_id`** on the final evaluated mesh. Every face of a
leaf must share one positive ID, and each different leaf must have a different
ID within that evaluated mesh. Zero/unassigned IDs on any leaf face make the
tagged count unavailable. Assign IDs per generated leaf before realization and
ensure they remain unique after joins. IDs from separately exported instances
are namespaced by instance; repeated IDs in one realized mesh are not assumed
to be distinct leaves. The tool counts supplied IDs but cannot verify their
biological correctness. The island estimate remains available alongside them.

Measurements are grouped by the generating Blender object; unrealized Geometry
Nodes instances are included in their generator's totals. A joined grove in one
object is one measured object, not an inferred number of trees. Ordinary meshes
work as well; Geometry Nodes are not required. In a stack of modifiers the output
is measured after the whole stack, not separately after every modifier.

## Interpretation

Leaf area density and leaf area index are established vegetation descriptors
[1,2]. Vegetation depth, geometry and vegetation properties matter to radio
propagation [3]. This implementation applies geometric definitions to the
exported mesh. Its box envelopes, corridor size and component counts are explicit
measurement choices, not additional empirical propagation models. It does not
derive biomass, moisture, dielectric constants, diffuse scattering strength,
attenuation in dB/m or uncertainty from a mesh.

For comparisons with path gain, keep material properties, sampling region and
solver settings fixed unless they are the parameters under study. Solver-seed
replicates assess numerical variation; geometry-seed replicates assess variation
among generated scenes. A parameter sweep alone does not establish convergence
or biological uncertainty. Small or zero values of a generator's density socket
do not guarantee that its evaluated mesh contains no leaves.

## References

[1] One-dimensional models of radiation transfer in heterogeneous canopies:
a review, re-evaluation, and improved model (2020), section 2.1.
https://doi.org/10.5194/gmd-13-4789-2020

[2] FIFE LAI (Indirect): Light Wand – KSU, ORNL DAAC. Leaf area per canopy volume,
orientation and canopy path-length relationships.
https://daac.ornl.gov/FIFE/guides/Light_Wand_KSU.html

[3] ITU-R P.833-10 (2021), Attenuation in vegetation.
https://www.itu.int/rec/R-REC-P.833-10-202109-I/en

These references motivate the descriptors. They do not validate a particular
procedural plant, the automatic island count or a selected Sionna material.
