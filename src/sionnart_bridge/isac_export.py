"""Portable, lossless synthetic ISAC snapshots. Independent of display path limits."""
from pathlib import Path
import csv,json,hashlib,importlib.metadata,platform
import numpy as np

def write_json(path,value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8')

def runtime_material_metadata(scene):
    scalar=lambda v:float(np.asarray(v).reshape(-1)[0])
    return {'frequency_hz':scalar(scene.frequency), 'materials':[
        {'name':name,'relative_permittivity':scalar(m.relative_permittivity),
         'conductivity_s_m':scalar(m.conductivity),'thickness_m':scalar(m.thickness),
         'scattering_coefficient':scalar(m.scattering_coefficient),'xpd_coefficient':scalar(m.xpd_coefficient)}
        for name,m in scene.radio_materials.items()],
        'scene_objects':[{'name':name,'radio_material':o.radio_material.name} for name,o in scene.objects.items()]}

def write_csv(path,rows,fields):
    with Path(path).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def link_statistics(a,tau):
    good=(tau>=0)&np.isfinite(tau)&np.isfinite(a.real)&np.isfinite(a.imag)
    a=a[good];tau=tau[good];p=np.abs(a)**2;energy=float(p.sum())
    coherent=float(abs(a.sum())**2)
    mean=float(np.sum(p*tau)/energy) if energy>0 else None
    rms=float(np.sqrt(np.sum(p*(tau-mean)**2)/energy)) if energy>0 else None
    db=lambda v:float(10*np.log10(v)) if v>0 else None
    return {'valid_paths':len(a),'coherent_gain_linear':coherent,'coherent_gain_db':db(coherent),
            'incoherent_gain_linear':energy,'incoherent_gain_db':db(energy),
            'mean_path_gain_db':db(energy/len(a)) if len(a) else None,
            'mean_delay_s':mean,'rms_delay_spread_s':rms}

def cfr_from_cir(a,tau,frequencies):
    """a already contains carrier delay phase. Apply only baseband offsets."""
    valid=(tau>=0)&np.isfinite(tau)&np.isfinite(a.real)&np.isfinite(a.imag)
    result=np.zeros(a.shape[:-1]+(len(frequencies),),dtype=np.complex128)
    for i,f in enumerate(frequencies):
        result[...,i]=np.sum(np.where(valid,a,0)*np.exp(-2j*np.pi*f*np.where(valid,tau,0)),axis=-1)
    return result

def export_frame(paths,config,frame):
    options=config.get('isac',{})
    if not options.get('enabled'):return None
    root=Path(config['output']['status_json']).parent/'isac';root.mkdir(exist_ok=True)
    directory=root/f"F{int(frame['frame']):06d}";directory.mkdir(exist_ok=True)
    a,tau=paths.cir(normalize_delays=False,num_time_steps=1,out_type='numpy')
    a=np.asarray(a);tau=np.asarray(tau)
    native_tau=tau
    # Synthetic arrays share geometric delays between antenna elements.
    if a.ndim==6 and tau.ndim==3:
        tau=np.broadcast_to(tau[:,None,:,None,:],a.shape[:-1])
    if a.ndim!=6 or a.shape[-1]!=1 or tau.shape!=a.shape[:-1]:
        raise ValueError(f'Unexpected native CIR dimensions: a={a.shape}, tau={tau.shape}')
    alpha=a[...,0];valid=(tau>=0)&np.isfinite(tau)&np.isfinite(alpha.real)&np.isfinite(alpha.imag)
    sim=frame.get('simulation',config['simulation'])
    bw=float(sim.get('bandwidth_hz',20e6));n=int(options.get('csi_bins',64))
    if bw<=0 or n<2:raise ValueError('CSI requires positive bandwidth and at least two frequency bins')
    frequencies=(np.arange(n)-n//2)*(bw/n)
    arrays={'cir':a,'delay_s':tau,'native_delay_s':native_tau,'valid':valid}
    if options.get('csi',True):arrays.update(csi=cfr_from_cir(alpha,tau,frequencies),frequency_offset_hz=frequencies)
    np.savez_compressed(directory/'channels.npz',**arrays)
    stats=[];components=[];plots=[];errors=[]
    for rx,ra,tx,ta in np.ndindex(alpha.shape[:4]):
        values=alpha[rx,ra,tx,ta];delays=tau[rx,ra,tx,ta];mask=valid[rx,ra,tx,ta]
        identifiers={'rx_index':rx,'rx_antenna':ra,'tx_index':tx,'tx_antenna':ta,
          'rx_name':frame['receivers'][rx]['name'],'tx_name':frame['transmitters'][tx]['name']}
        stats.append({**identifiers,**link_statistics(values,delays)})
        if options.get('csv',True):
            for p in np.flatnonzero(mask):
                v=values[p];components.append({**identifiers,'path_index':int(p),'delay_s':float(delays[p]),'real':float(v.real),'imag':float(v.imag),'power_linear':float(abs(v)**2)})
        # Plot one explicitly labelled port per TX/RX; all ports remain in NPZ/CSV.
        if options.get('plots',False) and ra==0 and ta==0:
            try:
                import matplotlib
                matplotlib.use('Agg')
                import matplotlib.pyplot as plt
                fig,axs=plt.subplots(2,1,figsize=(7,6),constrained_layout=True)
                d=delays[mask]*1e9;v=values[mask]
                axs[0].stem(d,abs(v),basefmt=' ');axs[0].set(ylabel='CIR magnitude |a|',xlabel='Absolute delay (ns)')
                axs[1].stem(d,abs(v)**2,basefmt=' ');axs[1].set(ylabel='Path power |a|²',xlabel='Absolute delay (ns)')
                fig.suptitle(f"F{frame['frame']} · {identifiers['tx_name']} → {identifiers['rx_name']} · antenna 0/0")
                p=directory/f'cir_tx{tx:03d}_rx{rx:03d}.png';fig.savefig(p,dpi=180);plt.close(fig);plots.append(p.name)
            except Exception as exc:errors.append(str(exc))
    stat_fields=['rx_index','rx_antenna','tx_index','tx_antenna','rx_name','tx_name','valid_paths','coherent_gain_linear','coherent_gain_db','incoherent_gain_linear','incoherent_gain_db','mean_path_gain_db','mean_delay_s','rms_delay_spread_s']
    write_csv(directory/'link_statistics.csv',stats,stat_fields)
    if options.get('csv',True):write_csv(directory/'cir_components.csv',components,stat_fields[:6]+['path_index','delay_s','real','imag','power_linear'])
    ground=frame.get('isac_ground_truth',{})
    write_json(directory/'ground_truth.json',ground)
    pose=[]
    for obj in ground.get('objects',[]):
        for bone in obj.get('bones',[]):
            pose.append({'object':obj['name'],'bone':bone['name'],**dict(zip(['head_x_m','head_y_m','head_z_m'],bone['head_m'])),**dict(zip(['tail_x_m','tail_y_m','tail_z_m'],bone['tail_m']))})
    write_csv(directory/'skeleton.csv',pose,['object','bone','head_x_m','head_y_m','head_z_m','tail_x_m','tail_y_m','tail_z_m'])
    summary={'schema':'sionnart.isac.frame/1','frame':frame['frame'],'time_seconds':frame.get('time_seconds'),
      'activity':ground.get('activity','unlabelled'),'subject_id':options.get('subject_id','synthetic_subject_001'),
      'episode_id':options.get('episode_id','episode_001'),'environment_id':options.get('environment_id','room_001'),
      'synthetic':True,'simulation':sim,'transmitters':frame['transmitters'],'receivers':frame['receivers'],
      'materials':frame.get('materials',config.get('materials',[])),
      'materials_semantics':'configured inputs; see resolved_radio_materials for actual solver values',
      'resolved_radio_materials':frame.get('resolved_radio_materials'),
      'exported_shape_material_bindings':frame.get('isac_material_bindings',[]),
      'cir_shape':list(a.shape),'cir_axes':['rx','rx_antenna','tx','tx_antenna','path','time_sample'],
      'delay_reference':'absolute, unnormalized seconds','coefficient_convention':'native paths.cir baseband; carrier phase already included',
      'csi_grid':'ideal uniform baseband frequency offsets; not captured Wi-Fi packets or an 802.11 pilot mask',
      'temporal_model':'independently retraced frozen poses; no articulated-body micro-Doppler model',
      'scene_xml_sha256':frame.get('scene_xml_sha256',config.get('scene_xml_sha256')),
      'scene_files_sha256':frame.get('isac_scene_files',{}),
      'links':stats,'plots':plots,'plot_errors':errors}
    write_json(directory/'summary.json',summary)
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir() if p.is_file() and p.name!='completion.json'}
    write_json(directory/'completion.json',{'files_sha256':files})
    return {'frame':frame['frame'],'time_seconds':frame.get('time_seconds'),'directory':directory.name,'summary':directory.name+'/summary.json','activity':summary['activity'],'plot_errors':errors}

def finalize(config,records):
    root=Path(config['output']['status_json']).parent/'isac'
    records=[r for r in records if r]
    if not config.get('isac',{}).get('enabled'):return
    versions={'python':platform.python_version()}
    for package in ['sionna-rt','mitsuba','drjit','numpy']:
        try:versions[package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:versions[package]='unavailable'
    write_json(root/'dataset_manifest.json',{'schema':'sionnart.isac.dataset/1','synthetic':True,'bridge_version':config.get('bridge_version'),
       'runtime_versions':versions,'exporter_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
       'options':config['isac'],'frames':records,'coordinate_system':config.get('coordinate_system'),
       'materials':config.get('materials'),'materials_semantics':'configured inputs; per-frame summary contains resolved_radio_materials','antenna':config.get('antenna'),
       'status':'complete' if len(records)==len(config['frames']) else 'partial'})
    write_csv(root/'frame_index.csv',[{k:r[k] for k in ['frame','time_seconds','directory','activity']} for r in records],['frame','time_seconds','directory','activity'])
    source=Path(__file__).with_name('ISAC_DATA_DICTIONARY.md')
    if source.exists():(root/'DATA_DICTIONARY.md').write_bytes(source.read_bytes())
    (root/'DATASET_CARD.md').write_text(
        '# Synthetic channel and pose snapshots\n\n'
        'Generated with SionnaRT-Bridge. IDs, license declaration, runtime versions and frame index are in dataset_manifest.json. '
        'Channel conventions and units are in DATA_DICTIONARY.md. This is simulated data, not measured Wi-Fi packets.\n\n'
        'Before research release, complete and review: purpose and population represented; scene/character/animation provenance and rights; '
        'RF/material validation; sampling and annotation protocol; episode/subject/environment splits; known biases; expert review; '
        'ethics and licensing statement. No fall classifier, tissue-material validation or competition approval is implied by this export.\n\n'
        'Retain the parent run configuration and logs. Verify per-frame completion.json hashes and scene hashes. '
        'Partial manifests represent unfinished runs. Adjacent frames should not be randomly split across training and testing.\n',encoding='utf-8')
