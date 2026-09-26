"""Render frozen metrics in a plotting-only environment."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
f=pd.read_csv(ROOT/'MODEL_METRICS.csv');f=f[f.state.eq('RUNNING')]
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(2,3,figsize=(15,8.5),layout='constrained')
colors={'R0':'#7f8a99','R1':'#3678b5','R2':'#249f92','R3':'#dc7e36'}
fields=['coverage','GPU_coverage','overreserve_vs_requested','long_under','missed_GPU_slots','pinball_Q90']
titles=['Empirical coverage','GPU-weighted coverage','Overreserve / walltime overreserve','Underprediction: total runtime >4h','Missed GPU-slots','Q90 pinball (hours)']
for ax,field,title in zip(axes.flat,fields,titles):
    for j,role in enumerate(['EXPOSED_EVALUATION','MAY_HISTORICAL']):
        for k,arm in enumerate(['R0','R1','R2','R3']):
            g=f[f.role.eq(role)&f.arm.eq(arm)]
            if len(g):
                value=float(g.iloc[0][field]);value=value/3600 if field=='pinball_Q90' else value
                ax.bar(j+(k-1.5)*.18,value,width=.17,color=colors[arm],label=arm if j==1 else None)
    ax.set_xticks([0,1],['April diagnostic','May exposed diagnostic']);ax.set_title(title,loc='left',weight='bold');ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    if field in ['coverage','GPU_coverage']:ax.axhline(.9,color='#b73737',ls='--',lw=1);ax.set_ylim(0,1.04)
    if field=='long_under':ax.axhline(.15,color='#b73737',ls='--',lw=1)
    if field=='overreserve_vs_requested':ax.axhline(1,color='#b73737',ls='--',lw=1)
axes[0,0].legend(ncol=4,loc='lower left')
fig.suptitle('Runtime-vNext4 | Fixed Q90 Running bounds\nR2: GPU/long-job weighted MQ; R3: archive-conditional censored AFT',fontsize=17,weight='bold')
fig.text(.5,-.025,'Pending is exact frozen R0 in every arm. R0 unavailable for April. Scheduler/census provenance unverified; no production promotion.',ha='center',fontsize=10)
fig.savefig(ROOT/'COMPARISON.png',dpi=160,bbox_inches='tight')
print('PLOT_COMPLETE')
