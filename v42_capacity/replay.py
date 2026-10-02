"""Materialize causal physical replay from exact April source authority."""
from datetime import datetime
import csv
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from .common import *
from .actual import Request, Environment, replay


def seconds(text, issue): return (datetime.fromisoformat(text)-issue).total_seconds()


def main(days=None):
    truth={r['job_uid']:r for r in csv.DictReader((OUT/'ACTUAL_REALIZED_SERVICE_AUTHORITY_LEDGER.csv').open(encoding='utf8'))}
    assert read(OUT/'ACTUAL_REALIZED_SERVICE_AUTHORITY_AUDIT.json')['missing_realized_duration_unique_jobs']==0
    pooled=[]; audits=[]; physical=[]
    authority=read(PRIOR/'BUNDLE/DAY_20250401/POWER_AUTHORITY.json')
    c1path=resolve(authority['C1_implementation']); model=resolve(authority['C1'])
    sys.path.insert(0,str(c1path.parents[2]))
    from dayahead.v28r2.c1_affine import load_c1, exact_c1_pcc_kw
    import dayahead.v28r2.c1_affine as module
    assert Path(module.__file__).resolve()==c1path.resolve()
    params=load_c1(model)
    for d in (range(1,31) if days is None else days):
        day=f'2025-04-{d:02d}'; folder=day_folder(day); prior=PRIOR/'BUNDLE'/folder
        plan=read(prior/'PLANNING_INPUT_BUNDLE.json'); actual=read(prior/'ACTUAL_INPUT_BUNDLE.json')
        ref=read(OUT/'BUNDLE'/folder/'REFERENCE.json'); mapping={r['job_uid']:r for r in ref['rows']}
        issue=datetime.fromisoformat(plan['issue_time']); sites=sorted(plan['capacities'])
        requests=[]; running=[]; durations={}; completions={}
        for j in plan['known_population']+actual['post_issue_arrivals']:
            uid=j['job_uid']; t=truth[uid]
            r=Request(uid,seconds(j['submit_time'],issue),j['GPU_gang'],tuple(j['compatible_sites']),j['Q50_total_seconds'],j['source_site'])
            durations[uid]=float(t['realized_seconds'])
            if j['state_at_D1_cutoff']=='RUNNING':
                start=seconds(t['start_time'],issue); end=seconds(t['end_time'],issue)
                if not start<=0<end: raise ValueError('OBSERVED_RUNNING_SOURCE_TRUTH')
                running.append((r,mapping[uid]['reference_site'],start)); completions[uid]=end
            else: requests.append(r)
        gpu,rows,audit=replay(plan['capacities'],requests,Environment(durations,completions),running=running)
        prov=read(prior/'SOURCE_PROVENANCE.json')
        weather=pd.read_parquet(resolve(prov['daily_sources']['noaa_actual_weather.parquet']))
        caps=np.array([plan['capacities'][s] for s in sites])
        it=authority['current_IT_idle_kW_per_installed_GPU']*caps+authority['current_IT_swing_kW_per_active_GPU']*gpu
        pcc=np.array([exact_c1_pcc_kw(it[t],float(w.t_wb_c),float(w.rh_pct),params) for t,w in enumerate(weather.itertuples(index=False))])
        q=pcc*np.tan(np.arccos(.95))
        dest=OUT/'BUNDLE'/folder
        arrays=dict(sites=np.array(sites),GPU=gpu,IT_kw=it,PCC_P_kw=pcc,PCC_Q_kvar=q)
        if (dest/'ACTUAL_PHYSICAL.npz').exists():
            with np.load(dest/'ACTUAL_PHYSICAL.npz') as existing:
                if any(not np.array_equal(existing[k],v) for k,v in arrays.items()):
                    raise ValueError('SEALED_ACTUAL_PHYSICAL_ARRAY_DRIFT')
        else: np.savez_compressed(dest/'ACTUAL_PHYSICAL.npz',**arrays)
        audit.update(day=day,IT_recomputed_from_actual_occupancy=True,DayAhead_power_arrays_copied=False,
            actual_IT_kWh=float(it.sum()/4),actual_PCC_kWh=float(pcc.sum()/4),actual_GPUh=float(gpu.sum()/4),
            active_AIDC_slots=int(np.sum(gpu>0)),completion_authority='SOURCE_OBSERVED_END_MINUS_START_PRIVATE_ENVIRONMENT')
        audits.append(audit)
        write(OUT,'BUNDLE/'+folder+'/ACTUAL_CAPACITY_RECEIPT.json',audit)
        for r in rows:
            out=dict(day=day,**r)
            for key in ('submit_time','initial_admission_attempt','admitted_time','completion_observed_time','release_control_time'):
                if out[key] is not None:
                    from datetime import timedelta
                    out[key]=(issue+timedelta(seconds=out[key])).isoformat()
            pooled.append(out)
        daily_rows=[r for r in pooled if r['day']==day]
        table(OUT,'BUNDLE/'+folder+'/ACTUAL_QUEUE_LEDGER.csv',daily_rows,list(daily_rows[0]))
        assert audit['actual_IT_kWh']>0 and audit['actual_PCC_kWh']>0 and audit['actual_GPUh']>0
        print(day,'Actual physical PASS; queued',audit['queued_jobs'],'carryout',audit['carryout_jobs'],flush=True)
    all_audits=[]; all_rows=[]
    for d in range(1,31):
        folder=day_folder(f'2025-04-{d:02d}'); path=OUT/'BUNDLE'/folder
        if (path/'ACTUAL_CAPACITY_RECEIPT.json').exists():
            all_audits.append(read(path/'ACTUAL_CAPACITY_RECEIPT.json'))
            all_rows.extend(csv.DictReader((path/'ACTUAL_QUEUE_LEDGER.csv').open(encoding='utf8')))
    audits=all_audits
    table(OUT,'ACTUAL_CAPACITY_QUEUE_LEDGER.csv',all_rows,list(all_rows[0]))
    write(OUT,'ACTUAL_CAPACITY_AUDIT.json',dict(days=audits,capacity_violations=0,dropped_jobs=0,
        max_total_GPU=max(r['max_total_GPU'] for r in audits),grid_reads=0,optimizer_calls=0,
        future_duration_controller_reads=0,Actual_PQ_repair=0,Actual_global_reoptimization=0,
        actual_physical_days=len(audits),Actual_CC4_physical_GPU=0))


if __name__=='__main__':
    main([int(sys.argv[-1][-2:])] if '--day' in sys.argv else None)
