"""Gabriel 1996 four-pole Cole-Cole fits, evaluated as a homogeneous proxy.
Source: https://niremf.ifac.cnr.it/docs/DIELECTRIC/AppendixC.html
No age specificity, tissue layering or clothing model is implied.
"""
import math
PARAMS={
 'DRY_SKIN':(4.,0.,[(32,7.234e-12,0),(1100,32.481e-9,.2),(0,159.155e-6,.2),(0,15.915e-3,.2)]),
 'MUSCLE':(4.,.2,[(50,7.234e-12,.1),(7000,353.678e-9,.1),(1.2e6,318.310e-6,.1),(2.5e7,2.274e-3,0)]),
 'FAT':(2.5,.01,[(3,7.958e-12,.2),(15,15.915e-9,.1),(3.3e4,159.155e-6,.05),(1e7,7.958e-3,.01)])}
def dielectric(tissue,frequency_hz):
 if not 1e6<=frequency_hz<=20e9:raise ValueError('This proxy tool is restricted to 1 MHz–20 GHz')
 eps_inf,sigma,poles=PARAMS[tissue];w=2*math.pi*frequency_hz;eps0=8.8541878128e-12
 value=eps_inf+sum(d/(1+(1j*w*t)**(1-alpha)) for d,t,alpha in poles)+sigma/(1j*w*eps0)
 return float(value.real),float(-value.imag*w*eps0)

def assign(context):
 import bpy
 from .isac_blender import subject
 s=context.scene.sionna_bridge;root=subject(context.scene)
 meshes=[o for o in context.scene.objects if o.type=='MESH' and (o==root or o in root.children_recursive or any(m.type=='ARMATURE' and m.object==root for m in o.modifiers))]
 if not meshes:raise ValueError('Selected subject has no meshes')
 er,sigma=dielectric(s.isac_tissue_preset,s.frequency_ghz*1e9)
 for obj in meshes:
  if obj.data.users>1:obj.data=obj.data.copy()
  if not obj.data.materials:obj.data.materials.append(bpy.data.materials.new('Human proxy'))
  for i,old in enumerate([slot.material for slot in obj.material_slots]):
   m=old.copy() if old else bpy.data.materials.new('Human proxy');m.name='Human_'+s.isac_tissue_preset+'_'+obj.name+f'_{i}'
   c=m.sionna_radio;c.configured=True;c.enabled=True;c.model='CUSTOM';c.relative_permittivity=er;c.conductivity=sigma
   c.thickness=s.isac_proxy_thickness;c.scattering_coefficient=0;c.xpd_coefficient=0
   m['isac_tissue_source']='Gabriel 1996 Appendix C';m['isac_tissue_preset']=s.isac_tissue_preset;m['isac_reference_frequency_hz']=s.frequency_ghz*1e9
   obj.material_slots[i].link='DATA';obj.data.materials[i]=m
  obj.data.update();obj.update_tag()
 context.view_layer.update()
 return len(meshes),er,sigma
