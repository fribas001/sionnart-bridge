"""Factory-startup Blender integration test. Output directory after --."""
import bpy
import importlib.util
import json
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
out=Path(sys.argv[sys.argv.index('--')+1]).resolve();out.mkdir(exist_ok=True,parents=True)
spec=importlib.util.spec_from_file_location('parameter_test',root/'__init__.py',submodule_search_locations=[str(root)])
b=importlib.util.module_from_spec(spec);sys.modules[spec.name]=b;spec.loader.exec_module(b);b.register()
scene=bpy.context.scene;s=scene.sionna_bridge;s.workspace_dir=str(out);s.export_format='NONE';s.export_geometry_nodes_metadata=False;s.timeline_mode='RANGE';scene.frame_start=1;scene.frame_end=2
env=b._ensure_environment(scene)
bpy.ops.sionna_bridge.add_device(role='TX');bpy.ops.sionna_bridge.add_device(role='RX')
obj=bpy.data.objects.new('Tree',bpy.data.meshes.new('Tree mesh'));env['procedural_geometry'].objects.link(obj)
obj.data.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
group=bpy.data.node_groups.new('Tree params','GeometryNodeTree')
group.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry');group.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
density=group.interface.new_socket(name='Density',in_out='INPUT',socket_type='NodeSocketFloat')
inp=group.nodes.new('NodeGroupInput');output=group.nodes.new('NodeGroupOutput');setmat=group.nodes.new('GeometryNodeSetMaterial')
group.links.new(inp.outputs['Geometry'],setmat.inputs['Geometry']);group.links.new(setmat.outputs['Geometry'],output.inputs['Geometry'])
mat=bpy.data.materials.new('itu_glass');setmat.inputs['Material'].default_value=mat
transform=group.nodes.new('GeometryNodeTransform');transform.inputs['Translation'].default_value=(1,2,3);transform.inputs['Rotation'].default_value=(.1,.2,.3)
mod=obj.modifiers.new('Parameters','NODES');mod.node_group=group
prop=getattr(mod.properties.inputs,density.identifier)
for frame,value in [(1,6.),(2,0.)]:prop.value=value;prop.keyframe_insert(data_path='value',frame=frame)
bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
assert len(obj.data.materials)==0
materials=b._material_payloads(scene,dg)
assert any(m['blender_name']=='itu_glass' and m['itu_type']=='glass' for m in materials),materials
snapshot=b._geometry_nodes_metadata.capture(bpy.context,env['scene'],dg)
assert not snapshot['warnings'],snapshot['warnings']
tx=b._device_objects(scene,'TX');rx=b._device_objects(scene,'RX')
frames=b._sample_frame_payloads(bpy.context,[1,2],tx,rx)
assert all('parameter_study_inputs' in f and 'geometry_nodes_parameters' not in f for f in frames)
assert [next(p['value'] for k,p in f['parameter_study_inputs']['parameters'].items() if p['label'].endswith('/ Density')) for f in frames]==[6.,0.]
config={'frames':frames,'output':{'export_run_id':'test-parameters'},'scene_name':'Tree','procedural_scene':True,'bridge_version':b._ADDON_VERSION}
manifest={'frames':[{'frame':f,'channel_analytics':{'source':'all_valid_paths_first_antenna_pair','links':[{'frame':f,'pos_idx':0,'path_count':2,'total_power_db':gain,'strongest_path_gain_db':gain-1,'rms_delay_spread_ns':2,'los_available':False}]}} for f,gain in [(1,-120),(2,-100)]]}
result=bpy.data.objects.new('Paths result',bpy.data.meshes.new('Points'));env['simulated_paths'].objects.link(result);result['sionna_result_type']='paths_pointcloud'
study=b._parameter_study.attach(b,scene,result,config,manifest)
assert json.loads(result['sionna_parameter_study'])['run_id']=='test-parameters'
assert Path(result['sionna_parameter_report']).is_file()
assert b._parameter_study.dataset_from_object(result)==study
assert b._parameter_study.write_selected(b,scene).is_file()
export={'run_id':'test-parameters','categories':{'paths':{'parameters':config,'results_summary':manifest}}}
p=out/'export.metadata.json';p.write_text(json.dumps(export),encoding='utf-8')
assert bpy.ops.sionna_bridge.import_parameter_run(filepath=str(p))=={'FINISHED'}
assert s.parameter_study_imported and s.parameter_study_source=='IMPORTED'
# A second reference run is persisted separately and changes are reported.
export['run_id']='reference';export['categories']['paths']['parameters']['output']['export_run_id']='reference';export['categories']['paths']['parameters']['antenna']={'tx':{'num_rows':4}}
ref=out/'reference.metadata.json';ref.write_text(json.dumps(export),encoding='utf-8')
assert bpy.ops.sionna_bridge.import_parameter_run(filepath=str(ref),as_reference=True)=={'FINISHED'}
assert b._parameter_study.write_selected(b,scene).is_file()
s.parameter_analysis_enabled=False
assert all('parameter_study_inputs' not in f for f in b._sample_frame_payloads(bpy.context,[1,2],tx,rx))
bpy.ops.wm.save_as_mainfile(filepath=str(out/'parameter_studies.blend'))
bpy.ops.wm.open_mainfile(filepath=str(out/'parameter_studies.blend'))
scene=bpy.context.scene;s=scene.sionna_bridge
assert s.parameter_study_imported and s.parameter_study_reference
assert b._parameter_study.write_selected(b,scene).is_file()
b.unregister()
print('BLENDER_PARAMETER_ANALYSIS_PASS')
