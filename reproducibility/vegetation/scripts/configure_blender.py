"""Reconstruct recorded inputs in a clean Blender scene; never edits the source.
Run: blender --background --factory-startup --python THIS_FILE -- --study foliage_r1 --output new_experiment
SPDX-License-Identifier: GPL-3.0-or-later
"""
import argparse, importlib.util, json, sys, shutil, xml.etree.ElementTree as ET
from pathlib import Path
import bpy

ROOT=Path(__file__).resolve().parents[1]
def write(p,d):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def main():
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);p.add_argument('--output',required=True);p.add_argument('--frames',default='all');p.add_argument('--sionna-python',default='');p.add_argument('--no-blend',action='store_true')
 a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);out=Path(a.output).resolve()
 if out.exists() and any(out.iterdir()):raise ValueError('Use a new empty output directory; recorded data are never overwritten.')
 out.mkdir(parents=True,exist_ok=True)
 records=json.loads((ROOT/'data'/a.study/'configurations.json').read_text())
 if a.frames!='all':records=[r for r in records if r['frame'] in {int(x) for x in a.frames.split(',')}]
 if not records:raise ValueError('No matching frames.')
 addon=ROOT/'software/sionnart_bridge';spec=importlib.util.spec_from_file_location('reproduction_bridge',addon/'__init__.py',submodule_search_locations=[str(addon)])
 b=importlib.util.module_from_spec(spec);sys.modules[spec.name]=b;spec.loader.exec_module(b);b.register();b._ensure_bundled_geometry_nodes(verbose=False)
 for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
 scene=bpy.context.scene;scene.animation_data_clear();s=scene.sionna_bridge
 s.workspace_dir=str(out/'new_runs');s.runtime_mode='EXTERNAL';s.sionna_python=a.sionna_python;s.dynamic_mode=False
 s.procedural_geometry_enabled=True;s.isac_enabled=False;s.timeline_mode='CURRENT'
 s.export_format='CSV';s.export_geometry_nodes_metadata=True;s.parameter_analysis_enabled=True
 env=b._ensure_environment(scene)
 source=ROOT/'blender/Procedural_Vegetation_reproducible.blend'
 with bpy.data.libraries.load(str(source),link=False) as (src,dst):dst.objects=[records[0]['tree']]
 tree=dst.objects[0];env['procedural_geometry'].objects.link(tree);tree.animation_data_clear()
 tree.hide_viewport=False;tree.hide_render=False;tree.hide_set(False)
 mod=next(m for m in tree.modifiers if m.type=='NODES');sockets={i.name:i for i in mod.node_group.interface.items_tree if i.item_type=='SOCKET' and i.in_out=='INPUT'}
 for role in ['TX','RX']:
  b._set_role_antenna_profile(s,role,records[0]['antenna'][role.lower()]);bpy.ops.sionna_bridge.add_device(role=role)
 tx,rx=b._device_objects(scene,'TX')[0],b._device_objects(scene,'RX')[0]
 for obj,other in [(tx,rx),(rx,tx)]:
  obj.sionna_device_config.configured=True;obj.sionna_device_config.orientation_mode='LOOK_AT';obj.sionna_device_config.look_at_target=other
 reports=[]
 for r in records:
  frame=r['frame'];scene.frame_set(frame)
  for name,value in r['controls'].items():
   if name not in sockets or value is None or isinstance(value,dict):continue
   getattr(mod.properties.inputs,sockets[name].identifier).value=value
  tree.update_tag()
  sim=r['simulation'];s.frequency_ghz=sim['frequency_hz']/1e9;s.bandwidth_mhz=sim['bandwidth_hz']/1e6;s.temperature_k=sim['temperature_k']
  for key in ['max_depth','max_num_paths_per_src','samples_per_src','seed']:setattr(s,key,sim[key])
  s.deterministic_paths=sim['deterministic']
  for prop,key in [('enable_los','los'),('enable_reflection','specular_reflection'),('enable_diffuse','diffuse_reflection'),('enable_refraction','refraction'),('enable_diffraction','diffraction'),('enable_edge_diffraction','edge_diffraction'),('diffraction_lit_region','diffraction_lit_region')]:setattr(s,prop,sim[key])
  for mat in bpy.data.materials:
   preset='LEAF_P833' if 'leaf' in mat.name.lower() else 'WOOD40_P833' if any(k in mat.name.lower() for k in ['twig','branch','wood']) else None
   ref=next((x for x in r['materials'] if x.get('plant_model')==preset),None)
   if not ref:continue
   radio=mat.sionna_radio;radio.configured=True;radio.enabled=True;radio.model='VEGETATION';radio.plant_model=preset
   for k in ['thickness','scattering_coefficient','xpd_coefficient','scattering_pattern']:setattr(radio,k,ref[k])
  for obj,ref in [(tx,r['transmitters'][0]),(rx,r['receivers'][0])]:
   obj.location=ref['position'];obj.sionna_device_config.tx_power_dbm=ref.get('power_dbm',44)
   b._sync_device_name(obj,s)
  bpy.context.view_layer.update()
  # Direct export of the selected tree only; no floor or other retained models.
  dest=out/'scenes'/f'F{frame:04d}'/'scene.xml';dest.parent.mkdir(parents=True,exist_ok=True)
  b._export_scene_package(bpy.context,dest,[tree],asset_prefix=f'F{frame:04d}_')
  payload=b._sample_frame_payloads(bpy.context,[frame],[tx],[rx])[0]
  reports.append({'frame':frame,'geometry_seed':r['geometry_seed'],'scene':dest.relative_to(out).as_posix(),'payload':payload})
  print('EXPORTED',a.study,frame,flush=True)
 if not a.no_blend:
  scene.frame_start=min(r['frame'] for r in records);scene.frame_end=max(r['frame'] for r in records)
  bpy.ops.wm.save_as_mainfile(filepath=str(out/'configured_scene.blend'),compress=True)
 write(out/'reconstruction.json',{'study':a.study,'source':'blender/Procedural_Vegetation_reproducible.blend','note':'Reconstructed exports, not recovered original file bytes. configured_scene.blend shows the last exported frame; run this script with --frames N for a chosen configuration.','records':reports})
main()
