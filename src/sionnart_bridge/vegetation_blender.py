"""Measure final evaluated vegetation surfaces in the actual export scope."""
import json
import numpy as np
import bpy
from . import vegetation_metrics as vm


def capture(bridge, context, depsgraph, transmitters=(), receivers=()):
    settings = context.scene.sionna_bridge
    result = {'schema':vm.SCHEMA,'schema_version':1,'frame':int(context.scene.frame_current),
              'status':'complete','settings':{'corridor_width_m':float(settings.vegetation_corridor_width),
              'leaf_area_convention':settings.vegetation_leaf_area_convention,
              'length_convention':'Blender world coordinates interpreted as metres, matching scene export',
              'bounds':'world-axis-aligned bounds of vegetation faces per generating object',
              'corridor':'square prism, straight TX-RX segment, includes empty space',
              'leaf_ids':'positive FACE-domain integer sionna_leaf_id; unique per biological leaf within each evaluated mesh'},
              'warnings':[]}
    workflow = bridge._find_environment(context.scene)
    if not workflow:
        return {**result,**vm.measure_packets([],transmitters,receivers,settings.vegetation_corridor_width)}
    exporter = bridge._integrated_exporter_module()
    sources = bridge._scene_export_objects(context.scene)
    pointers = {exporter._object_pointer(o) for o in sources}
    packets = []
    cache = {}
    for inst in depsgraph.object_instances:
        obj = inst.object
        if not exporter._instance_is_selected(inst,pointers) or obj.hide_render: continue
        if not inst.is_instance:
            obj = exporter._fresh_evaluated_object(obj,depsgraph)
        if obj.type not in {'MESH','CURVE','SURFACE','FONT','META'}: continue
        owner = obj.original
        if inst.is_instance:
            parent = inst.parent
            while parent is not None:
                if exporter._object_pointer(parent) in pointers:
                    owner = parent.original; break
                parent = parent.parent
        key = obj.as_pointer()
        if key not in cache:
            mesh = None
            try:
                mesh = obj.to_mesh(preserve_all_data_layers=True,depsgraph=depsgraph)
                roles = []
                for material in mesh.materials:
                    config = getattr(material,'sionna_radio',None)
                    if material is not None and bridge._material_is_sionna(material) and config and config.model == 'VEGETATION':
                        roles.append('leaf' if config.plant_model == 'LEAF_P833' else 'wood')
                    else: roles.append(None)
                if not any(roles):
                    cache[key] = None
                    continue
                face_roles = [roles[p.material_index] if p.material_index < len(roles) else None for p in mesh.polygons]
                if not any(face_roles):
                    cache[key] = None
                    continue
                faces = [tuple(p.vertices) for p in mesh.polygons]
                ids = None
                attribute = mesh.attributes.get('sionna_leaf_id')
                if attribute is not None and attribute.domain == 'FACE' and attribute.data_type == 'INT':
                    ids = np.empty(len(mesh.polygons),dtype=np.int32);attribute.data.foreach_get('value',ids)
                factors,count,tagged,closed,nonmanifold = vm.leaf_topology(faces,face_roles,ids,settings.vegetation_leaf_area_convention)
                if tagged is None:
                    result['warnings'].append(f'{owner.name}: leaf count uses mesh islands; supplied leaf IDs are absent or incomplete.')
                if nonmanifold:
                    result['warnings'].append(f'{owner.name}: non-manifold leaf surfaces; check the leaf area convention and duplicate faces.')
                coordinates = np.empty(len(mesh.vertices)*3);mesh.vertices.foreach_get('co',coordinates)
                mesh.calc_loop_triangles()
                triangles = np.empty(len(mesh.loop_triangles)*3,dtype=np.int32);mesh.loop_triangles.foreach_get('vertices',triangles)
                polygons = np.empty(len(mesh.loop_triangles),dtype=np.int32);mesh.loop_triangles.foreach_get('polygon_index',polygons)
                cache[key] = {'coordinates':coordinates.reshape(-1,3),'triangles':triangles.reshape(-1,3),
                              'roles':np.asarray(face_roles,dtype=object)[polygons],'factors':factors[polygons],
                              'components':count,'tagged':tagged,'closed':closed}
            finally:
                if mesh is not None: obj.to_mesh_clear()
        data = cache[key]
        if data is None: continue
        matrix = np.asarray(inst.matrix_world.copy() if inst.is_instance else obj.matrix_world.copy(),dtype=float)
        coordinates = data['coordinates']@matrix[:3,:3].T + matrix[:3,3]
        tri = coordinates[data['triangles']]
        if not np.isfinite(tri).all(): raise ValueError(f'{owner.name}: non-finite vegetation coordinates')
        leaf_mask = data['roles']=='leaf';wood_mask = data['roles']=='wood'
        leaf_tri,wood_tri = tri[leaf_mask],tri[wood_mask]
        used = tri[leaf_mask|wood_mask].reshape(-1,3)
        if not len(used): continue
        leaf_areas = vm.areas(leaf_tri)
        owner_label = owner.name_full + (f' [{owner.library.filepath}]' if owner.library else '')
        packets.append({'owner':owner_label,'source':obj.original.name_full,
                        'lo':used.min(axis=0),'hi':used.max(axis=0),
                        'leaf_triangles':leaf_tri,'wood_triangles':wood_tri,'leaf_factors':data['factors'][leaf_mask],
                        'metrics':{'leaf_surface_area_m2':float(leaf_areas.sum()),
                        'leaf_area_estimate_m2':float(np.sum(leaf_areas*data['factors'][leaf_mask])),
                        'wood_surface_area_m2':float(vm.areas(wood_tri).sum()),
                        'leaf_component_count':data['components'],'tagged_leaf_count':data['tagged']}})
    result.update(vm.measure_packets(packets,transmitters,receivers,settings.vegetation_corridor_width))
    result['warnings'] = sorted(set(result['warnings']))
    return result


def capture_payload(bridge,context,depsgraph,payload):
    if not context.scene.sionna_bridge.vegetation_metrics_enabled: return
    try:
        payload['vegetation_metrics'] = capture(bridge,context,depsgraph,payload.get('transmitters',()),payload.get('receivers',()))
    except Exception as exc:
        # Do not silently export partial totals or turn an absent value into zero.
        payload['vegetation_metrics'] = {'schema':vm.SCHEMA,'schema_version':1,'frame':payload['frame'],
            'status':'error','objects':[],'scene':{},'links':[],
            'warnings':['Vegetation measurements unavailable: '+str(exc)]}


def preview(bridge,context):
    dg = context.evaluated_depsgraph_get()
    tx = [bridge._device_payload(o,dg) for o in bridge._device_objects(context.scene,'TX')]
    rx = [bridge._device_payload(o,dg) for o in bridge._device_objects(context.scene,'RX')]
    data = capture(bridge,context,dg,tx,rx)
    text = bpy.data.texts.get('Sionna Vegetation Measurements') or bpy.data.texts.new('Sionna Vegetation Measurements')
    lines = [f'Vegetation measurements — frame {data["frame"]}',
             'Evaluated mesh; Geometry Nodes and instances included.',
             'Leaf islands are count estimates. Bounds densities use a box envelope.',
             f'Link corridor width: {data["settings"]["corridor_width_m"]:g} m (square cross section).','']
    def add_metrics(metrics):
        for key,value in metrics.items():
            label,unit = vm.FIELDS[key]
            lines.append(f'  {label}: {value:.6g} {unit}' if value is not None else f'  {label}: unavailable')
    for obj in data['objects']:
        lines.append(obj['name']);add_metrics(obj['metrics']);lines.append('')
    if not data['objects']: lines.append('No exported faces use a vegetation radio material.')
    for link in data['links']:
        lines.append(link['tx']+' → '+link['rx']);add_metrics(link['metrics']);lines.append('')
    lines.extend(data['warnings'])
    text.clear();text.write('\n'.join(lines));text['vegetation_metrics_json'] = json.dumps(data,allow_nan=False)
    if context.area is not None:
        context.area.type = 'TEXT_EDITOR';context.area.spaces.active.text = text
    return data
