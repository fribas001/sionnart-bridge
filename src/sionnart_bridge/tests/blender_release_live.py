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
s.runtime_mode='BLENDER';s.max_depth=2;s.samples_per_src=8192
s.enable_diffuse=True;s.enable_diffraction=True;s.enable_edge_diffraction=True
material=mesh.materials[0].sionna_radio;material.scattering_coefficient=.2
for pattern in ['lambertian','directive','backscattering']:
 material.scattering_pattern=pattern
 assert bpy.ops.sionna_bridge.run_selected()=={'FINISHED'};wait_run()
 assert 'rejected' not in s.last_status,(s.last_status,s.last_status_details)
 checks.append('Blender Python worker / '+pattern+' / diffraction enabled')
# Live recomputation uses the same worker lifecycle, with current frame only.
s.dynamic_mode=True;s.auto_compute_paths_on_tx_move=True
bpy.context.view_layer.update();b._prime_auto_path_transform_signatures(scene,bpy.context.evaluated_depsgraph_get())
rx.location.x+=.5;bpy.context.view_layer.update()
b._auto_path_depsgraph_update(scene,bpy.context.evaluated_depsgraph_get())
assert b._AUTO_PATH_STATE['pending'],b._AUTO_PATH_STATE
b._AUTO_PATH_STATE['deadline']=0
b._auto_path_compute_timer();assert b._RUN_STATE.get('process'),s.last_status
wait_run();assert 'rejected' not in s.last_status,(s.last_status,s.last_status_details)
assert any(o.get('sionna_auto_device_move_result') for o in env['simulated_paths'].objects)
manual_count=len([o for o in env['simulated_paths'].objects if not o.get('sionna_auto_device_move_result')])
rx.location.x+=.5;bpy.context.view_layer.update();b._auto_path_depsgraph_update(scene,bpy.context.evaluated_depsgraph_get())
b._AUTO_PATH_STATE['deadline']=0;b._auto_path_compute_timer();wait_run()
assert len([o for o in env['simulated_paths'].objects if o.get('sionna_auto_device_move_result')])==1
assert len([o for o in env['simulated_paths'].objects if not o.get('sionna_auto_device_move_result')])==manual_count
s.dynamic_mode=False;assert not b._auto_move_enabled(s)
checks.append('live RX movement, automatic replacement and manual result retention')
# Coverage depends on TX motion, not RX motion.
s.simulation_mode='BATCH';s.simulate_radio_map=True;s.simulate_radio_map_3d=True
s.auto_compute_radio_map_on_device_move=True;s.auto_compute_radio_map_3d_on_device_move=True
assert not b._auto_move_requested_outputs(s,'RX')['radio_map']
assert all(b._auto_move_requested_outputs(s,'TX').values())
checks.append('live output selection by device role')
b.unregister();(out/'test_report.json').write_text(json.dumps({'checks':checks},indent=2))
print('RELEASE_LIVE_RUNTIME_PASS',flush=True)
