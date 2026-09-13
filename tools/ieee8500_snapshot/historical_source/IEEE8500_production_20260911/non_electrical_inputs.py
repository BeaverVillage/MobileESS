"""Read-only reuse of causal job, capacity, WAN, weather and road authorities."""
import sys,gzip,json,time
from pathlib import Path
from types import SimpleNamespace
from dataclasses import asdict
import numpy as np
import pandas as pd
import ac8500 as ac
sys.dont_write_bytecode=True
REPO=Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
sys.path.insert(0,str(REPO))
CAPROOT=Path('C:/codex_mobileess_workspace/MobileESS_v41r2_780gpu_capacity_rebase/dayahead/artifacts/v41r2_780gpu_capacity_rebase')
DAY='2025-05-21'
INPUT=REPO/'frozen_artifacts/v41r3_may/inputs'/DAY
CANDIDATES=REPO/'frozen_artifacts/v41r4_may/audit'/DAY/'domain/combined/FULL_CANDIDATES.jsonl.gz'
TRAFFIC=Path('C:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt/dayahead/cache/v37_may_locked_final/traffic/shared/traffic')/DAY
WEATHER=ac.ROOT/'MobileESS_v28r2_heavy_backend/cache/v28r2_campaign_sources/may_2025/days'/DAY/'gfs_d1_weather.parquet'
C1=REPO/'dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json'
FILES=[CAPROOT/'V41R2_780GPU_CAPACITY_AUTHORITY.json',CAPROOT/'V41R2_LOGICAL_RACK_AUTHORITY.json',INPUT/'common_q90_v3/COMMON_B0_REFERENCE_JOBS.json',INPUT/f'V41_ML_SNAPSHOT_{DAY}.json',CANDIDATES,TRAFFIC/'ROUTE_TABLE.json.gz',TRAFFIC/'TRAFFIC_FORECAST.npz',WEATHER,C1,REPO/'pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json']
def service_alias(s):return 'A'+s if s.startswith('IDC') else s

def context(load_candidates=True):
    from dayahead.v38.authority import CapacityAuthority,RackPool,load_wan_authority
    from dayahead.v28r2.c1_affine import load_c1,exact_c1_pcc_kw
    from dayahead.v39a.power import site_it_power_kw
    from dayahead.v41.temporal_restore import activate
    from dayahead.v41.reserve import bind
    from dayahead.v35.execution import _load_route_table,_load_forecast,MESS_INITIAL
    from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority,MessMobilityInputs
    from dayahead.v33m.grid_interface import ServicePCCMapping
    from dayahead.v40g_segments.canonical import import_frozen,planning_power
    c=ac.read(FILES[0]);r=ac.read(FILES[1]);caps=c['site_capacity']
    capacity=CapacityAuthority(caps,caps,tuple(RackPool(x['aidc_id'],x['rack_pool_id'],x['compatibility_GPU_limit']) for x in r['logical_Rack_pools']),ac.sha(FILES[0]))
    weather=pd.read_parquet(WEATHER);par=load_c1(C1);tables={}
    for site,cap in caps.items():
        it=np.array([float(site_it_power_kw(cap,g)) for g in range(cap+1)])
        tables[site]=np.array([exact_c1_pcc_kw(it,float(w.t_wb_c),float(w.rh_pct),par) for w in weather.itertuples()])
    ctx=SimpleNamespace(capacity=capacity,tables=tables,wan=load_wan_authority(REPO),day=DAY)
    bind(ctx,FILES[3],ac.sha(FILES[3]));ctx.reference=ac.read(FILES[2]);assert isinstance(ctx.reference,list) and len(ctx.reference)==708
    ctx.jobs=import_frozen(ctx.reference);ctx.power=planning_power(ctx.jobs,ctx)
    ctx.route_table=_load_route_table(TRAFFIC/'ROUTE_TABLE.json.gz');ctx.traffic=_load_forecast(TRAFFIC/'TRAFFIC_FORECAST.npz')
    assert ctx.traffic.causality_pass and ctx.traffic.future_actual_read_count==0 and ctx.traffic.max_input_timestamp<=ctx.traffic.issue_time
    assert str(ctx.traffic.forecast_day)==DAY and {service_alias(s) for s in ctx.route_table.service_ids}==set(ac.SERVICES)
    assert all(r.traffic_forecast_sha==ctx.traffic.canonical_sha256 for r in ctx.route_table.records.values())
    by=ac.binding();ctx.mapping=ServicePCCMapping({s:by['MESS',service_alias(s)]['PCC_bus'] for s in ctx.route_table.service_ids},ac.sha(ac.s.PCC/'PCC_OVERLAY_INVENTORY.json'))
    ctx.initial=MESS_INITIAL;ctx.electrical=MessElectricalAuthority.from_repository();ctx.mobility_inputs=MessMobilityInputs.create(ctx.route_table,96,ctx.initial,ctx.mapping,electrical_authority=ctx.electrical)
    if load_candidates:
        ctx.options={}
        with gzip.open(CANDIDATES,'rt',encoding='utf-8') as f:
            for line in f:
                x=json.loads(line);ctx.options[x['job_id']]=x['options']
        assert set(ctx.options)=={r['job_uid'] for r in ctx.reference}
    return ctx

def main():
    started=time.perf_counter();ctx=context();by=ac.binding();count=0;bindings=[]
    for row in ctx.reference:
        opts=ctx.options[row['job_uid']];assert [row['AIDC_site'],row['start_slot'],row['end_slot'],-1,-1,-1,''] in opts
        for opt in opts:
            assert opt[0] in ac.SITES or opt[0]=='UNASSIGNED'
            assert opt[6] in ac.SITES or opt[6]==''
        count+=len(opts)
    assert count==1341947,count
    for (role,site),r in sorted(by.items()):bindings.append(dict(role=role,location=site,**r))
    from dayahead.v41r1.feasible_seed import job_audit
    audit,power=job_audit(ctx.jobs,ctx);assert audit['status']=='PASS'
    with np.load(ac.s.OLD/'V41R4_B0_AIDC_POWER_UNCHANGED.npz') as z:
        diffs={k:float(np.max(np.abs(z[k]-power[k]))) for k in ['gpu','it','pcc','qcc']}
    assert max(diffs.values())<1e-10,diffs
    from dayahead.v38.contracts import RAW_WAN_TOPOLOGY,RAW_WAN_README,RAW_WAN_TRAFFIC
    refs=[ac.record(p) for p in FILES+[RAW_WAN_TOPOLOGY,RAW_WAN_README,RAW_WAN_TRAFFIC]]
    imported=[]
    for mod in list(sys.modules.values()):
        p=getattr(mod,'__file__',None)
        if p and str(p).lower().startswith(str(REPO).lower()) and Path(p).suffix=='.py':imported.append(ac.record(Path(p)))
    ac.save(ac.H/'preflight/NON_ELECTRICAL_INPUT_AND_BINDING_AUDIT.json',dict(status='PASS',day=DAY,jobs=708,full_candidate_count=count,full_domain_unchanged=True,binding=bindings,service_count=24,MESS_initial=ctx.initial,MESS_scale=asdict(ctx.electrical),GPU_capacities=ctx.capacity.site_capacity,traffic=dict(issue_time=str(ctx.traffic.issue_time),max_input_timestamp=str(ctx.traffic.max_input_timestamp),canonical_SHA=ctx.traffic.canonical_sha256,route_SHA=ctx.route_table.canonical_sha256,route_count=len(ctx.route_table.records),causality_pass=True,future_actual_read_count=0),B0_power_reconstruction_max_difference=diffs,job_audit=audit,input_files=refs,imported_source_files=imported,wall_seconds=time.perf_counter()-started))
    np.savez_compressed(ac.H/'preflight/NON_ELECTRICAL_POWER_TABLES.npz',**ctx.tables)
    print('NON_ELECTRICAL_BINDING_PASS',count,diffs,flush=True)
if __name__=='__main__':main()
