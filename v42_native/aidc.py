"""PR90 complete-option domain bound to native Gurobi resource/grid callbacks."""
from dataclasses import asdict
from collections import defaultdict
from time import perf_counter
import gurobipy as gp
from gurobipy import GRB
from v42_job_capability import build_domain,resources_used,resource_limit
from .contracts import require,digest
from .solver import optimize,size
from .service import service_identity,NativeServiceBoundary
from v42_a_stage_domain_v2.execution import day_from_authority,require_action_authorized,tag_model_for_day


def solve(stage,deadline,jobs,boundaries,resources,grid_builder,incumbent=None,*,seconds_authority=None,progress=None,day=None):
    require(stage in ('A1','A2') and deadline.stage==stage,'AIDC_STAGE');started=perf_counter()
    # Deadline metadata is present in native requests; synthetic fixtures have
    # no production date and are explicitly independent of these identities.
    day=day_from_authority(day if day is not None else deadline)
    if day is not None:require_action_authorized(day,stage)
    elif any(j.duration_authority!='EXPLICIT_TEST_SERVICE' for j in jobs.values()):
        raise PermissionError('A_STAGE_PRODUCTION_DAY_REQUIRED')
    require(set(jobs)==set(boundaries),'JOB_SERVICE_AUTHORITY_AXIS')
    require(seconds_authority is not None and set(seconds_authority)==set(jobs),'EXACT_SERVICE_SECONDS_AUTHORITY_REQUIRED')
    domains={};screens=[]
    for uid,j in sorted(jobs.items()):
        deadline.check();require(isinstance(boundaries[uid],NativeServiceBoundary),'NATIVE_BOUNDARY_ADAPTER_REQUIRED')
        domains[uid],audit=build_domain(j,boundaries[uid],resources)
        require(domains[uid],'EMPTY_ADMITTED_DOMAIN:'+uid)
        screens.append(dict(uid=uid,**audit))
        for o in domains[uid]:service_identity(seconds_authority[uid],j.gpu,o.segments,resources.control_end)
    domain=digest({u:[asdict(o) for o in opts] for u,opts in domains.items()})
    if incumbent:require(incumbent['domain_sha256']==domain,'A1_A2_DOMAIN_DRIFT')
    generated=perf_counter();model=gp.Model('V42_NATIVE_'+stage);model.Params.OutputFlag=0
    if day is not None:tag_model_for_day(model,day)
    use=defaultdict(gp.LinExpr);z={}
    try:
        for u,opts in domains.items():
            for k,o in enumerate(opts):
                deadline.check();z[u,k]=1. if len(opts)==1 else model.addVar(vtype=GRB.BINARY,name=f'z[{u},{k}]')
                for key,amount in resources_used(jobs[u],o).items():use[key]+=amount*z[u,k]
            if len(opts)>1:model.addConstr(gp.quicksum(z[u,k] for k in range(len(opts)))==1,name='choose_one_job_option')
        keys=set(use)|{('GPU',s,t) for s,t in resources.fixed_gpu}|{('WAN',s,t) for s,t in resources.fixed_wan}|{('ACTIVE','',t) for t in resources.fixed_transfers}
        for key in sorted(keys):model.addConstr(use[key]<=resource_limit(key,resources),name='resource_'+key[0])
        gpu={(s,t):use['GPU',s,t]+resources.fixed_gpu.get((s,t),0) for s in resources.capacities for t in range(resources.control_end)}
        primary=grid_builder(model,gpu)
        require([n for n,_ in primary]==['rho','reserve_shortfall'],'GRID_PRIMARY_AND_P2_CONTRACT')
        migration=gp.quicksum(int(o.migrated)*z[u,k] for u,opts in domains.items() for k,o in enumerate(opts))
        shift=gp.quicksum(abs(o.start-jobs[u].reference_start)*z[u,k] for u,opts in domains.items() for k,o in enumerate(opts))
        placement=gp.quicksum(int(o.initial_site!=jobs[u].reference_site)*z[u,k] for u,opts in domains.items() for k,o in enumerate(opts))
        tie=gp.quicksum((k+1)*z[u,k] for u,opts in domains.items() for k in range(len(opts)))
        objectives=primary+[('migration_count',migration),('shift_slots',shift),('prestart_changes',placement),('tie',tie)]
        built=perf_counter();pre=size(model)
        best,receipt=optimize(model,objectives,deadline,incumbent,progress=progress)
        receipt.update(candidate_generation_seconds=generated-started,model_build_seconds=built-generated,model_size_before_solve=pre,
            raw_complete_options=sum(r['attempted_complete_options'] for r in screens),retained_options=sum(map(len,domains.values())),
            singleton_jobs=sum(len(v)==1 for v in domains.values()),prescreen=screens)
        if best is None:return None,receipt
        selected={u:next(o for k,o in enumerate(opts) if isinstance(z[u,k],float) or best['values'][z[u,k].VarName]>.5) for u,opts in domains.items()}
        occupancy=defaultdict(float)
        for u,o in selected.items():
            for key,n in resources_used(jobs[u],o).items():occupancy[key]+=n
        require(all(v<=resource_limit(k,resources)+1e-6 for k,v in occupancy.items()),'INDEPENDENT_GPU_WAN_VALIDATION')
        best.update(domain_sha256=domain,selected={u:asdict(o) for u,o in selected.items()},physical_audit={'PASS':True},
                    gpu=[[s,t,v] for (kind,s,t),v in occupancy.items() if kind=='GPU'])
        return best,receipt
    finally:model.dispose()
