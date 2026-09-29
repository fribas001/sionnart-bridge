"""Regression checks for valid empty channels, curve imports and failed batches."""
import bpy,importlib.util,json,sys,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
out=Path(sys.argv[sys.argv.index('--')+1]).resolve();out.mkdir(parents=True,exist_ok=True)
python=sys.argv[sys.argv.index('--')+2]
spec=importlib.util.spec_from_file_location('release_edges',root/'__init__.py',submodule_search_locations=[str(root)])
b=importlib.util.module_from_spec(spec);sys.modules[spec.name]=b;spec.loader.exec_module(b);b.register()
scene=bpy.context.scene;s=scene.sionna_bridge;s.workspace_dir=str(out);s.runtime_mode='EXTERNAL';s.sionna_python=python
b._ensure_bundled_geometry_nodes(verbose=False);env=b._ensure_environment(scene);b._ensure_default_sionna_materials()
mesh=bpy.data.meshes.new('Ground');mesh.from_pydata([(-10,-10,-1),(10,-10,-1),(10,10,-1),(-10,10,-1)],[],[(0,1,2,3)])
floor=bpy.data.objects.new('Ground',mesh);env['scene'].objects.link(floor);mesh.materials.append(bpy.data.materials['itu_concrete'])
for role in ['TX','RX']:bpy.ops.sionna_bridge.add_device(role=role)
tx=b._device_objects(scene,'TX')[0];rx=b._device_objects(scene,'RX')[0];tx.location=(-2,0,2);rx.location=(2,0,1)
s.samples_per_src=2048;s.max_num_paths_per_src=100;s.max_depth=0;s.timeline_mode='CURRENT';s.simulation_mode='PATHS';s.export_format='CSV'
def wait_run():
 deadline=time.monotonic()+120
 while any(x.get('process') for x in (b._RUN_STATE,b._RADIO_MAP_STATE,b._RADIO_MAP_3D_STATE)):
  assert time.monotonic()<deadline
  for state,poll in [(b._RUN_STATE,b._poll_sionna_process),(b._RADIO_MAP_STATE,b._poll_radio_map_process),(b._RADIO_MAP_3D_STATE,b._poll_radio_map_3d_process)]:
   if state.get('process') and state['process'].poll() is not None:poll()
  time.sleep(.03)
checks=[]
# A valid solved frame with no paths is still a useful experiment observation.
s.enable_los=False;s.enable_reflection=False;s.enable_diffuse=False;s.enable_refraction=False;s.enable_diffraction=False;s.enable_edge_diffraction=False
assert bpy.ops.sionna_bridge.run_selected()=={'FINISHED'};wait_run()
assert 'rejected' not in s.last_status,(s.last_status,s.last_status_details)
obj=b._analytics_target_object(scene,'PATHS');assert obj is not None and len(obj.data.vertices)==0
study=b._parameter_study.dataset_from_object(obj);r=study['records'][0]
assert r['metrics']['path_count']==0 and r['metrics']['total_power_db'] is None and r['metrics']['strongest_path_gain_db'] is None,r
assert b._parameter_study.write_selected(b,scene).is_file()
assert Path(s.last_export_path).is_file()
checks.append('zero paths retained and gains unavailable')
# Optional curves cannot destroy the primary embedded point object and analysis.
s.enable_los=True;s.enable_reflection=True;s.max_depth=1;s.pointcloud_top_paths_per_pair=1;s.post_run_action='CURVES'
assert bpy.ops.sionna_bridge.run_selected()=={'FINISHED'};wait_run()
assert 'failed' not in s.last_status.lower() and 'rejected' not in s.last_status.lower(),s.last_status
obj=b._analytics_target_object(scene,'PATHS');assert obj and obj.get('sionna_parameter_study')
assert any(o.type=='CURVE' and 'sionna_path_index' in o for o in env['simulated_paths'].objects)
full_count=b._parameter_study.dataset_from_object(obj)['records'][0]['metrics']['path_count']
visual_count=sum(p.value==0 for p in obj.data.attributes['point_order'].data)
assert full_count>visual_count==1,(full_count,visual_count)
checks.append('optional curves preserve embedded results')
# Failed statuses cannot be reclassified from an earlier fresh manifest.
status=out/'failed_status.json';status.write_text('{"state":"failed","error":"test failure"}')
assert b._completed_status_with_recovery(out/'missing.json',status,out/'missing.csv',0,'test')['state']=='failed'
# Fail the paths worker, then run the queued map. The batch must retain its error.
bad=out/'failing_worker.py';bad.write_text("import sys; print('Intentional test failure',flush=True);sys.exit(4)")
original=b._worker_script;b._worker_script=lambda:bad
s.simulation_mode='BATCH';s.simulate_paths=True;s.simulate_radio_map=True;s.simulate_radio_map_3d=False
s.radio_map_size_x=2;s.radio_map_size_y=2;s.radio_map_cell_size_x=1;s.radio_map_cell_size_y=1
s.post_run_action='CSV_ONLY'
assert bpy.ops.sionna_bridge.run_selected()=={'FINISHED'};failed_dir=Path(b._RUN_STATE['run_dir']);wait_run()
assert s.last_status.startswith('Batch finished with errors'),s.last_status
assert failed_dir.exists() and (failed_dir/'sionna.log').is_file()
assert 'Intentional test failure' in (failed_dir/'sionna.log').read_text()
assert not b._active_run_lock_path(s).exists()
b._worker_script=original;checks.append('worker failure retained through queued successful output')
b.unregister();(out/'test_report.json').write_text(json.dumps({'checks':checks},indent=2))
print('RELEASE_EDGE_CASES_PASS',flush=True)
