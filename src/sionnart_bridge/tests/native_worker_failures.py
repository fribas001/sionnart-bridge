"""Every worker must report failed and exit nonzero for an invalid run."""
import json,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
records={}
for worker in ['sionna_worker','radio_map_worker','radio_map_3d_worker']:
 folder=out/worker;folder.mkdir(exist_ok=True)
 status=folder/'status.json';config={'output':{'status_json':str(status)},'frames':[{'frame':1}],'scene_xml':str(folder/'missing.xml'),'scene_xml_sha256':'0'*64}
 path=folder/'config.json';path.write_text(json.dumps(config))
 result=subprocess.run([sys.executable,str(root/(worker+'.py')),'--config',str(path)],capture_output=True,text=True,timeout=40)
 (folder/'worker.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
 assert result.returncode==1,(worker,result.returncode)
 receipt=json.loads(status.read_text());assert receipt['state']=='failed' and receipt['error']
 records[worker]={'returncode':result.returncode,'state':receipt['state']}
(out/'test_report.json').write_text(json.dumps(records,indent=2));print('NATIVE_FAILURES_PASS')
