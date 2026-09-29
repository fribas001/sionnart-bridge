"""Camera-relative Geometry Nodes statistics card, excluded from RT export."""
import bpy,json
from pathlib import Path
from mathutils import Matrix,Vector
from bpy.app.handlers import persistent
NAME='SBR_ISAC_Statistics'

def emission(name,color):
    m=bpy.data.materials.get(name)
    if m:return m
    m=bpy.data.materials.new(name);m.use_nodes=True;n=m.node_tree.nodes;n.clear()
    e=n.new('ShaderNodeEmission');e.inputs['Color'].default_value=(*color,1)
    out=n.new('ShaderNodeOutputMaterial');m.node_tree.links.new(e.outputs[0],out.inputs['Surface']);return m

def ensure(scene):
    obj=scene.objects.get(NAME)
    if obj:return obj
    g=bpy.data.node_groups.get(NAME)
    if not g:
        g=bpy.data.node_groups.new(NAME,'GeometryNodeTree');g.is_modifier=True
        for name,io,kind in [('Geometry','INPUT','NodeSocketGeometry'),('Geometry','OUTPUT','NodeSocketGeometry'),('Text','INPUT','NodeSocketString'),('Size','INPUT','NodeSocketFloat'),('Text position','INPUT','NodeSocketVector')]:g.interface.new_socket(name=name,in_out=io,socket_type=kind)
        n=g.nodes;lk=g.links;i=n.new('NodeGroupInput');o=n.new('NodeGroupOutput')
        text=n.new('GeometryNodeStringToCurves');fill=n.new('GeometryNodeFillCurve');real=n.new('GeometryNodeRealizeInstances');move=n.new('GeometryNodeTransform')
        lk.new(i.outputs['Text'],text.inputs['String']);lk.new(i.outputs['Size'],text.inputs['Size']);lk.new(text.outputs['Curve Instances'],real.inputs['Geometry']);lk.new(real.outputs['Geometry'],fill.inputs['Curve']);lk.new(fill.outputs['Mesh'],move.inputs['Geometry']);lk.new(i.outputs['Text position'],move.inputs['Translation'])
        white=n.new('GeometryNodeSetMaterial');white.inputs['Material'].default_value=emission(NAME+'_Text',(1,1,1));lk.new(move.outputs['Geometry'],white.inputs['Geometry'])
        dark=n.new('GeometryNodeSetMaterial');dark.inputs['Material'].default_value=emission(NAME+'_Panel',(.012,.018,.028));lk.new(i.outputs['Geometry'],dark.inputs['Geometry'])
        join=n.new('GeometryNodeJoinGeometry');lk.new(white.outputs['Geometry'],join.inputs['Geometry']);lk.new(dark.outputs['Geometry'],join.inputs['Geometry']);lk.new(join.outputs['Geometry'],o.inputs['Geometry'])
        for j,node in enumerate(n):node.location=((j%5)*230,-(j//5)*240)
    mesh=bpy.data.meshes.new(NAME);mesh.from_pydata([(0,0,0),(1,0,0),(1,1,0),(0,1,0)],[],[(0,1,2,3)])
    obj=bpy.data.objects.new(NAME,mesh)
    coll=bpy.data.collections.get('ISAC_Visuals')
    if not coll:coll=bpy.data.collections.new('ISAC_Visuals');scene.collection.children.link(coll)
    coll.objects.link(obj);obj['sionna_blender_only']=True
    for attr in ['visible_shadow','visible_diffuse','visible_glossy','visible_transmission','visible_volume_scatter']:
        if hasattr(obj,attr):setattr(obj,attr,False)
    m=obj.modifiers.new('Camera statistics','NODES');m.node_group=g
    return obj

@persistent
def update(scene,*_args):
    s=getattr(scene,'sionna_bridge',None)
    if s is None:return
    obj=scene.objects.get(NAME)
    if not s.isac_hud:
        if obj:obj.hide_render=True;obj.hide_viewport=True
        return
    if not scene.camera:
        if obj:obj.hide_render=True
        return
    if obj is None:return
    obj.hide_render=False;obj.hide_viewport=False
    cam=scene.camera
    if cam.data.type not in {'PERSP','ORTHO'}:
        obj.hide_render=True;return
    distance=max(cam.data.clip_start*2,.5)
    corners=cam.data.view_frame(scene=scene)
    corners=[p*(distance/abs(p.z)) if cam.data.type=='PERSP' else Vector((p.x,p.y,-distance)) for p in corners]
    xmin,xmax=min(p.x for p in corners),max(p.x for p in corners);ymin,ymax=min(p.y for p in corners),max(p.y for p in corners)
    w=xmax-xmin;h=ymax-ymin;card_width=min(.90*w,min(.65*w,.50*h)*s.isac_hud_scale)
    obj.matrix_world=cam.matrix_world@Matrix.Translation((0,0,-distance))
    lines=['SIONNA / ISAC',f'Frame {scene.frame_current}','No matching channel snapshot']
    manifest=Path(s.isac_last_run_dir or s.last_run_dir)/'isac'/'dataset_manifest.json'
    if manifest.is_file():
        try:
            data=json.loads(manifest.read_text());r=next((r for r in data['frames'] if r['frame']==scene.frame_current),None)
            if r:
                summary=json.loads((manifest.parent/r['summary']).read_text())
                links=summary['links'];link=next((v for v in links if v['tx_index']==s.isac_hud_tx and v['rx_index']==s.isac_hud_rx and v['tx_antenna']==0 and v['rx_antenna']==0),None)
                if link:
                    f=lambda v:'n/a' if v is None else f'{v:.2f}'
                    lines=['SIONNA / ISAC',f'Frame {scene.frame_current} | {summary["time_seconds"]:.3f} s',f'TX {s.isac_hud_tx} > RX {s.isac_hud_rx} | ant 0/0',f'Paths: {link["valid_paths"]}',f'Coherent gain: {f(link["coherent_gain_db"])} dB',f'Mean path gain: {f(link["mean_path_gain_db"])} dB',f'RMS delay: {f(None if link["rms_delay_spread_s"] is None else 1e9*link["rms_delay_spread_s"])} ns',summary['activity'][:28]]
        except (OSError,ValueError,KeyError):pass
    m=obj.modifiers[0]
    size=min(h*.029*s.isac_hud_scale,(card_width-.03*w)/(max(map(len,lines))*.65))
    card_height=.065*h+len(lines)*size*1.2
    x=xmin+.02*w if s.isac_hud_corner.endswith('LEFT') else xmax-.02*w-card_width
    y=ymax-.04*h if s.isac_hud_corner.startswith('TOP') else ymin+.04*h+card_height
    for v,co in zip(obj.data.vertices,[(x,y-card_height,0),(x+card_width,y-card_height,0),(x+card_width,y,0),(x,y,0)]):v.co=co
    for item in m.node_group.interface.items_tree:
        if item.item_type=='SOCKET' and item.in_out=='INPUT':
            value={'Text':'\n'.join(lines),'Size':size,'Text position':(x+.015*w,y-.042*h,.001)}.get(item.name)
            if value is not None:getattr(m.properties.inputs,item.identifier).value=value
    obj.data.update();obj.update_tag()
