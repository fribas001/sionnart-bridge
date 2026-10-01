"""Reproduce numerical summaries and figures from packaged observations.
No Blender/Sionna imports and no dependence on the author's original folders.
SPDX-License-Identifier: GPL-3.0-or-later
"""
from pathlib import Path
import argparse,csv,json,shutil,subprocess,sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import run_vegetation as native
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def ranks(x):
 x=np.asarray(x);out=np.zeros(len(x));order=np.argsort(x);start=0
 while start<len(x):
  end=start+1
  while end<len(x) and x[order[end]]==x[order[start]]:end+=1
  out[order[start:end]]=(start+end-1)/2+1;start=end
 return out
def run(output,verify=True):
 out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True);figs=out/'Figures';figs.mkdir(exist_ok=True)
 summary={'definition':'All valid paths, RX0/RX antenna0/TX0/TX antenna0. Gain=10*log10(sum(|a|^2)); not a coherent sum, not array-combined received power.'};table=[];errors=[]
 runs=[];configs=[]
 for i in range(1,6):
  d=ROOT/'data'/f'foliage_r{i}';rr=read(d/'records.json');cc=read(d/'configurations.json');runs.append(rr);configs.append(cc)
  for r,c in zip(rr,cc):
   if verify:
    with np.load(d/c['raw_arrays'],allow_pickle=False) as a:m=native.summarize(a)
    for k,v in m.items():
     target=c['channel']['links'][0][k]
     if v is None or isinstance(v,(bool,int)):assert v==target,(i,r['frame'],k)
     else:errors.append(abs(v-target));assert abs(v-target)<1e-8,(i,r['frame'],k,v,target)
   table.append({'realization':i,'generator_seed':c['geometry_seed'],'frame':r['frame'],'leaf_density_input':r['tree_inputs']['Leaf Density'],'add_leaves':r['tree_inputs']['Add Leaves'],'leaf_components':c['vegetation_metrics']['scene']['leaf_component_count'],**{k:r['metrics'].get(k) for k in ['path_count','los_available','total_power_db','strongest_path_gain_db','rms_delay_spread_ns']}})
 delta=[r[8]['metrics']['total_power_db']-r[0]['metrics']['total_power_db'] for r in runs]
 summary['foliage']={'frames':len(table),'minimum_foliage_gain_change_db':delta,'median_change_db':float(np.median(delta)),'raw_arrays_verified':50 if verify else 0,'maximum_recalculation_error':max(errors,default=0),'realization_to_generator_seed':[1,2,4,5,6]}
 with (out/'foliage_observations.csv').open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=list(table[0]));w.writeheader();w.writerows(table)
 plt.rcParams.update({'font.size':10,'font.family':'DejaVu Sans','axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42,'svg.fonttype':'none'})
 def save(fig,name):
  for ext in ['png','pdf','svg']:fig.savefig(figs/f'{name}.{ext}',dpi=300,bbox_inches='tight')
  plt.close(fig)
 colors=['#0072B2','#D55E00','#009E73','#CC79A7','#6B5A30'];fig,ax=plt.subplots(1,2,figsize=(8,3.5),layout='constrained')
 for i,(rr,cc,col) in enumerate(zip(runs,configs,colors),1):
  gains=np.array([r['metrics']['total_power_db'] for r in rr]);counts=np.array([c['vegetation_metrics']['scene']['leaf_component_count'] for c in cc]);x=100*counts/counts[0]
  ax[0].plot(x[:9],gains[:9],'-o',ms=3,color=col,label=str(i));ax[0].scatter(0,gains[9],marker='D',facecolor='white',edgecolor=col)
  ax[1].plot([i,i],[gains[8]-gains[0],gains[9]-gains[0]],color=col);ax[1].scatter(i,gains[8]-gains[0],color=col);ax[1].scatter(i,gains[9]-gains[0],marker='D',facecolor='white',edgecolor=col)
 ax[0].set(xlim=(104,-5),xlabel='Remaining leaf components (%)',ylabel='Summed path gain (dB)',title='(A) Foliage sensitivity');ax[0].legend(title='Realization',ncol=3,frameon=False,fontsize=8)
 ax[1].set(xlabel='Realization',ylabel='Change from full foliage (dB)',xticks=range(1,6),title='(B) Endpoint changes');ax[1].axhline(0,color='grey',ls='--',lw=.8)
 for a in ax:a.grid(alpha=.15)
 save(fig,'foliage_sensitivity_five_realizations')
 rs=read(ROOT/'data/seed_ensemble/records.json');gain=np.array([r['metrics']['total_power_db'] for r in rs]);area=np.array([r['values']['vegetation/scene/leaf_area_estimate_m2'] for r in rs]);lad=np.array([r['values']['vegetation/link/corridor_leaf_area_density_m_inv'] for r in rs])
 rhoa=float(np.corrcoef(ranks(area),ranks(gain))[0,1]);rhol=float(np.corrcoef(ranks(lad),ranks(gain))[0,1])
 summary['seed_ensemble']={'n':len(rs),'min_gain_db':float(gain.min()),'max_gain_db':float(gain.max()),'range_db':float(np.ptp(gain)),'median_gain_db':float(np.median(gain)),'quartiles_db':np.quantile(gain,[.25,.75]).tolist(),'rho_area':rhoa,'rho_corridor':rhol,'source':'original exported summaries; limited CIR components are not used to recompute full-path power'}
 with (out/'seed_observations.csv').open('w',newline='',encoding='utf-8') as f:
  w=csv.writer(f);w.writerow(['frame','geometry_seed','total_power_db','leaf_area_m2','corridor_leaf_area_density_m_inv'])
  w.writerows((r['frame'],r['geometry_seed'],g,a,l) for r,g,a,l in zip(rs,gain,area,lad))
 fig,ax=plt.subplots(1,3,figsize=(8.6,3.1),layout='constrained');ax[0].step(np.sort(gain),np.arange(1,len(gain)+1)/len(gain),where='post');ax[0].set(xlabel='Summed path gain (dB)',ylabel='Cumulative fraction',title='(A) Gain distribution')
 for a,x,label,title,rho in [(ax[1],area,'Total leaf area (m²)','(B) Bulk foliage',rhoa),(ax[2],lad,'Corridor leaf-area density\n(m²/m³)','(C) Link-specific foliage',rhol)]:
  a.scatter(x,gain,s=15,color='#156082');a.set(xlabel=label,ylabel='Summed path gain (dB)',title=title);a.text(.04,.95,f'Spearman $\\rho$ = {rho:.3f}',transform=a.transAxes,va='top',fontsize=8)
 for a in ax:a.grid(alpha=.15)
 save(fig,'seed_variability')
 # Earlier numerical sweeps remain separate from the matched foliage checks.
 fig,axes=plt.subplots(2,2,figsize=(8,5.5),layout='constrained')
 for col,study,field,xlabel in [(0,'exploratory_depth','max_depth','Maximum interaction depth'),(1,'exploratory_rays','samples_per_src','Samples per transmitter (millions)')]:
  rr=read(ROOT/'data'/study/'records.json');cc=read(ROOT/'data'/study/'configurations.json');x=np.array([c['simulation'][field] for c in cc],dtype=float)
  if col:x/=1e6
  g=[r['metrics']['total_power_db'] if r['metrics']['path_count'] else np.nan for r in rr];strong=[r['metrics']['strongest_path_gain_db'] if r['metrics']['path_count'] else np.nan for r in rr]
  axes[0,col].plot(x,g,'-o',ms=3,label='Summed path gain');axes[0,col].plot(x,strong,'--',label='Strongest path');axes[0,col].set(ylabel='Gain (dB)',xlabel=xlabel);axes[0,col].legend(fontsize=8,frameon=False)
  axes[1,col].plot(x,[r['metrics']['rms_delay_spread_ns'] if r['metrics']['path_count'] else np.nan for r in rr],'-o',ms=3);axes[1,col].set(xlabel=xlabel,ylabel='RMS delay spread (ns)')
  for row in [0,1]:axes[row,col].grid(alpha=.15)
 save(fig,'numerical_settings')
 # The spatial example uses the original evaluated mesh snapshots and top-five paths.
 from matplotlib.collections import PolyCollection
 with (ROOT/'data/foliage_r2/displayed_path_points.csv').open(encoding='utf-8',newline='') as f:points=list(csv.DictReader(f))
 fig,axes=plt.subplots(1,3,figsize=(8.2,3.05),layout='constrained')
 for ax,frame,title in zip(axes,[1,9,10],['(A) Full foliage','(B) Reduced foliage','(C) Bare tree']):
  geo=np.load(ROOT/'data/spatial_figure'/f'realization_2_F{frame:04d}.npz',allow_pickle=False);xyz=geo['xyz'];tri=geo['triangles'];leaf=geo['leaf']
  ax.add_collection(PolyCollection(xyz[tri[~leaf]][:,:,[1,2]],facecolors='#85735d',edgecolors='none',alpha=.35,rasterized=True))
  if leaf.any():ax.add_collection(PolyCollection(xyz[tri[leaf]][:,:,[1,2]],facecolors='#4b8d43',edgecolors='none',alpha=.18,rasterized=True))
  selected=[p for p in points if int(p['frame'])==frame and int(p['top_rank'])<=5];pids=sorted(set(p['path_index'] for p in selected));assert len(pids)==5
  for pid in pids:
   rows=sorted([p for p in selected if p['path_index']==pid],key=lambda p:int(p['point_order']));ax.plot([float(p['y']) for p in rows],[float(p['z']) for p in rows],lw=.9,color='#a52b3d',alpha=.85)
  ax.scatter([-10,10],[7,7],c=['#d53b30','#277cb9'],s=25,zorder=5)
  for y,label in [(-10,'TX'),(10,'RX')]:ax.text(y,7.8,label,ha='center',fontsize=8)
  count=configs[1][frame-1]['vegetation_metrics']['scene']['leaf_component_count'];g=runs[1][frame-1]['metrics']['total_power_db']
  ax.set(xlim=(-11.5,11.5),ylim=(-.5,12.5),aspect='equal',xlabel='$y$ (m)',title=f'{title}\n{count:,} leaf components\nSummed gain {g:.2f} dB');ax.set_xticks([-10,0,10]);ax.set_yticks([0,5,10]);ax.grid(alpha=.15)
 axes[0].set_ylabel('$z$ (m)');save(fig,'procedural_foliage_paths')
 # Keep the archival observations intact: sub-study analyzers run on fresh copies.
 for name,script in [('native_comparison','analyze_comparison.py'),('numerical_stability','analyze_stability.py')]:
  target=out/name
  if not target.exists():shutil.copytree(ROOT/'studies'/name,target,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
  subprocess.run([sys.executable,str(target/'reproduce'/script)],check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
  summary[name]={'recalculated':True,'output':name}
 (out/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n',encoding='utf-8');return summary
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',default='reproduced_analysis');a=p.parse_args();print(json.dumps(run(a.output),indent=2))
