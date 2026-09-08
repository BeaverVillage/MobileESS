"""Descriptive daily rho maxima; cannot alter the frozen selection."""
from v41r4_may_alpha_screen import *
import shutil

def main():
    authority=OUT/'V41R4_MAY_WIDE_BACKGROUND_SCALE_AUTHORITY.json';before=rec(authority)
    source=read(OUT/'V41R4_MAY_ALPHA_SCREEN.json');rows=source['all_day_alpha_results']
    daily=[dict(day=day,**{f'alpha_{a:.2f}':next(r['rho_max'] for r in rows if r['day']==day and r['alpha_BG']==a) for a in ALPHAS}) for day in DAYS]
    summary=[]
    for a in ALPHAS:
        v=np.array([r[f'alpha_{a:.2f}'] for r in daily])
        summary.append(dict(alpha_BG=a,days=31,mean_daily_rho_max=float(v.mean()),median_daily_rho_max=float(np.median(v)),min_daily_rho_max=float(v.min()),max_daily_rho_max=float(v.max())))
    result=dict(status='DESCRIPTIVE_ONLY',definition='rho_max_daily = max over 96 slots and all line-phases of measured current/rating; mean = sum of 31 daily maxima / 31',
        summary=summary,daily_rho_max=daily,selection_authority=before,selection_unchanged=True,Actual_used=False,source=rec(__file__))
    save(OUT/'V41R4_DAILY_RHO_MAX.json',result)
    lines=['# Daily maximum line loading and its May mean','',
        'Each daily value is the maximum measured line-phase loading over all lines/phases and the 96 quarter-hour slots. The mean below is the arithmetic mean of the 31 daily maxima, not the mean of all line/slot loading samples.','',
        '| alpha | Mean daily rho max | Median | Minimum | Maximum |','|---:|---:|---:|---:|---:|']
    for r in summary:lines.append(f'| {r["alpha_BG"]:.2f} | {r["mean_daily_rho_max"]:.9f} | {r["median_daily_rho_max"]:.9f} | {r["min_daily_rho_max"]:.9f} | {r["max_daily_rho_max"]:.9f} |')
    lines+=['','| Date | alpha 1.35 | alpha 1.40 | alpha 1.45 | alpha 1.50 |','|:---|---:|---:|---:|---:|']
    for r in daily:lines.append('| '+r['day']+' | '+' | '.join(f'{r[f"alpha_{a:.2f}"]:.9f}' for a in ALPHAS)+' |')
    lines+=['','All four candidates remain May-wide FAIL. These descriptive statistics do not change eligibility or the frozen selection rule.','']
    content='\n'.join(lines)
    (OUT/'V41R4_DAILY_RHO_MAX.md').write_text(content,encoding='utf-8')
    # Supplement the primary report; the frozen selection authority stays byte exact.
    source['daily_rho_max_statistics']=result
    atomic(OUT/'V41R4_MAY_ALPHA_SCREEN.json',source)
    with (OUT/'V41R4_MAY_ALPHA_SCREEN.md').open('a',encoding='utf-8') as f:f.write('\n'+content.replace('# Daily maximum','## Daily maximum',1))
    assert rec(authority)==before
    delivery=Path('C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/artifacts/v41r4_may_alpha_screen')
    files=[]
    for name in ('V41R4_DAILY_RHO_MAX.json','V41R4_DAILY_RHO_MAX.md','V41R4_MAY_ALPHA_SCREEN.json','V41R4_MAY_ALPHA_SCREEN.md'):
        shutil.copyfile(OUT/name,delivery/name);assert rec(OUT/name)['sha256']==rec(delivery/name)['sha256'];files.append(rec(delivery/name))
    save(OUT/'DAILY_RHO_DELIVERY_MANIFEST.json',dict(status='PASS',supersedes_report_hashes_in='DELIVERY_MANIFEST.json',files=files,selection_authority_unchanged=before))
    print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':main()
