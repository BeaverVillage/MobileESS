from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
ROOT=Path(__file__).resolve().parents[1];f=pd.read_csv(ROOT/'MODEL_METRICS.csv')
arms=['B0','B1','B2','B3','B4','B5'];colors=['#65778d','#b44738','#d47a45','#007eaa','#498c7b','#846d9b']
fig,axes=plt.subplots(2,4,figsize=(18,8.4),layout='constrained');fig.patch.set_facecolor('#f7f9fc')
for i,(role,title) in enumerate([('EXPOSED_EVALUATION','Dec-Feb exposed diagnostic'),('MAY_HISTORICAL','May exposed historical diagnostic')]):
    data=f[f.role==role].set_index('arm').loc[arms]
    for j,(metric,label) in enumerate([('Q90_coverage','Q90 empirical coverage'),('Q90_pinball','Q90 pinball [GPUh]'),('requirement_ratio','Requirement ratio'),('burst_coverage','TRAIN-defined burst coverage')]):
        ax=axes[i,j];vals=data[metric];ax.bar(arms,vals,color=colors,zorder=3);ax.set_title(title+'\n'+label,fontsize=12,fontweight='bold');ax.grid(axis='y',alpha=.2,zorder=0)
        ax.spines[['right','top']].set_visible(False)
        if metric in ['Q90_coverage','burst_coverage']:
            ax.yaxis.set_major_formatter(PercentFormatter(1));ax.set_ylim(0,1.07)
            if metric=='Q90_coverage':ax.axhspan(.88,.92,color='#42b979',alpha=.15,zorder=1)
        else:ax.set_ylim(0,max(vals)*1.16)
        if metric=='requirement_ratio':ax.axhline(2,color='#bd3b32',linestyle='--',linewidth=1.2)
        for x,value in enumerate(vals):ax.text(x,value+(ax.get_ylim()[1])*.016,f'{value:.1%}' if metric in ['Q90_coverage','burst_coverage'] else f'{value:.2f}',ha='center',fontsize=10)
fig.suptitle('CC4-v2.6 | Frozen distributional / hybrid comparison',fontsize=22,fontweight='bold')
fig.supxlabel('B0 LightGBM  |  B1 zero-atom lognormal  |  B2 gated hybrid  |  B3 LGBM + DeepAR  |  B4 TFT  |  B5 DeepAR\nB4/B5: frozen 3-seed prediction mean. DEV/CAL selection: B0. No evaluation tuning.',fontsize=11)
fig.savefig(ROOT/'COMPARISON.png',dpi=160,facecolor=fig.get_facecolor());fig.savefig(ROOT/'COMPARISON.pdf',facecolor=fig.get_facecolor());plt.close(fig)
