"""Run in factory-startup Blender 5.2, with an output directory after --."""
import bpy
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
out = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
out.mkdir(parents=True, exist_ok=True)
spec = importlib.util.spec_from_file_location('submission_test', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
b = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = b
spec.loader.exec_module(b)
b.register()
scene = bpy.context.scene
s = scene.sionna_bridge
s.workspace_dir = str(out)
s.dynamic_mode = False
s.export_format = 'NONE'
s.timeline_mode = 'RANGE'
s.timeline_step = 1
s.samples_per_src = 256
s.max_num_paths_per_src = 256
scene.frame_start = 1
scene.frame_end = 2
assert s.export_geometry_nodes_metadata is False
assert not any('ris' in p.identifier.lower() or 'pointset' in p.identifier.lower() for p in s.bl_rna.properties)
assert not any('ris' in c.__name__.lower() or 'pointset' in c.__name__.lower() for c in b._CLASSES)
env = b._ensure_environment(scene)
assert bpy.ops.sionna_bridge.add_device(role='TX') == {'FINISHED'}
assert bpy.ops.sionna_bridge.add_device(role='RX') == {'FINISHED'}
txs = b._device_objects(scene, 'TX')
rxs = b._device_objects(scene, 'RX')
txs[0].location = (-2, 0, 2)
rxs[0].location = (2, 0, 2)
nested = bpy.data.collections.new('Vegetation \u00e1')
env['procedural_geometry'].children.link(nested)
mesh = bpy.data.meshes.new('PlantMesh')
mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)], [], [(0,1,2)])
obj = bpy.data.objects.new('Plant', mesh)
nested.objects.link(obj)
group = bpy.data.node_groups.new('Procedural Plant', 'GeometryNodeTree')
group.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
group.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
ni = group.nodes.new('NodeGroupInput')
no = group.nodes.new('NodeGroupOutput')
group.links.new(ni.outputs['Geometry'], no.inputs['Geometry'])
sockets = {}
for name, kind in [('Growth','Float'),('Seed','Int'),('Enabled','Bool'),('Direction','Vector'),('Color','Color'),('Label','String'),('Reference','Object'),('Density','Float'),('Driven','Float')]:
    sockets[name] = group.interface.new_socket(name=name, in_out='INPUT', socket_type='NodeSocket'+kind)
mod = obj.modifiers.new('Plant Parameters', 'NODES')
mod.node_group = group
def prop(name):
    return getattr(mod.properties.inputs, sockets[name].identifier)
for name,value in [('Seed',77),('Enabled',True),('Direction',(1,2,3)),('Color',(0.1,0.2,0.3,1)),('Label','Oak \u00e1'),('Reference',txs[0])]:
    prop(name).value = value
for frame,value in [(1,0.25),(2,0.75)]:
    prop('Growth').value = value
    prop('Growth').keyframe_insert(data_path='value', frame=frame)
prop('Density').type = 'ATTRIBUTE'
prop('Density').attribute_name = 'leaf_density'
prop('Driven').driver_add('value').driver.expression = 'frame * 0.5'
literal = group.nodes.new('ShaderNodeValue')
literal.name = 'Animated Value'
for frame,value in [(1,10.0),(2,20.0)]:
    literal.outputs[0].default_value = value
    literal.outputs[0].keyframe_insert(data_path='default_value', frame=frame)
inner = bpy.data.node_groups.new('Nested Parameters', 'GeometryNodeTree')
inner_node = inner.nodes.new('ShaderNodeMath')
inner_node.inputs[0].default_value = 9.0
group.nodes.new('GeometryNodeGroup').node_tree = inner
disabled = obj.modifiers.new('Disabled Parameters', 'NODES')
disabled.node_group = group
disabled.show_viewport = False
disabled.show_render = False
outside = bpy.data.objects.new('Not In Simulation Scene', mesh.copy())
scene.collection.objects.link(outside)
outside.modifiers.new('Ignore Me','NODES').node_group = group
bpy.context.view_layer.objects.active = obj
obj.select_set(True)
scene.frame_set(8, subframe=0.25)
bpy.context.view_layer.update()

samplers = [lambda: b._sample_frame_payloads(bpy.context,[1,2],txs,rxs),
            lambda: b._sample_radio_map_frame_payloads(bpy.context,[1,2],txs,out),
            lambda: b._sample_radio_map_3d_frame_payloads(bpy.context,[1,2],txs)]
for sample in samplers:
    assert all('geometry_nodes_parameters' not in p for p in sample())
s.export_geometry_nodes_metadata = True
for sample in samplers:
    frames = sample()
    assert scene.frame_current == 8 and scene.frame_subframe == 0.25
    for f in frames:
        data = f['geometry_nodes_parameters']
        assert [o['object']['name'] for o in data['objects']] == ['Plant'], data['objects']
        assert len(data['node_groups']) == 2
        mods = data['objects'][0]['modifiers']
        assert len(mods) == 2 and mods[1]['show_viewport'] is False
        values = {x['name']:x for x in mods[0]['inputs']}
        assert values['Growth']['value'] == {1:0.25,2:0.75}[f['frame']], values
        assert abs(values['Driven']['value'] - f['frame'] * 0.5) < 1e-6, values['Driven']
        assert values['Seed']['value'] == 77
        assert values['Enabled']['value'] is True
        assert values['Direction']['value'] == [1.0,2.0,3.0]
        assert values['Label']['value'] == 'Oak \u00e1'
        assert values['Reference']['value']['datablock']['name'] == txs[0].name
        assert values['Density']['value'] is None and values['Density']['attribute_name'] == 'leaf_density'
        nodes = data['node_groups'][mods[0]['node_group']]['nodes']
        lit = next(n for n in nodes if n['name'] == 'Animated Value')
        assert lit['literal_outputs'][0]['value'] == f['frame'] * 10, lit
        assert not data['warnings'], data['warnings']
        json.dumps(data, allow_nan=False)

# Exercise actual scene export and all three package builders. Keep metadata
# after normal completion cleanup; copying config allows worker regression too.
s.procedural_geometry_enabled = True
source = b._export_procedural_scene_frames(bpy.context, [1,2])
builders = [b._build_run_package, b._build_radio_map_package, b._build_radio_map_3d_package]
configs = []
for build in builders:
    run,path,config,*unused = build(bpy.context,source)
    descriptor = config['geometry_nodes_metadata']
    manifest_path = Path(descriptor['manifest_json'])
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert len(manifest['frames']) == 2
    for f in manifest['frames']:
        snapshot = json.loads((manifest_path.parent/f['file']).read_text(encoding='utf-8'))
        assert snapshot['run_id'] == config['output']['export_run_id']
        assert snapshot['frame'] == f['frame']
        assert snapshot['scene_source']['sha256']
        assert snapshot['scene_source']['evaluated_per_frame'] is True
        assert snapshot['time_seconds'] is not None
    saved = out / (descriptor['simulation_category'] + '_config.json')
    saved.write_text(json.dumps(config,indent=2),encoding='utf-8')
    configs.append(str(saved))
    note = b._cleanup_external_run(run,s,export_format='NONE',geometry_nodes_metadata=str(manifest_path))
    assert not run.exists() and manifest_path.exists()
    assert 'Geometry Nodes JSON retained' in note
s.export_geometry_nodes_metadata = False
run,path,config,*unused = b._build_run_package(bpy.context,source)
assert 'geometry_nodes_metadata' not in config and 'geometry_nodes_metadata_json' not in config['output']
b._cleanup_external_run(run,s,export_format='NONE')

# Invoke every panel draw against a layout that checks RNA/property/operator
# references. This catches stale UI references after feature removal.
class Layout:
    def __getattr__(self,name):
        if name in {'row','column','box','split','grid_flow'}:
            return lambda *a,**k: Layout()
        if name in {'label','separator','template_list','template_ID','menu','popover'}:
            return lambda *a,**k: None
        raise AttributeError(name)
    def prop(self,data,name,**kwargs):
        assert hasattr(data,name), name
    def prop_search(self,data,name,*args,**kwargs):
        assert hasattr(data,name), name
    def operator(self,name,**kwargs):
        owner,op = name.split('.')
        getattr(getattr(bpy.ops,owner),op).get_rna_type()
        return SimpleNamespace()
for mode in ['PATHS','RADIO_MAP','RADIO_MAP_3D','BATCH']:
    s.simulation_mode = mode
    for cls in b._UI_CLASSES:
        cls.draw(SimpleNamespace(layout=Layout()),bpy.context)
b.unregister()
b.register()
b.unregister()
(out/'test_report.json').write_text(json.dumps({'blender':bpy.app.version_string,'bridge':b._ADDON_VERSION,'checks':'registration, feature removal, all UI modes, animated/driver/nested/disabled Geometry Nodes, frame restore, all three run packages, opt-out, cleanup retention','worker_configs':configs},indent=2))
print('GEOMETRY_METADATA_BLENDER_PASS')
