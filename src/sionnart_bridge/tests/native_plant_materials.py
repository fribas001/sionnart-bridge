"""Use Sionna Python: native_plant_materials.py BLENDER_TEST_DIR OUTPUT_DIR."""
import cmath,json,math,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
import plant_materials as p
source,out=[Path(v).resolve() for v in sys.argv[1:3]];out.mkdir(parents=True,exist_ok=True)
proof={}
for category,worker in [('paths','sionna_worker'),('coverage_2d','radio_map_worker'),('coverage_3d','radio_map_3d_worker')]:
    config=json.loads((source/(category+'_config.json')).read_text(encoding='utf-8'))
    folder=out/category;folder.mkdir(parents=True,exist_ok=True)
    output=config['output']
    for k,v in list(output.items()):
        if isinstance(v,str) and v and (k.endswith('_json') or k.endswith('_csv')):output[k]=str(folder/Path(v).name)
    output.update(export_format='CSV',export_file=str(folder/'plant.csv'),export_metadata_json=str(folder/'plant.metadata.json'),keep_external_results=True)
    for f in config['frames']:
        for k,v in f['output'].items():f['output'][k]=str(folder/Path(v).name)
        f['simulation'].update(max_depth=3,samples_per_src=16384,max_num_paths_per_src=8192,refraction=True,specular_reflection=True,diffuse_reflection=True,diffraction=False,edge_diffraction=False)
        if 'radio_map' in f:f['radio_map'].update(center_x=0,center_y=0,height=1,size_x=2,size_y=2,cell_size_x=1,cell_size_y=1)
        if 'radio_map_3d' in f:f['radio_map_3d'].update(center_x=0,center_y=0,center_z=1,size_x=2,size_y=2,size_z=1,cell_size_x=1,cell_size_y=1,cell_size_z=.5)
    cfile=folder/'config.json';cfile.write_text(json.dumps(config,indent=2),encoding='utf-8')
    with (folder/'worker.log').open('w',encoding='utf-8') as log:
        result=subprocess.run([sys.executable,str(root/(worker+'.py')),'--config',str(cfile)],stdout=log,stderr=subprocess.STDOUT,timeout=180)
    assert Path(output['status_json']).is_file(),(category,(folder/'worker.log').read_text(encoding='utf-8')[-8000:])
    assert result.returncode == 0, (category, result.returncode)
    status=json.loads(Path(output['status_json']).read_text(encoding='utf-8'))
    assert status['state']=='finished' and status['completed_frames']==len(config['frames']),(status,(folder/'worker.log').read_text(encoding='utf-8')[-8000:])
    manifest=json.loads(Path(output['frames_manifest_json']).read_text(encoding='utf-8'))
    readings=[]
    slab_checks=[]
    for frame,prepared in zip(manifest['frames'],config['frames']):
        assert len(frame['materials'])==2,frame['materials']
        for material in frame['materials']:
            ref=material['plant_reference'];frequency=prepared['simulation']['frequency_hz']
            er,sigma=p.dielectric(ref['dielectric_model'],frequency)
            assert material['object_count']==1,material
            assert math.isclose(material['relative_permittivity'],er,rel_tol=1e-6),material
            assert math.isclose(material['conductivity'],sigma,rel_tol=1e-6),material
            assert math.isclose(ref['frequency_hz'],frequency,rel_tol=1e-7)
            assert material['scattering_coefficient']==0 and material['xpd_coefficient']==0
            readings.append({'frame':frame['frame'],'material':material['blender_name'],'frequency_hz':frequency,'epsilon_real':material['relative_permittivity'],'sigma':material['conductivity'],'thickness':material['thickness']})
        if category=='paths':
            link=frame['channel_analytics']['links'][0]
            assert link['path_count']>0 and not link['los_available'],link
            assert any(c['path_type']=='Refraction' for c in link['cir_components']),link['path_type_counts']
            # Independent scalar normal-incidence slab + free-space formula.
            # This checks the end-to-end material/units mapping, not field
            # accuracy of a real plant or the validity of geometric optics.
            material=next(m for m in frame['materials'] if m['plant_reference']['dielectric_model']=='LEAF_P833')
            freq=material['plant_reference']['frequency_hz'];wave=299792458./freq
            er,sigma=p.dielectric('LEAF_P833',freq)
            n=cmath.sqrt(complex(er,-sigma/(2*math.pi*freq*p.EPSILON_0)))
            r=(1-n)/(1+n);phase=cmath.exp(-1j*2*math.pi*n*material['thickness']/wave)
            transmission=(1-r*r)*phase/(1-r*r*phase*phase)
            predicted=20*math.log10(abs(transmission)*wave/(4*math.pi*4.))
            direct=min((c for c in link['cir_components'] if c['path_type']=='Refraction'),key=lambda c:c['delay_ns'])
            error=direct['path_gain_db']-predicted
            assert abs(error)<1e-3,(predicted,direct,error)
            slab_checks.append({'frame':frame['frame'],'predicted_gain_db':predicted,'actual_gain_db':direct['path_gain_db'],'error_db':error})
    metadata=json.loads(Path(output['export_metadata_json']).read_text(encoding='utf-8'))
    assert 'plant_reference' in json.dumps(metadata)
    assert Path(output['export_file']).stat().st_size>100
    proof[category]={'finished':True,'worker_exit_code':result.returncode,'materials':readings,'csv_metadata':True,'slab_checks':slab_checks}
    print(category,'PLANT_NATIVE_PASS',flush=True)
(out/'test_report.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
print('NATIVE_PLANT_MATERIALS_PASS',flush=True)
