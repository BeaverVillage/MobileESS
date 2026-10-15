"""Table V D0 E1/FLEX30 descriptors and original F2-CRA case factories.

Only observed D0 Known records enter this compiler. No future request bank,
realized service, model construction or optimization is read/run at prepare.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict,fields,replace
import math
from pathlib import Path

from .actual import JobRequest,_require_public_metadata
from .actual_validation import load_stats
from .a_engine import ACase,PlanningGridContext
from .d0_a_planning import D0ACase,D0PlanningGridContext,input_fingerprint
from .experimental_qos import ExperimentalQoSProvider,FROZEN_SEED
from .m_engine import file_record,_write
from .policy import digest
from .qos import ObservedJob,QoSWindowProvider,CausalReferenceScheduler
from .release_date_case import _require_context as require_basic_context,load_state
from .release_private_actual_inputs import STRICT_STATS,STRICT_STATS_SHA

SCHEMA='TABLE_V_FULL_FLEX_D0_CASE_V1'
POLICY='TABLE_V_D0_E1_FLEX30_R1_FULL_WORKLOAD_FLEXIBILITY_V1'
ROOT=Path(__file__).resolve().parents[1]
SLOT=900;OFFSET=24;H=120


def _seal(value,key):
    value=deepcopy(value);value[key]=digest(value);return value


def _records():
    names=('table_v_flex_planning.py','experimental_qos.py','experimental_planning.py',
        'experimental_policy.py','qos.py','d0_actual_inputs.py')
    paths=[Path(__file__).with_name(n) for n in names]
    paths += [ROOT/p for p in ('v42_native/service.py','v42_job_capability.py',
        'v42_a_stage_domain_v2/domain.py','v42_a_stage_phase1/producer.py','v42_boundary/generator.py')]
    return [file_record(p) for p in paths]


def verify_native_migration_authority(resources,authority):
    scalar=authority['scalar']
    paths={(r['source'],r['destination']):tuple(r['links']) for r in authority['routes'].values()}
    if (resources.bytes_per_gpu!=scalar['bytes_per_GPU'] or resources.max_active_transfers!=1
            or resources.max_active_transfers!=scalar['maximum_active_transfers_network_wide']
            or resources.restart_slots*SLOT!=scalar['current_conservative_restart_seconds']
            or scalar['checkpoint_interval_seconds']!=1800 or scalar['maximum_migrations_per_job']!=1
            or resources.paths!=paths):
        raise ValueError('TABLE_V_ORIGINAL_CHECKPOINT_WAN_NUMERIC_AUTHORITY_DRIFT')
    for link,row in authority['links'].items():
        if any(resources.wan_capacities.get((link,t))!=row['bandwidth_bytes_per_second']*SLOT for t in range(OFFSET,H)):
            raise ValueError('TABLE_V_ORIGINAL_96_SLOT_WAN_LINK_CAPACITY_DRIFT')
    return dict(PASS=True,source_packet_sha=authority['packet_source_sha'],original_native_WAN_unchanged=True,
        source_residency='EXISTING_APPROVED_PRESTAGED_AT_ALL_12_IDCS_CASE_STUDY',
        checkpoint_capability_measured=False,network_geography_measured=False,
        R2_payload_sensitivity_used=False)


def compile_public_reference(state):
    """Original nominal grid-blind scheduler; no realized completions."""
    begin=state['begin_epoch_seconds']
    reference_sha=digest(dict(rule='TABLE_V_D0_ORIGINAL_CAUSAL_REFERENCE_V1',
        common_initial_state_sha=state['common_initial_state_sha'],capacities=state['capacities'],
        original_scheduler=file_record(ROOT/'v42_integration/qos.py')))
    scheduler=CausalReferenceScheduler(state['capacities'],reference_sha=reference_sha)
    requests={}
    for kind,key in (('RUNNING','running'),('PENDING','pending')):
        for row in sorted(state[key],key=lambda r:(r['submit_seconds'],r['uid'])):
            request=JobRequest(row['uid'],row['submit_seconds'],row['gpu'],tuple(row['compatible_sites']),
                row['q50'],row['site'] if kind=='RUNNING' else None,deepcopy(row['metadata']))
            requests[row['uid']]=request
            if kind=='RUNNING':
                scheduler.observe_running(request,site=row['site'],start_seconds=row['observed_start_seconds'],
                    event_seconds=begin,elapsed_compute_seconds=row['elapsed_compute_seconds'])
            else:scheduler.submit(request,event_seconds=begin)
    if set(scheduler.assigned)!=set(requests):raise ValueError('TABLE_V_ALL_D0_REFERENCE_UIDS_REQUIRED')
    return scheduler,requests


def public_e1_records(state,scheduler):
    begin=state['begin_epoch_seconds'];records={}
    provider_sha=state['provider_identifiers']['runtime_provider_sha']
    for kind,key in (('RUNNING','running'),('PENDING','pending')):
        for row in state[key]:
            metadata=row['metadata'];uid=row['uid'];_require_public_metadata(metadata)
            # RUNNING's native start is its D0 remaining-service continuation.
            # Its historical episode start/elapsed/site remain separate above.
            reference=begin if kind=='RUNNING' else scheduler.assigned[uid]['reference_start_seconds']
            if kind=='PENDING':
                reference=SLOT*math.ceil(max(reference,metadata.get('release_seconds') or -math.inf,
                    metadata.get('hard_earliest_start_seconds') or -math.inf)/SLOT)
            attrs={f.name:deepcopy(metadata[f.name]) for f in fields(ObservedJob) if f.name in metadata}
            attrs.update(uid=uid,submit_seconds=row['submit_seconds'],event_seconds=begin,
                reference_start_seconds=reference,t50_seconds=row['q50'],gpu=row['gpu'],
                origin_unknown=False,is_observed=True,state=kind,provider_sha=provider_sha,
                reference_sha=scheduler.reference_sha,
                nominal_service_seconds=max(0.,row['q50']-row['elapsed_compute_seconds']) if kind=='RUNNING' else row['q50'])
            records[uid]=ObservedJob(**attrs)
    return records


def compile_flex_descriptors(base,*,strict_stats,source_records):
    """Public typed descriptor transform; full graph construction stays lazy."""
    state=base['state'];begin=state['begin_epoch_seconds']
    scheduler,_=compile_public_reference(state);observed=public_e1_records(state,scheduler)
    provisional=QoSWindowProvider(strict_stats,case_sha=base['manifest']['identity']['case_sha'],
        provider_sha=state['provider_identifiers']['runtime_provider_sha'])
    template=ExperimentalQoSProvider(provisional,scenario='E1',participation='FLEX30',case_sha='0'*64)
    policy=dict(policy_id=POLICY,scenario='E1',participation='FLEX30',seed=FROZEN_SEED,
        original_E1_spec=deepcopy(template.spec),original_E1_spec_sha=template.stats.sha,
        membership='EXISTING_UID_AND_PUBLIC_D0_EPISODE_THRESHOLD',
        baseline_reference='ORIGINAL_CAUSAL_GRID_BLIND_Q50_FROM_APPROVED_D0',
        normal_additional_delay_seconds=1800,verified_standby_additional_delay_seconds=3600,
        blanket_60_minute_authority=False,source_hard_contracts_extended=False,
        source_metadata_changed=False,research_contract_is_customer_SLA=False,
        pending_initial_site_scope='APPROVED_D0_SOURCE_COMPATIBLE_BACKLOG_PLACEMENT',
        checkpoint='EXISTING_E1_ASSUMED_CHECKPOINTABLE_FLEX30_ONLY',checkpoint_period_seconds=1800,
        maximum_migrations=1,original_WAN_payload_path_capacity_and_restart_preserved=True,
        R1='OBSERVED_FLEX30_PENDING_SHARED_INPUT_ASSUMPTION_ONLY',R2='HOLD',
        full_remaining_service_and_carry_preserved=True,future_Unknown_UIDs_used=False,
        old_Basic_bound_or_optimality_transferred=False,P2_calls=0)
    science_derivation=dict(parent_science=base['manifest']['identity']['science_sha'],
        source_records=source_records,policy=policy,public_records={u:asdict(j) for u,j in observed.items()})
    science=digest(science_derivation)
    case_derivation=dict(science=science,initial=state['common_initial_state_sha'],
        parent_case=base['manifest']['identity']['case_sha'],original_CC4=base['forecast']['forecast_receipt_sha'],
        native_math='ORIGINAL_F2_CRA_D0_FULL_FLEX')
    identity=deepcopy(base['manifest']['identity'])
    identity.update(science_sha=science,case_sha=digest(case_derivation))
    provider=ExperimentalQoSProvider(provisional,scenario='E1',participation='FLEX30',case_sha=identity['case_sha'])
    initial={r['uid']:r for key in ('running','pending') for r in state[key]}
    for uid,job in observed.items():
        provider.register_observed(uid,episode_id=initial[uid]['episode_id'],
            source_authority=dict(verified_fields=[],source_sha=base['manifest']['initial_record']['sha256'],
                observed_at_seconds=begin))
        provider.issue(job)
    bundle,jobs,bounds,resources,raw,_,_,prep=base['data']
    bundle=deepcopy(bundle);raw=deepcopy(raw);jobs=dict(jobs);bounds=dict(bounds)
    bundle['D0_source_identity']=identity
    bundle['Table_V_full_flex_policy']=deepcopy(policy)
    windows={};receipts={u:provider.receipts[u] for u in jobs};audit_rows=[];issues=[]
    from v42_native.service import boundary
    for uid,original in jobs.items():
        row=initial[uid];receipt=provider.receipts[uid];model=receipt.model_metadata
        running=original.state=='RUNNING'
        reference=OFFSET if running else OFFSET+int((observed[uid].reference_start_seconds-begin)/SLOT)
        allowed=(OFFSET,) if running else tuple(OFFSET+int((t-begin)/SLOT) for t in receipt.allowed_starts_seconds
            if begin<=t<begin+86400 and t>=observed[uid].reference_start_seconds)
        if not allowed or reference not in allowed:
            issues.append(dict(uid=uid,reason='CAUSAL_REFERENCE_OR_E1_WINDOW_OUTSIDE_ORIGINAL_D0_CONTROL_REPRESENTATION',
                reference_native_slot=reference,receipt_status=receipt.status,allowed_native_slots=list(allowed)))
            continue
        eligible=receipt.participant and receipt.eligible_for_contract
        jobs[uid]=replace(original,reference_start=reference,reference_site=scheduler.assigned[uid]['reference_site'],
            initial_sites=tuple(row['compatible_sites']) if not running or eligible else (row['site'],),
            checkpoint_authorized=eligible,qos_policy_id=receipt.policy_id,qos_receipt_sha=digest(receipt.to_dict()),
            qos_allowed_starts=allowed,qos_budget_seconds=receipt.budget_seconds,
            batch_eligible=model['batch_eligible'],qos=model['qos'],protected=model['protected'])
        bounds[uid]=boundary(jobs[uid],allowed,digest(receipt.to_dict()),identity['runtime_sha'],H=H)
        deadline=observed[uid].completion_deadline_seconds
        if deadline is not None:
            hard_end=math.floor((deadline-(begin-OFFSET*SLOT))/SLOT)
            bounds[uid]=replace(bounds[uid],latest_completion=min(bounds[uid].latest_completion,hard_end))
            if bounds[uid].latest_completion<reference+original.service_slots:
                issues.append(dict(uid=uid,reason='ORIGINAL_HARD_COMPLETION_BOUND_EXCLUDES_FULL_REFERENCE_SERVICE'))
        windows[uid]=allowed
        raw[uid].update(reference_start_if_authorized=reference,reference_end=reference+original.service_slots,
            planning_site=jobs[uid].reference_site,can_timeshift=eligible and not running and len(allowed)>1,
            can_checkpoint_migrate=eligible,can_prestart_place=not running,
            compatible_sites=deepcopy(row['compatible_sites']),
            Table_V_E1_receipt_sha=digest(receipt.to_dict()))
        if not running:
            raw[uid]['risk_nominal_completion_issue_slot']+=reference-original.reference_start
        audit_rows.append(dict(uid=uid,state=original.state,episode_id=row['episode_id'],participant=receipt.participant,
            eligible=eligible,source_qos=observed[uid].qos,model_qos=model['qos'],budget_seconds=receipt.budget_seconds,
            reference_native_slot=reference,allowed_native_starts=list(allowed),initial_sites=list(jobs[uid].initial_sites),
            checkpoint_authorized=eligible,checkpoint_records='DEFERRED_EXACT_ORIGINAL_DOMAIN_MATERIALIZATION',
            full_service_slots=original.service_slots,elapsed_seconds=original.elapsed_seconds,
            source_hard_contract=deepcopy(receipt.hard_contract),old_basic_windows=len(base['windows'][uid])))
    bundle['known_population']=[deepcopy(raw[r['job_uid']]) for r in bundle['known_population']]
    newprep=deepcopy(prep);newprep.update(classes={},domain_authority='TABLE_V_E1_FULL_FLEX_UNMATERIALIZED',
        full_migration_domain_active=True,checkpoint_domain_scope='ORIGINAL_E1_FLEX30_SOURCE_WAN_HARD_CONTRACT',
        Table_V_full_flex_policy_sha=digest(policy))
    data=(bundle,jobs,bounds,deepcopy(resources),raw,{},{},newprep)
    return dict(identity=identity,policy=policy,provider=provider,observed=observed,
        reference=scheduler,data=data,windows=windows,receipts=receipts,audit_rows=audit_rows,issues=issues,
        science_derivation=science_derivation,case_derivation=case_derivation)


def require_flex_case(manifest,*,stage=None):
    from .release_date_case import require_date_case
    if (manifest.get('schema')!=SCHEMA or manifest.get('manifest_sha')!=digest({k:v for k,v in manifest.items() if k!='manifest_sha'})
            or manifest.get('day')!='2025-05-01' or manifest.get('Table_V_full_flex') is not True):
        raise ValueError('EXACT_TABLE_V_FULL_FLEX_MANIFEST_REQUIRED')
    require_date_case(manifest['parent_basic_manifest'])
    if (manifest['identity']['initial_state_sha']!=manifest['parent_basic_manifest']['identity']['initial_state_sha']
            or manifest['identity']['case_sha']==manifest['parent_basic_manifest']['identity']['case_sha']
            or manifest['identity']['science_sha']==manifest['parent_basic_manifest']['identity']['science_sha']):
        raise ValueError('TABLE_V_NEW_FULL_FLEX_CASE_AND_SAME_INITIAL_REQUIRED')
    freeze=manifest['source_freeze']
    required={r['path']:r for r in manifest['parent_basic_manifest']['source_freeze']['files']+_records()+[file_record(STRICT_STATS)]}
    present={r['path']:r for r in freeze['files']}
    if (freeze['source_sha']!=digest(freeze['files']) or manifest['source_sha']!=freeze['source_sha']
            or any(present.get(path)!=record for path,record in required.items())
            or any(file_record(r['path'])!=r for r in freeze['files'])):
        raise ValueError('TABLE_V_FULL_FLEX_SOURCE_BYTES_DRIFT')
    if (digest(manifest['science_derivation'])!=manifest['identity']['science_sha']
            or digest(manifest['case_derivation'])!=manifest['identity']['case_sha']
            or manifest['science_derivation']['source_records']!=freeze['files']
            or manifest['science_derivation']['policy']['policy_id']!=POLICY
            or manifest['science_derivation']['policy']['scenario']!='E1'
            or manifest['science_derivation']['policy']['participation']!='FLEX30'
            or manifest['case_derivation']['initial']!=manifest['identity']['initial_state_sha']
            or manifest['case_derivation']['parent_case']!=manifest['parent_basic_manifest']['identity']['case_sha']):
        raise ValueError('TABLE_V_FLEX_SCIENCE_CASE_DERIVATION_DRIFT')
    if stage is not None and stage not in ('A1','A2','M1','M2'):raise ValueError('TABLE_V_ORIGINAL_STAGE_REQUIRED')
    return manifest


def require_flex_context(context):
    require_flex_case(context['manifest'])
    if (context['data'][0]['D0_source_identity']!=context['manifest']['identity']
            or input_fingerprint(context['data'])!=context['input_audit']['a_input_sha']
            or context['input_audit']['a_input_sha']!=context['manifest']['full_flex_input_sha']
            or context['input_audit']['status']!='PASS'):
        raise ValueError('TABLE_V_FULL_FLEX_TYPED_INPUT_DRIFT_OR_UNAVAILABLE')
    return context


def compile_table_v_flex_context(base_context,*,output,call_cap=600.):
    require_basic_context(base_context)
    state=base_context['state']
    if state['day']!='2025-05-01':raise ValueError('TABLE_V_MAY01_ONLY_AUTHORIZATION')
    output=Path(output)
    if output.exists():raise FileExistsError('TABLE_V_FULL_FLEX_PREPARATION_MUST_NOT_OVERWRITE')
    stats_record=file_record(STRICT_STATS)
    if stats_record['sha256']!=STRICT_STATS_SHA:raise ValueError('TABLE_V_ORIGINAL_STRICT_STATISTICS_DRIFT')
    sources=base_context['manifest']['source_freeze']['files']+_records()+[stats_record]
    from .experimental_policy import load_experimental_migration_authority
    migration=load_experimental_migration_authority()
    migration_check=verify_native_migration_authority(base_context['data'][3],migration)
    sources += [file_record(r['path']) for r in migration['source_receipts']]
    sources=list({r['path']:r for r in sources}.values())
    compiled=compile_flex_descriptors(base_context,strict_stats=load_stats(STRICT_STATS),source_records=sources)
    identity=compiled['identity'];source_sha=digest(sources)
    manifest=deepcopy(base_context['manifest']);manifest.pop('manifest_sha')
    manifest.update(schema=SCHEMA,day=state['day'],Table_V_full_flex=True,
        parent_basic_manifest=deepcopy(base_context['manifest']),identity=identity,source_sha=source_sha,
        source_freeze=dict(files=sources,source_sha=source_sha,science_version=POLICY),
        science_derivation=compiled['science_derivation'],case_derivation=compiled['case_derivation'],
        full_flex_input_sha=input_fingerprint(compiled['data']),
        science_payload=dict(parent=base_context['manifest']['science_payload'],policy=compiled['policy'],
            E1_spec_sha=compiled['provider'].stats.sha,Known_records_sha=digest({u:asdict(j) for u,j in compiled['observed'].items()})))
    backlog=_seal(dict(schema='TABLE_V_D0_E1_FULL_FLEX_BACKLOG_V1',policy_id=POLICY,
        initial_state_sha=state['common_initial_state_sha'],issue_seconds=state['begin_epoch_seconds'],
        end_seconds=state['end_epoch_seconds'],pending_source_compatible_placement_research_authorized=True,
        E1_FLEX30=True,additional_delay_caps=dict(normal=1800,source_verified_standby=3600),
        all_job_60min_authority=False,hard_source_contracts_extended=False),'contract_sha')
    manifest=_seal(manifest,'manifest_sha')
    audit=deepcopy(base_context['input_audit']);audit.update(identity=identity,
        a_input_sha=input_fingerprint(compiled['data']),backlog_contract_sha=backlog['contract_sha'],
        status='PASS' if not compiled['issues'] else 'INPUT_UNAVAILABLE',full_flex_domain=True,
        Table_V_E1_FLEX30=True,domain_materialization='DEFERRED_ORIGINAL_AUTHORIZED_DATA',
        native_model_build='NOT_RUN',issues=compiled['issues'])
    provider=compiled['provider'];reference=compiled['reference']
    flex=dict(spec=compiled['policy'],stats_sha=provider.stats.sha,strict_stats_record=stats_record,
        strict_stats_sha=provider.strict.stats.sha,case_sha=identity['case_sha'],provider_sha=provider.provider_sha,
        reference_sha=reference.reference_sha,known_issued_receipts=provider.export_ledger(),
        known_source_contexts=deepcopy(provider.contexts),known_observed_records={u:asdict(j) for u,j in compiled['observed'].items()},
        domain_mask=compiled['audit_rows'],reference_records=deepcopy(reference.assigned))
    flex.update(migration_authority=migration,migration_numeric_source_check=migration_check)
    context=dict(base_context,manifest=manifest,data=compiled['data'],windows=compiled['windows'],
        receipts=compiled['receipts'],backlog=backlog,input_audit=audit,tablev_flex=flex,
        production_case_verifier=require_flex_case,require_case=require_flex_case)
    classification=deepcopy(base_context['classification'])
    for row in classification:
        uid=row['uid']
        if uid in compiled['windows']:
            row.update(legal_D0_start_seconds=[state['begin_epoch_seconds']+(s-OFFSET)*SLOT for s in compiled['windows'][uid]],
                D0_backlog_contract_sha=backlog['contract_sha'],D0_science_sha=identity['science_sha'],
                D0_case_sha=identity['case_sha'],E1_receipt_sha=digest(provider.receipts[uid].to_dict()),
                additional_intentional_delay_budget_seconds=provider.receipts[uid].budget_seconds,
                Table_V_full_flex=True)
    context['classification']=classification
    _attach_a_factory(context,base_context,output,call_cap)
    output.mkdir(parents=True)
    for name,value in [('TABLE_V_FLEX_CASE_MANIFEST.json',manifest),('TABLE_V_FLEX_INPUT_AUDIT.json',audit),
        ('TABLE_V_FLEXIBILITY_POLICY_FREEZE.json',flex),('TABLE_V_FULL_FLEX_KNOWN_FUNNEL.json',compiled['audit_rows'])]:
        _write(output/name,value)
    return context


def _attach_a_factory(context,base,output,call_cap):
    physical_cache={}
    def materialize_physical():
        if not physical_cache:
            template=base['make_a_case']('A1')
            physical=base['materialize_physical']()['physical'] if 'materialize_physical' in base else base['physical']
            physical_cache.update(physical=physical,template_grid=template.grid,
                initial_mess=deepcopy(template.grid.fixed_mess))
        return physical_cache
    def make_a_case(stage='A1',fixed_mess=None,folder=None,upstream_m_result=None,*,arm='B3'):
        require_flex_context(context)
        if arm not in ('B1','B3') or stage not in ('A1','A2') or arm=='B1' and stage!='A1':
            raise ValueError('TABLE_V_EXACT_FLEXIBLE_ARM_AND_A_STAGE_REQUIRED')
        cache=materialize_physical();grid0=cache['template_grid']
        fixed=fixed_mess or cache['initial_mess']
        if fixed.get('plan_sha')!=digest({k:v for k,v in fixed.items() if k!='plan_sha'}):
            raise ValueError('TABLE_V_FIXED_MESS_PLAN_SEAL_DRIFT')
        if stage=='A1' and fixed!=cache['initial_mess']:raise ValueError('TABLE_V_A1_MESS_OFF_REQUIRED')
        if stage=='A2':
            from .coordinator import _full_m
            if (upstream_m_result is None or upstream_m_result.get('stage')!='M1'
                    or upstream_m_result.get('D0_source_identity')!=context['manifest']['identity']
                    or _full_m(upstream_m_result)!=fixed):
                raise ValueError('TABLE_V_A2_CURRENT_FULL_M1_ANCHOR_REQUIRED')
        attrs={f.name:getattr(grid0,f.name) for f in fields(PlanningGridContext)}
        attrs.update(fixed_mess=fixed,planning_arrays=None,
            authority=replace(grid0.authority,service_sha=digest(context['data'][0])))
        grid=D0PlanningGridContext(**attrs)
        stage_sha=digest(dict(parent=context['manifest']['identity']['case_sha'],stage=stage,
            input_MESS_anchor=fixed['plan_sha'],backlog_contract=context['backlog']['contract_sha']))
        case=D0ACase(context['data'],grid,Path(folder or output/arm/stage),stage_sha,stage,arm,
            context['windows'],context['receipts'],call_cap=float(call_cap),d0_input_audit=context['input_audit'])
        case.table_v_full_flex=True
        case.table_v_arm_certificate=_seal(dict(arm=arm,stage=stage,stage_case_sha=stage_sha,
            shared_full_flex_case=context['manifest']['identity'],math_input_sha=context['input_audit']['a_input_sha'],
            MESS_anchor=fixed['plan_sha'],P1_only=True,P2_calls=0),'certificate_sha')
        return case
    context.update(make_a_case=make_a_case,materialize_physical=materialize_physical)


def build_flex_native_model(case,*,build_admission):
    """Supervisor-only build, preserving original authorized_data/F2-CRA math."""
    if (not isinstance(case,D0ACase) or getattr(case,'table_v_full_flex',False) is not True
            or case.d0_input_audit['status']!='PASS' or input_fingerprint(case.data)!=case.d0_input_audit['a_input_sha']):
        raise ValueError('TABLE_V_FULL_FLEX_A_CASE_REQUIRED')
    if (build_admission.get('status')!='PASS' or build_admission.get('operation')!='TABLE_V_FULL_FLEX_A_NATIVE0_BUILD'
            or build_admission.get('case_sha')!=case.case_sha or build_admission.get('concurrent_heavy_solver') is not False):
        raise ValueError('TABLE_V_SUPERVISOR_FULL_FLEX_BUILD_ADMISSION_REQUIRED')
    from .a_engine import authorized_data
    from v42_root.native import build
    from v42_native.voltage import Stage
    data,domains=authorized_data(case)
    if not data[7]['full_migration_domain_active']:raise ValueError('TABLE_V_ORIGINAL_FULL_DOMAIN_NOT_ACTIVE')
    class Context:
        folder=Path(case.output)
        def check(self):pass
        def progress(self,value):
            if case.progress:case.progress(value)
    Context.folder.mkdir(parents=True,exist_ok=True)
    model,units,levels,controls,bindings=build(Context(),data,'F2-CRA',grid_context=case.grid,
        stage=Stage.A2 if case.stage=='A2' else Stage.A1)
    try:
        if [n for n,_ in levels]!=['rho','reserve_shortfall','CC4_reference_deviation','migration_count','shift_slots','prestart_changes']:
            raise ValueError('TABLE_V_ORIGINAL_OBJECTIVE_LAYER_DRIFT')
        receipt=dict(status='PASS',scope='TABLE_V_ORIGINAL_FULL_FLEX_MATRIX_NATIVE0_NOT_FULL_FEASIBLE',
            stage=case.stage,arm=case.arm,case_sha=case.case_sha,source_identity=case.d0_input_audit['identity'],
            input_MESS_anchor=case.grid.fixed_mess['plan_sha'],rows=model.NumConstrs,columns=model.NumVars,
            nonzeros=model.NumNZs,Native_calls=0,full_physical_domains=len(domains),
            full_migration_domain_active=True,domain_authority=data[7]['domain_authority'],
            original_objective_layers=[n for n,_ in levels],P2_calls=0,
            checkpoint_UIDs=sum(j.checkpoint_authorized for j in data[1].values()),
            migration_block_count=sum(len(d.blocks) for d in domains.values()),
            complete_remaining_service_and_carry_preserved=True,old_bound_or_point_transferred=False)
        return model,units,levels,controls,bindings,data,receipt
    except Exception:model.dispose();raise


def audit_basic_a1_reuse(context,saved_result):
    require_flex_context(context)
    data=context['data'];violations=[]
    from v42_job_capability import Option,validate
    for uid,record in saved_result['selected_jobs'].items():
        if uid not in data[1]:violations.append(dict(uid=uid,reason='NATIVE_SERVICE_ROSTER_CHANGED'));continue
        option=deepcopy(record);option['segments']=tuple(tuple(r) for r in option['segments'])
        option['wan']=tuple(tuple(r) for r in option.get('wan',()))
        try:validate(data[1][uid],Option(**option),data[2][uid],data[3])
        except ValueError as exc:violations.append(dict(uid=uid,reason=str(exc)))
    same=False
    return dict(status='DIFFERENT_MATHEMATICAL_CASE',old_objective=saved_result.get('objective',saved_result.get('rho')),
        same_science_case=False,same_Job_domain=False,same_E1_time_shift_budget=False,
        same_checkpoint_domain=False,CC4_and_electrical_source_preserved=True,
        old_optimal_bound_transfer_allowed=False,old_optimality_transfer_allowed=False,
        old_point_as_new_domain_warmstart_allowed=not violations,
        old_point_requires_new_original_FULL_matrix_replay=True,local_option_violations=violations,
        Native_calls=0,native_model_builds=0)


def b1_b3_a1_math_equivalence(context):
    require_flex_context(context)
    manifest=context['manifest']
    payload=dict(input_sha=context['input_audit']['a_input_sha'],policy_sha=digest(context['tablev_flex']['spec']),
        source_identity=manifest['identity'],CC4_sha=manifest['identity']['cc4_sha'],
        physical_sha=manifest['physical_sha'],objective='ORIGINAL_P1_MIN_MAX_PHASE_LINE_LOADING',
        native_offset=24,native_F2_CRA_source=file_record(ROOT/'v42_root/native.py'),
        original_a_engine_source=file_record(ROOT/'v42_integration/a_engine.py'),MESS='INITIAL_ZERO_P_Q_STAY')
    return dict(status='PASS_IDENTICAL_B1_B3_A1_PUBLIC_MATH_INPUTS_PENDING_MATRIX_REPLAY',
        common_math_sha=digest(payload),math_payload=payload,arms=['B1','B3'],
        original_FULL_per_arm_replay_required=True,same_native_point_implied_without_replay=False,
        Native_calls=0,native_model_builds=0,old_Basic_optimum_reused=False)


def compile_flex_commands(a_result,context):
    """Original native Option conversion with the new E1 case/UID guards."""
    require_flex_context(context)
    from .coordinator import _full_a
    from .known_commands import compile_known_commands
    state=context['state'];manifest=context['manifest'];begin=state['begin_epoch_seconds']
    stage=a_result.get('stage');anchor=a_result.get('input_MESS_anchor')
    expected=digest(dict(parent=manifest['identity']['case_sha'],stage=stage,
        input_MESS_anchor=anchor,backlog_contract=context['backlog']['contract_sha']))
    residual=a_result.get('FULL_max_residual',math.inf)
    if (stage not in ('A1','A2') or a_result.get('case_sha')!=expected
            or a_result.get('source_identity')!=manifest['identity']
            or a_result.get('D0_input_sha')!=context['input_audit']['a_input_sha']
            or a_result.get('D0_issue_seconds')!=begin or not isinstance(anchor,str) or len(anchor)!=64
            or a_result.get('FULL_feasible') is not True or a_result.get('FULL_point_replay',{}).get('PASS') is not True
            or type(residual) not in (int,float) or not math.isfinite(residual) or not 0<=residual<=1e-5):
        raise ValueError('TABLE_V_CURRENT_ORIGINAL_FULL_A_SOURCE_STAGE_REQUIRED')
    _full_a(a_result)
    if stage=='A1' and anchor!=context['materialize_physical']()['initial_mess']['plan_sha']:
        raise ValueError('TABLE_V_A1_ORIGINAL_MESS_OFF_ANCHOR_REQUIRED')
    selected=a_result['selected_jobs'];holds=a_result.get('initial_Q50_expired_physical_holds',{})
    initial={r['uid']:r for key in ('running','pending') for r in state[key]}
    expected_holds={uid for uid,r in context['data'][4].items() if r['state']=='RUNNING' and r['service_slots']==0}
    if set(selected)!=set(context['data'][1]) or set(holds)!=expected_holds or set(selected)|set(holds)!=set(initial):
        raise ValueError('TABLE_V_ALL_D0_KNOWN_SERVICE_OR_PHYSICAL_HOLD_REQUIRED')
    for uid,hold in holds.items():
        row=initial[uid]
        if (hold.get('site')!=row['site'] or hold.get('gpu')!=row['gpu']
                or hold.get('elapsed_seconds')!=row['elapsed_compute_seconds']
                or hold.get('physical_release_rule')!='OBSERVED_COMPLETION_ONLY'):
            raise ValueError('TABLE_V_EXPIRED_RUNNING_PHYSICAL_HOLD_DRIFT')
    commands=compile_known_commands(selected,slot_zero_seconds=begin-OFFSET*SLOT,
        migration_authority=context['tablev_flex']['migration_authority'],
        gpu_by_uid={uid:context['data'][1][uid].gpu for uid in selected})
    from v42_job_capability import Option,validate
    for uid,command in commands.items():
        row=initial[uid];option=deepcopy(selected[uid])
        option['segments']=tuple(tuple(r) for r in option['segments']);option['wan']=tuple(tuple(r) for r in option.get('wan',()))
        validate(context['data'][1][uid],Option(**option),context['data'][2][uid],context['data'][3])
        running=row['site'] is not None
        if command['start_seconds']<begin or command['site'] not in row['compatible_sites']:
            raise ValueError('TABLE_V_COMMAND_SOURCE_SITE_OR_D0_TIME_DRIFT')
        if running and (command['start_seconds']!=begin or command['site']!=row['site']):
            raise ValueError('TABLE_V_RUNNING_PINNED_EPISODE_CONTINUATION_REQUIRED')
        command.update(command_type='D0_RUNNING_CONTINUATION' if running else 'D0_PENDING_NEW_OPTIMIZED_START',
            episode_id=row['episode_id'])
        if running:command.update(historical_episode_start_seconds=row['observed_start_seconds'],
            elapsed_compute_seconds=row['elapsed_compute_seconds'],physical_job_restarted=False)
    return commands


def load_table_v_context(path,*,call_cap=5400.):
    """Reconstruct public context and byte-compare the saved immutable inputs."""
    import tempfile
    from .release_date_case import compile_date_case
    from .actual_validation import read
    path=Path(path)
    if not (path/'TABLE_V_FLEX_CASE_MANIFEST.json').exists():path=path/'FULL_FLEX'
    names=('TABLE_V_FLEX_CASE_MANIFEST.json','TABLE_V_FLEX_INPUT_AUDIT.json',
        'TABLE_V_FLEXIBILITY_POLICY_FREEZE.json','TABLE_V_FULL_FLEX_KNOWN_FUNNEL.json')
    saved={name:file_record(path/name) for name in names}
    require_flex_case(read(path/names[0]))
    with tempfile.TemporaryDirectory(prefix='v42_table_v_public_context_') as scratch:
        scratch=Path(scratch)
        basic=compile_date_case('2025-05-01',output=scratch/'BASIC',call_cap=call_cap)
        context=compile_table_v_flex_context(basic,output=scratch/'FULL_FLEX',call_cap=call_cap)
        for name,record in saved.items():
            if (scratch/'FULL_FLEX'/name).read_bytes()!=(path/name).read_bytes() or file_record(record['path'])!=record:
                raise ValueError('TABLE_V_SAVED_PUBLIC_CONTEXT_BYTES_DRIFT:'+name)
        _attach_a_factory(context,basic,path,call_cap)
    require_flex_context(context)
    return context
