# Munich urban stacked-height radio-map example

This Blender scene demonstrates an animated stacked-height radio map created
with SionnaRT-Bridge using the Munich example environment distributed with
Sionna RT.

The coverage visualization is generated from a regular stack of horizontal
Sionna RT radio maps. It is displayed as three-dimensional attributed Blender
geometry and should not be interpreted as a separate volumetric
electromagnetic solver.

## Included files

- `sionnart_example_city_scene.blend` - complete example scene containing the
  city environment, devices, simulation settings, imported results, Geometry
  Nodes visualization, camera, materials, and animation.
- `sionnart_example_city_scene.blend.sha256` - SHA-256 checksum for the
  Blender scene.
- `ATTRIBUTION.md` - attribution and licensing information for the Munich
  environment and OpenStreetMap-derived data.

## Opening the example

1. Install Blender 4.5 LTS.
2. Install Mitsuba-Blender 4.5 Compatibility v0.4.8.
3. Install SionnaRT-Bridge v1.0.0.
4. Open `sionnart_example_city_scene.blend`.
5. Use the timeline to inspect the animated coverage result.
6. Inspect the Sionna RT sidebar for the recorded simulation settings.
7. Inspect the result object and Geometry Nodes modifier for numerical
   attributes and visualization controls.

## Re-running the simulation

The scene retains the devices, environment, timeline, and simulation
configuration used to create the displayed result.

Configure a compatible external Sionna RT Python environment before running
the simulation again. Re-execution time and numerical output can depend on
the selected Mitsuba backend, GPU, driver, and hardware.

## Demonstrated features

- Munich urban environment
- Transmitter and receiver placement
- Stacked-height radio-map sampling
- Frame-based result visualization
- Geometry Nodes filtering and styling
- Animated three-dimensional coverage display
- Transmitter-association attributes

## Software environment

- Blender 4.5 LTS
- SionnaRT-Bridge v1.0.0
- Mitsuba-Blender 4.5 Compatibility v0.4.8
- Python 3.11
- Sionna RT 2.0.1
- Mitsuba 3.5.0

See `ATTRIBUTION.md` for information about the Munich scene and
OpenStreetMap-derived data.
