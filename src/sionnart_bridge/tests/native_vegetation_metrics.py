"""Run the small two-receiver Blender fixture, verify durable metadata and plots."""
import json,sys,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
import parameter_analysis as analysis
import result_export_worker as export
import h5py
source=Path(sys.argv[1]).resolve()
config_path=source/'paths_config.json';config=json.loads(config_path.read_text(encoding='utf-8'))
with (source/'worker.log').open('w',encoding='utf-8') as log:
    run=subprocess.run([sys.executable,str(root/'sionna_worker.py'),'--config',str(config_path)],stdout=log,stderr=subprocess.STDOUT,timeout=180)
assert run.returncode == 0, (run.returncode, (source/'worker.log').read_text(encoding='utf-8')[-3000:])
status=json.loads(Path(config['output']['status_json']).read_text(encoding='utf-8'))
assert status['state']=='finished',status
metadata=json.loads(Path(config['output']['export_metadata_json']).read_text(encoding='utf-8'))
frames=metadata['categories']['paths']['parameters']['frames']
assert all(f['vegetation_metrics']==g['vegetation_metrics'] for f,g in zip(frames,config['frames']))
study=analysis.from_export(metadata)
for r in study['records']:
    assert r['values']['vegetation/object/Tree/tagged_leaf_count']==2
    expected=2 if r['rx']=='RX_001' else 0
    assert r['values']['vegetation/link/leaf_surface_crossings']==expected,(r['rx'],r['values'])
analysis.write_report(source/'vegetation_parameter_analysis.html',[study])
hdf=source/'vegetation.h5'
output={**config['output'],'export_format':'HDF5','export_file':str(hdf),'export_metadata_json':str(source/'vegetation.hdf.metadata.json')}
export.export_completed_run(config_path=config_path,manifest_path=output['frames_manifest_json'],csv_path=output['results_csv'],output=output)
with h5py.File(hdf) as handle:
    saved=json.loads(handle['simulations/paths/frame_metadata/input_json'][0])
    assert saved['vegetation_metrics']==frames[0]['vegetation_metrics']
(source/'native_test_report.json').write_text(json.dumps({'finished':True,'worker_exit_code':run.returncode,'frames':len(frames),'links':len(study['records']),'metadata_preserved':True,'per_link_join_correct':True,'hdf5_metadata_preserved':True},indent=2),encoding='utf-8')
print('NATIVE_VEGETATION_METRICS_PASS',run.returncode,flush=True)
