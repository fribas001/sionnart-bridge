"""Exercise the public run operator, import, export, plots, motion and cancellation.
Run in factory-startup Blender; output folder and external Python after --.
"""
import bpy, importlib.util, json, sys, time, math
from pathlib import Path
root=Path(__file__).resolve().parents[1]
out=Path(sys.argv[sys.argv.index('--')+1]).resolve();out.mkdir(parents=True,exist_ok=True)
python=sys.argv[sys.argv.index('--')+2]
spec=importlib.util.spec_from_file_location('release_workflows',root/'__init__.py',submodule_search_locations=[str(root)])
b=importlib.util.module_from_spec(spec);sys.modules[spec.name]=b;spec.loader.exec_module(b);b.register()
scene=bpy.context.scene;s=scene.sionna_bridge;s.workspace_dir=str(out)
s.runtime_mode='EXTERNAL';s.sionna_python=python
assert bpy.ops.sionna_bridge.test_environment()=={'FINISHED'}
assert json.loads(s.runtime_probe_json)['sionna_rt']=='2.1.0'
assert s.refresh_scene_before_run
b._ensure_bundled_geometry_nodes(verbose=False)
env=b._ensure_environment(scene)
bpy.ops.sionna_bridge.create_default_materials()
# Reflecting ground below a free-space link. It also exercises ITU materials.
mesh=bpy.data.meshes.new('Ground');mesh.from_pydata([(-20,-20,-1),(20,-20,-1),(20,20,-1),(-20,20,-1)],[],[(0,1,2,3)])
floor=bpy.data.objects.new('Ground',mesh);env['scene'].objects.link(floor)
mesh.materials.append(bpy.data.materials['itu_concrete'])
for role in ['TX','TX','RX','RX']:bpy.ops.sionna_bridge.add_device(role=role)
tx=b._device_objects(scene,'TX');rx=b._device_objects(scene,'RX')
for o,p in zip(tx+rx,[(-2,0,3),(2,0,3),(0,0,1),(0,2,1)]):o.location=p
s.samples_per_src=32768;s.max_num_paths_per_src=4096;s.max_depth=2
s.timeline_mode='CURRENT';s.export_format='HDF5';s.export_geometry_nodes_metadata=True
s.tx_array_rows=2;s.tx_array_cols=2;s.rx_array_rows=1;s.rx_array_cols=2
s.radio_map_size_x=2;s.radio_map_size_y=2;s.radio_map_cell_size_x=1;s.radio_map_cell_size_y=1;s.radio_map_height=1
s.radio_map_3d_size_x=2;s.radio_map_3d_size_y=2;s.radio_map_3d_size_z=1
s.radio_map_3d_cell_size_x=1;s.radio_map_3d_cell_size_y=1;s.radio_map_3d_cell_size_z=.5;s.radio_map_3d_center_z=1.25
s.radio_map_replace_existing=False;s.radio_map_3d_replace_existing=False
checks=[]
def wait_run():
    deadline=time.monotonic()+180
    while any(x.get('process') for x in (b._RUN_STATE,b._RADIO_MAP_STATE,b._RADIO_MAP_3D_STATE)):
        assert time.monotonic()<deadline, s.last_status_details
        for state,poll in [(b._RUN_STATE,b._poll_sionna_process),(b._RADIO_MAP_STATE,b._poll_radio_map_process),(b._RADIO_MAP_3D_STATE,b._poll_radio_map_3d_process)]:
            if state.get('process') and state['process'].poll() is not None:poll()
        time.sleep(.03)
    assert not b._BATCH_STATE['active'],b._BATCH_STATE
    assert 'rejected' not in s.last_status.lower() and 'error' not in s.last_status.lower(), (s.last_status,s.last_status_details)
    assert not b._active_run_lock_path(s).exists()

def run(label):
    assert bpy.ops.sionna_bridge.run_selected()=={'FINISHED'}
    wait_run();checks.append(label);print('WORKFLOW_PASS',label,flush=True)

s.simulation_mode='BATCH';s.simulate_paths=True;s.simulate_radio_map=True;s.simulate_radio_map_3d=True
run('paths + 2D + 3D / HDF5 / multiple TX-RX / antenna arrays')
export=Path(s.last_export_path);assert export.is_file() and export.suffix=='.h5'
meta=json.loads(Path(s.last_export_metadata_path).read_text(encoding='utf-8'))
assert set(meta['categories'])=={'paths','coverage_2d','coverage_3d'},meta.keys()
for source in ['PATHS','RADIO_MAP','RADIO_MAP_3D']:
    s.analytics_source=source;s.analytics_scope='ALL'
    summary=b._refresh_analytics_cache(scene)
    dashboard,_=b._write_analytics_dashboard(scene);assert dashboard.is_file()
    obj=b._analytics_target_object(scene,source);assert obj is not None
    assert obj.modifiers[0].node_group
    ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());assert ev is not None
study=b._parameter_study.selected_study(b,scene);assert len(study['records'])==4
assert all(r['metrics']['path_count']>0 for r in study['records'])
assert b._parameter_study.write_selected(b,scene).is_file()
checks.append('all analytics dashboards and embedded results')
# Same geometry/seed; RSS and SINR selected independently for both map types.
s.simulate_paths=False;s.export_format='CSV'
for metric in ['rss','sinr']:
    s.radio_map_metric=metric;s.radio_map_3d_metric=metric
    run('2D + 3D '+metric)
# Projected measurement uses an explicit mesh outside propagation geometry.
s.simulation_mode='RADIO_MAP';s.radio_map_surface_mode='PROJECTED'
measure_mesh=bpy.data.meshes.new('Measurement surface');measure_mesh.from_pydata([(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)],[],[(0,1,2),(0,2,3)])
measure=bpy.data.objects.new('Measurement surface',measure_mesh);scene.collection.objects.link(measure)
s.radio_map_reference_mesh=measure
run('projected mesh radio map')
obj=b._analytics_target_object(scene,'RADIO_MAP');assert len(obj.data.vertices)==2
# A saved Blender result retains values without intermediate worker files.
s.simulation_mode='PATHS';s.export_format='NONE';s.export_geometry_nodes_metadata=False
s.timeline_mode='RANGE';scene.frame_start=1;scene.frame_end=2;s.enable_mobility_doppler=True
for f,x in [(1,0),(2,.1)]:rx[0].location.x=x;rx[0].keyframe_insert(data_path='location',frame=f)
scene.frame_set(1)
run('animated paths / Doppler / embedded-only output')
obj=b._analytics_target_object(scene,'PATHS');study=b._parameter_study.dataset_from_object(obj)
assert study['result_frames']==2 and len(study['records'])==8
assert any((r['metrics'].get('max_abs_doppler_hz') or 0)>0 for r in study['records'])
assert not s.last_run_dir
# Grid samples are defined in world coordinates and follow a movable helper.
s.motion_template_grid_rows=2;s.motion_template_grid_columns=3;s.motion_template_start_frame=4
s.motion_template_device=rx[1]
grid,start,end,count=b._create_grid_motion_template(bpy.context,rx[1],s)
positions=b._sample_device_world_positions(bpy.context,list(range(start,end+1)),[rx[1]])
assert count==6 and end==9
b._remove_motion_template_for_device(rx[1])
# Point cloud path follows transformed points without exporting its helper.
pc=bpy.data.pointclouds.new('Motion points');pc.resize(3)
for p,co in zip(pc.points,[(0,0,1),(1,0,1),(2,0,1)]):p.co=co
po=bpy.data.objects.new('Motion points',pc);scene.collection.objects.link(po);po.location=(3,0,0)
s.motion_template_pointcloud=po;s.motion_template_style='POINT_CLOUD';s.motion_template_start_frame=1
b._create_pointcloud_motion_template(bpy.context,rx[1],s)
scene.frame_set(2);b._apply_pointcloud_motion_for_device(scene,rx[1]);bpy.context.view_layer.update()
assert (rx[1].matrix_world.translation-b.Vector((4,0,1))).length<1e-5,tuple(rx[1].matrix_world.translation)
b._remove_motion_template_for_device(rx[1]);checks.append('grid and point-cloud motion')
# Stop operator retains partial files and clears queued outputs/locks.
s.timeline_mode='CURRENT';s.samples_per_src=1000000
assert bpy.ops.sionna_bridge.run_selected()=={'FINISHED'}
process=b._RUN_STATE['process'];run_dir=Path(b._RUN_STATE['run_dir'])
assert bpy.ops.sionna_bridge.cancel_run()=={'FINISHED'}
assert process.poll() is not None and b._processes_idle() and not b._BATCH_STATE['active']
assert json.loads((run_dir/'status.json').read_text())['state']=='cancelled'
assert run_dir.exists() and not b._active_run_lock_path(s).exists()
checks.append('cancel and ownership cleanup')
# Opening another .blend / disabling add-on must not orphan its worker.
s.samples_per_src=32768
save=out/'release_results.blend';bpy.ops.wm.save_as_mainfile(filepath=str(save))
assert bpy.ops.sionna_bridge.run_selected()=={'FINISHED'}
loading_process=b._RUN_STATE['process']
bpy.ops.wm.open_mainfile(filepath=str(save));scene=bpy.context.scene;s=scene.sionna_bridge
assert loading_process.poll() is not None and b._processes_idle()
assert len(b._parameter_study.selected_study(b,scene)['records'])==8
assert bpy.ops.sionna_bridge.run_selected()=={'FINISHED'}
process=b._RUN_STATE['process'];b.unregister();assert process.poll() is not None
checks.append('save/reopen and disable while running')
(out/'test_report.json').write_text(json.dumps({'checks':checks,'blender':bpy.app.version_string,'bridge':b._ADDON_VERSION},indent=2))
print('RELEASE_WORKFLOWS_PASS',flush=True)
