from common13 import *
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import platform

def main():
    comp=pd.read_csv(ROOT/'TOTAL_MODEL_COMPARISON.csv');folds=pd.read_csv(ROOT/'TOTAL_FOLD_METRICS.csv')
    fig,axes=plt.subplots(1,2,figsize=(13.5,5),layout='constrained')
    colors=['#363b45','#4477aa','#228833','#ccbb44','#cc6677','#aa3377','#66ccee']
    for n,(_,r) in enumerate(comp.iterrows()):
        f=folds[folds.arm.eq(r.arm)].sort_values('fold');label=r.arm.replace('EXPANDING_','')
        axes[0].plot(f.fold,f.Q90_coverage*100,marker='o',label=label,color=colors[n],linewidth=1.6)
        axes[1].plot([4,12,24],[r.gt4h_coverage*100,r.gt12h_coverage*100,r.gt24h_coverage*100],marker='o',label=label,color=colors[n])
    axes[0].axhline(85,color='black',linestyle='--',linewidth=1,label='Min-fold gate 85%')
    axes[1].plot([4,12,24],[85,80,70],'k--',label='Tail gates')
    axes[0].set(title='Temporal coverage: every fold',xlabel='Original temporal fold',ylabel='Q90 coverage (%)',xticks=range(1,6),ylim=(0,102))
    axes[1].set(title='Pooled long-runtime coverage',xlabel='Actual runtime exceeds (hours)',ylabel='Q90 coverage (%)',xticks=[4,12,24],ylim=(0,102))
    for ax in axes:ax.grid(alpha=.2);ax.legend(fontsize=8,loc='lower left')
    modes='/'.join(comp.calibration.unique())
    fig.suptitle('Runtime-vNext13 | pre-April only | '+modes+' fixed hazard + current workload state',fontsize=13)
    fig.savefig(ROOT/'TEMPORAL_COVERAGE.png',dpi=180);plt.close(fig)
    write('PLOT_ENVIRONMENT.json',dict(time=now(),python=platform.python_version(),matplotlib=matplotlib.__version__,pandas=pd.__version__,scope='plotting existing metrics only; no model fitting'))
if __name__=='__main__':main()
