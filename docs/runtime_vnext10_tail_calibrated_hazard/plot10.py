from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'.local/plotdeps'))
import json,pandas as pd,numpy as np,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path(__file__).resolve().parent;arm=json.loads((root/'PREAPRIL_SELECTION_RESULT.json').read_text())['selected']['arm']
fold=pd.read_csv(root/'FOLD_LEVEL_METRICS.csv');f=fold[fold.arm.eq(arm)];ref=pd.read_csv(root/'PREAPRIL_REFERENCE_METRICS.csv').set_index('arm');s=pd.read_csv(root/'CALIBRATION_COMPARISON.csv').set_index('arm').loc[arm]
april=pd.read_csv(root/'APRIL_EXPOSED_RUNTIME_METRICS.csv').set_index('arm');remaining=pd.read_csv(root/'APRIL_CONDITIONAL_REMAINING.csv');remaining=remaining[remaining.scope.eq('ALL')].set_index('arm')
fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
for label,source,color in [('V9',fold[fold.arm=='T0_V9'],'#777777'),('V10 selected',f,'#b73339')]:
    axes[0].plot(source.fold,100*source.Q90_coverage,marker='o',label=label,color=color,lw=2)
axes[0].axhline(85,ls='--',color='#333333',label='Min-fold gate 85%');axes[0].set(ylim=(25,100),xticks=range(1,6),xlabel='Temporal fold',ylabel='Q90 coverage (%)',title='Pre-April: fold collapse remains');axes[0].legend(loc='lower left')
xpos=np.arange(3);v9=[100*ref.loc['T0_V9','Q90_coverage'],100*april.loc['V9','Q90_coverage'],100*remaining.loc['V9','Q90_coverage']];v10=[100*s.Q90_coverage,100*april.loc['V10','Q90_coverage'],100*remaining.loc['V10','Q90_coverage']]
axes[1].bar(xpos-.18,v9,.36,label='V9',color='#777777');axes[1].bar(xpos+.18,v10,.36,label='V10',color='#b73339')
axes[1].axhspan(88,92,color='#52936d',alpha=.22,label='Target 88–92%');axes[1].set(xticks=xpos,xticklabels=['Pre-April total','April total','April remaining'],ylim=(0,103),ylabel='Q90 coverage (%)',title='Exposed April regression: no retuning');axes[1].legend(loc='lower left')
for xx,v in zip(xpos-.18,v9):axes[1].text(xx,v+1,f'{v:.1f}',ha='center',fontsize=9)
for xx,v in zip(xpos+.18,v10):axes[1].text(xx,v+1,f'{v:.1f}',ha='center',fontsize=9)
fig.savefig(root/'VALIDATION_COVERAGE.png',dpi=180);plt.close(fig)

