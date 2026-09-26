"""Display-only plot from frozen CSV evidence; no fitting or selection."""
import argparse
import sys
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--dependencies',type=Path,help='Optional existing matplotlib/Pillow package directory')
args=parser.parse_args()
if args.dependencies:sys.path.insert(0,str(args.dependencies))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

root=Path(__file__).resolve().parent
m=pd.read_csv(root/'SEED_MEAN_METRICS.csv')
b=pd.read_csv(root/'BURST_METRICS.csv')
families=['SEASONAL','LGBM','TFT','DEEPAR']
colors=['#9ca3af','#2563eb','#059669','#d97706']
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(2,4,figsize=(16,7.6),layout='constrained')
for row,(split,label) in enumerate([('EXPOSED_EVALUATION','Dec 2024 - Feb 2025 (88 days)'),('MAY_HISTORICAL','May 2025 (31 days)')]):
    s=m[m.split.eq(split)&m.variant.eq('calibrated')].set_index('model').loc[families]
    burst=b[b.split.eq(split)&b.variant.eq('calibrated')&b.regime.eq('burst')].groupby('model').Q90_coverage.mean().loc[families]
    vectors=[s.Q90_coverage*100,s.Q90_pinball,s.requirement_ratio,burst*100]
    titles=['Q90 coverage (%)','Q90 pinball (GPU h)','Prediction / realized work','Burst Q90 coverage (%)']
    for col,(vals,title) in enumerate(zip(vectors,titles)):
        ax=axes[row,col]
        ax.bar(families,vals,color=colors,width=.65,zorder=3)
        ax.grid(axis='y',alpha=.18,zorder=0)
        ax.set_title(title,loc='left',fontweight='bold',fontsize=10)
        ax.tick_params(axis='x',rotation=25)
        if col==0:
            ax.axhspan(88,92,color='#bbf7d0',alpha=.5,zorder=1)
            ax.axhline(90,color='#14532d',ls='--',lw=1)
            ax.set_ylim(75,100)
            ax.set_ylabel(label,fontweight='bold')
        else:ax.set_ylim(0,float(max(vals))*1.25)
        for i,val in enumerate(vals):ax.text(i,val+(.45 if col==0 else max(vals)*.025),f'{val:.2f}',ha='center',fontsize=9)
fig.suptitle('CC4-v2: removing the cap enables near-90% coverage, but does not solve sharpness or bursts\n'
             'Frozen calibration; three-seed means (seasonal: one); DeepAR selected on DEVELOPMENT only',fontsize=14,fontweight='bold')
fig.savefig(root/'FORECAST_COMPARISON.png',dpi=150)
fig.savefig(root/'FORECAST_COMPARISON.svg')
print('Saved frozen-metric figure')
