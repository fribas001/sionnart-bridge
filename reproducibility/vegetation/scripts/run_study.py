"""Run a chosen subset in native Sionna, outside Blender. New outputs only.
SPDX-License-Identifier: GPL-3.0-or-later
"""
from pathlib import Path
import argparse,datetime,json,subprocess,sys
from build_native_configs import build
def main():
 p=argparse.ArgumentParser();p.add_argument('study');p.add_argument('--frames',default='1');p.add_argument('--output',required=True);p.add_argument('--check',action='store_true');a=p.parse_args()
 out=Path(a.output).resolve()
 if out.exists() and any(out.iterdir()):raise ValueError('Use a new empty output directory.')
 paths=build(a.study,out/'configs');selected=None if a.frames=='all' else {int(x) for x in a.frames.split(',')};results=[]
 for config in paths:
  c=json.loads(config.read_text());item=c['scenes'][0]
  if selected is not None and item['frame'] not in selected:continue
  command=[sys.executable,str(Path(__file__).with_name('run_vegetation.py')),str(config)]
  command+=['--check'] if a.check else ['--output',str(out/'runs'/item['id'])]
  code=subprocess.call(command);results.append({'id':item['id'],'exit_code':code})
  (out/'status.json').write_text(json.dumps(results,indent=2)+'\n')
 if not results:raise ValueError('No matching frames selected.')
 return 0 if all(x['exit_code']==0 for x in results) else 2
if __name__=='__main__':sys.exit(main())
