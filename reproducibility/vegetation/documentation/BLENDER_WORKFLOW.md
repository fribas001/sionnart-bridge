# Blender workflow

Use Blender 5.2.0 LTS and install `software/SionnaRT-Bridge_2.1.0_Blender52_Sionna21.zip`. The archive also contains the exact add-on source. Open the packaged `.blend`; its geometry-node groups and textures are embedded, so EasyTree installation is not needed to evaluate the existing models. The separately included upstream archive has manifest version 1.0.0 and supplied display textures; it is not asserted to be the original installed extension version. The embedded node groups are the reconstruction source of truth.

The full project retains result collections for inspection. The scene currently visible is not a guarantee of which objects the simulator exports. For a reproducible new calculation, the recommended entry point creates a clean scene with one selected tree and the recorded link. It excludes the floor and other trees.

Example (replace the two executable locations with your installation paths):

```text
blender --background --factory-startup --disable-autoexec --python scripts/configure_blender.py -- --study foliage_r4 --frames 1 --output ../new_R4_frame1 --sionna-python /path/to/sionna/python
```

On Windows PowerShell, use `& "C:/path/to/blender.exe" ...` when the executable path contains spaces.

Open the resulting `configured_scene.blend`. It contains one evaluated configuration, TX and RX, configured radio materials, and the add-on settings. The tree retains editable Geometry Nodes; exported scenes are in `scenes/`. Select your runtime in the add-on and run the path calculation. The reconstruction script itself exports geometry and does not run Sionna. `--frames 1,9,10` exports those states; `--frames all` exports the study. The saved clean `.blend` shows the last exported frame; it is not an animated reconstruction of the entire schedule. The full research `.blend` retains the original animation and result collections for interactive exploration.

Study names: `foliage_r1` through `foliage_r5`, `seed_ensemble`, `exploratory_depth`, `exploratory_rays`. `data/<study>/configurations.json` contains the exact discrete input values, so reconstruction does not depend on interpreting an interpolated slider between reported frames.

Recorded setup: TX (0, -10, 7) m, RX (0, 10, 7) m, devices facing one another; 26 GHz; TX 4×4 tr38901/V with 0.5-wavelength spacing; one isotropic vertically polarized RX. The tree is the only simulated environmental mesh. Optical bark/leaf textures are display assets; explicit radio-material values determine propagation.

For foliage, frames 1–9 retain Add Leaves enabled while the density control decreases. Frame 10 disables Add Leaves. Density=0 is therefore not interchangeable with a leaf-free tree. Realization 4's live seed was restored to the recorded value 5 in the packaged copy. The original project was not overwritten.

The packaged full model deliberately has dynamic auto-calculation disabled and no workstation-specific Python interpreter selected. Set a writable workspace and your interpreter before using the UI. Generated figures and copied results can be filtered, recoloured and rendered without a new propagation calculation; editing geometry or radio settings requires recalculation.
