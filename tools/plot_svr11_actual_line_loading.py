"""Static scientific plot: same-date Actual peaks, separate own PASS cohorts."""
from pathlib import Path
import sys,json,statistics
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,sha,now

def run(root):
    root=Path(root);manifest=read(root/'CAMPAIGN_MANIFEST.json');report=read(root/'PERFORMANCE_COMPARISON.json')
    assert report['source_SHA']==manifest['execution_SHA'] and report['campaign_root']==str(root)
    for name,value in manifest['execution_sources'].items():assert sha(Path(manifest['code_root'])/name)==value
    assert read(manifest['hardware']['path'])['equipment_SHA']==report['equipment_SHA']
    pair=next(p for p in report['paired_same_date_comparisons'] if p['policies']==['B0','B2'])
    points=pair['metrics']['maximum_line_loading']['dates'];assert points
    x=np.array([int(p['day'][-2:]) for p in points]);a=np.array([p['a']*100 for p in points]);b=np.array([p['b']*100 for p in points])
    fig,(ax,delta)=plt.subplots(2,1,figsize=(9,5.7),sharex=True,gridspec_kw={'height_ratios':[2.3,1]},layout='constrained')
    own=[]
    for arm,color in [('B0','#64748b'),('B2','#087e8b')]:
        rows=[v for v in report['dates'] if v['arm']==arm and v['status']=='PASS'];values=[v['latest_performance']['maximum_line_loading'] for v in rows]
        own.append(dict(arm=arm,days=len(values),mean_percent=statistics.mean(values)*100,maximum_percent=max(values)*100))
        ax.plot([int(v['day'][-2:]) for v in rows],[t*100 for t in values],'.--',alpha=.35,color=color)
    ax.plot(x,a,'o-',color='#64748b',label=f'B0 on {len(points)} common PASS dates')
    ax.plot(x,b,'o-',color='#087e8b',label=f'B2 on {len(points)} common PASS dates')
    ax.axhline(100,color='#b91c1c',lw=1,ls=':',label='100% physical line rating')
    ax.set_ylim(40,104);ax.set_ylabel('Actual daily maximum line loading (%)');ax.grid(alpha=.18);ax.legend(fontsize=9)
    ax.set_title('SVR11 May 2025: actual line loading, common equipment')
    delta.bar(x,b-a,color='#087e8b');delta.axhline(0,color='#64748b',lw=.7)
    delta.set_ylabel('B2 - B0 (pp)');delta.set_xlabel('May 2025 day');delta.set_xlim(.3,31.7);delta.set_xticks(range(1,32,2));delta.grid(axis='y',alpha=.18)
    fig.suptitle(f'Common-date mean: B0 {a.mean():.2f}% / B2 {b.mean():.2f}% / change {(b-a).mean():.2f} pp',fontsize=11)
    path=root/'ACTUAL_LINE_LOADING_COMPARISON.png';fig.savefig(path,dpi=170);plt.close(fig)
    receipt=dict(PASS=True,source_SHA=manifest['execution_SHA'],equipment_SHA=report['equipment_SHA'],
        comparison_report=record(root/'PERFORMANCE_COMPARISON.json'),image=record(path),
        same_PASS_dates=pair['same_PASS_dates'],same_date_n=len(points),
        B0_same_date_mean_percent=float(a.mean()),B2_same_date_mean_percent=float(b.mean()),
        mean_B2_minus_B0_percentage_points=float((b-a).mean()),
        B2_lower_dates=int((b<a).sum()),policy_own_cohorts=own,
        population_note='Use common-date comparison; own-policy PASS populations differ. Missing B2 dates are not zero.',
        retrospective_design=True,independent_holdout_claim=False,UTC=now())
    atomic(root/'ACTUAL_LINE_LOADING_COMPARISON.json',receipt);print(json.dumps(receipt))

if __name__=='__main__':run(sys.argv[1])
