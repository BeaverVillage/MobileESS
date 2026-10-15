"""Shared B0/B2 public D0 causal reference; never an optimized FULL point.

The original reference AIDC power/CC4 fill equations are retained. Native
slot24 denotes D0, so RUNNING remaining service starts at24 rather than0.
The approved expired-Q50 current gang is added at24, with no invented work.
"""
from copy import deepcopy
import math
from pathlib import Path
import numpy as np

from .m_engine import file_record,_write
from .policy import digest
from .table_v_flex_planning import require_flex_context,compile_public_reference

SCHEMA='TABLE_V_CAUSAL_REFERENCE_ACCEPTANCE_V1'
ROOT=Path(__file__).resolve().parents[1]
ANCHOR_FIELDS=('selected_jobs','AIDC_P_by_site','AIDC_Q_by_site','CC4_service','CC4_carryout',
    'anonymous_resource_envelope')


def _seal(value,key):
    value=deepcopy(value);value[key]=digest(value);return value


def reference_arrays(context,grid):
    """Original _reference_aidc equations with explicit D0 native24 mapping."""
    bundle,jobs,bounds,resources,raw,*_=context['data']
    begin=context['state']['begin_epoch_seconds'];sites=sorted(bundle['capacities'])
    reference=context['tablev_flex']['reference_records']
    known=np.zeros((96,len(sites)));selected={};obligations={}
    for uid,job in jobs.items():
        ref=reference[uid]
        start=24 if job.state=='RUNNING' else 24+int((ref['reference_start_seconds']-begin)/900)
        site=ref['reference_site'];stop=start+job.service_slots
        # The common Actual reference applies Source release/earliest limits
        # before starting. Those limits are explicit public metadata here.
        original=next(r for key in ('running','pending') for r in context['state'][key] if r['uid']==uid)
        if job.state=='PENDING':
            earliest=max(begin,original['metadata'].get('release_seconds') or -math.inf,
                original['metadata'].get('hard_earliest_start_seconds') or -math.inf)
            start=max(start,24+math.ceil((earliest-begin)/900));stop=start+job.service_slots
        selected[uid]=dict(start=start,initial_site=site,segments=((site,start,stop),),
            checkpoint=-1,destination=None,wan=(),migration_count=0)
        for t in range(max(24,start),min(120,stop)):
            known[t-24,sites.index(site)]+=job.gpu
        from v42_native.service import service_identity
        exact=max(0.,original['q50']-original['elapsed_compute_seconds']) if job.state=='RUNNING' else original['q50']
        mass=service_identity(exact,job.gpu,((site,start,stop),),H=120)
        obligations[uid]=dict(uid=uid,source_state=job.state,gpu=job.gpu,exact_nominal_seconds=exact,
            reservation_slots=job.service_slots,initial_site=site,native_start=start,
            service_identity=mass,source_row_sha=digest(original))
    for (site,tick),gpu in resources.fixed_gpu.items():
        if 24<=tick<120:known[tick-24,sites.index(site)]+=gpu
    nominal_tail=np.asarray(bundle['unknown_nominal_GPU'],float)
    if nominal_tail.ndim!=1 or len(nominal_tail)<96:
        raise ValueError('TABLE_V_FROZEN_ANONYMOUS_NOMINAL_AXIS_REQUIRED')
    nominal=nominal_tail[:96];anonymous=np.zeros_like(known);shortfall=0.
    for t in range(96):
        remaining=float(nominal[t])
        for si,site in enumerate(sites):
            grant=min(remaining,max(0.,bundle['capacities'][site]-known[t,si]))
            anonymous[t,si]=grant;remaining-=grant
        shortfall+=remaining/4.
    envelope=[dict(slot_start=t*900.,slot_end=(t+1)*900.,site=s,
        gpu_capacity=float(anonymous[t,si]),source_variable='GRID_BLIND_FROZEN_CC4_REFERENCE',
        carryout_end=86400.) for t in range(96) for si,s in enumerate(sites)]
    power,idle,swing=grid.power,grid.idle_kw,grid.swing_kw
    p={s:[float(power[s,t].slope*(idle*bundle['capacities'][s]+swing*(known[t,si]+anonymous[t,si]))+power[s,t].intercept_kw)
        for t in range(96)] for si,s in enumerate(sites)}
    q={s:(np.asarray(row)*np.tan(np.arccos(.95))).tolist() for s,row in p.items()}
    total=float(sum(bundle['C0_Q50']));served=float(anonymous.sum()/4.);carry=max(0.,total-served)
    if served>total+1e-6:raise ValueError('TABLE_V_REFERENCE_CC4_MASS_EXCEEDS_FROZEN_FORECAST')
    capacity_excess=np.max(known+anonymous-np.asarray([bundle['capacities'][s] for s in sites])[None,:],initial=0.)
    result=dict(FULL_feasible=False,selected_jobs=selected,AIDC_P_by_site=p,AIDC_Q_by_site=q,
        CC4_service={'GRID_BLIND_NOMINAL_GPUh':served},CC4_carryout={'GRID_BLIND_NOMINAL_GPUh':carry},
        anonymous_resource_envelope=envelope,reference_rule='CAUSAL_REFERENCE_START',
        nominal_anonymous_capacity_shortfall_GPUh=shortfall,source_nominal_forecast_GPUh=total,
        planning_power_recomputed=True,original_job_nominal_service_preserved=True,global_gap_certified=False,
        reference_schedule_only=True,reference_FULL_optimization_not_claimed=True,
        resource_sites=sites,known_site_GPU={s:known[:,i].tolist() for i,s in enumerate(sites)},
        nominal_site_GPU={s:anonymous[:,i].tolist() for i,s in enumerate(sites)},
        service_obligations=obligations,reference_capacity_max_excess_GPU=float(capacity_excess),
        source_identity=deepcopy(context['manifest']['identity']),source_sha=context['manifest']['source_sha'],
        reference_sha=context['tablev_flex']['reference_sha'],public_reference_records=deepcopy(reference),
        initial_record=deepcopy(context['manifest']['initial_record']),initial_state_sha=context['state']['common_initial_state_sha'],
        capacities=deepcopy(bundle['capacities']),D0_issue_seconds=begin,native_internal_offset=24,
        known_nominal_current_expired_hold_GPU=sum(resources.fixed_gpu.values()),
        fixed_Q50_expired_running_holds={uid:dict(site=r['planning_site'],gpu=r['GPU_gang'],
            elapsed_seconds=r['elapsed_seconds'],physical_release_rule='OBSERVED_COMPLETION_ONLY')
            for uid,r in raw.items() if r['state']=='RUNNING' and r['service_slots']==0},
        source_B0_B2_reference_identical=True,additional_timeshifting=0,additional_presite=0,migration_count=0,
        P2_calls=0,Native_calls=0,native_model_builds=0,Actual_truth_reads=0)
    result['aidc_anchor']=digest({k:result[k] for k in ANCHOR_FIELDS})
    result['reference_service_proof']=dict(PASS=bool(capacity_excess<=1e-8),
        public_Known_UIDs=len(reference),positive_service_UIDs=len(jobs),
        current_Q50_expired_holds=len(result['fixed_Q50_expired_running_holds']),
        full_nominal_service_and_carry_preserved=True,CC4_Q50_mass_preserved=abs(served+carry-total)<=1e-6,
        native24_is_D0_not_six_hour_prefix=True,private_truth_read=False,
        original_power_formula=file_record(ROOT/'v42_integration/production_case.py'))
    return result


def make_reference(context,*,output):
    require_flex_context(context)
    output=Path(output)
    if output.exists():raise FileExistsError('TABLE_V_REFERENCE_MUST_NOT_OVERWRITE')
    grid=context['materialize_physical']()['template_grid']
    result=reference_arrays(context,grid)
    if result['reference_service_proof']['PASS'] is not True:
        raise ValueError('TABLE_V_REFERENCE_NOMINAL_CAPACITY_CONFLICT')
    sources=[file_record(__file__),file_record(ROOT/'v42_integration/production_case.py'),
        file_record(ROOT/'v42_integration/qos.py'),file_record(ROOT/'v42_native/service.py'),
        *context['manifest']['source_freeze']['files']]
    sources=list({r['path']:r for r in sources}.values())
    result['reference_sources']=sources
    result=_seal(result,'reference_artifact_sha')
    acceptance=dict(schema=SCHEMA,status='REFERENCE_VALIDATED',source_identity=deepcopy(context['manifest']['identity']),
        source_sha=context['manifest']['source_sha'],result_sha=digest(result),AIDC_anchor=result['aidc_anchor'],
        reference_sha=result['reference_sha'],initial_state_sha=result['initial_state_sha'],
        reference_service_obligations_validated=True,FULL_optimization_claimed=False,P2_calls=0,
        exact_original_reference_formula_with_D0_axis=True,B0_B2_identical=True)
    acceptance=_seal(acceptance,'acceptance_sha')
    require_reference_acceptance(acceptance,identity=context['manifest']['identity'],result=result)
    output.mkdir(parents=True)
    _write(output/'REFERENCE_AIDC_RESULT.json',result)
    _write(output/'REFERENCE_ACCEPTANCE.json',acceptance)
    _write(output/'REFERENCE_ORIGINAL_SERVICE_CERTIFICATE.json',result['reference_service_proof'])
    return result,acceptance


def require_reference_acceptance(receipt,*,identity,result):
    if (receipt.get('schema')!=SCHEMA or receipt.get('status')!='REFERENCE_VALIDATED'
            or receipt.get('source_identity')!=identity or result.get('source_identity')!=identity
            or receipt.get('source_sha')!=result.get('source_sha') or receipt.get('result_sha')!=digest(result)
            or receipt.get('acceptance_sha')!=digest({k:v for k,v in receipt.items() if k!='acceptance_sha'})
            or result.get('reference_artifact_sha')!=digest({k:v for k,v in result.items() if k!='reference_artifact_sha'})
            or receipt.get('AIDC_anchor')!=digest({k:result[k] for k in ANCHOR_FIELDS})
            or receipt.get('AIDC_anchor')!=result.get('aidc_anchor')
            or receipt.get('reference_service_obligations_validated') is not True
            or receipt.get('FULL_optimization_claimed') is not False or result.get('FULL_feasible') is not False
            or receipt.get('P2_calls')!=0 or result.get('P2_calls')!=0
            or result.get('initial_state_sha')!=identity['initial_state_sha']
            or result.get('reference_service_proof',{}).get('PASS') is not True):
        raise ValueError('TABLE_V_EXACT_PUBLIC_REFERENCE_ACCEPTANCE_REQUIRED')
    if any(file_record(r['path'])!=r for r in result['reference_sources']):
        raise ValueError('TABLE_V_REFERENCE_SOURCE_BYTES_DRIFT')
    sites=result['resource_sites'];caps=result['capacities']
    matrices=[np.asarray([result[k][s] for s in sites],float).T
        for k in ('AIDC_P_by_site','AIDC_Q_by_site','known_site_GPU','nominal_site_GPU')]
    if (any(m.shape!=(96,len(sites)) or not np.isfinite(m).all() for m in matrices)
            or np.any(matrices[2]<0) or np.any(matrices[3]<0)
            or np.any(matrices[2]+matrices[3]>np.asarray([caps[s] for s in sites])[None,:]+1e-8)):
        raise ValueError('TABLE_V_REFERENCE_FINITE_96_SLOT_POWER_AND_CAPACITY_REQUIRED')
    if abs(sum(result['CC4_service'].values())+sum(result['CC4_carryout'].values())-result['source_nominal_forecast_GPUh'])>1e-6:
        raise ValueError('TABLE_V_REFERENCE_CC4_SERVICE_CARRY_CONSERVATION')
    from .release_initial_states import load_initial_state
    state=load_initial_state(result['initial_record'])
    if state['common_initial_state_sha']!=identity['initial_state_sha'] or state['capacities']!=caps:
        raise ValueError('TABLE_V_REFERENCE_PUBLIC_INITIAL_SOURCE_DRIFT')
    scheduler,_=compile_public_reference(state)
    if scheduler.reference_sha!=result['reference_sha'] or scheduler.assigned!=result['public_reference_records']:
        raise ValueError('TABLE_V_REFERENCE_ORIGINAL_CAUSAL_RECORDS_DRIFT')
    initial={r['uid']:r for key in ('running','pending') for r in state[key]}
    selected=result['selected_jobs'];holds=result['fixed_Q50_expired_running_holds']
    if set(selected)&set(holds) or set(selected)|set(holds)!=set(initial):
        raise ValueError('TABLE_V_REFERENCE_SERVICE_OR_HOLD_UID_DROP')
    known=np.zeros_like(matrices[2]);begin=state['begin_epoch_seconds']
    for uid,option in selected.items():
        row=initial[uid];running=row['site'] is not None
        exact=max(0.,row['q50']-row['elapsed_compute_seconds']) if running else row['q50']
        slots=math.ceil(exact/900);site=option['initial_site'];start=option['start']
        proof=result['service_obligations'].get(uid,{})
        if (site not in row['compatible_sites'] or option.get('checkpoint',-1)>=0
                or option['segments'] not in ([(site,start,start+slots)],((site,start,start+slots),),[[site,start,start+slots]])
                or proof.get('source_row_sha')!=digest(row) or proof.get('exact_nominal_seconds')!=exact
                or proof.get('gpu')!=row['gpu'] or proof.get('reservation_slots')!=slots
                or running and (site!=row['site'] or start!=24)):
            raise ValueError('TABLE_V_REFERENCE_ORIGINAL_FULL_SERVICE_HISTORY_DRIFT:'+uid)
        if not running:
            reference=scheduler.assigned[uid]
            earliest=max(begin,reference['reference_start_seconds'],row['metadata'].get('release_seconds') or -math.inf,
                row['metadata'].get('hard_earliest_start_seconds') or -math.inf)
            expected=24+math.ceil((earliest-begin)/900)
            if start!=expected or site!=reference['reference_site']:
                raise ValueError('TABLE_V_REFERENCE_PENDING_NOT_ORIGINAL_GRID_BLIND:'+uid)
        absolute=begin+(start-24)*900
        if ((row['metadata'].get('hard_latest_start_seconds') is not None and absolute>row['metadata']['hard_latest_start_seconds'])
                or row['metadata'].get('completion_deadline_seconds') is not None
                and absolute+exact>row['metadata']['completion_deadline_seconds']):
            raise ValueError('TABLE_V_REFERENCE_SOURCE_HARD_WINDOW_CONFLICT:'+uid)
        for t in range(max(24,start),min(120,start+slots)):known[t-24,sites.index(site)]+=row['gpu']
    for uid,hold in holds.items():
        row=initial[uid]
        if (row['site'] is None or row['q50']>row['elapsed_compute_seconds']
                or hold['site']!=row['site'] or hold['gpu']!=row['gpu']
                or hold['elapsed_seconds']!=row['elapsed_compute_seconds']):
            raise ValueError('TABLE_V_REFERENCE_EXPIRED_RUNNING_HOLD_DRIFT:'+uid)
        known[0,sites.index(row['site'])]+=row['gpu']
    if not np.array_equal(known,matrices[2]):raise ValueError('TABLE_V_REFERENCE_KNOWN_GPU_RECONSTRUCTION_DRIFT')
    return receipt
