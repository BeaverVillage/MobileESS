from pathlib import Path
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent
def main():
    m=pd.read_csv(ROOT/'ARM_METRICS.csv');d=pd.read_csv(ROOT/'TARGET_DISTRIBUTION.csv')
    colors=plt.cm.tab10(np.arange(6));roles=['EXPOSED_EVALUATION','OOS_EXTENSION','MAY_HISTORICAL']
    plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':160})
    for metric,ylabel,file in [('requirement_ratio','Integrated reserve ratio','PARETO_RESERVE'),('Q90_pinball','Pinball / same-target F0','PARETO_PINBALL')]:
        fig,axs=plt.subplots(4,3,figsize=(13,13),layout='constrained')
        for i,t in enumerate(['T0','T1','T2','T3']):
            for j,role in enumerate(roles):
                ax=axs[i,j];g=m[m.target.eq(t)&m.role.eq(role)]
                ax.axvspan(.88,.92,color='#d7e9df',alpha=.6);ax.axvline(.9,color='#36735b',lw=.7)
                for k,f in enumerate(['F0','F1','F2','F3','F4','F5']):
                    if f=='F3':continue # Alias shown explicitly in caption, no overplot concealment.
                    for variant,marker in [('RAW','o'),('CALIBRATED','^')]:
                        r=g[g.features.eq(f)&g.variant.eq(variant)].iloc[0];base=g[g.features.eq('F0')&g.variant.eq(variant)].iloc[0]
                        value=r[metric]/base[metric] if metric=='Q90_pinball' else r[metric]
                        ax.scatter(r.Q90_coverage,value,c=[colors[k]],marker=marker,s=35,label=f+' '+variant if i==j==0 else None)
                        ax.annotate(f,(r.Q90_coverage,value),xytext=(3,3),textcoords='offset points',fontsize=7,color=colors[k])
                ax.set_title(t+' | '+role.replace('EXPOSED_EVALUATION','Dec-Feb').replace('OOS_EXTENSION','Feb-Apr').replace('MAY_HISTORICAL','May diagnostic'))
                ax.set_xlabel('Empirical Q90 coverage');ax.set_ylabel(ylabel);ax.grid(alpha=.2)
        fig.suptitle('CC4-v2.7: calibration and sharpness\nCircles: raw | triangles: fixed calibration | F3 = F0 (state unavailable)',fontsize=13)
        for ext in ['png','svg','pdf']:fig.savefig(ROOT/(file+'.'+ext))
        plt.close(fig)
    tr=d[d.role.eq('TRAIN')].set_index('target');fig,axs=plt.subplots(1,3,figsize=(12,4),layout='constrained')
    for ax,col,title in zip(axs,['CV','top1_mass_share','zero_fraction'],['Coefficient of variation','Top 1% mass share','Zero fraction']):
        ax.bar(tr.index,tr[col],color=['#496a88','#7a9aa1','#479f87','#97bd87']);ax.set_title(title);ax.grid(axis='y',alpha=.2)
    fig.suptitle('TRAIN-only target distribution (different target semantics)',fontsize=13)
    for ext in ['png','svg','pdf']:fig.savefig(ROOT/('TARGET_DISTRIBUTIONS.'+ext))
    plt.close(fig)
if __name__=='__main__':main()
