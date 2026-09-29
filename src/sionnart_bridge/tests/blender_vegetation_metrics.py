"""Analytical mesh/instance integration checks in factory-startup Blender."""
import bpy, importlib.util, sys, json, math
from pathlib import Path
root=Path(__file__).resolve().parents[1]
out=Path(sys.argv[sys.argv.index('--')+1]).resolve();out.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('veg_test',root/'__init__.py',submodule_search_locations=[str(root)])
b=importlib.util.module_from_spec(spec);sys.modules[spec.name]=b;spec.loader.exec_module(b);b.register()
scene=bpy.context.scene;s=scene.sionna_bridge;s.workspace_dir=str(out)
env=b._ensure_environment(scene);b._ensure_default_sionna_materials()
leaf=bpy.data.materials['itu_plant_leaf_p833'];wood=bpy.data.materials['itu_plant_branch_p833']

# Two 1 m2 leaf quads and a 2 x 2 x 2 m wood box, one procedural object.
vertices=[];faces=[]
for x in [-.5,.5]:
    start=len(vertices);vertices.extend([(x,-.5,1),(x,.5,1),(x,.5,2),(x,-.5,2)]);faces.append(tuple(range(start,start+4)))
vertices.extend([(-1,-1,0),(1,-1,0),(1,1,0),(-1,1,0),(-1,-1,2),(1,-1,2),(1,1,2),(-1,1,2)])
faces.extend([tuple(v+8 for v in f) for f in [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]])
mesh=bpy.data.meshes.new('KnownTree');mesh.from_pydata(vertices,[],faces);mesh.materials.append(leaf);mesh.materials.append(wood)
for p in mesh.polygons:p.material_index=0 if p.index<2 else 1
ids=mesh.attributes.new('sionna_leaf_id','INT','FACE')
for i,item in enumerate(ids.data):item.value=i+7 if i<2 else 0
tree=bpy.data.objects.new('Tree',mesh);env['procedural_geometry'].objects.link(tree)
group=bpy.data.node_groups.new('Measured Geometry','GeometryNodeTree')
group.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
group.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
ni=group.nodes.new('NodeGroupInput');no=group.nodes.new('NodeGroupOutput');tr=group.nodes.new('GeometryNodeTransform')
group.links.new(ni.outputs['Geometry'],tr.inputs['Geometry']);group.links.new(tr.outputs['Geometry'],no.inputs['Geometry'])
mod=tree.modifiers.new('Vegetation nodes','NODES');mod.node_group=group
bpy.context.view_layer.update()
tx={'name':'TX','blender_name':'Transmitter','position':[-2,0,1.5]}
rx={'name':'RX','blender_name':'Receiver','position':[2,0,1.5]}
def capture():
    bpy.context.view_layer.update()
    return b._vegetation.capture(b,bpy.context,bpy.context.evaluated_depsgraph_get(),[tx],[rx])
d=capture();m=d['objects'][0]['metrics'];l=d['links'][0]['metrics']
for key,value in {'leaf_area_estimate_m2':2,'wood_surface_area_m2':24,'leaf_component_count':2,'tagged_leaf_count':2,'vegetation_bounds_volume_m3':8,'leaf_area_density_bbox_m_inv':.25,'leaf_area_index_bbox':.5}.items():assert math.isclose(m[key],value), (key,m)
for key,value in {'leaf_surface_crossings':2,'wood_surface_crossings':2,'vegetation_bounds_length_m':2,'corridor_leaf_area_m2':2,'corridor_volume_m3':4,'corridor_leaf_area_density_m_inv':.5}.items():assert math.isclose(l[key],value), (key,l)
assert bpy.ops.sionna_bridge.vegetation_measurements()=={'FINISHED'}
# Geometry Nodes transform, including a mirror/nonuniform scaling, must affect
# measured world areas and preserve face ID counts.
tr.inputs['Scale'].default_value=(-1,2,3)
scaled=capture()['objects'][0]['metrics']
assert math.isclose(scaled['leaf_area_estimate_m2'],12)
assert scaled['tagged_leaf_count']==2
tr.inputs['Scale'].default_value=(1,1,1)
# Out-of-scope and render-hidden duplicates cannot inflate the vegetation totals.
outside=bpy.data.objects.new('Outside',mesh.copy());scene.collection.objects.link(outside)
hidden=bpy.data.objects.new('Hidden',mesh.copy());env['scene'].objects.link(hidden);hidden.hide_render=True
assert len(capture()['objects'])==1
# Distinct links and per-frame export; the first receiver intersects leaves,
# while a second receiver does not. Enable actual result export round-trip.
bpy.ops.sionna_bridge.add_device(role='TX');bpy.ops.sionna_bridge.add_device(role='RX');bpy.ops.sionna_bridge.add_device(role='RX')
txs=b._device_objects(scene,'TX');rxs=b._device_objects(scene,'RX')
txs[0].location=tx['position'];rxs[0].location=rx['position'];rxs[1].location=(-2,3,1.5)
s.procedural_geometry_enabled=True;s.export_geometry_nodes_metadata=True;s.parameter_analysis_enabled=True
s.export_format='CSV';s.timeline_mode='RANGE';scene.frame_start=1;scene.frame_end=2
s.samples_per_src=10000;s.max_num_paths_per_src=10000;s.max_depth=3
source=b._export_procedural_scene_frames(bpy.context,[1,2])
run,config_path,config,*_=b._build_run_package(bpy.context,source)
assert all(f['vegetation_metrics']['status']=='complete' for f in config['frames'])
for f in config['frames']:
    record=json.loads(Path(f['geometry_nodes_metadata_file']).read_text(encoding='utf-8'))
    assert record['vegetation_metrics']==f['vegetation_metrics']
    values=f['parameter_study_inputs']['parameters']
    assert values['vegetation/object/Tree/tagged_leaf_count']['value']==2
    assert len(f['parameter_study_inputs']['vegetation_links'])==2
(out/'paths_config.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
(out/'measurements.json').write_text(json.dumps(d,indent=2),encoding='utf-8')
assert scene.frame_current==1
b.unregister()
print('BLENDER_VEGETATION_METRICS_PASS')
