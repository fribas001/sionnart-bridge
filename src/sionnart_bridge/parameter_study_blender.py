"""Blender integration for immutable per-run parameter studies."""
import json
from pathlib import Path
import bpy
from . import parameter_analysis as analysis


def text_poll(_self,text):
    return bool(text.get('sionna_parameter_study',False))


def object_poll(_self,obj):
    return obj.get('sionna_result_type')=='paths_pointcloud'


def dataset_from_object(obj):
    if obj is None:raise ValueError('Select a paths result object or import a simulation export')
    raw=obj.get('sionna_parameter_study')
    if raw:return analysis.from_export(json.loads(raw))
    # 1.22 results can be analyzed without rerunning if their GN JSON files
    # and the embedded full-path summaries are still available.
    manifest_value=obj.get('sionna_geometry_nodes_metadata_json','')
    if not manifest_value:raise ValueError('This result has no saved parameter inputs. Import its CSV metadata ZIP, or run with parameter analysis enabled.')
    path=Path(manifest_value)
    if not path.is_file():raise ValueError('The older result’s parameter files are missing. Import the simulation metadata ZIP.')
    receipt=json.loads(path.read_text(encoding='utf-8'))
    run_id=obj.get('sionna_export_run_id','')
    if not run_id or receipt.get('run_id')!=run_id:raise ValueError('Result and parameter run identifiers disagree')
    frames=[];first=None
    for item in receipt['frames']:
        file=(path.parent/item['file']).resolve()
        if not file.is_relative_to(path.parent.resolve()):raise ValueError('Parameter frame path is outside its export folder')
        raw=file.read_bytes()
        if analysis.hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('Parameter frame checksum does not match its manifest')
        record=json.loads(raw)
        if record.get('run_id')!=run_id or record['frame']!=item['frame']:raise ValueError('Parameter frame identity mismatch')
        first=first or record
        frames.append({'frame':record['frame'],'geometry_nodes_parameters':record['geometry_nodes'],
                       'simulation':record.get('simulation',{}),'materials':record.get('materials',[]),
                       'transmitters':record.get('transmitters',[]),'receivers':record.get('receivers',[]),
                       'vegetation_metrics':record.get('vegetation_metrics',{}),
                       'procedural_geometry_stats':record.get('procedural_geometry_stats',{})})
    channel=json.loads(obj.get('sionna_channel_analytics','{}'))
    config={'frames':frames,'scene_name':receipt.get('scene_name','Scene'),'created_utc':receipt.get('created_utc',''),
            'bridge_version':receipt.get('bridge_version',''),'output':{'export_run_id':run_id},
            'antenna':(first or {}).get('antenna',{}),'procedural_scene':(first or {}).get('scene_source',{}).get('evaluated_per_frame',False)}
    study=analysis.build_study(config,channel)
    obj['sionna_parameter_study']=json.dumps(study,separators=(',',':'),allow_nan=False)
    return study


def selected_study(bridge,scene):
    settings=scene.sionna_bridge
    if settings.parameter_study_source=='IMPORTED':
        text=settings.parameter_study_imported
        if text is None:raise ValueError('Import a simulation metadata JSON or ZIP first')
        return analysis.from_export(json.loads(text.as_string()))
    obj=settings.parameter_study_object or bridge._analytics_target_object(scene,'PATHS')
    return dataset_from_object(obj)


def write_selected(bridge,scene):
    settings=scene.sionna_bridge
    studies=[selected_study(bridge,scene)]
    if settings.parameter_study_reference is not None:
        reference=analysis.from_export(json.loads(settings.parameter_study_reference.as_string()))
        if reference['run_id']==studies[0]['run_id']:raise ValueError('Choose a different reference run, or clear the reference')
        studies.append(reference)
    token='_vs_'.join(bridge._sanitize_name(s['run_id']) for s in studies)
    path=bridge._workspace(settings)/'parameter_analysis'/token/'parameter_analysis.html'
    analysis.write_report(path,studies)
    settings.parameter_study_report=str(path)
    settings.parameter_study_status=f"{studies[0]['result_frames']} frames ready; {len(studies)} run(s)"
    return path


def attach(bridge,scene,obj,config,manifest):
    if not any('parameter_study_inputs' in f for f in config.get('frames',[])):
        return None
    study=analysis.build_study(config,manifest)
    obj['sionna_parameter_study']=json.dumps(study,separators=(',',':'),allow_nan=False)
    settings=scene.sionna_bridge
    settings.parameter_study_object=obj
    settings.parameter_study_source='RESULT'
    settings.parameter_study_status=f"Saved {study['result_frames']} frames on {obj.name}"
    # Honor the run's sampled analysis flag, not a checkbox changed mid-run.
    path=bridge._workspace(settings)/'parameter_analysis'/bridge._sanitize_name(study['run_id'])/'parameter_analysis.html'
    analysis.write_report(path,[study])
    obj['sionna_parameter_report']=str(path)
    settings.parameter_study_report=str(path)
    return study


def import_run(scene,filepath,reference=False):
    study=analysis.load_export(filepath)
    text=bpy.data.texts.new('Sionna parameter study '+study['run_id'])
    text.write(json.dumps(study,separators=(',',':'),allow_nan=False))
    text['sionna_parameter_study']=True
    text.use_fake_user=True
    settings=scene.sionna_bridge
    if reference:settings.parameter_study_reference=text
    else:
        settings.parameter_study_imported=text
        settings.parameter_study_source='IMPORTED'
    settings.parameter_study_status=f"Imported {study['result_frames']} frames from run {study['run_id']}"
    return study
