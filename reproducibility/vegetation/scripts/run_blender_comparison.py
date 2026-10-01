"""Launch the supplied Blender/native harness in a new directory.
SPDX-License-Identifier: GPL-3.0-or-later
"""
from pathlib import Path
import argparse,json,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--blender',required=True);p.add_argument('--sionna-python',required=True);p.add_argument('--output',required=True);p.add_argument('--quick',action='store_true');p.add_argument('--prepare-only',action='store_true');a=p.parse_args();out=Path(a.output).resolve()
 if out.exists() and any(out.iterdir()):raise ValueError('Use a new empty output directory.')
 shutil.copytree(ROOT/'studies/native_comparison/benchmark_harness',out,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 env={'addon':str(ROOT/'software/sionnart_bridge'),'blend_file':str(ROOT/'blender/Procedural_Vegetation_reproducible.blend'),'python':str(Path(a.sionna_python).resolve()),'runner':str(ROOT/'scripts/run_vegetation.py'),'frames':[1] if a.quick else [1,9,10],'trials':1 if a.quick else 4}
 (out/'benchmark_environment.json').write_text(json.dumps(env,indent=2)+'\n')
 if a.prepare_only:return
 subprocess.run([a.blender,'--background','--factory-startup','--disable-autoexec','--python',str(out/'reproduce/blender_comparison.py')],check=True)
if __name__=='__main__':main()
