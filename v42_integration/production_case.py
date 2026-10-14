"""One isolated real May01 Case factory for common A/M and Job-event Actual.

Old DATA.pkl supplies immutable job/service/resource descriptors, not its old
start-window policy, model certificate or completion status. All new model
preparation is lazy and uses the approved Source18r physical coefficient bytes.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict,replace
from datetime import datetime
import argparse
import csv
import importlib
import json
from pathlib import Path
import pickle
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd

from .a_engine import ACase, PlanningGridContext, digest
from .coordinator import IntegrationCase, verify_sources
from .m_engine import _write, export_plan, file_record

ARCHIVE = Path('D:/v42_may_joint_repair_campaign_20261013')
STATIC = Path('D:/MobileESS_V42/runtime/v42_may_campaign/native90_build_reuse_20261009_01/dates/B1/2025-05-01/output/STATIC/DATA/DATA.pkl')
RECOVERY = Path('D:/MobileESS_V42/docs/v42_may01_native_canary/EXACT_SOURCE_PATH_RECOVERY.json')
TIMING = Path('D:/MobileESS_V42/docs/v42_ts_cc4_temporal_refinement/CC4_SERVICE_TIMING_ENVELOPE.csv')
KERNEL = STATIC.parent / 'CC4_EXECUTION_LAG_KERNEL.csv'
FIELDS = ('voltage_constant','voltage_matrix','current_constant','current_matrix',
          'flow_p_constant','flow_q_constant','flow_p_matrix','flow_q_matrix','branch_limits')
RESOURCE_DISTRIBUTION_FIELDS = ('nominal_site_GPU','reserve_site_GPU','known_site_GPU',
                              'resource_sites','CC4_reserve_service','CC4_reserve_carryout')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def assemble_native_bundle(original, projection, current_template):
    """Preserve full saved job schema; select explicit current physical receipts.

    The campaign projection deliberately omits legacy modeled placement and
    eligibility fields. It supplies current source observations/compatibility,
    never a replacement job roster or another Arm's reference placement.
    """
    required=('planning_eligible','current_site_if_running','service_slots','GPU_gang',
              'state','submit_time','elapsed_seconds','V10_Q50_total_seconds')
    def by_uid(packet):
        rows=packet['known_population']
        by={row['job_uid']:row for row in rows}
        if len(by)!=len(rows):
            raise ValueError('NATIVE_BUNDLE_DUPLICATE_KNOWN_UID')
        return by
    old, raw, current=map(by_uid,(original,projection,current_template))
    if set(old)!=set(raw) or set(old)!=set(current):
        raise ValueError('NATIVE_BUNDLE_KNOWN_UID_ROSTER_DRIFT')
    if any(any(field not in row for field in required) for row in old.values()):
        raise ValueError('SAVED_FULL_NATIVE_JOB_DESCRIPTOR_SCHEMA_REQUIRED')
    if digest(original['known_population'])!=digest(current_template['known_population']):
        raise ValueError('SAVED_FROZEN_CURRENT_JOB_SERVICE_DESCRIPTOR_DRIFT')
    if any(datetime.fromisoformat(packet['issue_time']).timestamp()!=
           datetime.fromisoformat(original['issue_time']).timestamp() for packet in (projection,current_template)):
        raise ValueError('NATIVE_BUNDLE_ISSUE_EPOCH_DRIFT')
    invariants=('day','network','alpha_BG','capacities','racks','WAN','battery',
        'initial_MESS_sites','C0_Q50','C0_Q90','C0_binding','runtime_provider',
        'runtime_reserve_gamma','runtime_survival_kernel','traffic_forecast_sha')
    for name in invariants:
        if any(digest(packet[name])!=digest(original[name]) for packet in (projection,current_template)):
            raise ValueError('NATIVE_BUNDLE_FROZEN_RESOURCE_PROVIDER_QUANTITY_DRIFT:'+name)
    for uid, row in old.items():
        observed=raw[uid]
        if (observed['state']!=row['state'] or observed['GPU_gang']!=row['GPU_gang']
            or datetime.fromisoformat(observed['submit_time']).timestamp()!=datetime.fromisoformat(row['submit_time']).timestamp()
            or observed['elapsed_seconds']!=(0. if row['state']=='PENDING' and row['elapsed_seconds'] is None
                                            else row['elapsed_seconds'])
            or observed['Q50_total_seconds']!=row['V10_Q50_total_seconds']):
            raise ValueError('NATIVE_BUNDLE_ISSUE_JOB_NOMINAL_SERVICE_DRIFT:'+uid)
        eligible=sorted(s for s,cap in original['capacities'].items() if row['GPU_gang']<=cap
            and any(r['aidc_id']==s and row['GPU_gang']<=r['compatibility_GPU_limit'] for r in original['racks']))
        if sorted(observed['compatible_sites'])!=eligible:
            raise ValueError('NATIVE_BUNDLE_JOB_GANG_RACK_COMPATIBILITY_DRIFT:'+uid)
    bundle=deepcopy(original)
    replacements=[]
    for name in ('electrical_certificate','grid_outputs','route_table'):
        if name=='route_table' and any(original[name][k]!=projection[name][k] for k in ('sha256','bytes')):
            raise ValueError('NATIVE_BUNDLE_EXACT_SAME_DAY_ROUTE_DRIFT')
        bundle[name]=deepcopy(projection[name])
        replacements.append(dict(field=name,old_value_sha=digest(original[name]),
            current_value_sha=digest(projection[name]),source='EXPLICIT_CURRENT_FROZEN_PHYSICAL_PACKET',
            old_placement_or_model_certificate_transfer=False))
    # Correct only a source-path encoding in the full current template. Its
    # authority bytes must match; the new QoS policy independently binds starts.
    for name in ('new_timeshift_authority',):
        if any(original[name][k]!=current_template[name][k] for k in ('sha256','bytes')):
            raise ValueError('NATIVE_BUNDLE_LEGACY_POLICY_RECEIPT_BYTES_DRIFT')
        bundle[name]=deepcopy(current_template[name])
    cc4={}
    for name in ('unknown_nominal_GPU','CC4_reserve_GPU'):
        saved=np.asarray(original[name],float)
        projected=np.asarray(projection[name],float)
        if saved.shape!=projected.shape or np.any(~np.isfinite(saved)) or np.any(saved<0):
            raise ValueError('NATIVE_BUNDLE_FROZEN_CC4_RESOURCE_AXIS_DRIFT:'+name)
        # Exact saved quantities are retained even when the independent
        # projection regenerated a few floating-point bits. No tolerance grants
        # authority to replace the frozen array.
        cc4[name]=dict(retained='EXACT_SAVED_DATA_PACKET',saved_value_sha=digest(original[name]),
            projected_value_sha=digest(projection[name]),projection_exact_equal=np.array_equal(saved,projected),
            projected_max_absolute_delta=float(np.max(np.abs(saved-projected),initial=0.)),
            saved_total_GPUslots=float(saved.sum()),projected_total_GPUslots=float(projected.sum()))
    audit=dict(schema='FULL_NATIVE_PACKET_EXPLICIT_CURRENT_PHYSICAL_MERGE_V1',
        known_uid_count=len(old),full_saved_job_descriptor_sha=digest(original['known_population']),
        current_full_template_descriptor_sha=digest(current_template['known_population']),
        raw_projection_descriptor_sha=digest(projection['known_population']),
        full_job_schema_retained=True,known_UID_changes=0,nominal_service_changes=0,
        gang_or_resource_quantity_changes=0,current_physical_replacements=replacements,
        CC4=cc4,raw_projection_reference_not_imported=True,
        future_Actual_data_reads=0,old_certificate_transfer=False)
    return bundle,audit


def _checked(receipt, recovery=None):
    path = Path(receipt['path'])
    if not path.is_file() and recovery is not None:
        path = Path(recovery.get(str(path), str(path)))
    record = file_record(path)
    if any(record[k] != receipt[k] for k in ('sha256', 'bytes')):
        raise ValueError('PRODUCTION_FROZEN_SOURCE_BYTES_DRIFT:'+str(path))
    return path, record


class ProductionPhysicalContext:
    """Explicit immutable numerical model and approved physical scope."""
    def __init__(self, source_freeze, manifest, bundle):
        self.freeze, self.manifest, self.bundle = source_freeze, manifest, bundle
        self.receipts = [manifest[k] for k in ('hardware','scenario','thermal')] + [bundle['electrical_certificate']]
        self.verify()
        self.certificate = read(bundle['electrical_certificate']['path'])
        self.thermal = read(manifest['thermal']['path'])
        if (self.certificate.get('day') != bundle['day'] or
            self.certificate.get('schema') != 'V42_SVR11_LDC_INTERVAL_ELECTRICAL_CERTIFICATE_V2'):
            raise ValueError('APPROVED_DAY_PHYSICAL_COEFFICIENT_CONTRACT_REQUIRED')
        reference = self.certificate['outputs']['planning_coefficients']
        path, actual = _checked(reference)
        self.receipts.append(actual)
        mapping = {r['branch_phase'].lower():float(r['NormalAmps']) for r in self.thermal['rows']+self.thermal['lines']}
        from v42_thermal.common import SCHEMA
        with np.load(path, allow_pickle=False) as packet:
            names, controls = tuple(map(str,packet['branch_names'])), tuple(map(str,packet['control_names']))
            expected = np.asarray([mapping[n.lower()] for n in names])
            if not np.array_equal(expected,packet['rating_a']):
                raise ValueError('EXACT_COMPILED_THERMAL_DENOMINATOR_DRIFT')
            if len(controls)!=60 or int(sum(n.startswith('transformer.') for n in names))!=153:
                raise ValueError('APPROVED_11SVR_PHYSICAL_AXIS_DRIFT')
            ratings = tuple(None if np.isnan(v) else float(v) for v in packet['transformer_ratings'])
            fields = {name:packet[name].copy() for name in FIELDS+('anchor_control',)}
        if any(fields[name].shape[0] != 96 for name in fields):
            raise ValueError('FULL96_PHYSICAL_COEFFICIENT_AXIS_REQUIRED')
        self.coefficients = tuple(SimpleNamespace(**{f:fields[f][t].copy() for f in FIELDS},slot=t,
            control_names=controls,branch_names=names,anchor=fields['anchor_control'][t].copy(),
            transformer_ratings=ratings,coefficient_sha256=actual['sha256'],
            current_denominators_A=expected.copy(),transformer_current_contract=SCHEMA,
            transformer_current_authority_sha256=self.thermal['transformer_current_authority_sha256']) for t in range(96))
        self.verify()

    def verify(self):
        verify_sources(self.freeze,self.receipts)

    def physical_scope(self):
        from v42_svr11.authority import integration_physical_scope
        return integration_physical_scope(self.freeze,hardware=self.manifest['hardware'],
            scenario=self.manifest['scenario'],thermal_receipt=self.manifest['thermal'])


def planning_power(bundle, certificate):
    """Original frozen C1 endpoint secants and constants, no model refit."""
    recovery = {r['original']:r['resolved']['path'] for r in read(RECOVERY)['recovered']}
    inputs = certificate['input_identity']['identity']['inputs']
    sources, receipts = {}, [file_record(RECOVERY)]
    for descriptor in inputs['AIDC_power_C1'].values():
        path, rec = _checked(descriptor,recovery)
        sources[path.name]=path
        receipts.append(rec)
    source_root=sources['c1_affine.py'].parents[2]
    sys.path.insert(0,str(source_root))
    affine=importlib.import_module('dayahead.v28r2.c1_affine')
    constants=importlib.import_module('dayahead.v39a.contracts')
    for module,name in ((affine,'c1_affine.py'),(constants,'contracts.py')):
        if file_record(module.__file__)['sha256']!=file_record(sources[name])['sha256']:
            raise ValueError('ORIGINAL_C1_IMPORT_SOURCE_IDENTITY_DRIFT')
    weather_path, weather_record=_checked(inputs['weather'],recovery)
    weather=pd.read_parquet(weather_path)
    if len(weather)!=96 or any(k not in weather for k in ('t_wb_c','rh_pct')):
        raise ValueError('SAME_DAY_FORECAST_WEATHER_AXIS_REQUIRED')
    params=affine.load_c1(sources['V24T_C1_QUASISTATIC_MODEL.json'])
    idle=float(constants.IDLE_W_PER_GPU)/1000.
    swing=float(constants.CENTER_SWING_W_PER_GPU)/1000.
    power={(s,t):affine.endpoint_secant(s,t,idle*cap,(idle+swing)*cap,
            float(weather.iloc[t].t_wb_c),float(weather.iloc[t].rh_pct),params)
            for s,cap in bundle['capacities'].items() for t in range(96)}
    return power,idle,swing,receipts+[weather_record]


def initial_mess(bundle):
    """Zero-power immutable stationary anchor; full route/mode/SOC fields."""
    from v42_bootstrap.m1 import native_inputs
    sites, origins, routes, battery, receipt=native_inputs(bundle)
    stays=[(s,t,s,t+1,None) for s in sites for t in range(96)]
    ids={(a[0],a[1]):k for k,a in enumerate(stays)}
    plan=dict(schema='V42_FULL_MESS_PHYSICAL_ANCHOR_V1',MESS_control='OFF',
        routes={u:[ids[s,t] for t in range(96)] for u,s in origins.items()},
        initial_sites=origins,connection_site={u:[s]*96 for u,s in origins.items()},
        P_by_site={s:[0.]*96 for s in sites},Q_by_site={s:[0.]*96 for s in sites},
        SOC={u:[battery.initial]*97 for u in origins},Mode={u:[0.]*96 for u in origins},
        time_axis=list(range(96)),dt_seconds=900.,moves=[],route_table=bundle['route_table'],
        battery=bundle['battery'],all_physical_inputs_fixed=True,
        P_sign='POSITIVE_GRID_INJECTION_Pdis_MINUS_Pch',Q_sign='ORIGINAL_Q_VARIABLE_SIGN')
    plan['plan_sha']=digest(plan)
    return plan


def compile_production_control_policy(*, arm, aidc, mess, bindings, envelope, output,
        mess_validation, coefficients, power, idle_kw, swing_kw, capacities,
        grid_authority, cc4_inputs, initial_state_sha, rack_limits=None, qos_provider=None,
        unknown_conditions=None, migration_authority=None,service_reallocation=False):
    """Compile the conditional table from the final, source-validated A/M pair."""
    from .cc4_policy_inputs import validate_optimized_reserve
    from .sensitivity_policy import (build_grid_packet, compile_sensitivity_policy,
                                     bounded_prototypes, export_policy_evidence)
    if arm not in ('B1','B3'):
        raise ValueError('GRID_SENSITIVITY_POLICY_B1_B3_ONLY')
    if not initial_state_sha or len(initial_state_sha)!=64:
        raise ValueError('CONTROL_POLICY_CURRENT_INITIAL_STATE_SHA_REQUIRED')
    if any(key not in aidc for key in RESOURCE_DISTRIBUTION_FIELDS):
        raise ValueError('CONTROL_POLICY_OPTIMIZED_SITE_TIME_DISTRIBUTION_NOT_EXPORTED')
    distribution={key:aidc[key] for key in RESOURCE_DISTRIBUTION_FIELDS}
    if aidc.get('resource_distribution_sha')!=digest(distribution):
        raise ValueError('CONTROL_POLICY_RESOURCE_DISTRIBUTION_SHA_DRIFT')
    sites=tuple(sorted(capacities))
    if aidc['resource_sites']!=list(sites):
        raise ValueError('CONTROL_POLICY_RESOURCE_SITE_AXIS_DRIFT')
    arrays={}
    for name in ('nominal_site_GPU','reserve_site_GPU','known_site_GPU'):
        if sorted(aidc[name])!=list(sites):
            raise ValueError('CONTROL_POLICY_RESOURCE_SITE_AXIS_DRIFT:'+name)
        array=np.asarray([aidc[name][site] for site in sites],float).T
        if array.shape!=(96,len(sites)) or np.any(~np.isfinite(array)) or np.any(array<0):
            raise ValueError('CONTROL_POLICY_RESOURCE_FULL96_FINITE_AXIS:'+name)
        arrays[name]=array
    nominal=arrays['nominal_site_GPU']; known=arrays['known_site_GPU']
    if np.any(nominal+known>np.asarray([capacities[s] for s in sites])+1e-7):
        raise ValueError('CONTROL_POLICY_OPTIMIZED_GPU_CAPACITY_DRIFT')
    if not envelope:
        raise ValueError('CONTROL_POLICY_OPTIMIZED_ENVELOPE_EMPTY')
    midnight=min(row['slot_start'] for row in envelope)
    rebuilt=np.full_like(nominal,np.nan)
    for row in envelope:
        slot=(row['slot_start']-midnight)/900
        if slot!=int(slot) or not 0<=slot<96 or row['site'] not in sites:
            raise ValueError('CONTROL_POLICY_ENVELOPE_ABSOLUTE_TIME_AXIS_DRIFT')
        rebuilt[int(slot),sites.index(row['site'])]=row['gpu_capacity']
    if not np.array_equal(rebuilt,nominal):
        raise ValueError('CONTROL_POLICY_ENVELOPE_NOMINAL_VARIABLE_DRIFT')
    for j,site in enumerate(sites):
        expected=np.asarray([power[site,t].slope*(idle_kw*capacities[site]+
            swing_kw*(known[t,j]+nominal[t,j]))+power[site,t].intercept_kw for t in range(96)])
        if not np.allclose(aidc['AIDC_P_by_site'][site],expected,rtol=0,atol=1e-7):
            raise ValueError('CONTROL_POLICY_C1_KNOWN_ANONYMOUS_FINAL_POWER_DRIFT:'+site)
    output=Path(output)
    a_path=output/('A2' if arm=='B3' else 'A1')/'A_RESULT.json'
    frozen=read(a_path)
    if (frozen.get('aidc_anchor')!=aidc['aidc_anchor'] or
            frozen.get('resource_distribution_sha')!=aidc['resource_distribution_sha'] or
            digest({key:frozen[key] for key in RESOURCE_DISTRIBUTION_FIELDS})!=aidc['resource_distribution_sha']):
        raise ValueError('CONTROL_POLICY_FINAL_A_RESULT_ARTIFACT_DRIFT')
    response_sources=sorted({c.coefficient_sha256 for c in coefficients})
    expanded=dict(bindings,cc4_sha=cc4_inputs['prediction_sha'],runtime_sha=cc4_inputs['runtime_sha'],
        response_sha=response_sources[0] if len(response_sources)==1 else digest(response_sources),
        initial_state_sha=initial_state_sha)
    authority=validate_optimized_reserve(cc4_inputs,nominal,arrays['reserve_site_GPU'],
        nominal_carryout_GPUh=sum(aidc['CC4_carryout'].values()),
        stress_carryout_GPUh=sum(aidc['CC4_reserve_carryout'].values()),
        source_receipt=file_record(a_path),allocation_aidc_anchor=aidc['aidc_anchor'],full_row_validation=aidc)
    authority.update({key:cc4_inputs[key] for key in ('model_id','prediction_sha','runtime_sha','kernel_sha')})
    authority['resource_distribution_sha']=aidc['resource_distribution_sha']
    authority['source_receipts']=cc4_inputs['source_receipts']
    authority['reserve_site_distribution_meaning']='CC4_ARRIVAL_TARGET_NOT_CAPACITY_BACKED_ACHIEVED_RESERVE'
    authority['P2_calls']=0
    authority['stress_overflow_actions_rejected_not_clipped']=True
    packet=build_grid_packet(coefficients,power,swing_kw,capacities,aidc,mess,grid_authority,
        expanded,begin_seconds=midnight,known_gpu=known,power_factor=.95,mess_validation=mess_validation,
        rack_compatibility=rack_limits)
    if getattr(qos_provider,'scenario','E0')!='E0':
        from .frozen_unknown import compile_unknown_policy,coverage_grammar
        from .q90_recourse import load_nominal_service
        import pandas as pd
        timing_rows=pd.read_csv(TIMING)
        lower,upper=np.asarray(timing_rows.Q10),np.asarray(timing_rows.Q90)
        recourse_authority=dict(authority,timing_envelope_sha=file_record(TIMING)['sha256'])
        nominal=load_nominal_service(aidc,cc4_inputs['q50_hourly_GPUh'],lower,upper,source_authority=recourse_authority)
        policy=compile_unknown_policy(packet,expanded,qos_provider=qos_provider,nominal_service=nominal,
            q90_hourly=cc4_inputs['q90_hourly_GPUh'],timing_lower=lower,timing_upper=upper,
            source_authority=recourse_authority,conditions=coverage_grammar(packet) if unknown_conditions is None else unknown_conditions,
            envelope=envelope,migration_authority=migration_authority,service_reallocation=service_reallocation)
        export_policy_evidence(policy,output)
        return policy
    prototypes=bounded_prototypes(packet,envelope)
    if rack_limits is not None:
        for prototype in prototypes:
            prototype['compatible_sites']=[site for site in prototype['compatible_sites']
                if any(prototype['gpu']<=limit for limit in rack_limits.get(site,()))]
        authority['source_rack_compatibility_limits']=rack_limits
    policy=compile_sensitivity_policy(packet,envelope,cc4_inputs['q50_hourly_GPUh'],
        cc4_inputs['q90_hourly_GPUh'],cc4_inputs['kernel'],prototypes,expanded,authority)
    if policy.document['scenario_audit'].get('status')=='INSUFFICIENT_SOURCE_SITE_DISTRIBUTION':
        raise ValueError('CONTROL_POLICY_INSUFFICIENT_SOURCE_SITE_DISTRIBUTION')
    export_policy_evidence(policy,output)
    _write(output/'A_STAGE_RESOURCE_ENVELOPE.json',dict(aidc_anchor=aidc['aidc_anchor'],
        resource_distribution_sha=aidc['resource_distribution_sha'],final_stage='A2' if arm=='B3' else 'A1',
        source_A_RESULT=file_record(a_path),envelope=envelope,**distribution,
        original_C1_power_bound=True,optimized_RESERVE_is_Actual_load=False))
    _write(output/'CC4_V21_SOURCE_BINDING_AUDIT.json',dict(
        schema='PRODUCTION_FROZEN_CC4_POLICY_BINDING_V1',model_id=cc4_inputs['model_id'],
        **{key:cc4_inputs[key] for key in ('prediction_sha','runtime_sha','kernel_sha','prediction_index','source_receipts')},
        literal_original_prediction_values=True,new_fit_calls=0,new_calibrator_calls=0,
        prediction_scaling_or_clipping=False,future_May_actual_used=False,
        A_stage_optimized_reserve_authority=authority,convolution=cc4_inputs['convolution']))
    return policy


def _reference_aidc(data, prepared, power, idle, swing):
    """Common causal known reservations plus fixed grid-blind CC4 baseline."""
    bundle,jobs,bounds,resources,raw,*_=data
    issue=prepared['issue_epoch_seconds']
    sites=sorted(bundle['capacities'])
    known=np.zeros((96,len(sites)))
    selected={}
    for uid,job in jobs.items():
        shared=prepared['known_receipts'][uid]
        ref=shared['reference']
        start=0 if job.state=='RUNNING' else int((ref['reference_start_seconds']-issue)/900)
        site=ref['reference_site']
        stop=start+job.service_slots
        selected[uid]=dict(start=start,initial_site=site,segments=((site,start,stop),),
            checkpoint=-1,destination=None,wan=(),migration_count=0)
        for t in range(max(24,start),min(120,stop)):
            known[t-24,sites.index(site)]+=job.gpu
    for (site,tick),gpu in resources.fixed_gpu.items():
        if tick==0:
            # Source overrun jobs have zero nominal compute but keep their gang
            # at the initial observed boundary; runtime reserve handles future.
            pass
    nominal_tail=np.asarray(bundle['unknown_nominal_GPU'],float)
    if nominal_tail.ndim!=1 or len(nominal_tail)<96:
        raise ValueError('FROZEN_ANONYMOUS_NOMINAL_AXIS_REQUIRED')
    nominal=nominal_tail[:96]
    anonymous=np.zeros_like(known)
    shortfall=0.
    for t in range(96):
        remaining=float(nominal[t])
        for si,site in enumerate(sites):
            grant=min(remaining,max(0.,bundle['capacities'][site]-known[t,si]))
            anonymous[t,si]=grant
            remaining-=grant
        shortfall+=remaining/4.
    envelope=[dict(slot_start=t*900.,slot_end=(t+1)*900.,site=s,
        gpu_capacity=float(anonymous[t,si]),source_variable='GRID_BLIND_FROZEN_CC4_REFERENCE',
        carryout_end=86400.) for t in range(96) for si,s in enumerate(sites)]
    p={s:[float(power[s,t].slope*(idle*bundle['capacities'][s]+swing*(known[t,si]+anonymous[t,si]))+power[s,t].intercept_kw)
           for t in range(96)] for si,s in enumerate(sites)}
    q={s:(np.asarray(row)*np.tan(np.arccos(.95))).tolist() for s,row in p.items()}
    # Preserve total forecast mass. Any unavailable anonymous nominal service
    # remains explicit carryout; no job population or realized work is deleted.
    total=float(sum(bundle['C0_Q50']))
    served=float(anonymous.sum()/4.)
    carry=max(0.,total-served)
    if served>total+1e-6:
        raise ValueError('REFERENCE_CC4_NOMINAL_MASS_EXCEEDS_FROZEN_FORECAST')
    result=dict(FULL_feasible=False,selected_jobs=selected,AIDC_P_by_site=p,AIDC_Q_by_site=q,
        CC4_service={'GRID_BLIND_NOMINAL_GPUh':served},CC4_carryout={'GRID_BLIND_NOMINAL_GPUh':carry},
        anonymous_resource_envelope=envelope,reference_rule='CAUSAL_REFERENCE_START',
        nominal_anonymous_capacity_shortfall_GPUh=shortfall,
        source_nominal_forecast_GPUh=total,planning_power_recomputed=True,
        original_job_nominal_service_preserved=True,global_gap_certified=False,
        reference_schedule_only=True,reference_FULL_optimization_not_claimed=True)
    result['aidc_anchor']=digest({k:result[k] for k in ('selected_jobs','AIDC_P_by_site','AIDC_Q_by_site',
        'CC4_service','CC4_carryout','anonymous_resource_envelope')})
    return result


def build_integration_case(*, source_freeze, strict_stats, output,
        archive=ARCHIVE, data_path=STATIC, day='2025-05-01',
        a_call_cap=5400., m_stage_cap=1800.,initial_site_authority=None,initial_state_freeze=None,fresh_ac_slots=96):
    """Prepare descriptors only; A and M model construction/solves stay lazy."""
    from .planning_inputs import prepare_planning
    from .qos import receipt_slot_domain,bind_native_job
    from v42_native.grid import GridAuthority
    from v42_native.voltage import Stage,voltage_for
    archive,output=Path(archive),Path(output)
    if initial_site_authority is not None:
        raise ValueError('SYNTHETIC_INITIALIZATION_SUPERSEDED_BY_DDAY_BOUNDARY_POLICY')
    if day!='2025-05-01':
        raise ValueError('NEW_DATE_PREPARED_JOB_DESCRIPTOR_NOT_AVAILABLE')
    source_paths=[Path(data_path),archive/'inputs/B2'/day/'NATIVE_INPUT.json',TIMING,KERNEL,archive/'CAMPAIGN_MANIFEST.json']
    current_template_path=archive/'raw'/day/'NATIVE_INPUT_TEMPLATE_B1.json'
    receipts=[file_record(p) for p in source_paths]
    receipts.append(file_record(current_template_path))
    verify_sources(source_freeze,receipts)
    with Path(data_path).open('rb') as stream:
        data=pickle.load(stream)
    projection=read(source_paths[1])
    original_bundle=data[0]
    bundle,schema_audit=assemble_native_bundle(original_bundle,projection,read(current_template_path))
    from .cc4_policy_inputs import load_frozen_cc4
    cc4_inputs=load_frozen_cc4(
        'D:/MobileESS_V42/docs/v42_may_b0_zero_margin_holdout/MAY_CC4_BINDING.json',
        'D:/MobileESS_V42/docs/v42_may_b0_zero_margin_holdout/CC4/DAY_'+day.replace('-','')+'.json',
        kernel_path=KERNEL,runtime_integrity_path=Path(__file__).parents[1]/'v42_final/runtime_bundle/INTEGRITY.json',
        planning_bundle_path=current_template_path)
    receipts.extend(cc4_inputs['source_receipts'])
    if data[0]['day']!=day or data[0]['capacities']!=bundle['capacities']:
        raise ValueError('STATIC_ORIGINAL_DESCRIPTOR_DAY_CAPACITY_DRIFT')
    # Statistical policy changes; nominal providers, UID roster and original
    # service/rack/WAN descriptors stay exactly those in the saved packet.
    if set(data[1])!={r['job_uid'] for r in bundle['known_population'] if r['planning_eligible'] and r['service_slots']>0}:
        raise ValueError('ORIGINAL_EXPLICIT_JOB_ROSTER_DRIFT')
    data=(bundle,)+tuple(data[1:])
    from .actual_validation import load_stats
    stats=load_stats(strict_stats) if isinstance(strict_stats,(str,Path)) else strict_stats
    manifest=read(source_paths[-1])
    # Whole campaign manifests contain Actual evidence and historical outcomes.
    # Only observed descriptors and approved numeric contracts identify Planning.
    # The full static/campaign file SHA remains a read-only integrity receipt.
    planning_identity=dict(day=day,science=source_freeze['science_version'],
        source=source_freeze['source_sha'],bundle=digest(bundle),
        known_job_descriptors={u:asdict(j) for u,j in data[1].items()},
        representation_bounds={u:asdict(b) for u,b in data[2].items()},
        hardware={k:manifest[k] for k in ('hardware','scenario','thermal')},
        statistical_QoS_sha=stats.sha,timing=receipts[2],kernel=receipts[3],
        frozen_CC4_prediction_sha=cc4_inputs['prediction_sha'],
        frozen_CC4_selected_row_sha=cc4_inputs['original_selected_row_sha'],
        frozen_runtime_provider_sha=cc4_inputs['runtime_sha'],
        policy='EMPIRICAL_QOS_Q90_REFERENCE_SLACK_V1')
    case_sha=digest(planning_identity)
    provider_sha=digest(bundle['runtime_provider'])
    prepared=prepare_planning(archive/'raw'/day,data,source_freeze=source_freeze,strict_stats=strict_stats,
                             case_sha=case_sha,provider_sha=provider_sha)
    physical=ProductionPhysicalContext(source_freeze,manifest,bundle)
    power,idle,swing,power_receipts=planning_power(bundle,physical.certificate)
    receipts+=prepared['receipts']+physical.receipts+power_receipts
    verify_sources(source_freeze,receipts)
    output.mkdir(parents=True,exist_ok=True)
    issue=prepared['issue_epoch_seconds']
    if datetime.fromisoformat(bundle['issue_time']).timestamp()!=issue or prepared['day_begin_epoch_seconds']-issue!=24*900:
        raise ValueError('EXPLICIT_ISSUE_TO_MIDNIGHT_TIME_AXIS_DRIFT')
    windows,known_receipts,changed_jobs,rebindings,domain_diff={}, {}, {}, [], []
    from v42_a_stage_domain_v2.domain import physical_starts
    for uid,job in data[1].items():
        shared=prepared['known_receipts'][uid]
        known_receipts[uid]=shared['receipt']
        receipt=prepared['qos_provider'].receipts[uid]
        starts=receipt_slot_domain(receipt,axis_origin_seconds=issue)
        bound=bind_native_job(job,receipt,axis_origin_seconds=issue)
        if job.state=='RUNNING':
            starts=(job.reference_start,)
            changed_jobs[uid]=replace(bound,reference_site=shared['reference']['reference_site'])
        else:
            ref=shared['reference']
            changed_jobs[uid]=replace(bound,reference_site=ref['reference_site'])
        if changed_jobs[uid].service_slots!=job.service_slots or changed_jobs[uid].gpu!=job.gpu:
            raise ValueError('BOUND_JOB_NOMINAL_SERVICE_OR_GANG_CHANGED:'+uid)
        rebindings.append(dict(uid=uid,state=job.state,old_cached_reference_site=job.reference_site,
            rebound_reference_site=changed_jobs[uid].reference_site,
            reference_site_changed=job.reference_site!=changed_jobs[uid].reference_site,
            old_cached_reference_start=job.reference_start,rebound_reference_start=changed_jobs[uid].reference_start,
            reference_start_changed=job.reference_start!=changed_jobs[uid].reference_start,
            service_slots_preserved=job.service_slots,GPU_gang_preserved=job.gpu,
            authority='FROZEN_SOURCE_RUNNING_SITE' if job.state=='RUNNING' else 'FROZEN_CAUSAL_REFERENCE_AT_ISSUE',
            old_placement_certificate_transfer=False))
        windows[uid]=tuple(starts)
        original_representation=physical_starts(job,data[2][uid],data[3].control_end)
        new_representation=physical_starts(changed_jobs[uid],replace(data[2][uid],allowed_starts=tuple(starts)),
                                           data[3].control_end)
        doc=receipt.to_dict()
        domain_diff.append(dict(uid=uid,state=job.state,service_slots=job.service_slots,GPU_gang=job.gpu,
            original_reference_start=job.reference_start,
            original_legacy_allowed_starts=list(data[2][uid].allowed_starts),
            original_physical_representation_starts=list(original_representation),
            original_physical_representation_count=len(original_representation),
            new_QoS_allowed_starts=list(starts),new_QoS_allowed_count=len(starts),
            new_physical_representation_starts=list(new_representation),
            new_physical_representation_count=len(new_representation),
            representation_completion_ceiling=data[2][uid].latest_completion,
            representation_ceiling_is_customer_deadline=False,
            legacy_allowed_starts_are_new_QoS_authority=False,
            actual_completion_used=False,Running_history_restarted=False,
            reference_label=prepared['reference_label'],QoS_policy_id=receipt.policy_id,
            QoS_receipt_sha=digest(doc),budget_seconds=receipt.budget_seconds,
            QoS_status=doc.get('status'),receipt=doc))
    # Bind the precise frozen Source18r issue reference. Preserve every 210 pin.
    source_rows={r['job_uid']:r for r in bundle['known_population']}
    for uid,job in changed_jobs.items():
        if job.state=='RUNNING':
            changed_jobs[uid]=replace(job,reference_site=prepared['known_receipts'][uid]['reference']['reference_site'])
    resources=deepcopy(data[3])
    original_running=[r for r in bundle['known_population'] if r['state']=='RUNNING']
    source_initial_GPU=sum(r['GPU_gang'] for r in original_running)
    rebound_initial_GPU=sum(j.gpu for j in changed_jobs.values() if j.state=='RUNNING')+sum(
        gpu for (site,t),gpu in resources.fixed_gpu.items() if t==0)
    source_assigned_GPU=sum(r['GPU_gang'] for r in original_running if r['current_site_if_running'] is not None)
    if source_assigned_GPU!=rebound_initial_GPU:
        raise ValueError('SOURCE_210_ASSIGNED_RUNNING_GPU_RESOURCE_DRIFT:'+str((source_assigned_GPU,rebound_initial_GPU)))
    data=(data[0],changed_jobs,data[2],resources)+tuple(data[4:])
    reference=_reference_aidc(data,prepared,power,idle,swing)
    initial=initial_mess(bundle)
    timing=pd.read_csv(TIMING)
    kernel=tuple(pd.read_csv(KERNEL).kappa)
    voltage=voltage_for(Stage.A1)
    authority=GridAuthority(physical.certificate['input_identity']['identity']['inputs']['OpenDSS_master']['sha256'],
        digest(bundle['capacities']),digest(bundle),digest(bundle['battery']),voltage.lower_squared,voltage.upper_squared,
        True,stage=Stage.A1,transformer_current_authority_sha256=physical.thermal['transformer_current_authority_sha256'],
        thermal_authority=physical.thermal,require_all_transformer_currents=True)
    def make_a_case(arm,stage,mess,folder):
        grid=PlanningGridContext(physical.coefficients,power,idle,swing,tuple(timing.Q10),tuple(timing.Q90),kernel,authority,mess)
        return ACase(data,grid,Path(folder),digest(dict(parent=case_sha,arm=arm,stage=stage,
            MESS_anchor=mess['plan_sha'],QoS=prepared['qos_provider'].stats.sha)),stage,arm,
            windows,known_receipts,call_cap=float(a_call_cap))
    def make_m_case(arm,stage,aidc,folder):
        from v42_may_campaign_native90.m_model import build_case
        from .m_candidates import generate
        sites=sorted(bundle['capacities'])
        planning=dict(sites=sites,PCC_P_kw=np.asarray([aidc['AIDC_P_by_site'][s] for s in sites]).T.tolist(),
            PCC_Q_kvar=np.asarray([aidc['AIDC_Q_by_site'][s] for s in sites]).T.tolist(),
            complete_AIDC_anchor=aidc['aidc_anchor'],CC4_service=aidc['CC4_service'],
            CC4_carryout=aidc['CC4_carryout'],anonymous_resource_envelope=aidc['anonymous_resource_envelope'])
        payload=dict(bundle=bundle,planning=planning,identity=dict(PASS=True,day=day,arm=arm,
            stage=stage,AIDC_anchor=aidc['aidc_anchor'],QoS_SHA=prepared['qos_provider'].stats.sha,
            all_AIDC_PQ_and_anonymous_frozen=True,parent_case_sha=case_sha))
        case=build_case(payload,dict(day=day,arm=arm,stage=stage,output=str(folder)),integration_context=physical)
        case.identity.update(arm=arm,stage=stage,aidc_anchor=aidc['aidc_anchor'],
                             qos_sha=prepared['qos_provider'].stats.sha)
        from v42_native.contracts import digest as native_digest
        case.case_sha=native_digest(case.identity)
        case.candidate_generator=generate
        case.plan_exporter=export_plan
        case.mess_stage_budget_seconds=float(m_stage_cap)
        _write(Path(folder)/'INTEGRATION_COMPLETE_AIDC_BINDING.json',payload['identity'])
        _write(Path(folder)/'SCIENTIFIC_CASE_IDENTITY.json',dict(case_sha=case.case_sha,**case.identity))
        return case
    # Signed line-current sensitivity under a +1 kW AIDC load, aggregated as
    # an effect vector by site/time. Original signs are retained, never abs().
    effects={}
    for t,c in enumerate(physical.coefficients):
        for site in bundle['capacities']:
            j=c.control_names.index('aidc_load_kw['+site+']')
            # Policy ranks a whole GPU gang's nominal incremental IT/PCC load.
            # The slope/swing are the same frozen affine Planning power model.
            effects[site,t*900.]=tuple(map(float,c.current_matrix[j]*power[site,t].slope*swing))
    arguments=dict(prepared['arguments'])
    arguments.pop('qos_window_provider',None)
    actual_gate=deepcopy(prepared['actual_gate'])
    # Boundary audit summaries are Actual gate metadata only, loaded after the
    # Planning identity/variables are fixed. No per-UID boundary realization,
    # queue, site or completion from this file enters the Planning packet.
    boundary_path=Path(__file__).parents[1]/'docs/v42_common_am_qos_integration/DDAY_INITIAL_STATE_AUDIT.json'
    if boundary_path.is_file():
        boundary=read(boundary_path)
        if boundary['day']!=day or boundary['day_begin_epoch_seconds']!=issue+24*900:
            raise ValueError('ACTUAL_BOUNDARY_AUDIT_DAY_AXIS_DRIFT')
        keys=('initial_state_sha','common_initial_state_sha','Arm_initial_state_SHA',
            'initial_queue_verified','active_running_site_authority','active_running_jobs',
            'active_running_GPU','active_running_preserved_site_jobs','active_running_preserved_site_GPU',
            'active_running_unverified_site_jobs','active_running_unverified_site_GPU',
            'initial_pending_jobs','initial_pending_GPU','completed_by_boundary_jobs')
        actual_gate.update({k:deepcopy(boundary[k]) for k in keys if k in boundary})
        actual_gate.update(boundary_audit=file_record(boundary_path),
            source_boundary_status=boundary['status'],Actual_gate_metadata_read_after_planning_identity=True,
            boundary_data_used_in_Planning_identity_or_variables=False)
    _write(output/'PRODUCTION_CASE_PREPARATION.json',dict(PASS=True,case_sha=case_sha,
        science_sha=source_freeze['source_sha'],day=day,known_explicit_jobs=len(changed_jobs),
        known_observed_jobs=len(prepared['known_receipts']),known_zero_service_retained_in_actual=True,
        native_optimize_calls=0,source_receipts=receipts,reference_AIDC=reference,
        initial_MESS=initial,QoS_budget_ledger=prepared['qos_provider'].to_dict(),
        time_axis=dict(issue_epoch_seconds=issue,planning_native_slots=[24,120],M_slots=[0,96],dt_seconds=900),
        old_model_certificate_reused_as_new_policy_certificate=False,
        original_nominal_job_and_CC4_values_preserved=True,current_physical_source_explicitly_bound=True,
        old_running_placement_certificate_transfer=False,
        scope='ISSUE_ONLY_PLANNING_PREPARATION',
        initial_site_policy='PRE_DDAY_SYNTHETIC_INITIALIZATION_CANCELLED; DDAY_MODEL_BOUND_SEPARATELY',
        planning_reference_label=prepared['reference_label'],planning_reference_sha=prepared['reference_sha'],
        frozen_known_reference_reused=prepared['frozen_known_reference_reused'],
        same_reference_rule_for_known_unknown_real_actual=prepared['same_reference_rule_for_known_unknown_real_actual'],
        planning_external_running=prepared['planning_external_running'],
        planning_actual_truth_reads=0,reference_queue_regeneration_calls=0,
        planning_only=True,pre_execution_boundary_audit=actual_gate,
        requires_ACTUAL_INITIAL_STATE_BINDING_for_execution=True,
        source_policy_disclaimer='REAL_QOS_UNSUPPORTED_METADATA_RETAINS_ZERO_ADDITIONAL_BUDGET'))
    _write(output/'FULL_NATIVE_PACKET_SCHEMA_MERGE.json',schema_audit)
    _write(output/'AUTHORIZED_START_DOMAIN_DIFF.json',dict(
        source_original_DATA=file_record(data_path),source_frozen_reference=bundle['reference'],
        scope='EXPLICIT_1499_KNOWN_NOMINAL_PLANNING_JOBS;44_EXTERNAL_ZERO_DDAY_NOMINAL_RETAINED_IN_QOS_LEDGER',
        original_representation_is_not_QoS_permission=True,
        legacy_research_windows_superseded=True,real_hard_contracts_not_superseded=True,
        actual_end_or_D00_future_state_reads=0,reference_regeneration_calls=0,
        source_recovered_or_synthetic_sites_used=False,UID_roster_changes=0,service_or_GPU_changes=0,
        original_representation_total_starts=sum(r['original_physical_representation_count'] for r in domain_diff),
        new_authorized_total_starts=sum(r['new_QoS_allowed_count'] for r in domain_diff),
        new_physical_total_starts=sum(r['new_physical_representation_count'] for r in domain_diff),
        empty_new_physical_domains=sum(not r['new_physical_representation_count'] for r in domain_diff),
        per_UID=domain_diff))
    csv_fields=tuple(k for k in domain_diff[0] if k!='receipt')
    with (output/'AUTHORIZED_START_DOMAIN_DIFF.csv').open('w',newline='',encoding='utf8') as stream:
        writer=csv.DictWriter(stream,fieldnames=csv_fields);writer.writeheader()
        for row in domain_diff:
            writer.writerow({k:(json.dumps(row[k],separators=(',',':')) if isinstance(row[k],list) else row[k])
                             for k in csv_fields})
    _write(output/'KNOWN_DESCRIPTOR_REFERENCE_REBINDING.json',dict(rows=rebindings,
        descriptor_roster=len(rebindings),running_reference_site_rebindings=sum(
            r['state']=='RUNNING' and r['reference_site_changed'] for r in rebindings),
        nominal_service_changes=0,GPU_gang_changes=0,
        initial_running_jobs=len(original_running),initial_running_GPU=source_initial_GPU,
        rebound_source_assigned_running_GPU=rebound_initial_GPU,
        source_assigned_running_GPU=source_assigned_GPU,old_placement_certificate_transfer=False,
        external_44_59_source_records_preserved=True,external_44_Dday_nominal_GPUh=0,
        actual_44_completion_not_used_in_planning=True,initial_site_authority=None))
    result=IntegrationCase(case_sha,source_freeze['source_sha'],prepared['qos_provider'],reference,initial,
        make_a_case,make_m_case,effects,arguments,receipts,source_freeze,'REAL_DATA',issue)
    result.actual_gate=actual_gate
    if initial_state_freeze is not None:
        from .actual_validation import prepare_actual
        actual_prepared=prepare_actual(archive/'raw'/day,source_freeze=source_freeze,
            strict_stats=strict_stats,case_sha=case_sha,provider_sha=provider_sha,
            initial_state_freeze=initial_state_freeze,planning_provider=prepared['qos_provider'],
            planning_known_receipts=prepared['known_receipts'])
        execution_arguments=dict(actual_prepared['arguments'])
        execution_arguments.pop('qos_window_provider',None)
        result.actual_arguments=execution_arguments
        result.actual_gate=actual_prepared['actual_gate']
        result.input_receipts.extend(actual_prepared['receipts'])
        result.evaluation_case_sha=digest(dict(planning_case_sha=case_sha,
            common_Dday_initial_state_sha=result.actual_gate['common_initial_state_sha']))
        _write(output/'ACTUAL_INITIAL_STATE_BINDING.json',dict(
            planning_case_sha=case_sha,evaluation_case_sha=result.evaluation_case_sha,
            initial_state_freeze=file_record(initial_state_freeze),actual_gate=result.actual_gate,
            planning_effective_inputs_unchanged=True,Dday_snapshot_used_in_Planning_variables=False,
            initial_QoS_ledger_known_UIDs=len(prepared['qos_provider'].receipts),
            prefix_unknown_QoS_issued_before_Actual=False,Apr30_queue_replay=False,
            source_receipts=actual_prepared['receipts']))
        _write(output/'PRE_DDAY_HISTORICAL_SOURCE_LEDGER.json',actual_prepared['historical_source_ledger'])
        _write(output/'DDAY_BOUNDARY_CONSUMPTION_AUDIT.json',actual_prepared['boundary_consumption_audit'])
    def control_policy_factory(*,arm,aidc,mess,bindings,envelope,output,mess_validation):
        verify_sources(source_freeze,result.input_receipts)
        return compile_production_control_policy(arm=arm,aidc=aidc,mess=mess,bindings=bindings,
            envelope=envelope,output=output,mess_validation=mess_validation,
            coefficients=physical.coefficients,power=power,idle_kw=idle,swing_kw=swing,
            capacities=bundle['capacities'],grid_authority=authority,cc4_inputs=cc4_inputs,
            initial_state_sha=(result.actual_gate or {}).get('common_initial_state_sha'),
            rack_limits={site:tuple(r['compatibility_GPU_limit'] for r in bundle['racks'] if r['aidc_id']==site)
                for site in bundle['capacities']},qos_provider=result.qos_provider,
            unknown_conditions=getattr(result,'unknown_conditions',None),
            migration_authority=getattr(result,'experimental_migration_authority',None),
            service_reallocation=getattr(result,'service_reallocation',False))
    result.control_policy_factory=control_policy_factory
    def fresh_evaluator(trace,mess,folder,budget,*,arm):
        from .actual_validation import fresh_ac_minimum
        from time import perf_counter
        folder=Path(folder)
        execution=read(folder.parent/'MESS_ACTUAL_EXECUTION_RECEIPT.json')
        began=perf_counter()
        status='FAILED'
        try:
            receipt=fresh_ac_minimum(archive/'raw'/day,folder.parent,folder,
                source_freeze=source_freeze,campaign_manifest=source_paths[-1],slots=fresh_ac_slots,
                mess_plan=mess,mess_execution_receipt=execution,trace_path=trace,arm=arm,
                case_scope=dict(planning_identity=planning_identity,
                    planning_case_sha=case_sha,evaluation_case_sha=getattr(result,'evaluation_case_sha',None),
                    common_initial_state_sha=result.actual_gate.get('common_initial_state_sha')))
            status=receipt['status']
            return receipt
        finally:
            budget.record_external('FRESH_ACTUAL_AC_'+str(fresh_ac_slots)+'_SLOTS',perf_counter()-began,solver='AC',status=status)
    result.fresh_evaluator=fresh_evaluator
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-freeze',type=Path,required=True)
    parser.add_argument('--strict-stats',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--initial-site-authority',type=Path)
    parser.add_argument('--initial-state-freeze',type=Path)
    args=parser.parse_args()
    case=build_integration_case(source_freeze=read(args.source_freeze),strict_stats=args.strict_stats,
        output=args.output,initial_site_authority=args.initial_site_authority,initial_state_freeze=args.initial_state_freeze)
    print(json.dumps(dict(PASS=True,case_sha=case.case_sha,Native_optimize_calls=0,production_models_prepared=False)))


if __name__=='__main__':
    main()
