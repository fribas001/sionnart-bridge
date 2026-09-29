"""Factory-startup Blender test; generates native worker configs and a demo scene."""
import bpy,importlib.util,json,math,sys
from pathlib import Path
from types import SimpleNamespace
root=Path(__file__).resolve().parents[1]
out=Path(sys.argv[sys.argv.index('--')+1]).resolve();out.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('plant_test',root/'__init__.py',submodule_search_locations=[str(root)])
b=importlib.util.module_from_spec(spec);sys.modules[spec.name]=b;spec.loader.exec_module(b);b.register()
scene=bpy.context.scene;s=scene.sionna_bridge;s.workspace_dir=str(out);s.export_format='NONE';s.export_geometry_nodes_metadata=True
s.timeline_mode='RANGE';scene.frame_start=1;scene.frame_end=3
env=b._ensure_environment(scene)
assert bpy.ops.sionna_bridge.create_default_materials()=={'FINISHED'}
assert bpy.ops.sionna_bridge.select_plant_material()=={'FINISHED'}
leaf=s.material_selection;wood=bpy.data.materials['itu_plant_branch_p833']
assert leaf.name=='itu_plant_leaf_p833' and leaf.sionna_radio.model=='VEGETATION'
assert math.isclose(leaf.sionna_radio.thickness,.0002,rel_tol=1e-6)
leaf.sionna_radio.scattering_coefficient=.23
b._ensure_default_sionna_materials()
assert math.isclose(leaf.sionna_radio.scattering_coefficient,.23,rel_tol=1e-6)
leaf.sionna_radio.scattering_coefficient=0
assert bpy.ops.sionna_bridge.plant_solver_settings()=={'FINISHED'}
assert s.enable_reflection and s.enable_refraction and s.enable_diffuse
assert bpy.ops.sionna_bridge.plant_material_reference()=={'FINISHED'}
assert any(t.get('sionna_plant_guide') for t in bpy.data.texts)
bpy.ops.sionna_bridge.add_device(role='TX');bpy.ops.sionna_bridge.add_device(role='RX')
tx=b._device_objects(scene,'TX');rx=b._device_objects(scene,'RX');tx[0].location=(-2,0,2);rx[0].location=(2,0,2)

# A leaf plane exists OUTSIDE the simulation collection and is brought in as
# a GN instance. The un-instanced source itself must not be exported twice.
mesh=bpy.data.meshes.new('LeafPlane');mesh.from_pydata([(0,-1,1),(0,1,1),(0,1,3),(0,-1,3)],[],[(0,1,2,3)]);mesh.materials.append(leaf)
mesh.materials.append(bpy.data.materials['itu_glass'])  # Unused slot must not reach the worker.
source=bpy.data.objects.new('LeafSource',mesh);scene.collection.objects.link(source)
generator=bpy.data.objects.new('Plant',bpy.data.meshes.new('PlantMesh'));env['procedural_geometry'].objects.link(generator)
group=bpy.data.node_groups.new('Plant Instances','GeometryNodeTree');group.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
node=group.nodes.new('GeometryNodeObjectInfo');node.inputs['Object'].default_value=source;node.inputs['As Instance'].default_value=True
output=group.nodes.new('NodeGroupOutput');group.links.new(node.outputs['Geometry'],output.inputs['Geometry'])
mod=generator.modifiers.new('Plant Nodes','NODES');mod.node_group=group
# Wood is deliberately outside the direct link to exercise a second material.
woodmesh=bpy.data.meshes.new('WoodPlane');woodmesh.from_pydata([(-1,4,0),(1,4,0),(1,4,2),(-1,4,2)],[],[(0,1,2,3)]);woodmesh.materials.append(wood)
woodobj=bpy.data.objects.new('WoodProxy',woodmesh);env['procedural_geometry'].objects.link(woodobj)
for frame,freq in [(1,5.8),(2,26.),(3,30.)]:
    s.frequency_ghz=freq;s.keyframe_insert(data_path='frequency_ghz',frame=frame)
scene.frame_set(1);bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
assert len(generator.evaluated_get(dg).data.materials)==0
materials=b._material_payloads(scene,dg)
assert {m['blender_name'] for m in materials}=={leaf.name,wood.name},materials
for sample in [lambda:b._sample_frame_payloads(bpy.context,[1,2,3],tx,rx),lambda:b._sample_radio_map_frame_payloads(bpy.context,[1,2,3],tx,out),lambda:b._sample_radio_map_3d_frame_payloads(bpy.context,[1,2,3],tx)]:
    for f in sample():
        for m in f['materials']:
            expected=b._plant_materials.dielectric(m['plant_model'],f['simulation']['frequency_hz'])
            assert math.isclose(m['relative_permittivity'],expected[0],rel_tol=1e-8)
            assert math.isclose(m['conductivity'],expected[1],rel_tol=1e-8)
            assert m['plant_reference']['frequency_hz']==f['simulation']['frequency_hz']
s.procedural_geometry_enabled=True
scene_source=b._export_procedural_scene_frames(bpy.context,[1,2,3])
for category,build in [('paths',b._build_run_package),('coverage_2d',b._build_radio_map_package),('coverage_3d',b._build_radio_map_3d_package)]:
    run,path,config,*_=build(bpy.context,scene_source)
    (out/(category+'_config.json')).write_text(json.dumps(config,indent=2),encoding='utf-8')
    assert all(len(f['materials'])==2 for f in config['frames'])

class Layout:
    def __getattr__(self,name):
        if name in {'row','column','box','split','grid_flow'}:return lambda *a,**k:Layout()
        if name in {'label','separator','template_list','template_ID','menu','popover'}:return lambda *a,**k:None
        raise AttributeError(name)
    def prop(self,data,name,**kw):assert hasattr(data,name),name
    def prop_search(self,data,name,*a,**kw):assert hasattr(data,name),name
    def operator(self,name,**kw):
        owner,op=name.split('.');getattr(getattr(bpy.ops,owner),op).get_rna_type();return SimpleNamespace()
for material in [leaf,wood]:
    s.material_selection=material
    for cls in b._UI_CLASSES:cls.draw(SimpleNamespace(layout=Layout()),bpy.context)
bpy.ops.wm.save_as_mainfile(filepath=str(out/'plant_materials.blend'))
bpy.ops.wm.open_mainfile(filepath=str(out/'plant_materials.blend'))
assert bpy.data.materials['itu_plant_leaf_p833'].sionna_radio.model=='VEGETATION'
b.unregister()
print('BLENDER_PLANT_MATERIALS_PASS')
