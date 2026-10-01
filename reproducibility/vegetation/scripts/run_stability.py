"""Prepare a fresh copy of the 30-case schedule, without old completion logs.
SPDX-License-Identifier: GPL-3.0-or-later
"""
from pathlib import Path
import argparse,shutil,subprocess,sys
import run_vegetation as native
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--limit',type=int);p.add_argument('--check',action='store_true');a=p.parse_args();out=Path(a.output).resolve()
 if out.exists() and any(out.iterdir()):raise ValueError('Use a new empty output directory.')
 src=ROOT/'studies/numerical_stability';out.mkdir(parents=True,exist_ok=True)
 for folder in ['configs','scenes','reproduce']:shutil.copytree(src/folder,out/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 shutil.copy2(src/'schedule.json',out/'schedule.json');(out/'logs').mkdir();(out/'runs').mkdir()
 for c in (out/'configs').glob('*.json'):native.load_experiment(c)
 if a.check:print('Fresh 30-case inputs validated; no simulations executed.');return
 command=[sys.executable,str(out/'reproduce/run_schedule.py'),'--python',sys.executable]
 if a.limit is not None:command+=['--limit',str(a.limit)]
 subprocess.run(command,check=True)
if __name__=='__main__':main()
