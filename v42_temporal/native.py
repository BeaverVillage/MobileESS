"""PR96 complete options with hierarchical starts and schedulable CC4 binding.

No complete option is sampled, truncated, or granted extra WAN authority.
The externally supervised build budget includes complete-option generation.
"""
from collections import defaultdict
from dataclasses import replace,asdict
from time import perf_counter
import sys
import numpy as np
from v42_native.voltage import Stage,voltage_for
import gurobipy as gp
from .common import *
from .service import bind_forecast,objective_order
from v42_final.native import canonical_jobs
from v42_final.workload import ForecastBook
from v42_final.reserve import risk_exposure,bind_headroom
from v42_job_capability import Job,Resources,build_domain,resources_used,resource_limit,validate
from v42_native.service import boundary,service_identity
from v42_native.grid import add_grid,GridAuthority
from v42_native.solver import size,assert_milp
from v42_native.contracts import digest
from v42_native.supervision import atomic
from v42_may01.prepare import native_coefficients

def temporal_domain(job,window,resources):
    # Each frozen authorized start uses the same complete-option generator.
    # T0 plus no standby shortcut ensures no legacy eligibility can leak in.
    options=set();audits=[]
    for start in window.allowed_starts:
        shifted=replace(job,reference_start=start,standby_candidate_authorized=False)
        opts,audit=build_domain(shifted,window,resources)
        for o in opts:validate(job,o,window,resources)
        options.update(opts);audits.append(audit)
    return tuple(sorted(options)),dict(attempted_complete_options=sum(a['attempted_complete_options'] for a in audits),
        kept=len(options),pruning='INHERITED_HARD_ONLY_AND_EXACT_DUPLICATE',allowed_starts=list(window.allowed_starts))

def native_jobs(bundle,ledger):
    caps=bundle['capacities'];wan=bundle['WAN'];jobs={};windows={};seconds={};raw={}
    for r in bundle['known_population']:
        if r['planning_eligible']:
            r=dict(r);a=ledger[r['job_uid']]
            r.update(can_timeshift=bool(a['can_timeshift']),delay_budget_slots=int(a['TS_slots']));raw[r['job_uid']]=r
    updated=dict(bundle,known_population=list(raw.values()))
    for r in canonical_jobs(updated):
        if r['nominal_slots']==0:continue
        uid=r['job_id'];source=raw[uid];d=source['cohort'].split('|');start=r['reference_start']
        jobs[uid]=Job(uid,r['state'],0,0,start,r['site'],r['nominal_slots'],r['GPU_gang'],qos=d[0],protected=d[3]=='True',
            initial_sites=r['compatible_sites'],checkpoint_authorized=r['can_checkpoint_migrate'],elapsed_seconds=r['elapsed_seconds'],duration_authority=MODEL)
        starts=range(start,start+source['delay_budget_slots']+1) if source['can_timeshift'] else (start,)
        windows[uid]=boundary(jobs[uid],starts,sha(OUT/'TS_HIERARCHICAL_BACKOFF_AUTHORITY.json'),sha(OLD/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json'),H=120)
        seconds[uid]=r['exact_compute_seconds']
    resources=Resources(caps,{s:tuple(r['compatibility_GPU_limit'] for r in bundle['racks'] if r['aidc_id']==s) for s in caps},
        {(link,t):(n[t-24] if t>=24 else 0) for link,n in wan['link_capacity_bytes_15min'].items() for t in range(120)},
        {(p['source'],p['destination']):tuple(p['links']) for p in wan['paths']},120,wan['bytes_per_gpu'],{}, {}, {},
        restart_slots=1,max_active_transfers=wan['maximum_active_transfers'])
    # Q50-expired RUNNING jobs still occupy the entire gang at the observation
    # boundary; their future uncertainty remains in the frozen risk target.
    for r in raw.values():
        if r['state']=='RUNNING' and r['service_slots']==0:
            key=(r['planning_site'],0);resources.fixed_gpu[key]=resources.fixed_gpu.get(key,0)+r['GPU_gang']
    return jobs,windows,seconds,resources,raw

def load_power(bundle):
    cert=read(bundle['electrical_certificate']['path']);inputs=cert['input_identity']['identity']['inputs']
    recovery={r['original']:r['resolved']['path'] for r in read(ROOT/'docs/v42_may01_native_canary/EXACT_SOURCE_PATH_RECOVERY.json')['recovered']}
    def checked(r):
        p=Path(r['path']);p=p if p.exists() else Path(recovery.get(str(p),str(p)))
        require(sha(p)==r['sha256'],'NATIVE_SOURCE_DRIFT');return p
    rows=inputs['AIDC_power_C1'];paths={Path(r['path']).name:checked(r) for r in rows.values()}
    # Import only the exact source-preserved C1 implementation and constants.
    source_root=paths['c1_affine.py'].parents[2];sys.path.insert(0,str(source_root))
    from dayahead.v28r2.c1_affine import endpoint_secant,load_c1
    from dayahead.v39a.contracts import IDLE_W_PER_GPU,CENTER_SWING_W_PER_GPU
    require(sha(Path(sys.modules['dayahead.v28r2.c1_affine'].__file__))==sha(paths['c1_affine.py']),'C1_IMPORT_IDENTITY')
    require(sha(Path(sys.modules['dayahead.v39a.contracts'].__file__))==sha(paths['contracts.py']),'POWER_IMPORT_IDENTITY')
    params=load_c1(paths['V24T_C1_QUASISTATIC_MODEL.json']);weather=pd.read_parquet(checked(inputs['weather']))
    require(len(weather)==96,'CAUSAL_WEATHER_AXIS')
    idle=float(IDLE_W_PER_GPU)/1000;swing=float(CENTER_SWING_W_PER_GPU)/1000
    coefficients={(s,t):endpoint_secant(s,t,idle*cap,(idle+swing)*cap,float(weather.iloc[t].t_wb_c),float(weather.iloc[t].rh_pct),params)
                  for s,cap in bundle['capacities'].items() for t in range(96)}
    return cert,coefficients,idle,swing

def grid_binding(model,bundle,known,domains,z,raw,*,stage=Stage.A1,mess_p=None,mess_q=None):
    require(stage in (Stage.A1,Stage.A2),"AIDC_GRID_STAGE")
    require(stage!=Stage.A1 or (mess_p is None and mess_q is None),"BOOTSTRAP_MESS_MUST_BE_ZERO")
    require(stage!=Stage.A2 or (mess_p is not None and mess_q is not None),"A2_ACCEPTED_MESS_ANCHOR_REQUIRED")
    e=pd.read_csv(OUT/'CC4_SERVICE_TIMING_ENVELOPE.csv');k=pd.read_csv(OLD/'CC4_EXECUTION_LAG_KERNEL.csv').kappa.to_numpy()
    day=pd.Timestamp('2025-05-01T00:00:00+10:00').timestamp()
    book=ForecastBook(tuple(bundle['C0_Q50']),tuple(bundle['C0_Q90']),day)
    timing=bind_forecast(model,book,pd.Timestamp(bundle['issue_time']).timestamp(),k,e.Q10,e.Q90)
    caps=bundle['capacities'];anon={};arrival_target={};risk=defaultdict(gp.LinExpr)
    for t in range(96):
        for s in caps:
            anon[s,t+24]=model.addVar(lb=0,name=f'anonymous_GPU[{s},{t}]')
            arrival_target[s,t+24]=model.addVar(lb=0,name=f'arrival_target_GPU[{s},{t}]')
        model.addConstr(gp.quicksum(anon[s,t+24] for s in caps)==timing['nominal']['gpu'][t],name='CC4_site_nominal_partition')
        model.addConstr(gp.quicksum(arrival_target[s,t+24] for s in caps)==timing['reserve']['gpu'][t],name='CC4_site_reserve_partition')
    for uid,r in raw.items():
        options=domains.get(uid,())
        cases=[(r['planning_site'],r['risk_nominal_completion_issue_slot'],1.)] if not options else [
            (o.segments[-1][0],r['risk_nominal_completion_issue_slot']+o.segments[-1][2]-r['reference_end'],z[uid,i]) for i,o in enumerate(options)]
        for site,end,weight in cases:
            for key,v in risk_exposure(r['GPU_gang'],int(end),site,bundle['runtime_survival_kernel'],range(24,120)).items():
                risk[key]+=bundle['runtime_reserve_gamma']*v*weight
    reserve=bind_headroom(model,known,anon,arrival_target,risk,caps,range(24,120))
    cert,power,idle,swing=load_power(bundle);coeff=native_coefficients(cert)
    ga=GridAuthority(sha(Path(cert['input_identity']['identity']['inputs']['OpenDSS_master']['path'])),
        digest(bundle['capacities']),sha(OLD/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json'),digest(bundle['battery']),voltage_for(stage).lower_squared,voltage_for(stage).upper_squared,True,stage=stage,
        transformer_current_authority_sha256=getattr(coeff[0],'transformer_current_authority_sha256',None))
    controls=[]
    for t,c in enumerate(coeff):
        row=[]
        for name in c.control_names:
            site=name.split('[')[1][:-1]
            if name.startswith('aidc_load_kw'):
                it=idle*caps[site]+swing*(known.get((site,t+24),0)+anon[site,t+24]);a=power[site,t]
                row.append(a.slope*it+a.intercept_kw)
            elif name.startswith('mess_p_kw'):row.append((mess_p or {}).get((site,t),0.))
            else:row.append((mess_q or {}).get((site,t),0.))
        controls.append(row)
    rho=add_grid(model,coeff,controls,ga)
    return [('rho',rho),('reserve_shortfall',reserve['CC4_shortfall']+reserve['runtime_shortfall'])],timing,controls

def solve_a1(context,bundle,ledger):
    start=perf_counter();jobs,windows,seconds,resources,raw=native_jobs(bundle,ledger)
    domains={};screens=[];attempts=0
    for uid,j in sorted(jobs.items()):
        context.check();context.progress(dict(phase='COMPLETE_OPTION_GENERATION',jobs_completed=len(domains),jobs_total=len(jobs),current_job=uid,
            retained_options=sum(map(len,domains.values())),attempted_complete_options=attempts,build_seconds=perf_counter()-start))
        domains[uid],audit=temporal_domain(j,windows[uid],resources)
        require(domains[uid],'EMPTY_ADMITTED_DOMAIN:'+uid);screens.append(dict(uid=uid,**audit));attempts+=audit['attempted_complete_options']
        for o in domains[uid]:service_identity(seconds[uid],j.gpu,o.segments,120)
    generated=perf_counter();m=gp.Model('V42_TEMPORAL_A1');m.Params.OutputFlag=0;use=defaultdict(gp.LinExpr);z={}
    try:
        for uid,opts in domains.items():
            context.check()
            for i,o in enumerate(opts):
                z[uid,i]=1. if len(opts)==1 else m.addVar(vtype=gp.GRB.BINARY,name=f'z[{uid},{i}]')
                for key,v in resources_used(jobs[uid],o).items():use[key]+=v*z[uid,i]
            if len(opts)>1:m.addConstr(gp.quicksum(z[uid,i] for i in range(len(opts)))==1,name='choose_one_job_option')
        for key in sorted(set(use)|{('GPU',s,t) for s,t in resources.fixed_gpu}):
            m.addConstr(use[key]<=resource_limit(key,resources),name='resource_'+key[0])
        known={(s,t):use['GPU',s,t]+resources.fixed_gpu.get((s,t),0) for s in resources.capacities for t in range(120)}
        primary,timing,controls=grid_binding(m,bundle,known,domains,z,raw,stage=Stage.A1)
        later=[('migration_count',gp.quicksum(int(o.migrated)*z[u,i] for u,opts in domains.items() for i,o in enumerate(opts))),
            ('shift_slots',gp.quicksum((o.start-jobs[u].reference_start)*z[u,i] for u,opts in domains.items() for i,o in enumerate(opts))),
            ('prestart_changes',gp.quicksum(int(o.initial_site!=jobs[u].reference_site)*z[u,i] for u,opts in domains.items() for i,o in enumerate(opts))),
            ('tie',gp.quicksum((i+1)*z[u,i] for u,opts in domains.items() for i in range(len(opts))))]
        objectives=objective_order(primary,timing['deviation'],later);stats=assert_milp(m)
        atomic(context.folder/'model_build.json',dict(build_seconds=perf_counter()-start,candidate_generation_seconds=generated-start,
            model_size=stats,objective_order=[n for n,_ in objectives],retained_options=sum(map(len,domains.values())),attempted_complete_options=attempts))
        m.Params.MIPGap=.001;m.Params.Threads=1;m.Params.Seed=20260929
        passes=[];events=dict(presolve_removed_rows=0,presolve_removed_columns=0)
        def callback(model,where):
            if where==gp.GRB.Callback.PRESOLVE:
                events.update(presolve_removed_rows=int(model.cbGet(gp.GRB.Callback.PRE_ROWDEL)),presolve_removed_columns=int(model.cbGet(gp.GRB.Callback.PRE_COLDEL)))
            if context.remaining<=0:model.terminate()
        for name,obj in objectives:
            context.check();m.setObjective(obj);m.Params.TimeLimit=min(600.,context.remaining);m.optimize(callback)
            row=dict(objective_level=name,status=m.Status,solve_seconds=m.Runtime,incumbent=m.ObjVal if m.SolCount else None,
                best_bound=m.ObjBound,gap=m.MIPGap if m.SolCount else None,nodes=m.NodeCount,**events)
            passes.append(row);atomic(context.folder/'solve_receipt.json',dict(passes=passes,model_size=stats))
            if m.Status!=gp.GRB.OPTIMAL:return None
            m.addConstr(obj<=m.ObjVal+(1e-7 if name=='rho' else 1e-8),name='objective_lock_'+name)
        values={v.VarName:v.X for v in m.getVars()}
        selected={u:asdict(next(o for i,o in enumerate(opts) if isinstance(z[u,i],float) or z[u,i].X>.5)) for u,opts in domains.items()}
        return dict(values=values,selected=selected,stage='A1',lex_complete=True,accepted_native_plan=False,
                    independent_validation_required=True,passes=passes,controls=[[float(gp.LinExpr(x).getValue()) for x in row] for row in controls])
    finally:m.dispose()
