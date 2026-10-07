"""Unchanged native equations; exact local/Runtime interface projections."""
from collections import defaultdict,Counter
from dataclasses import replace,asdict
from time import perf_counter
import gurobipy as gp,numpy as np,psutil
from .common import *
from . import factor
from v42_compact.native import grid,completion_risk
from v42_native.voltage import Stage
from v42_compact.formulation import intervention
from v42_final.reserve import risk_exposure
from v42_boundary.generator import Generator
from v42_job_capability import Option,validate
from v42_sparse.config import settings
from v42_sparse.runtime import coefficient_vector
from v42_a_stage_domain_v2.execution import tag_model_for_day
from v42_a_stage_domain_v2.status import initial_domain_status

def bind(m,row,x,coefficient):
    if isinstance(x,gp.Var):m.chgCoeff(row,x,coefficient)
    elif isinstance(x,gp.LinExpr):
        for i in range(x.size()):m.chgCoeff(row,x.getVar(i),coefficient*x.getCoeff(i))
        if x.getConstant():m._root_binding_constants[row]+=coefficient*x.getConstant()
    elif x:m._root_binding_constants[row]+=coefficient*x

def local_units(m,jobs,bounds,r,graphs,classes,kind,context=None):
    tail=max(b.latest_completion for b in bounds.values());started=perf_counter()
    context=context or Context()
    units=[];class_for={u:key for key,us in classes.items() for u in us};generator=Generator(r,tail)
    cfg=settings(kind)
    def push(uid,v,*,members=None,optional=False,stay_count=False,unit_id=None):
        units.append(dict(id=unit_id or uid,uid=uid,members=members or [uid],v=v,optional=optional,stay_count=stay_count,class_key=class_for[uid],canonical_post_tie=kind not in ('F2A','F2B','F2C') and not cfg['tie']))
    aggregate=cfg['aggregate'];compress=cfg['aux']
    options=dict(eliminate_depart=compress or cfg['depart'],eliminate_arrive=compress or cfg['arrive'],share_links=compress or cfg['link'],eliminate_f0=compress or cfg['f0'],eliminate_state=compress or cfg['state'],byte_scale=2.**20 if cfg['scale_wan'] else 1.)
    if not aggregate:
        for i,(uid,j) in enumerate(sorted(jobs.items())):
            push(uid,factor.add_job(m,j,graphs[uid],r,**options))
            if i%20==0:context.progress(dict(phase='LOCAL_UNITS',formulation=kind,jobs_complete=i+1,jobs_required=len(jobs),seconds=perf_counter()-started))
    else:
        for index,(key,us) in enumerate(sorted(classes.items())):
            uid=us[0];j=jobs[uid];g=graphs[uid];N=len(us)
            if N==1 or g.fixed:
                for u in us:push(u,factor.add_job(m,jobs[u],graphs[u],r,**options))
                continue
            stays=tuple((k,s) for k,s in g.events['y'] if s+j.service_slots<=bounds[uid].latest_completion and generator.fits(k,s,j.service_slots,j.gpu))
            sj=replace(j,uid='CLASS_'+key[:12]);sv=factor.stay(m,sj,g,N,starts=stays,eliminate_f0=options['eliminate_f0'],eliminate_state=options['eliminate_state'])
            push(uid,sv,members=us,stay_count=True,unit_id=sj.uid+'_STAY')
            amount=gp.quicksum(sv['y'].values())
            if g.events['w']:
                # Each selected migration lane carries ONE complete job.
                # Counts alone cannot enforce individual D or nonlinear WAN min.
                for lane in range(N):
                    lj=replace(j,uid=sj.uid+'_LANE_'+str(lane));lv=factor.add_job(m,lj,g,r,optional=True,**options)
                    push(uid,lv,members=us,optional=True,unit_id=lj.uid)
                    amount+=lv['migration_selected']['selected'] if cfg['sparse_cardinality'] else gp.quicksum(lv['pair'].values())
            m.addConstr(amount==N,name='class_exact_cardinality')
            context.progress(dict(phase='CLASS_UNITS',formulation=kind,classes_complete=index+1,classes_required=len(classes),seconds=perf_counter()-started))
    return units

def build(context,data,kind):
    if kind in ('F2','F2-BASE'):
        from v42_exact.native import build as baseline
        m,v,o,c,b=baseline(context,data,'F2')
        units=[dict(id=u,uid=u,members=[u],v=vv,optional=False,stay_count=False) for u,vv in v.items()]
        return m,units,o,c,b
    bundle,jobs,bounds,r,raw,graphs,old,prep=data;started=perf_counter();cfg=settings(kind);compress=cfg['aux'];aggregate=cfg['aggregate']
    m=gp.Model('V42_ROOT_EXACT_'+kind);m.Params.OutputFlag=0;m._root_binding_constants=defaultdict(float)
    tag_model_for_day(m,bundle,require_day=False)
    tail=max(b.latest_completion for b in bounds.values());known={};risk={};gpurows={};riskrows={};fixedrisk=defaultdict(float)
    for uid,row in raw.items():
        if uid not in jobs:
            for key,x in risk_exposure(row['GPU_gang'],int(row['risk_nominal_completion_issue_slot']),row['planning_site'],bundle['runtime_survival_kernel'],range(24,120)).items():fixedrisk[key]+=bundle['runtime_reserve_gamma']*x
    for site,cap in r.capacities.items():
        for t in range(tail):
            known[site,t]=m.addVar(lb=0,ub=cap,name=f'known[{site},{t}]');gpurows[site,t]=m.addConstr(known[site,t]==r.fixed_gpu.get((site,t),0),name='known_GPU_binding')
        for t in range(24,120):
            risk[site,t]=m.addVar(lb=0,name=f'risk[{site},{t}]');riskrows[site,t]=m.addConstr(risk[site,t]==fixedrisk[site,t],name='Runtime_risk_binding')
    byte_scale=2.**20 if cfg['scale_wan'] else 1.
    wanrows={(l,t):m.addConstr(gp.LinExpr()<=(rate-r.fixed_wan.get((l,t),0))/byte_scale,name='physical_WAN') for (l,t),rate in r.wan_capacities.items()}
    active={t:m.addConstr(gp.LinExpr()<=r.max_active_transfers-r.fixed_transfers.get(t,0),name='physical_ACTIVE') for t in range(r.control_end)}
    primary,timing,controls=grid(m,bundle,known,risk,stage=Stage.A1);m.update();grid_seconds=perf_counter()-started;global_vars=m.NumVars
    classes=prep['classes'];units=local_units(m,jobs,bounds,r,graphs,classes,kind,context)
    metrics=[gp.LinExpr() for _ in range(3)];finish_groups=defaultdict(list);representative={};runtime_vectors={};tie=gp.LinExpr();rank=0
    process=psutil.Process();peak=process.memory_info().rss
    for index,unit in enumerate(units):
        uid=unit['uid'];j=jobs[uid];v=unit['v'];g=graphs[uid]
        for n in ('r0','r1'):
            for key,x in v[n].items():bind(m,gpurows[key],x,-j.gpu)
        for n in ('f0','f1'):
            if unit['optional'] and n=='f0':continue # sum f0=0 in every optional lane
            for (site,end),x in v[n].items():
                if cfg['runtime']:
                    key=unit['class_key'],site,end;vector=coefficient_vector(j,raw[uid],site,end,bundle)
                    if key in runtime_vectors and runtime_vectors[key]!=vector:raise ValueError('UNEQUAL_RUNTIME_COEFFICIENT_VECTOR')
                    runtime_vectors[key]=vector;finish_groups[key].append(x);representative[key]=uid
                else:
                    for key,a in completion_risk(j,raw[uid],site,end,bundle).items():bind(m,riskrows[key],x,-a)
        if 'pair' in v:
            for key,x in v['link_bytes'].items():
                if key in wanrows:bind(m,wanrows[key],x,1./byte_scale)
                else:m.addConstr(gp.LinExpr(x)/byte_scale<=-r.fixed_wan.get(key,0)/byte_scale)
            for t,x in v['wan_active'].items():bind(m,active[t],x,1.)
        else:
            for key,x in v['w'].items():
                tr=g.transfers[key]
                for l,t,n in tr.wan:bind(m,wanrows[l,t],x,n/byte_scale)
                for t in range(key[2],tr.end):bind(m,active[t],x,1.)
        for a,x in zip(metrics,intervention(j,v)):a+=x
        if cfg['tie'] and not g.fixed:
            expr,rank=factor.tie_expression(m,j,old[uid],g,v,rank);tie+=expr
        if index%20==0:
            m.update();peak=max(peak,process.memory_info().rss);context.progress(dict(phase='NATIVE_BINDINGS',formulation=kind,units_complete=index+1,units_required=len(units),seconds=perf_counter()-started))
    runtime_counts={}
    for key,xs in sorted(finish_groups.items()):
        klass,site,end=key;uid=representative[key];j=jobs[uid]
        from v42_a_stage_domain_v2.runtime_projection import finish_count
        x=finish_count(m,xs,len(classes[klass]),f'finish_count[{klass[:12]},{site},{end}]',
                       direct=prep.get('domain_authority')=='AIDC_A_STAGE_DOMAIN_AUTHORITY_V2')
        runtime_counts[key]=x
        for target,a in runtime_vectors[key]:bind(m,riskrows[target],x,-a)
    for row,a in m._root_binding_constants.items():row.RHS-=a
    m.update();peak=max(peak,process.memory_info().rss);family_indices=defaultdict(set);seen=set()
    for unit in units:
        for family,items in unit['v'].items():
            for x in items.values():
                variables=[x] if isinstance(x,gp.Var) else [x.getVar(i) for i in range(x.size())] if isinstance(x,gp.LinExpr) else []
                for variable in variables:
                    if variable.index not in seen:family_indices[family].add(variable.index);seen.add(variable.index)
    family_indices['Runtime_finish_count']={x.index for x in runtime_counts.values() if isinstance(x,gp.Var)}
    counts={n:len(ids) for n,ids in family_indices.items()};row_density=np.diff(m.getA().indptr)
    stats=dict(formulation=kind,features=cfg,jobs_complete=len(jobs),all_jobs_complete=True,scientific_classes=len(classes),aggregation=aggregate,aggregation_mode='exact staying-path integer histogram plus individually service-preserving optional migration lanes' if aggregate else 'none',columns=m.NumVars,binaries=m.NumBinVars,integers=m.NumIntVars-m.NumBinVars,continuous=m.NumVars-m.NumIntVars,constraints=m.NumConstrs,nonzeros=m.NumNZs,max_row_density=int(row_density.max()),family_counts=counts,logical_units=len(units),global_variables=global_vars,Runtime_finish_counts=len(runtime_counts),model_build_seconds=perf_counter()-started,grid_seconds=grid_seconds,peak_observed_RSS_bytes=peak,quadratic_constraints=m.NumQConstrs,quadratic_objective=m.NumQNZs,SOS=m.NumSOS,general_constraints=m.NumGenConstrs,original_tie_in_MILP=cfg['tie'],canonical_post_tie=not cfg['tie'],complete_domains=True)
    stats.update(complete_domains=prep.get('full_migration_domain_active',True),
        aidc_domain_authority=prep.get('domain_authority','PR134_HISTORICAL'),
        domain_status=initial_domain_status(hard_physical_domain_defined=prep.get('domain_authority')=='AIDC_A_STAGE_DOMAIN_AUTHORITY_V2',
            authority=prep.get('domain_authority','PR134_HISTORICAL')),
        scientific_full_domain_optimal=False,
        optimization_scope='restricted_domain_optimum' if not prep.get('full_migration_domain_active',True) else 'historical_active_domain')
    m._v42_domain_status=stats['domain_status']
    dump(kind+'_MODEL_STATS.json',stats);atomic(context.folder/(kind+'_MODEL_COMPLETE.json'),stats)
    levels=primary+[('CC4_reference_deviation',timing['deviation'])]+list(zip(('migration_count','shift_slots','prestart_changes'),metrics))
    if cfg['tie']:levels.append(('physical_event_tie',tie))
    return m,units,levels,controls,dict(known=known,risk=risk,timing=timing,Runtime_finish_counts=runtime_counts)

def reconstruct(units,data,pool=False):
    bundle,jobs,bounds,r,raw,graphs,old,prep=data;selected={};aggregate=defaultdict(list);members={}
    for unit in units:
        uid=unit['uid'];j=jobs[uid];g=graphs[uid];a=values(unit['v'],pool)
        if unit['stay_count']:
            key=unit['class_key'];members[key]=unit['members']
            for (k,s),x in a['y'].items():
                if abs(x-round(x))>1e-5:raise ValueError('FRACTIONAL_CLASS_COUNT')
                aggregate[key].extend([Option(s,k,((k,s,s+j.service_slots),))]*int(round(x)))
        elif unit['optional']:
            key=unit['class_key'];members[key]=unit['members']
            if sum(a['pair'].values())>.5:aggregate[key].append(factor.reconstruct(j,bounds[uid],r,g,a))
        else:selected[uid]=factor.reconstruct(j,bounds[uid],r,g,a)
    for key,plans in aggregate.items():
        us=sorted(members[key]);plans=sorted(plans)
        if len(plans)!=len(us):raise ValueError('CLASS_CARDINALITY_RECONSTRUCTION')
        for uid,o in zip(us,plans):validate(jobs[uid],o,bounds[uid],r);selected[uid]=o
    if set(selected)!=set(jobs):raise ValueError('MISSING_INDIVIDUAL_JOBS')
    result={u:asdict(o) for u,o in sorted(selected.items())}
    if any(unit.get('canonical_post_tie') for unit in units):
        from v42_sparse.canonical import assign
        result=assign(result,data)
    return result
