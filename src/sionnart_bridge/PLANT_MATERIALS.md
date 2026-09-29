# Plant radio materials

These presets provide documented dielectric starting points for explicit leaf and wood geometry. They do not identify plant species, infer moisture from appearance, or calibrate a real tree automatically.

## Library and assignment

Under **Materials**, use **Create Default Materials** or choose a **Plant** preset and click **Load Preset**. The library contains:

| Material | Radio model | Default effective thickness |
|---|---|---|
| `itu_plant_leaf_p833` | Reference leaf | 0.2 mm |
| `itu_plant_twig_p833` | Moist wood | 4 mm |
| `itu_plant_branch_p833` | Moist wood | 56 mm |
| `itu_plant_large_branch_p833` | Moist wood | 228 mm |

The leaf model follows equation (18) of [ITU-R P.833-10](https://www.itu.int/rec/R-REC-P.833-10-202109-I/en). With f in GHz:

`epsilon_leaf = 3.1686 + 28.938/(1 + j*f/18) - j*0.5672/f`.

Wood uses linear interpolation of the real permittivity and positive loss tangent in Table 10, for 40% moisture content and 20°C. The reported frequency knots are 1, 2.4, 5.8 and 30 GHz. Leaf thickness comes from Table 9; the three wood thicknesses use twice the listed radii of branch categories 5, 3 and 1 as effective slab dimensions. These are reference dimensions, not measurements of the user's tree.

The add-on supports these reference presets at **1–30 GHz** and refuses silent extrapolation. It converts dielectric loss to positive conductivity in S/m using `sigma = 2*pi*f_Hz*epsilon_0*epsilon_loss`. Frequency changes are evaluated for every simulation frame, including 2D and 3D maps. At 26 GHz, the implemented leaf model gives epsilon real 12.544512 and conductivity 19.620737 S/m; the wood model gives 5.415702 and 3.290724 S/m.

Assign leaf and wood materials separately. In Geometry Nodes, choose the leaf material on the leaf geometry and the wood material on branches, before combining them. Use the generator's material inputs if available. A final **Set Material** node with Selection=true after combining the tree overrides both assignments. The add-on does not guess which polygons are leaves and does not modify existing node graphs when creating the library. Ordinary meshes can use **Assign to Selected** and Blender's face-level material assignment.

## Transmission and geometry

Click **Enable Plant Reflection / Transmission** to enable reflection, refraction/transmission and diffuse interactions in the scene settings. This does not increase ray budgets or change geometry. Diffuse strength remains controlled by each material's S value.

[Sionna RadioMaterial](https://nvlabs.github.io/sionna/rt/api/radio_materials.html) treats each intersected surface as a complete slab of the material's specified thickness. Use a **single surface per leaf**. Avoid duplicate coincident triangles or adding a second surface solely to model the same leaf thickness: those surfaces can produce additional slab interactions.

Wood presets are also slab approximations. A closed branch mesh does not become an exact dielectric cylinder: Sionna does not infer the material thickness from the distance to the mesh's far side. Multiple boundary hits can overcount slab penetration. For quantitative through-trunk transmission, use an appropriate single-surface proxy with an effective thickness, or a validated solid-object propagation model. Visually detailed closed branches remain useful for geometry studies, with that limitation stated.

## Scattering assumptions

Sionna's effective-roughness coefficient S is dimensionless; its squared value controls the diffuse share of reflected power. A canopy scattering coefficient in inverse metres, a scattering cross-section, and optical-shader roughness are different quantities. This release does not convert them into an invented measured S.

Default **S=0 and Kx=0** are a smooth-surface baseline. The Lambertian pattern is dormant at S=0. Specular reflection, absorption, transmission, and enabled geometric diffraction can still occur; zero diffuse coefficient does not mean the whole tree has no scattering. Surface normals and explicit geometry determine those interactions. These defaults are modelling choices, not literature-fitted plant scattering constants.

S, Kx and the pattern remain editable for calibrated data or sensitivity tests. If a nonzero S is used, the selected pattern becomes active when the solver's diffuse option is enabled. Export metadata explicitly distinguishes the baseline from user-selected roughness parameters. Unresolved leaf structure, species, hydration, bark and roughness can require additional calibration. The dielectric presets do not implement the canopy scattering formulation in P.833.

## Inspect and reproduce

The material panel previews epsilon real and conductivity at the current frequency. Thickness is editable with sufficient precision for thin leaves. Geometry Nodes assignments, including exported instances, are included in frame material payloads. Result metadata records the actual solver values, model version, source, frequency, thickness and scattering assumptions. Changing a library material is preserved when the library is created again; existing project assignments are not replaced.

Keep the material assignments, geometry, antenna settings and solver sampling fixed when checking numerical convergence. Use separate geometry seeds to study structural variation. For comparisons with measurements, include an unobstructed reference and document moisture, geometry scale and the chosen effective thickness.
