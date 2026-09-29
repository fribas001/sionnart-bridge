"""Self-contained optional sensing regression; no private character assets."""
import bpy,importlib.util,json,sys,time,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[1]
out=Path(sys.argv[sys.argv.index('--')+1]).resolve();out.mkdir(parents=True,exist_ok=True)
python=sys.argv[sys.argv.index('--')+2]
spec=importlib.util.spec_from_file_location('sensing_release',root/'__init__.py',submodule_search_locations=[str(root)])
b=importlib.util.module_from_spec(spec);sys.modules[spec.name]=b;spec.loader.exec_module(b);b.register()
scene=bpy.context.scene;s=scene.sionna_bridge;s.workspace_dir=str(out);s.runtime_mode='EXTERNAL';s.sionna_python=python
s.frequency_ghz=6;s.max_depth=1;s.samples_per_src=2048;s.max_num_paths_per_src=512;s.timeline_mode='RANGE';scene.frame_start=1;scene.frame_end=2
s.export_format='NONE';s.isac_enabled=True;s.isac_capture_pose=True
b._ensure_bundled_geometry_nodes(verbose=False);env=b._ensure_environment(scene);b._ensure_default_sionna_materials()
# Two-bone procedural rig with one simple skinned mesh.
rigdata=bpy.data.armatures.new('Test rig');rig=bpy.data.objects.new('Test rig',rigdata);env['scene'].objects.link(rig)
bpy.context.view_layer.objects.active=rig;rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
one=rigdata.edit_bones.new('Root');one.head=(0,0,0);one.tail=(0,0,1)
two=rigdata.edit_bones.new('Tip');two.head=(0,0,1);two.tail=(0,0,2);two.parent=one
bpy.ops.object.mode_set(mode='OBJECT')
mesh=bpy.data.meshes.new('Proxy body');mesh.from_pydata([(0,-.2,0),(0,.2,0),(0,.2,2),(0,-.2,2)],[],[(0,1,2,3)])
body=bpy.data.objects.new('Proxy body',mesh);env['scene'].objects.link(body);body.parent=rig
mesh.materials.append(bpy.data.materials['itu_concrete'])
vg=body.vertex_groups.new(name='Tip');vg.add([0,1,2,3],1,'REPLACE');mod=body.modifiers.new('Rig','ARMATURE');mod.object=rig
s.isac_subject=rig
assert bpy.ops.sionna_bridge.human_material()=={'FINISHED'}
assert mesh.materials[0].sionna_radio.model=='CUSTOM' and mesh.materials[0].name!='itu_concrete'
for f,x in [(1,0),(2,.1)]:rig.pose.bones['Tip'].location.x=x;rig.pose.bones['Tip'].keyframe_insert(data_path='location',frame=f)
scene.timeline_markers.new('isac:test_motion',frame=2)
body.hide_render=True
try:b._isac_blender.validate_subject(scene,b._scene_export_objects(scene));raise AssertionError('Hidden subject accepted')
except ValueError:pass
body.hide_render=False
for role in ['TX','RX']:bpy.ops.sionna_bridge.add_device(role=role)
b._device_objects(scene,'TX')[0].location=(-2,2,1);b._device_objects(scene,'RX')[0].location=(2,2,1)
camdata=bpy.data.cameras.new('Camera');cam=bpy.data.objects.new('Camera',camdata);scene.collection.objects.link(cam);scene.camera=cam
assert bpy.ops.sionna_bridge.isac_overlay()=={'FINISHED'}
hud=bpy.data.objects['SBR_ISAC_Statistics'];assert hud not in b._scene_export_objects(scene)
assert bpy.ops.sionna_bridge.run_selected()=={'FINISHED'}
deadline=time.monotonic()+120
while b._RUN_STATE.get('process'):
 assert time.monotonic()<deadline
 if b._RUN_STATE['process'].poll() is not None:b._poll_sionna_process()
 time.sleep(.03)
assert 'rejected' not in s.last_status,(s.last_status,s.last_status_details)
manifest=Path(s.isac_last_run_dir)/'isac'/'dataset_manifest.json';data=json.loads(manifest.read_text())
assert data['status']=='complete' and len(data['frames'])==2
for f in data['frames']:
 folder=manifest.parent/f['directory'];summary=json.loads((folder/'summary.json').read_text())
 assert not summary['plot_errors'],summary['plot_errors']
 completion=json.loads((folder/'completion.json').read_text())
 for filename,digest in completion['files_sha256'].items():assert hashlib.sha256((folder/filename).read_bytes()).hexdigest()==digest
 assert (folder/'skeleton.csv').stat().st_size>80
assert data['frames'][1]['activity']=='test_motion'
scene.frame_set(2);b._isac_hud.update(scene);bpy.context.view_layer.update()
hud_geometry=hud.evaluated_get(bpy.context.evaluated_depsgraph_get()).evaluated_geometry()
assert not hud.hide_render and len(hud_geometry.mesh.vertices)>4
s.isac_capture_pose=False;assert b._isac_blender.capture(bpy.context)['objects']==[]
s.runtime_mode='BLENDER';assert bpy.ops.sionna_bridge.test_environment()=={'FINISHED'}
(out/'test_report.json').write_text(json.dumps({'optional_sensing':True,'frames':2,'pose_labels':True,'dataset_checksums':True,'cir_csi_plots':True,'human_materials':True,'hud':True,'blender_python_runtime_probe':True},indent=2))
b.unregister();print('OPTIONAL_SENSING_PASS',flush=True)
