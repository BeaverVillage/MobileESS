from common12 import *
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
    f=pd.read_csv(ROOT/'TOTAL_FOLD_METRICS.csv');s=pd.read_csv(ROOT/'TOTAL_MODEL_COMPARISON.csv')
    assert len(s)==5
    colors=['#64748b','#2563eb','#0f766e','#9333ea','#ea580c']
    fig,axes=plt.subplots(1,2,figsize=(12,4.8),layout='constrained')
    for (arm,group),color in zip(f.groupby('arm',sort=False),colors):
        axes[0].plot(group.fold,100*group.Q90_coverage,marker='o',label=arm,color=color,lw=2)
    axes[0].axhline(85,color='#b91c1c',ls='--',label='Minimum-fold gate: 85%')
    axes[0].set(xlabel='Chronological fold',ylabel='Q90 coverage (%)',xticks=range(1,6),ylim=(35,102),title='Causal regime features do not prevent fold collapse')
    axes[0].legend(fontsize=8,loc='lower right')
    x=np.arange(len(s))
    axes[1].bar(x-.18,100*s.Q90_coverage,.36,label='Pooled',color='#2563eb')
    axes[1].bar(x+.18,100*s.gt4h_coverage,.36,label='Runtime >4h',color='#ea580c')
    axes[1].axhspan(88,92,color='#2563eb',alpha=.12,label='Pooled gate: 88–92%')
    axes[1].axhline(85,color='#b91c1c',ls='--',label='>4h gate: 85%')
    axes[1].set(xticks=x,xticklabels=['R0','R1','R2','R3','D90 R2'],ylabel='Q90 coverage (%)',ylim=(0,102),title='Pooled coverage can hide long-job undercoverage')
    axes[1].legend(fontsize=8,loc='lower right')
    for ax in axes:
        ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    fig.suptitle('Runtime-vNext12 • five unchanged pre-April folds • C0 raw hazard',fontsize=13)
    fig.savefig(ROOT/'TEMPORAL_COVERAGE.png',dpi=180)
    plt.close(fig)
    write('PLOT_ENVIRONMENT.json',dict(python=sys.executable,matplotlib=matplotlib.__version__,pandas=pd.__version__,numpy=np.__version__,scope='Plot only; model training uses EXECUTION_ENVIRONMENT.json'))
if __name__=='__main__':main()
