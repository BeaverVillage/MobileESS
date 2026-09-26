"""Plot-only artifact, isolated from scientific selection."""
from pathlib import Path
import sys,json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent
f=pd.read_csv(ROOT/'MODEL_METRICS.csv');f=f[f.role.eq('MAY_HISTORICAL')&f.state.eq('RUNNING')]
s=pd.read_csv(ROOT/'RUNNING_ELAPSED_METRICS.csv');s=s[s.role.eq('MAY_HISTORICAL')&s.arm.eq('R3')].set_index('elapsed_regime')
fig,axes=plt.subplots(1,2,figsize=(12,4.7),layout='constrained');ax=axes[0]
ax.axvspan(90,100,color='#dcfce7',alpha=.45);ax.axhspan(0,1,color='#dcfce7',alpha=.3)
ax.axvline(90,color='#148045',ls='--',lw=1);ax.axhline(1,color='#b91c1c',ls='--',lw=1)
colors={'R0':'#64748b','R1':'#2563eb','R2':'#d97706','R3':'#7c3aed'}
for r in f.itertuples():
    ax.scatter(r.GPU_coverage*100,r.overreserve_vs_requested,s=90,color=colors[r.arm],zorder=3)
    ax.annotate(r.arm,(r.GPU_coverage*100,r.overreserve_vs_requested),xytext=(5,7),textcoords='offset points',color=colors[r.arm],fontsize=11)
ax.set(xlabel='GPU-weighted coverage (%)',ylabel='Overreserved GPU h / walltime reference',xlim=(50,98),ylim=(0,1.9),title='Running: fixed Q90/Q95 envelope');ax.grid(alpha=.18)
order=['<1h','1-2h','2-4h','4-8h','>8h'];a=s.reindex(order)
axes[1].bar(order,a.Q95_fraction*100,color='#7c3aed',label='Job-issue weighted')
axes[1].plot(order,a.Q95_GPU_fraction*100,'o--',color='#d97706',label='GPU weighted')
axes[1].set(xlabel='Elapsed regime',ylabel='R3 assignments to Q95 (%)',ylim=(0,100),title='Frozen threshold 0.10 | May diagnostic')
axes[1].legend(frameon=False);axes[1].grid(axis='y',alpha=.18)
fig.suptitle('Runtime-vNext3 | Pending unchanged | No production replacement',fontsize=13)
fig.savefig(ROOT/'COMPARISON.png',dpi=190);fig.savefig(ROOT/'COMPARISON.svg');plt.close(fig)
(ROOT/'PLOT_ENVIRONMENT.json').write_text(json.dumps(dict(executable=sys.executable,numpy=np.__version__,pandas=pd.__version__,matplotlib=matplotlib.__version__,purpose='plot only; study environment unchanged'),indent=2),encoding='utf-8')
