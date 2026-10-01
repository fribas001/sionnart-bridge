"""Write native Sionna inputs from the recorded conditions and packaged scenes.
SPDX-License-Identifier: GPL-3.0-or-later
"""
from pathlib import Path
import argparse,copy,json,os,xml.etree.ElementTree as ET
import run_vegetation as native
ROOT=Path(__file__).resolve().parents[1]
def build(study,out):
 data=ROOT/'data'/study;records=json.loads((data/'configurations.json').read_text());out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True);paths=[]
 for r in records:
  xml=data/r['scene'] if r['geometry_status']=='original_export' else data/'reconstructed'/r['scene']
  if not xml.is_file():raise FileNotFoundError(f'{xml}: reconstruct this study using configure_blender.py first.')
  cfg=copy.deepcopy(native.read_json(ROOT/'scripts/experiment.json'));sim=r['simulation']
  cfg['scene'].update({k:sim[k] for k in ['frequency_hz','bandwidth_hz','temperature_k']})
  cfg['solver']={k:sim[k] for k in native.SOLVER_KEYS};cfg['deterministic']=sim['deterministic'];cfg['arrays']=r['antenna']
  for role,ref in [('tx',r['transmitters'][0]),('rx',r['receivers'][0])]:
   cfg['devices'][role]={'name':ref['name'],'position':ref['position'],'look_at':ref['look_at_target_position'],'velocity':ref.get('velocity_m_s',[0,0,0])}
   if role=='tx':cfg['devices'][role]['power_dbm']=ref['power_dbm']
  cfg['materials']={m['source_name']:{k:m[k] for k in native.MATERIAL_KEYS} for m in r['materials']}
  mids=[x.attrib['id'] for x in ET.parse(xml).findall('.//bsdf') if 'id' in x.attrib]
  bindings={m:m for m in mids if m in cfg['materials']}
  # Appended material names are unchanged; fail rather than guess a missing binding.
  item={'id':r['id'],'frame':r['frame'],'geometry_seed':r['geometry_seed'],'xml':Path(os.path.relpath(xml,out)).as_posix(),'material_bindings':bindings,'reference_metrics':{k:r['channel']['links'][0].get(k) for k in ['path_count','los_available','total_power_db','strongest_path_gain_db','first_arrival_ns','mean_excess_delay_ns','rms_delay_spread_ns']}}
  if r['raw_arrays']:item['reference_npz']=Path(os.path.relpath(data/r['raw_arrays'],out)).as_posix()
  cfg['scenes']=[item];path=out/f"{r['id']}.json";native.write_json(path,cfg);native.load_experiment(path);paths.append(path)
 return paths
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('study');p.add_argument('--output',required=True);a=p.parse_args();paths=build(a.study,a.output);print(f'{len(paths)} complete native configurations validated.')
