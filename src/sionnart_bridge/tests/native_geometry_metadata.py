"""Sionna RT end-to-end test using configs from blender_geometry_metadata.py.

Run with the Sionna Python environment: python tests/native_geometry_metadata.py INPUT OUTPUT
"""
import csv
import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path

import h5py

root = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
import geometry_nodes_metadata as metadata
from result_export_worker import export_completed_run

source,out = map(lambda p:Path(p).resolve(),sys.argv[1:3])
out.mkdir(parents=True,exist_ok=True)
evidence = {'sionna_rt':importlib.metadata.version('sionna-rt'),'cases':{}}
for category,worker in [('paths','sionna_worker'),('coverage_2d','radio_map_worker'),('coverage_3d','radio_map_3d_worker')]:
    config = json.loads((source/(category+'_config.json')).read_text(encoding='utf-8'))
    folder = out/category
    folder.mkdir(parents=True,exist_ok=True)
    output = config['output']
    for k,v in list(output.items()):
        if isinstance(v,str) and v and (k.endswith('_json') or k.endswith('_csv')):
            output[k] = str(folder/Path(v).name)
    output.update(export_format='HDF5',export_file=str(folder/'export.h5'),export_metadata_json=str(folder/'export_metadata.json'),keep_external_results=True)
    for frame in config['frames']:
        for k,v in frame['output'].items():
            frame['output'][k] = str(folder/Path(v).name)
        frame['simulation'].update(max_depth=1,samples_per_src=8192,max_num_paths_per_src=4096,refraction=False)
        if 'radio_map' in frame:
            frame['radio_map'].update(center_x=0,center_y=0,height=1,size_x=2,size_y=2,cell_size_x=1,cell_size_y=1)
        if 'radio_map_3d' in frame:
            frame['radio_map_3d'].update(center_x=0,center_y=0,center_z=1,size_x=2,size_y=2,size_z=1,cell_size_x=1,cell_size_y=1,cell_size_z=.5)
    metadata.write_run(config,folder/'geometry_nodes_metadata')
    path = folder/'config.json'
    path.write_text(json.dumps(config,indent=2),encoding='utf-8')
    with (folder/'worker.log').open('w',encoding='utf-8') as log:
        result = subprocess.run([sys.executable,str(root/(worker+'.py')),'--config',str(path)],stdout=log,stderr=subprocess.STDOUT,timeout=180)
    assert Path(output['status_json']).is_file(), (category,result.returncode,(folder/'worker.log').read_text(encoding='utf-8')[-6000:])
    assert result.returncode == 0, (category, result.returncode)
    status = json.loads(Path(output['status_json']).read_text(encoding='utf-8'))
    assert status['state'] == 'finished' and status['completed_frames'] == 2, status
    with h5py.File(output['export_file']) as h5:
        assert h5.attrs['run_id'] == output['export_run_id']
        records = [json.loads(v) for v in h5[f'simulations/{category}/frame_metadata/input_json'][...]]
        assert [r['frame'] for r in records] == [1,2]
        assert all(r['geometry_nodes_parameters']['objects'][0]['object']['name'] == 'Plant' for r in records)
        h5_config = json.loads(h5[f'metadata/configs/{category}'][()])
        assert h5_config['geometry_nodes_metadata']['run_id'] == output['export_run_id']
    # CSV export receives the same evaluated records as the HDF5 export.
    csv_output = dict(output,export_format='CSV',export_file=str(folder/'export.csv'),export_metadata_json=str(folder/'csv_metadata.json'))
    export_completed_run(config_path=path,manifest_path=output['frames_manifest_json'],csv_path=output['results_csv'],output=csv_output)
    exported = json.loads(Path(csv_output['export_metadata_json']).read_text(encoding='utf-8'))
    assert exported['run_id'] == output['export_run_id']
    encoded = json.dumps(exported)
    assert 'geometry_nodes_parameters' in encoded and 'leaf_density' in encoded
    with Path(csv_output['export_file']).open(newline='',encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    evidence['cases'][category] = {'frames':2,'csv_rows':len(rows),'hdf5_and_csv_metadata_join':True,'status':status['state'],'worker_exit_code':result.returncode}
    print(category,'PASS',len(rows),'rows',flush=True)
(out/'test_report.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
print('NATIVE_GEOMETRY_METADATA_PASS',flush=True)
