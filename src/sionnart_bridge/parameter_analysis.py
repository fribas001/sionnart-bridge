"""Offline parameter studies. No Blender, numpy or network dependencies.

All channel summaries are per TX/RX link and first antenna pair. Never sum
CSV point rows, invent missing values or combine different links implicitly.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import statistics
import zipfile
try:
    from .vegetation_fields import FIELDS as VEGETATION_FIELDS
except ImportError:
    from vegetation_fields import FIELDS as VEGETATION_FIELDS

SCHEMA = 'sionna_parameter_study'
METRICS = {
    'total_power_db': ('Path gain (sum of path powers)', 'dB'),
    'strongest_path_gain_db': ('Strongest path gain', 'dB'),
    'rms_delay_spread_ns': ('RMS delay spread', 'ns'),
    'mean_excess_delay_ns': ('Mean excess delay', 'ns'),
    'first_arrival_ns': ('First arrival', 'ns'),
    'path_count': ('Path count', ''),
    'los_available': ('Direct line of sight', '0/1'),
    'max_abs_doppler_hz': ('Maximum absolute Doppler', 'Hz'),
}
GEOMETRY_UNITS = {'surface_area_m2':'m²','volume_m3':'m³','bbox_volume_m3':'m³'}


def finite(value):
    return isinstance(value, (int,float)) and math.isfinite(value)


def _put(parameters, key, label, value, role='input', unit=''):
    if isinstance(value,dict) and 'datablock' in value:
        ref=value['datablock']
        value=ref.get('name','') + (f" [{ref['library']}]" if ref.get('library') else '')
    if isinstance(value,(tuple,list)):
        for i,v in enumerate(value):
            suffix=('X','Y','Z','W')[i] if len(value)<=4 else str(i)
            _put(parameters,key+'/'+str(i),label+' / '+suffix,v,role,unit)
    elif value is None or isinstance(value,(str,bool,int,float)):
        parameters[key]={'label':label,'value':value if not isinstance(value,float) or math.isfinite(value) else None,
                         'role':role,'unit':unit,'kind':'boolean' if isinstance(value,bool) else 'number' if finite(value) else 'category'}


def frame_inputs(frame, snapshot=None):
    """Compact immutable settings sampled with the corresponding mesh/frame."""
    if snapshot is None and frame.get('parameter_study_inputs'):
        return copy.deepcopy(frame['parameter_study_inputs'])
    snapshot=snapshot or frame.get('geometry_nodes_parameters') or {}
    parameters={}
    for obj in snapshot.get('objects',[]):
        ref=obj['object']; name=ref['name']; identity=json.dumps(ref,sort_keys=True)
        for mod in obj.get('modifiers',[]):
            base='gn/'+identity+'/'+mod['name']+'/'+str(mod.get('stack_index',0))
            label=name+' / '+mod['name']
            for prop in mod.get('inputs',[]):
                if prop.get('source')=='geometry': continue
                value=prop.get('value')
                if prop.get('input_mode','VALUE')!='VALUE': value='Attribute: '+prop.get('attribute_name',prop.get('layer_name',''))
                _put(parameters,base+'/'+prop['identifier'],label+' / '+prop['name'],value)
            _put(parameters,base+'/enabled',label+' / Modifier enabled',mod.get('show_viewport'),role='context')
    # Track material assignments made inside node groups as well as exposed
    # sockets. This catches changes invisible in the original object's slots.
    for group in snapshot.get('node_groups',{}).values():
        for node in group.get('nodes',[]):
            if node.get('type') != 'GeometryNodeSetMaterial': continue
            prefix='node_material/'+json.dumps(group.get('id',{}),sort_keys=True)+'/'+node['name']
            label=group.get('id',{}).get('name','Node group')+' / '+node['name']
            _put(parameters,prefix+'/mute',label+' / Muted',node.get('mute',False),'context')
            for socket in node.get('inputs',[]):
                if socket.get('socket_type')=='NodeSocketGeometry':continue
                value='Linked field' if socket.get('linked') else socket.get('default_value')
                _put(parameters,prefix+'/'+socket['identifier'],label+' / '+socket['name'],value,'context')
    for key,value in frame.get('procedural_geometry_stats',{}).items():
        if key!='geometry_signature': _put(parameters,'geometry/'+key,'Mesh / '+key.replace('_',' '),value,'descriptor',GEOMETRY_UNITS.get(key,''))
    for key,value in frame.get('simulation',{}).items():
        _put(parameters,'solver/'+key,'Solver / '+key.replace('_',' '),value)
    for role in ('transmitters','receivers'):
        for device in frame.get(role,[]):
            name=device.get('name',device.get('blender_name','Device'))
            for key in ('position','orientation_mode','look_at_target_position','orientation_sionna_rad','power_dbm','velocity_m_s'):
                if key in device: _put(parameters,'device/'+role+'/'+name+'/'+key,name+' / '+key.replace('_',' '),device[key])
    for material in frame.get('materials',[]):
        name=material.get('blender_name',material.get('source_name','Material'))
        for key,value in material.items(): _put(parameters,'material/'+name+'/'+key,name+' / '+key.replace('_',' '),value,'context')
    vegetation=frame.get('vegetation_metrics',{})
    for key,value in vegetation.get('settings',{}).items():
        _put(parameters,'vegetation/settings/'+key,'Vegetation / '+key.replace('_',' '),value,'context')
    vegetation_parameters(parameters,'vegetation/scene','Vegetation / Scene',vegetation.get('scene',{}))
    for obj in vegetation.get('objects',[]):
        vegetation_parameters(parameters,'vegetation/object/'+obj['name'],'Vegetation / '+obj['name'],obj['metrics'])
    return {'frame':int(frame['frame']),'parameters':parameters,
            'vegetation_links':vegetation.get('links',[]),
            'warnings':list(snapshot.get('warnings',[]))+vegetation.get('warnings',[]),
            'has_geometry_nodes':bool(snapshot.get('objects')),
            'geometry_signature':frame.get('procedural_geometry_stats',{}).get('geometry_signature')}


def vegetation_parameters(parameters,prefix,label,metrics):
    for key,value in metrics.items():
        title,unit=VEGETATION_FIELDS.get(key,(key,''))
        _put(parameters,prefix+'/'+key,label+' / '+title,value,'descriptor',unit)


def _flatten_context(data, prefix='', output=None):
    output={} if output is None else output
    if isinstance(data,dict):
        for k,v in sorted(data.items()): _flatten_context(v,prefix+'/'+str(k),output)
    elif isinstance(data,list):
        for i,v in enumerate(data): _flatten_context(v,prefix+'/'+str(i),output)
    else: output[prefix]=data
    return output


def build_study(config, manifest, run_id=None):
    frames=config.get('frames',[])
    input_map={int(f['frame']):f for f in frames}
    if len(input_map)!=len(frames): raise ValueError('Duplicate input frame identifiers')
    run_id=str(run_id or config.get('output',{}).get('export_run_id') or '')
    if not run_id: raise ValueError('Run identifier is missing; cannot safely join results')
    records=[];parameters={};warnings=[];contexts=[];seen=set()
    for result in manifest.get('frames',[]):
        frame=int(result['frame'])
        if frame in seen: raise ValueError(f'Duplicate result frame {frame}')
        seen.add(frame)
        if frame not in input_map: raise ValueError(f'Result frame {frame} has no matching parameter record')
        source=input_map[frame]; captured=frame_inputs(source)
        values={}
        for key,p in captured['parameters'].items():
            parameters.setdefault(key,{k:v for k,v in p.items() if k!='value'})
            values[key]=p['value']
        contexts.append(values)
        warnings.extend(captured['warnings'])
        analytics=result.get('channel_analytics') or {}
        if analytics.get('source') not in ('all_valid_paths_first_antenna_pair','worker_all_valid_paths',None):
            warnings.append('Channel summaries may include only displayed paths')
        pairs=set()
        for link in analytics.get('links',[]):
            pair=int(link['pos_idx'])
            if pair in pairs: raise ValueError(f'Duplicate link {pair} in frame {frame}')
            pairs.add(pair)
            if int(link.get('frame',frame))!=frame: raise ValueError('Channel and input frame identifiers disagree')
            metrics={k:(int(link[k]) if isinstance(link.get(k),bool) else link.get(k)) for k in METRICS}
            # No paths means absent gain/delay, not a manufactured -600 dB point.
            if not link.get('path_count',0):
                for key in METRICS:
                    if key not in ('path_count','los_available'):metrics[key]=None
            metrics={k:v if finite(v) else None for k,v in metrics.items()}
            link_values=dict(values)
            for vegetation_link in captured.get('vegetation_links',[]):
                if (vegetation_link['tx'],vegetation_link['rx']) != (link.get('tx_name'),link.get('rx_name')):continue
                link_parameters={}
                vegetation_parameters(link_parameters,'vegetation/link','Vegetation / Selected TX–RX link',vegetation_link['metrics'])
                for obj in vegetation_link.get('objects',[]):
                    vegetation_parameters(link_parameters,'vegetation/link/object/'+obj['name'],'Vegetation / Selected link / '+obj['name'],obj['metrics'])
                for key,p in link_parameters.items():
                    parameters.setdefault(key,{k:v for k,v in p.items() if k!='value'})
                    link_values[key]=p['value']
            records.append({'frame':frame,'pair':pair,'tx':link.get('tx_name','TX'), 'rx':link.get('rx_name','RX'),
                            'values':link_values,'metrics':metrics,'geometry_signature':captured.get('geometry_signature')})
    if not records: raise ValueError('No completed per-link channel summaries found. Import a paths export with its metadata JSON.')
    missing=sorted(set(input_map)-seen)
    if missing:warnings.append('No result summaries for prepared frames: '+', '.join(map(str,missing)))
    if not any(k.startswith('gn/') for k in parameters):warnings.append('No exposed Geometry Nodes inputs were recorded for this run')
    if not any(f.get('materials') for f in frames):warnings.append('Radio-material properties are absent from this export. Node material names alone do not establish the solver dielectric values.')
    if not config.get('procedural_scene',False):warnings.append('The run reused a static scene cache; sampled inputs do not establish that mesh changes were simulated.')
    context=_flatten_context(config.get('antenna',{}),'antenna')
    context['frequency_definition']='First transmit–receive antenna pair'
    return {'schema':SCHEMA,'schema_version':1,'run_id':run_id,'category':'paths',
            'label':str(config.get('scene_name','Scene'))+' / '+run_id,
            'created_utc':config.get('created_utc',''),'bridge_version':config.get('bridge_version',''),
            'parameters':parameters,'records':sorted(records,key=lambda r:(r['pair'],r['frame'])),
            'context':context,'warnings':sorted(set(warnings)),'input_frames':len(frames),
            'result_frames':len(seen),'metric_scope':'all valid paths, first transmit–receive antenna pair'}


def from_export(payload):
    if payload.get('schema')==SCHEMA:
        if payload.get('schema_version')!=1 or not payload.get('records'): raise ValueError('Unsupported or empty parameter study')
        return payload
    category=payload.get('categories',{}).get('paths')
    if not category:raise ValueError('Choose a propagation-paths metadata JSON or its export ZIP')
    config=category['parameters'];run_id=payload.get('run_id')
    if config.get('output',{}).get('export_run_id')!=run_id:raise ValueError('Export and configuration run identifiers disagree')
    return build_study(config,category['results_summary'],run_id)


def load_export(path):
    path=Path(path)
    if path.suffix.lower()=='.zip':
        with zipfile.ZipFile(path) as archive:
            names=[n for n in archive.namelist() if n.lower().endswith('.metadata.json')]
            if len(names)!=1:raise ValueError('Choose a simulation export ZIP containing exactly one .metadata.json file')
            if archive.getinfo(names[0]).file_size>512*1024*1024:raise ValueError('Metadata file exceeds 512 MB; select a smaller export')
            payload=json.loads(archive.read(names[0]))
    else:
        if path.stat().st_size>512*1024*1024:raise ValueError('Metadata file exceeds 512 MB')
        payload=json.loads(path.read_text(encoding='utf-8-sig'))
    return from_export(payload)


def variation(values):
    values=[float(v) for v in values if finite(v)]
    if not values:return {'n':0,'min':None,'max':None,'mean':None,'median':None,'std':None,'range':None,'delta':None,'varies':False}
    lo,hi=min(values),max(values)
    return {'n':len(values),'min':lo,'max':hi,'mean':statistics.fmean(values),'median':statistics.median(values),
            'std':statistics.pstdev(values),'range':hi-lo,'delta':values[-1]-values[0],
            'varies':hi-lo>max(1e-9,1e-7*max(abs(lo),abs(hi)))}


def pearson(xs,ys):
    if len(xs)<3 or not variation(xs)['varies'] or not variation(ys)['varies']:return None
    mx,my=statistics.fmean(xs),statistics.fmean(ys)
    dx=[x-mx for x in xs];dy=[y-my for y in ys]
    denominator=math.sqrt(sum(x*x for x in dx)*sum(y*y for y in dy))
    return max(-1.0,min(1.0,sum(x*y for x,y in zip(dx,dy))/denominator)) if denominator else None


def analyze(study,x_key,metric,pair):
    if metric not in METRICS:raise ValueError('Unknown channel metric')
    rows=[r for r in study['records'] if r['pair']==pair]
    points=[{'frame':r['frame'],'x':r['frame'] if x_key=='frame' else r['values'].get(x_key),'y':r['metrics'].get(metric)} for r in rows]
    valid=[p for p in points if p['x'] is not None and finite(p['y'])]
    numeric=[p for p in valid if finite(p['x'])]
    stats=variation([p['y'] for p in valid])
    stats['missing']=len(points)-len(valid)
    stats['pearson_r']=pearson([p['x'] for p in numeric],[p['y'] for p in numeric]) if len(numeric)==len(valid) else None
    stats['distinct_x']=len({json.dumps(p['x'],sort_keys=True) for p in valid})
    return {'points':points,'stats':stats}


def context_differences(studies):
    if len(studies)<2:return []
    def values(study):
        output={k:{json.dumps(v,sort_keys=True)} for k,v in study.get('context',{}).items()}
        for r in study['records']:
            for k,v in r['values'].items():
                if study['parameters'][k]['role']!='descriptor':output.setdefault(k,set()).add(json.dumps(v,sort_keys=True))
        return {k:sorted(v) for k,v in output.items()}
    a,b=map(values,studies[:2]);labels={k:p['label'] for s in studies for k,p in s['parameters'].items()}
    return [{'label':labels.get(k,k),'first':a.get(k,['Missing']),'second':b.get(k,['Missing'])}
            for k in sorted(set(a)|set(b)) if a.get(k)!=b.get(k)]


def write_report(path, studies):
    if not studies:raise ValueError('No parameter studies selected')
    payload={'studies':studies,'metrics':METRICS,'differences':context_differences(studies)}
    # The template is fully local; escaping < prevents closing the JSON script
    # from a scene/object name. Labels are inserted through textContent in JS.
    encoded=json.dumps(payload,ensure_ascii=True,allow_nan=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    template=Path(__file__).with_name('parameter_report.html').read_text(encoding='utf-8')
    destination=Path(path);destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_suffix('.html.tmp')
    temporary.write_text(template.replace('STUDY_DATA_PLACEHOLDER',encoded),encoding='utf-8')
    temporary.replace(destination)
    return destination
