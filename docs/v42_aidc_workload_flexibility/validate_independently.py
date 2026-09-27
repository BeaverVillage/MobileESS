"""Second implementation, without importing study or production modules."""
from pathlib import Path
import ast, hashlib, json
from types import SimpleNamespace
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    registration=json.loads((ROOT/'FLEXIBILITY_RULE_REGISTRATION.json').read_text(encoding='utf-8'))
    train=pd.read_csv(ROOT/'TRAIN_MEMBERSHIP.csv.gz',dtype={'id':str})
    assert train.id.is_unique
    assert pd.to_datetime(train.end_time,utc=True).lt(pd.Timestamp(registration['training_cutoff'])).all()
    stats=pd.read_csv(ROOT/'COHORT_LATENCY_STATISTICS.csv').set_index('cohort')
    for key,g in train.groupby('cohort'):
        s=stats.loc[key];assert int(s.N)==len(g)
        assert np.isclose(s.GPUh,g.GPUh.sum())
        for col,q in [('median_seconds',.5),('Q75_seconds',.75),('Q90_seconds',.9)]:
            assert np.isclose(s[col],np.quantile(g.queue_seconds,q))
        assert bool(s.latency_tolerant)==(len(g)>=100 and g.queue_seconds.median()>=900 and not g.protected.any())
    refs=pd.read_csv(ROOT/'REFERENCE_POPULATION.csv',dtype={'job_uid':str}).set_index(['day','job_uid'])
    options=pd.read_csv(ROOT/'FEASIBLE_OPTIONS.csv',dtype={'job_uid':str})
    assert not options.duplicated(['rule','day','job_uid','site']).any()
    actual={(r.rule,r.day,r.job_uid,r.site):tuple(map(int,r.starts.split())) for r in options.itertuples()}
    manifest=json.loads((ROOT/'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    for path,v in manifest['sources'].items():assert sha(path)==v['sha256'],path
    # Execute only frozen pure terminal formulas extracted by AST: no imports,
    # no ML/runtime/simulator/optimizer side effects are possible.
    terminal_path=next(p for p in manifest['sources'] if p.endswith('v41r1\\terminal.py') or p.endswith('v41r1/terminal.py'))
    tree=ast.parse(Path(terminal_path).read_text(encoding='utf-8'))
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['start_bounds','active']]
    ns={'ISSUE_BEGIN':24,'ISSUE_END':120,'CONTRACT':'V41R1_PER_JOB_TERMINAL_RESIDUAL_V1'}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),terminal_path,'exec'),ns)
    cap_path=next(p for p in manifest['sources'] if p.endswith('V41R2_780GPU_CAPACITY_AUTHORITY.json'))
    caps=json.loads(Path(cap_path).read_text(encoding='utf-8'))['site_capacity']
    rack_path=next(p for p in manifest['sources'] if p.endswith('V41R2_LOGICAL_RACK_AUTHORITY.json'))
    racks=json.loads(Path(rack_path).read_text(encoding='utf-8'))['logical_Rack_pools']
    for site,cap in caps.items():
        assert any(r['aidc_id']==site and r['compatibility_GPU_limit']==cap and r['aggregate_capacity_contribution_GPU']==0 for r in racks)
    source_root=Path(terminal_path).parents[1]
    c1path=source_root/'v28r2/c1_affine.py'
    tree=ast.parse(c1path.read_text(encoding='utf-8'))
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['_softplus','exact_c1_pcc_kw']]
    energy_ns=dict(np=np,C1Parameters=SimpleNamespace,FROZEN_NLR_EQUIVALENT_SCALE=3.4987194698200215,GFS_NORMALIZATION_FACTOR=5.987971384940258)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(c1path),'exec'),energy_ns)
    modelpath=next(p for p in manifest['sources'] if p.endswith('V24T_C1_QUASISTATIC_MODEL.json'))
    model=json.loads(Path(modelpath).read_text(encoding='utf-8'))
    params=SimpleNamespace(**model['coefficients'],t_ref_c=model['t_ref_c'],other_intercept=model['other_model_coefficients']['intercept'],other_it_mw=model['other_model_coefficients']['it_mw'])
    expected_daily=pd.read_csv(ROOT/'GPUH_SHARE_BY_DAY.csv').set_index(['rule','day'])
    energy_max_error=0.
    checked=0;rows_checked=0;expected_keys=set();base=None
    summaries=[]
    for rule in ['R0','R1','R2']:
        frame=pd.read_csv(ROOT/f'FLEXIBLE_MEMBERSHIP_{rule}.csv',dtype={'job_uid':str}).set_index(['day','job_uid'])
        assert frame.index.is_unique and set(frame.index)==set(refs.index)
        if base is None:base=frame
        assert frame.spatial_flexible.equals(base.spatial_flexible)
        assert not (frame.temporal_flexible & frame.protected).any()
        assert np.isclose(frame.day_GPUh.sum(),base.day_GPUh.sum())
        assert np.isclose(frame.full_service_GPUh.sum(),base.full_service_GPUh.sum())
        for day,group in frame.groupby(level=0):
            reference=refs.loc[day];horizon=int((reference.start_slot+reference.safe_duration_slots).max())+121
            load={s:np.zeros(horizon,dtype=int) for s in caps}
            for r in reference.itertuples():
                if r.AIDC_site in caps:load[r.AIDC_site][r.start_slot:r.start_slot+r.safe_duration_slots]+=r.requested_GPU
            for (_,uid),r in group.iterrows():
                rows_checked+=1;s=int(r.start_slot);d=int(r.safe_duration_slots);g=int(r.requested_GPU);site=r.AIDC_site
                assert np.isclose(r.full_service_GPUh,d*g/4)
                assert np.isclose(r.day_GPUh,(max(0,min(s+d,120)-max(s,24))*g/4 if site in caps else 0))
                co=stats.loc[r.cohort].to_dict() if r.cohort in stats.index else {}
                if rule=='R0':
                    raw=refs.loc[(day,uid)].to_dict();raw.update(job_uid=uid,terminal_contract=ns['CONTRACT'],terminal_reference_start_issue_slot=s,terminal_reference_selected=site!='UNASSIGNED',terminal_reference_remaining_slots=max(0,s+d-120))
                    if r.state_at_issue=='PENDING' and site in caps and 24<=s<120:
                        lower,upper=ns['start_bounds'](raw)
                    else:lower=upper=s
                else:
                    ok=r.state_at_issue=='PENDING' and not r.protected and site in caps and 24<=s<120 and r.RW_completion_slot-r.RSP_start_slot-d>=1 and (r.qos=='standby' or co.get('latency_tolerant',False))
                    lower=upper=s
                    if ok:
                        lower=max(24,int(r.RSP_start_slot));upper=min(int(r.RW_completion_slot)-d,119,max(120,s+d)-d)
                        if rule=='R2':upper=min(upper,int(r.RSP_start_slot)+int(co.get('budget_slots',0)))
                        if not lower<=s<=upper:lower=upper=s
                assert (int(r.lower_slot),int(r.upper_slot))==(lower,upper)
                feasible=[]
                if upper>lower:
                    for dest,capacity in caps.items():
                        if capacity<g:continue
                        residual=load[dest][:upper+d].copy()
                        if dest==site:residual[s:s+d]-=g
                        # Prefix-sum violations independently checks every interval.
                        prefix=np.r_[0,np.cumsum(residual+g>capacity)]
                        starts=tuple(t for t in range(lower,upper+1) if t!=s and prefix[t+d]==prefix[t])
                        key=(rule,day,uid,dest)
                        if starts:
                            expected_keys.add(key);assert actual[key]==starts
                        else:assert key not in actual
                        for t in starts:
                            assert t+d<=r.RW_completion_slot
                            assert max(0,t+d-120)<=max(0,s+d-120)
                            assert 24<=t<120
                            if rule=='R2':assert t-r.RSP_start_slot<=co['budget_slots']
                        feasible.extend(starts);checked+=len(starts)
                assert bool(r.temporal_flexible)==bool(feasible)
                assert int(r.option_count)==len(feasible)
                assert bool(r.newly_flexible)==(bool(feasible) and not base.loc[(day,uid),'temporal_flexible'])
            # Original frozen C1 scalar function, independently aggregate each
            # slot/site (study uses a separate vectorized expression).
            weatherpath=next(p for p in manifest['sources'] if day in p and p.endswith('gfs_d1_weather.parquet'))
            weather=pd.read_parquet(weatherpath)
            powerpaths=[p for p in manifest['sources'] if day in p and p.endswith('V41R2_B0_IT_PCC.npz')]
            if not powerpaths:powerpaths=[p for p in manifest['sources'] if 'v41r3_fast_power_scale_freeze' in p and p.endswith('V41R2_B0_IT_PCC.npz')]
            with np.load(powerpaths[0]) as power:
                fg={site:np.zeros(96) for site in caps}
                for r in group[group.temporal_flexible].itertuples():
                    fg[r.AIDC_site][max(0,r.start_slot-24):min(96,r.start_slot+r.safe_duration_slots-24)]+=r.requested_GPU
                e=0.
                for slot in range(96):
                    for i,site in enumerate(caps):
                        baseline=energy_ns['exact_c1_pcc_kw'](power['it'][slot,i],weather.t_wb_c.iloc[slot],weather.rh_pct.iloc[slot],params)
                        remaining=energy_ns['exact_c1_pcc_kw'](power['it'][slot,i]-fg[site][slot]*.5477239090195797,weather.t_wb_c.iloc[slot],weather.rh_pct.iloc[slot],params)
                        e+=float(baseline-remaining)/4
                record=expected_daily.loc[(rule,day)]
                assert np.isclose(record.total_AIDC_PCC_kWh,power['pcc'].sum()/4,atol=1e-7)
                assert abs(record.flexible_AIDC_PCC_kWh-e)<1e-6
                energy_max_error=max(energy_max_error,abs(record.flexible_AIDC_PCC_kWh-e))
        summaries.append(dict(rule=rule,rows=len(frame),flexible_jobs=int(frame.temporal_flexible.sum()),flexible_GPUh=float(frame.loc[frame.temporal_flexible,'day_GPUh'].sum())))
    assert expected_keys==set(actual)
    comparison=pd.read_csv(ROOT/'RULE_COMPARISON.csv')
    for r in comparison.itertuples():
        x=next(s for s in summaries if s['rule']==r.rule)
        assert x['flexible_jobs']==r.flexible_jobs and x['flexible_GPUh']==r.flexible_GPUh
        assert np.isclose(r.flexible_GPUh_pct,100*r.flexible_GPUh/r.total_GPUh)
        assert np.isclose(r.flexible_AIDC_energy_pct,100*r.flexible_AIDC_PCC_kWh/r.total_AIDC_PCC_kWh)
    result=dict(status='PASS',train_jobs=len(train),source_hashes_rechecked=len(manifest['sources']),membership_rows=rows_checked,all_options_independently_checked=checked,exact_membership_reproduced=True,original_R0_terminal_function_matches=True,original_C1_source_sha256=sha(c1path),PCC_energy_max_error_kWh=energy_max_error,rack_compatibility_verified=True,summaries=summaries)
    (ROOT/'INDEPENDENT_VALIDATION.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
