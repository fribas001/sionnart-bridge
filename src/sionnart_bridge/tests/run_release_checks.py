"""Reproduce release checks with generated fixtures and explicit local runtimes."""
import argparse,json,subprocess,time,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--blender',required=True);p.add_argument('--python',required=True);p.add_argument('--node',required=True);p.add_argument('--output',required=True);args=p.parse_args()
root=Path(__file__).resolve().parents[1];out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
records=[]
def run(name,command):
 start=time.monotonic()
 with (out/(name+'.log')).open('w',encoding='utf-8') as log:
  result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=360)
 record={'name':name,'returncode':result.returncode,'seconds':round(time.monotonic()-start,2),'command':list(map(str,command))}
 records.append(record);(out/'release_checks.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
 print(name, 'PASS' if result.returncode==0 else 'FAIL',flush=True)
 if result.returncode:raise SystemExit('Failed: '+name+'; inspect '+str(out/(name+'.log')))
def blender(name,script,*tail):
 run(name,[args.blender,'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(root/'tests'/script),'--',*map(str,tail)])
run('python_tests',[args.python,'-m','unittest','discover','-s',str(root/'tests'),'-p','test_*.py'])
run('report_js',[args.node,str(root/'tests/test_report_math.cjs')])
blender('geometry_metadata','blender_geometry_metadata.py',out/'metadata_blender')
run('native_metadata',[args.python,str(root/'tests/native_geometry_metadata.py'),str(out/'metadata_blender'),str(out/'metadata_native')])
blender('result_import','blender_metadata_results.py',out/'metadata_native')
blender('parameter_analysis','blender_parameter_analysis.py',out/'parameters')
blender('plant_materials','blender_plant_materials.py',out/'plant_blender')
run('native_plants',[args.python,str(root/'tests/native_plant_materials.py'),str(out/'plant_blender'),str(out/'plant_native')])
blender('vegetation','blender_vegetation_metrics.py',out/'vegetation')
run('native_vegetation',[args.python,str(root/'tests/native_vegetation_metrics.py'),str(out/'vegetation')])
for name,script in [('workflows','blender_release_workflows.py'),('edge_cases','blender_release_edges.py'),('live_updates','blender_release_live.py'),('optional_sensing','blender_optional_sensing.py')]:
 blender(name,script,out/name,args.python)
blender('radio_map_orientation','blender_radio_map_orientation.py',out/'radio_map_orientation',args.python)
run('orientation_exports',[args.python,str(root/'tests/native_radio_map_orientation.py'),str(out/'radio_map_orientation')])
run('native_failures',[args.python,str(root/'tests/native_worker_failures.py'),str(out/'native_failures')])
print('ALL_RELEASE_CHECKS_PASS',flush=True)
