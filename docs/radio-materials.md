# Radio materials

## Default ITU materials

Create or repair the Sionna environment to create these Blender materials when
missing:

`itu_vacuum`, `itu_concrete`, `itu_brick`, `itu_plasterboard`, `itu_wood`,
`itu_glass`, `itu_ceiling_board`, `itu_chipboard`, `itu_plywood`, `itu_marble`,
`itu_floorboard`, `itu_metal`, `itu_very_dry_ground`,
`itu_medium_dry_ground`, and `itu_wet_ground`.

The Blender colors are visualization aids only. Electromagnetic properties are
constructed in the external Sionna environment.

## Material editor

The Radio Materials panel can select any Blender material, prefix and configure
it for Sionna, and assign it to selected objects. ITU presets use Sionna's
frequency-dependent model. Custom materials expose relative permittivity and
conductivity. Both modes expose thickness, scattering coefficient, XPD
coefficient, and scattering-pattern controls.

## Animation

Insert Blender keyframes on the material properties in the usual way. Timeline
runs sample the values at each requested frame. The cached geometry can remain
unchanged because the exported material placeholder is replaced by a
frame-evaluated radio material in each worker solve.

When the material assignment itself changes, refresh/re-export the scene.
