"""Library creation and presentation; never infer leaf/wood faces by name."""
import bpy
from . import plant_materials as model


def configure(bridge, material, preset_id):
    p=model.PRESETS[preset_id];c=material.sionna_radio
    c.enabled=True;c.configured=True;c.model='VEGETATION';c.plant_model=p['model']
    c.thickness=p['thickness'];c.scattering_coefficient=0.;c.xpd_coefficient=0.
    c.scattering_pattern='lambertian';c.directive_alpha_r=1
    c.backscatter_alpha_r=1;c.backscatter_alpha_i=1;c.backscatter_lambda=1.
    c.relative_permittivity,c.conductivity=model.dielectric(p['model'],26e9)
    material['plant_library_preset']=preset_id
    material['plant_reference_url']=model.SOURCE_URL
    material.use_fake_user=True
    bridge._set_material_preview_color(material,p['color'])


def ensure_library(bridge):
    created=configured=0
    for key,p in model.PRESETS.items():
        material=bpy.data.materials.get(p['name'])
        if material is None:material=bpy.data.materials.new(p['name']);created+=1
        if not material.sionna_radio.configured:
            configure(bridge,material,key);configured+=1
    return created,configured


def draw(bridge,box,context,config):
    box.prop(config,'plant_model')
    try:
        frequency=float(context.scene.sionna_bridge.frequency_ghz)*1e9
        er,sigma=model.dielectric(config.plant_model,frequency)
        box.label(text=f'At {frequency/1e9:g} GHz: εr = {er:.4g}; σ = {sigma:.4g} S/m')
    except ValueError:
        box.label(text='Plant model frequency range: 1–30 GHz',icon='ERROR')
    box.label(text='Updates at each frame frequency.')
    if config.plant_model=='WOOD40_P833':
        box.label(text='Wood reference: 40% moisture, 20°C')
        box.label(text='Slab thickness is not a measured mesh chord.')
    else:
        box.label(text='Use one surface per leaf; avoid duplicate faces.')
    box.label(text='S = 0: smooth-surface baseline.')
    box.label(text='Geometry still redirects radio waves.')
    if not context.scene.sionna_bridge.enable_refraction:
        box.label(text='Transmission is off in the simulation settings.',icon='ERROR')
    box.operator('sionna_bridge.plant_solver_settings',text='Enable Plant Reflection / Transmission',icon='CHECKMARK')
    box.operator('sionna_bridge.plant_material_reference',text='Plant Material References & Setup',icon='HELP')
