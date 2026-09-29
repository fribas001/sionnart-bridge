"""Capture evaluated synthetic ground truth without guessing activity labels."""
import bpy
from mathutils import Vector
from pathlib import Path
import xml.etree.ElementTree as ET
import shutil,hashlib

def stage_scenes(frames,run_dir):
    for frame in frames:
        source=Path(frame['scene_xml']);root=Path(run_dir)/'isac'/'scenes'/f"F{frame['frame']:06d}"
        assets=root/'assets';assets.mkdir(parents=True,exist_ok=True)
        tree=ET.parse(source)
        frame['isac_material_bindings']=[{'shape_id':n.get('id'), 'material_id':n.find('ref').get('id') if n.find('ref') is not None else None} for n in tree.iter('shape')]
        for index,node in enumerate(tree.iter('string')):
            if node.get('name')!='filename':continue
            asset=Path(node.get('value',''))
            if not asset.is_absolute():asset=source.parent/asset
            if not asset.is_file():raise ValueError(f'Missing scene asset: {asset}')
            target=assets/f'{index:04d}_{asset.name}';shutil.copyfile(asset,target);node.set('value','assets/'+target.name)
        target=root/'scene.xml';tree.write(target,encoding='utf-8',xml_declaration=True)
        frame['scene_xml']=str(target);frame['scene_xml_sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
        frame['isac_scene_files']={str(p.relative_to(Path(run_dir)/'isac')).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}

def subject(scene):
    chosen=scene.sionna_bridge.isac_subject
    if chosen:return chosen
    rigs=[o for o in scene.objects if o.type=='ARMATURE']
    if len(rigs)==1:return rigs[0]
    raise ValueError('Select the human mesh or armature for ISAC ground truth')

def validate_subject(scene,export_objects):
    root=subject(scene)
    meshes=[o for o in scene.objects if o.type=='MESH' and (o==root or o in root.children_recursive or any(m.type=='ARMATURE' and m.object==root for m in o.modifiers))]
    missing=[o.name for o in meshes if o not in export_objects or o.hide_render or not o.visible_get() or o.get('sionna_blender_only',False)]
    if not meshes or missing:
        raise ValueError('ISAC subject must have viewport-visible, render-enabled meshes in the Sionna scene export: '+', '.join(missing or [root.name]))
    unconfigured=[]
    for o in meshes:
        for m in o.data.materials:
            c=getattr(m,'sionna_radio',None) if m else None
            if m is None or not ((c and c.configured and c.enabled) or m.name.startswith('itu_')):
                unconfigured.append(o.name)
        if not o.data.materials:unconfigured.append(o.name)
    if unconfigured:
        raise ValueError('Human radio material is not explicit: '+', '.join(sorted(set(unconfigured)))+'. Assign human radio proxy or configure the material in Sionna Materials.')

def capture(context):
    scene=context.scene;s=scene.sionna_bridge;root=subject(scene) if s.isac_capture_pose else None;dg=context.evaluated_depsgraph_get()
    objects=([root]+[o for o in scene.objects if o!=root and (o in root.children_recursive or any(m.type=='ARMATURE' and m.object==root for m in o.modifiers))]) if root else []
    label=s.isac_activity
    markers=[m for m in scene.timeline_markers if m.frame<=scene.frame_current and m.name.startswith('isac:')]
    if markers:label=max(markers,key=lambda m:m.frame).name[5:].strip() or 'unlabelled'
    data=[]
    for o in objects:
        e=o.evaluated_get(dg)
        item={'name':o.name,'type':o.type,'matrix_world':[list(row) for row in e.matrix_world],
              'origin_m':list(e.matrix_world.translation),'bones':[]}
        if o.type=='ARMATURE':
            item['bones']=[{'name':p.name,'parent':p.parent.name if p.parent else None,'head_m':list(e.matrix_world@p.head),'tail_m':list(e.matrix_world@p.tail),
                           'matrix_world':[list(row) for row in e.matrix_world@p.matrix]} for p in e.pose.bones]
        if o.type=='MESH':
            mesh=e.to_mesh()
            try:
                points=[e.matrix_world@v.co for v in mesh.vertices]
                item['vertex_count']=len(points)
                if points:
                    item['bbox_min_m']=[min(p[i] for p in points) for i in range(3)]
                    item['bbox_max_m']=[max(p[i] for p in points) for i in range(3)]
                    item['vertex_centroid_m']=list(sum(points,Vector())/len(points))
                item['materials']=[m.name for m in mesh.materials if m]
            finally:e.to_mesh_clear()
        data.append(item)
    return {'frame':scene.frame_current,'activity':label,'label_source':'timeline marker isac:label or user setting',
      'subject_object':root.name if root else None,'units':'metres, world XYZ, Z up','objects':data,
      'material_note':'Assignments recorded as model inputs; human tissue realism is not inferred from material names'}
