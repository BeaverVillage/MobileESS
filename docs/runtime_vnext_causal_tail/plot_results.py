"""Static display of sealed metrics; no fitting or metric modification."""
from common import *
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
 freeze=json.loads((ROOT/'FINAL_SELECTION_FREEZE.json').read_text(encoding='utf-8'))
 cc=(ROOT/'SEED_MEAN_METRICS.csv').exists();path=ROOT/('SEED_MEAN_METRICS.csv' if cc else 'MODEL_METRICS.csv');f=pd.read_csv(path)
 if cc:
  f=f[(f.policy.eq(freeze['temporal']['policy'])&f.variant.eq('causal_calibrated'))|f.model.eq('CURRENT_LGBM')].copy()
  f['role']=f['split'];f['x']=f.requirement_ratio;f['y']=f.Q90_coverage
  title='CC4-v2.1: frozen candidate and references';xlabel='Q90 requirement / actual GPUh';band=(.88,.92);limit=2.
 else:
  f=f[f.state.eq('ALL')&f.model.ne('PR31_FROZEN_MOE')].copy();f['x']=f.overreserved_GPUh/f.requested_overreserved_GPUh;f['y']=f.GPU_coverage
  title='Runtime-vNext: full common GPU cohort';xlabel='Overreserved GPUh / requested-walltime reference';band=(.90,.95);limit=1.
 roles=['EXPOSED_EVALUATION','MAY_HISTORICAL'];names=sorted(f.model.unique());colors=dict(zip(names,plt.cm.tab10.colors));selected=freeze['model']
 fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
 for ax,role in zip(axes,roles):
  g=f[f.role.eq(role)];ax.axhspan(*band,color='#c9dfc8',alpha=.55);ax.axvline(limit,color='#565656',linestyle='--',linewidth=1)
  for _,r in g.iterrows():
   chosen=r.model==selected;ax.scatter(r.x,r.y,s=165 if chosen else 72,marker='*' if chosen else 'o',color=colors[r.model],edgecolors='white',linewidth=.7,label=r.model)
  if g.x.max()>10:ax.set_xscale('symlog',linthresh=.01)
  else:ax.set_xlim(0,max(float(g.x.max())*1.15,limit*1.25))
  ax.set_ylim(max(0,min(float(g.y.min())-.045,band[0]-.05)),min(1,float(g.y.max())+.045));ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1))
  ax.set_title('Dec–Feb' if cc and role=='EXPOSED_EVALUATION' else 'Exposed Apr' if role=='EXPOSED_EVALUATION' else 'Historical May')
  ax.set_xlabel(xlabel);ax.set_ylabel('Q90 coverage' if cc else 'GPU-weighted Q90 coverage');ax.grid(alpha=.15)
 legend={}
 for ax in axes:
  handles,labels=ax.get_legend_handles_labels();legend.update(zip(labels,handles))
 fig.legend(list(legend.values()),list(legend),loc='outside lower center',ncol=3,fontsize=8)
 note='\nPR31 matched-Pending comparison is reported separately in MATCHED_REFERENCE_METRICS.csv' if not cc else ''
 fig.suptitle(title+'\nStar = candidate selected before evaluation; shaded band = coverage gate'+note,fontsize=11)
 fig.savefig(ROOT/'COMPARISON.png',dpi=180);fig.savefig(ROOT/'COMPARISON.svg');plt.close(fig)
 svg=ROOT/'COMPARISON.svg';svg.write_bytes(('\n'.join(line.rstrip() for line in svg.read_text(encoding='utf-8').splitlines())+'\n').encode())
 dump('PLOT_RECEIPT.json',dict(time=now(),input_sha256=sha(path),selection_unchanged=True,axes='no prediction scaling/capping; Runtime overview uses full common cohort, PR31 matched-Pending metrics remain in separate table'))

if __name__=='__main__':main()
