"""Display-only plot of frozen diagnostics; no selection or prediction changes."""
from pathlib import Path
import sys,json,hashlib
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
f=pd.read_csv(ROOT/'MODEL_METRICS.csv');ci=pd.read_csv(ROOT/'PAIRED_UNCERTAINTY.csv')
roles=['EXPOSED_EVALUATION','MAY_HISTORICAL'];colors={'C0':'#343434','C1':'#1769aa','C2':'#a343b4'}
fig,axs=plt.subplots(2,2,figsize=(11,7.5),layout='constrained')
for k,role in enumerate(roles):
 g=f[f.role.eq(role)];ax=axs[0,k]
 ax.axvspan(60,100,color='#c9dfc8',alpha=.35);ax.axhspan(88,92,color='#b6d5ea',alpha=.35)
 for _,r in g.iterrows():
  ax.scatter(100*r.burst_coverage,100*r.coverage,color=colors[r.model],marker='*' if r.model=='C0' else 'o',s=130 if r.model=='C0' else 65,label=r.model)
 ax.set(xlim=(-2,100),ylim=(65,100),xlabel='Burst coverage (%)',ylabel='Overall Q90 coverage (%)',title='Exposed Dec–Feb' if k==0 else 'Historical May')
 ax.grid(alpha=.15);ax.legend(loc='lower right')
 ax=axs[1,k];c=ci[ci.role.eq(role)&ci.metric.eq('Q90_pinball')&ci.block_observed_days.eq(7)]
 for j,(_,r) in enumerate(c.iterrows()):
  ax.plot([r.CI95_low,r.CI95_high],[j,j],color=colors[r.model],linewidth=2)
  ax.scatter(r.delta,j,color=colors[r.model],s=60)
 ax.set_yticks(range(len(c)),c.model.tolist());ax.axvline(0,color='#777',linestyle='--')
 ax.set(xlabel='Q90 pinball delta vs C0 [GPUh]; 95% paired CI',ylim=(-.6,len(c)-.4));ax.grid(axis='x',alpha=.15)
fig.suptitle('CC4-v2.2: fixed burst components, historical diagnostics\nStar = C0 retained by DEV/CAL rule; green = burst minimum, blue = preferred overall coverage')
fig.savefig(ROOT/'COMPARISON.png',dpi=180);fig.savefig(ROOT/'COMPARISON.svg');plt.close(fig)
svg=ROOT/'COMPARISON.svg';svg.write_text('\n'.join(line.rstrip() for line in svg.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8')
record={'python':sys.version,'matplotlib':matplotlib.__version__,'pandas':pd.__version__,'display_only':True,'ML_environment_unchanged':True,'inputs':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ['MODEL_METRICS.csv','PAIRED_UNCERTAINTY.csv']}}
(ROOT/'PLOT_RECEIPT.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
