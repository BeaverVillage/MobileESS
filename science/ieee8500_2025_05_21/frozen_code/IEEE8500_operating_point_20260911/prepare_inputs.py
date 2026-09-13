from pathlib import Path
import json, csv, io, zipfile, shutil, ast
from datetime import datetime, timedelta
import numpy as np
from select_date import HERE,ROOT,V41,sha,rec,save

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def verify_raw(p,family,f):
    assert sha(p)==f[family+'_source_sha256']
    found={};headers=None;seen_issues=set()
    with zipfile.ZipFile(p) as z:
        assert len(z.namelist())==1;member=z.namelist()[0]
        with z.open(member) as b,io.TextIOWrapper(b,encoding='utf-8-sig',newline='') as h:
            for r in csv.reader(h):
                if not r:continue
                if r[0]=='I':headers=r;continue
                if r[0]!='D' or headers is None:continue
                row=dict(zip(headers,r))
                if row.get('REGIONID')!='VIC1':continue
                if family=='demand':
                    if any(row.get(k)!=v for k,v in f['demand_identity'].items()):continue
                    target=row['DATETIME'];value=row['TOTALDEMAND'];issue=row['LASTCHANGED']
                else:
                    if row.get('VERSION_DATETIME')!=f['pv_identity']['VERSION_DATETIME']:continue
                    target=row['INTERVAL_DATETIME'];value=row['POWERMEAN'];issue=row['VERSION_DATETIME']
                t=datetime.strptime(target,'%Y/%m/%d %H:%M:%S').replace(tzinfo=datetime.fromisoformat(f['cutoff_fixed_aest']).tzinfo)
                if t.isoformat() not in f['timestamps_96'][1::2]:continue
                v=float(value)
                if t.isoformat() in found:assert found[t.isoformat()]==v
                found[t.isoformat()]=v;seen_issues.add(issue)
    values=np.repeat([found[t] for t in f['timestamps_96'][1::2]],2)
    assert len(found)==48 and np.array_equal(values,np.array(f[family+'_mw_96']))
    assert len(seen_issues)==1
    issue=datetime.strptime(next(iter(seen_issues)),'%Y/%m/%d %H:%M:%S').replace(tzinfo=datetime.fromisoformat(f['cutoff_fixed_aest']).tzinfo)
    assert issue.isoformat()==f[family+'_issue'] and issue<=datetime.fromisoformat(f['cutoff_fixed_aest'])
    return dict(**rec(p),member=member,region='VIC1',raw_half_hour_rows=48,exact_96_slot_match=True,issue=issue.isoformat())

def main():
    day=read(HERE/'SELECTED_DATE_FREEZE.json')['selected']['day'];assert day=='2025-05-21'
    da=V41/f'frozen_artifacts/v41r4_may/loop_wall_v4/{day}/B0/dayahead'
    ep=da/'authority/DAYAHEAD_EXOGENOUS_INPUTS.json';e=read(ep)
    assert e['target_day']==day and e['role']=='DAYAHEAD_ONLY'
    fp=ROOT/f'MobileESS_v28r2_heavy_backend/cache/v28r2_campaign_sources/may_2025/days/{day}/aemo_forecast.json';f=read(fp)
    expected=[v for k,v in e['electrical_input_sources'].items() if k.endswith('aemo_forecast.json')]
    assert expected==[sha(fp)]
    cutoff=datetime.fromisoformat(f['cutoff_fixed_aest']);assert str(cutoff.date())=='2025-05-20' and cutoff.hour==18
    raw=[verify_raw(Path(f['cross_month_archive_authority'][k+'_path']),k,f) for k in ('demand','pv')]
    bg=e['background'];gross=np.array([sum(r.values()) for r in bg['gross_p_kw_96']]);pv=np.array([sum(r.values()) for r in bg['pv_generation_kw_96']])
    D=np.array(f['demand_mw_96']);PV=np.array(f['pv_mw_96']);assert D.shape==PV.shape==(96,) and (D>0).all() and (PV>=0).all()
    assert np.allclose(pv/pv.max(),PV/PV.max(),atol=1e-12,rtol=0)
    ratio=float(pv.max()/gross.max())
    save('PV_PENETRATION_RATIO_AUTHORITY.json',dict(ratio=ratio,numerator='max_t sum_i selected-day V41R4 B0 exogenous pv_generation_kw_96',denominator='max_t sum_i selected-day V41R4 B0 exogenous gross_p_kw_96 (already final alpha_BG=1.15; excludes AIDC)',PV_peak_kw=float(pv.max()),background_gross_peak_kw=float(gross.max()),source=rec(ep),IEEE8500_rule='PV_peak(alpha)=ratio * alpha * sum(native_load_kW); PV(t)=PV_peak(alpha)*PV_DA(t)/max(PV_DA); allocation_i=Pnative_i/sum(Pnative); Qpv=0',old_gross_demand_plus_PV_formula_not_transferred=True))
    shutil.copyfile(fp,HERE/'D1_AEMO_VIC1_FORECAST_AUTHORITY.json')
    with (HERE/'DEMAND_PV_TEMPORAL_PROFILES.csv').open('x',encoding='utf-8',newline='') as h:
        w=csv.writer(h);w.writerow(['slot','interval_start_fixed_AEST','interval_end_fixed_AEST','demand_DA_MW','rooftop_PV_DA_MW','demand_peak_normalized_multiplier','PV_peak_normalized_multiplier'])
        for i,end in enumerate(f['timestamps_96']):w.writerow([i,(datetime.fromisoformat(end)-timedelta(minutes=15)).isoformat(),end,D[i],PV[i],D[i]/max(D),PV[i]/max(PV)])
    p=da/'FROZEN_AIDC_POWER.npz';shutil.copyfile(p,HERE/'V41R4_B0_AIDC_POWER_UNCHANGED.npz')
    with np.load(p) as z:
        assert all(z[k].shape==(96,12) for k in ('gpu','it','pcc','qcc'))
        assert np.allclose(z['qcc'],z['pcc']*np.tan(np.arccos(.95)),atol=1e-9)
    mp=da/'FROZEN_MESS_COMMANDS.json';m=read(mp)
    assert len(m['MESS_trajectory'])==384 and all(r['p_kw']==r['q_kvar']==0 for r in m['MESS_trajectory'])
    shutil.copyfile(mp,HERE/'V41R4_B0_MESS_ZERO_COMMANDS_UNCHANGED.json')
    cap=Path(r'C:\codex_mobileess_workspace\MobileESS_v41r2_780gpu_capacity_rebase\dayahead\artifacts\v41r2_780gpu_capacity_rebase\V41R2_780GPU_CAPACITY_AUTHORITY.json')
    c=read(cap);assert c['new_total']==780
    physics=V41/'dayahead/mess_physics.py';tree=ast.parse(physics.read_text(encoding='utf-8'));scales={}
    for node in tree.body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and isinstance(node.value,ast.Constant):scales[node.targets[0].id]=node.value.value
    gen=read(da/'GENERATION_INPUT_IDENTITY.json');bound=next(r for r in gen['source']['files'] if r['relative_path']=='dayahead/mess_physics.py');assert sha(physics)==bound['sha256']
    save('UNCHANGED_RESOURCE_SCALE_AUTHORITY.json',dict(AIDC_count=12,GPU_total=780,GPU_capacity_by_site=c['site_capacity'],AIDC_power=rec(p),AIDC_GPU_authority=rec(cap),AIDC_PF=.95,AIDC_PCC_kVA=1500,MESS_count=4,MESS_service_locations=24,MESS_service_PCC_kVA=750,MESS_runtime_constants=scales,MESS_constants_source=rec(physics),MESS_command_source=rec(mp),all_MESS_P_Q_zero=True,note='Runtime MESS PCS is 400 kVA and active limit 300 kW; the legacy PCC design contract mentions 700 kVA. No PCS dispatch/rating is altered and the immutable service transformer remains 750 kVA.'))
    save('FORECAST_CAUSALITY_AND_INPUT_BINDING.json',dict(status='PASS',target_day=day,cutoff=f['cutoff_fixed_aest'],demand_issue=f['demand_issue'],PV_issue=f['pv_issue'],forecast_cache=rec(fp),B0_exogenous=rec(ep),raw_forecast_sources=raw,Actual_inputs_read=False,B1_B2_B3_results_read=False,forecast_to_15min='48 interval-ending half-hours repeated twice; slot t is [00:00+15t,00:15+15t) in fixed AEST UTC+10',date_freeze_sha256=sha(HERE/'SELECTED_DATE_FREEZE.json')))
    print(json.dumps(dict(day=day,ratio=ratio,demand_peak_MW=float(D.max()),PV_peak_MW=float(PV.max()),B0_AIDC_source_sha256=sha(p))))
if __name__=='__main__':main()
