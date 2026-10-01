"""Native oriented-map solver, CSV/HDF5, animation and Geometry Nodes checks.

Run in factory-startup Blender; output directory and Sionna Python after --.
"""
import bpy
import importlib.util
import json
import math
import sys
import time
from pathlib import Path
import numpy as np
from mathutils import Euler, Vector

root = Path(__file__).resolve().parents[1]
out = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
out.mkdir(parents=True, exist_ok=True)
python = sys.argv[sys.argv.index('--') + 2]
spec = importlib.util.spec_from_file_location('orientation_test_addon', root/'__init__.py', submodule_search_locations=[str(root)])
b = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = b
spec.loader.exec_module(b)
b.register()
scene = bpy.context.scene
s = scene.sionna_bridge
s.workspace_dir = str(out)
s.runtime_mode = 'EXTERNAL'
s.sionna_python = python
assert s.radio_map_plane == 'XY'
b._ensure_bundled_geometry_nodes(verbose=False)
env = b._ensure_environment(scene)
bpy.ops.sionna_bridge.create_default_materials()
mesh = bpy.data.meshes.new('Ground')
mesh.from_pydata([(-20,-20,-1),(20,-20,-1),(20,20,-1),(-20,20,-1)], [], [(0,1,2,3)])
ground = bpy.data.objects.new('Ground', mesh)
env['scene'].objects.link(ground)
mesh.materials.append(bpy.data.materials['itu_concrete'])
bpy.ops.sionna_bridge.add_device(role='TX')
tx = b._device_objects(scene, 'TX')[0]
tx.location = (-4,-5,7)
s.samples_per_src = 65536
s.max_depth = 1
s.timeline_mode = 'CURRENT'
s.simulation_mode = 'RADIO_MAP'
s.export_geometry_nodes_metadata = True
s.radio_map_replace_existing = False
s.radio_map_center_x = 1
s.radio_map_center_y = 2
s.radio_map_height = 3
s.radio_map_size_x = 4
s.radio_map_size_y = 3
s.radio_map_cell_size_x = 2
s.radio_map_cell_size_y = 1
records = []


def run(label):
    assert bpy.ops.sionna_bridge.run_selected() == {'FINISHED'}
    deadline = time.monotonic() + 180
    while b._RADIO_MAP_STATE.get('process'):
        assert time.monotonic() < deadline, s.last_status_details
        if b._RADIO_MAP_STATE['process'].poll() is not None:
            b._poll_radio_map_process()
        time.sleep(.03)
    assert 'error' not in s.last_status.lower() and 'rejected' not in s.last_status.lower(), (s.last_status, s.last_status_details)
    obj = b._analytics_target_object(scene, 'RADIO_MAP')
    assert obj is not None
    records.append({'label': label, 'export': s.last_export_path, 'metadata': s.last_export_metadata_path,
                    'object': obj.name})
    print('ORIENTATION_RUN', label, flush=True)
    return obj


def check_geometry(obj, xyz, frame=1):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    rotation = Euler(xyz, 'XYZ').to_matrix()
    basis = np.asarray(rotation, dtype=float)
    expected = np.array([Vector((1,2,3)) + rotation @ Vector((u,v,0)) for v in (-1,0,1) for u in (-1,1)])
    points = np.array([v.co[:] for v in obj.data.vertices])
    frames = np.array([v.value for v in obj.data.attributes['frame'].data])
    np.testing.assert_allclose(points[frames == frame], expected, atol=2e-5)
    normals = np.array([v.vector[:] for v in obj.data.attributes['surface_normal'].data])
    np.testing.assert_allclose(normals[frames == frame], np.tile(basis[:,2], (6,1)), atol=2e-6)
    rotations = np.array([v.vector[:] for v in obj.data.attributes['map_rotation'].data])
    np.testing.assert_allclose(rotations[frames == frame], np.tile(xyz, (6,1)), atol=2e-6)
    metric = obj['sionna_metric_db_attribute']
    assert any(v.value > -200 for v in obj.data.attributes[metric].data), metric
    mod = obj.modifiers[0]
    for socket in mod.node_group.interface.items_tree:
        if socket.item_type == 'SOCKET' and 'greater than' in socket.name:
            getattr(mod.properties.inputs, socket.identifier).value = -301.0
    obj.update_tag()
    bpy.context.view_layer.update()
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    result = evaluated.to_mesh()
    try:
        assert len(result.polygons) == 6, (len(result.vertices), len(result.polygons))
        coords = np.array([v.co[:] for v in result.vertices])
        local = (coords - [1,2,3]) @ basis
        np.testing.assert_allclose(local[:,2], 0, atol=2e-5)
        np.testing.assert_allclose(local[:,:2].min(axis=0), [-2,-1.5], atol=2e-5)
        np.testing.assert_allclose(local[:,:2].max(axis=0), [2,1.5], atol=2e-5)
        for face in result.polygons:
            f = local[list(face.vertices)]
            np.testing.assert_allclose(np.ptp(f, axis=0), [2,1,0], atol=2e-5)
    finally:
        evaluated.to_mesh_clear()


custom = tuple(math.radians(v) for v in (23,-17,31))
for plane, xyz, metric, export in [
    ('XY', (0,0,0), 'path_gain', 'CSV'),
    ('XZ', (math.pi/2,0,0), 'path_gain', 'HDF5'),
    ('YZ', (math.pi/2,0,math.pi/2), 'path_gain', 'HDF5'),
    ('CUSTOM', custom, 'path_gain', 'HDF5'),
    ('XZ', (math.pi/2,0,0), 'rss', 'CSV'),
    ('YZ', (math.pi/2,0,math.pi/2), 'sinr', 'CSV'),
]:
    s.radio_map_plane = plane
    s.radio_map_metric = metric
    s.export_format = export
    for axis, value in zip('xyz', xyz):
        setattr(s, 'radio_map_rotation_' + axis, value)
    obj = run(plane + ' ' + metric)
    check_geometry(obj, xyz)
    # Project live TX centering into the plane, retaining its normal coordinate.
    p = b._radio_map_settings_payload(s)
    b._auto_center_radio_map_payload(p, scene, bpy.context.evaluated_depsgraph_get(), tx.name)
    moved = Vector((p['center_x'], p['center_y'], p['height']))
    normal = Euler(xyz, 'XYZ').to_matrix().col[2]
    assert abs((moved-Vector((1,2,3))).dot(normal)) < 2e-5

# Rotation animation alone must trigger AUTO frame selection and orient every frame.
s.radio_map_plane = 'CUSTOM'
s.radio_map_metric = 'path_gain'
s.export_format = 'HDF5'
scene.frame_start = 1
scene.frame_end = 2
s.timeline_mode = 'AUTO'
for frame, xyz in [(1, (0,0,0)), (2, custom)]:
    for axis, value in zip('xyz', xyz):
        setattr(s, 'radio_map_rotation_' + axis, value)
        s.keyframe_insert(data_path='radio_map_rotation_' + axis, frame=frame)
scene.frame_set(1)
assert b._radio_map_parameters_change(bpy.context, [1,2])
obj = run('animated custom')
assert len(obj.data.vertices) == 12
check_geometry(obj, (0,0,0), 1)
check_geometry(obj, custom, 2)
save = out/'oriented_radio_maps.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(save))
obj_name = obj.name
bpy.ops.wm.open_mainfile(filepath=str(save))
scene = bpy.context.scene
check_geometry(bpy.data.objects[obj_name], custom, 2)
(out/'orientation_checks.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
b.unregister()
print('ALL_ORIENTATION_CHECKS_PASS', flush=True)
