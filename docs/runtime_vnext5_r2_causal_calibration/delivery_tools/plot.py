"""Plot sealed-input diagnostic metrics; no model/calibration changes."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
m=pd.read_csv(ROOT/'MODEL_METRICS.csv');m=m[m.state.eq('RUNNING')&m.role.eq('MAY_HISTORICAL')].set_index('arm')
c=pd.read_csv(ROOT/'PAIRED_UNCERTAINTY.csv');c=c[c.state.eq('RUNNING')&c.reference.eq('R1')&c.block_days.eq(7)]
colors={'R0':'#7e8796','R1':'#347bbb','R2':'#26a291','R3':'#d58835'}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(2,3,figsize=(15,8.4),layout='constrained')
for ax,key,title,threshold in [(axes[0,0],'coverage','May empirical coverage',.90),(axes[0,1],'GPU_coverage','May GPU-weighted coverage',.90),(axes[0,2],'long_under','May underprediction: total runtime >4h',.15),(axes[1,2],'overreserve_vs_requested','May overreserve / walltime overreserve',1.)]:
    arms=['R0','R1','R2','R3'];values=m.loc[arms,key].to_numpy();ax.bar(arms,values,color=[colors[a] for a in arms]);ax.axhline(threshold,color='#b53737',ls='--',lw=1);ax.set_title(title,loc='left',weight='bold');ax.set_ylim(0,max(max(values)*1.15,threshold*1.1));ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    for x,y in enumerate(values):ax.text(x,y+ax.get_ylim()[1]*.015,f'{y:.3f}',ha='center',fontsize=9)
for ax,key,title,scale in [(axes[1,0],'missed_slots_reduction','Missed GPU-slot reduction vs raw R1 (%)',100),(axes[1,1],'pinball_Q90','Q90 pinball delta vs raw R1 (seconds)',1)]:
    for i,(role,arm) in enumerate([(r,a) for r in ['EXPOSED_EVALUATION','MAY_HISTORICAL'] for a in ['R2','R3']]):
        z=c[c.role.eq(role)&c.candidate.eq(arm)&c.metric.eq(key)].iloc[0];y=z.estimate*scale;lo=z.CI95_low*scale;hi=z.CI95_high*scale
        ax.errorbar(i,y,yerr=[[y-lo],[hi-y]],fmt='o',color=colors[arm],capsize=5,markersize=7)
    ax.set_xticks(range(4),['April R2','April R3','May R2','May R3']);ax.axhline(0,color='#777',lw=1);ax.set_title(title,loc='left',weight='bold');ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
fig.suptitle('Runtime-vNext5 | Causal residual calibration of frozen raw Q90\nR1 = PR71 R2 raw; R2 = global; R3 = GPU-weighted',fontsize=16,weight='bold')
fig.text(.5,-.025,'Historical diagnostics only. Paired 7-issue block 95% CI, 2,000 draws. Pending is exact R0. No model refits or production promotion.',ha='center',fontsize=10)
fig.savefig(ROOT/'COMPARISON.png',dpi=160,bbox_inches='tight');print('PLOT_COMPLETE')
