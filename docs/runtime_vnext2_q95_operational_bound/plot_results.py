"""Publication-only plot; run in isolated plotting environment."""
from pathlib import Path
import json,sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent
f=pd.read_csv(ROOT/'MODEL_METRICS.csv');f=f[f.role.eq('MAY_HISTORICAL')]
fig,axes=plt.subplots(1,2,figsize=(11.8,4.5),layout='constrained')
colors={'R0':'#626977','R1':'#2563eb','R2':'#d97706'}
for ax,state in zip(axes,['PENDING','RUNNING']):
    ax.axvspan(90,100,color='#dcfce7',alpha=.5);ax.axhspan(0,1,color='#dcfce7',alpha=.35)
    ax.axvline(90,color='#148045',ls='--',lw=1);ax.axhline(1,color='#b91c1c',ls='--',lw=1)
    for r in f[f.state.eq(state)].itertuples():
        ax.scatter(r.coverage*100,r.overreserve_vs_requested,s=95,color=colors[r.arm],zorder=3)
        ax.annotate(r.arm+' (Q'+str(int(r.nominal_quantile*100))+')',(r.coverage*100,r.overreserve_vs_requested),
                    xytext=(5,9),textcoords='offset points',fontsize=10,color=colors[r.arm])
    ax.set(title=state+' — '+('total runtime' if state=='PENDING' else 'remaining runtime'),
           xlabel='Empirical coverage (%)',ylabel='Overreserved GPU h / walltime reference',xlim=(45,100),ylim=(0,1.85))
    ax.grid(alpha=.18)
fig.suptitle('Runtime-vNext2 | May historical diagnostic | Frozen decision: retain R0',fontsize=13)
fig.savefig(ROOT/'COMPARISON.png',dpi=190);fig.savefig(ROOT/'COMPARISON.svg');plt.close(fig)
(ROOT/'PLOT_ENVIRONMENT.json').write_text(json.dumps(dict(executable=sys.executable,numpy=np.__version__,pandas=pd.__version__,matplotlib=matplotlib.__version__,purpose='plot only; study environment unchanged'),indent=2),encoding='utf-8')
