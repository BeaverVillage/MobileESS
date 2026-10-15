"""Real serial P1-only campaign dispatch with durable fail-closed checkpoints.

No injected executor is accepted by the production entrypoint. The underscored
fixture loop tests checkpoint mechanics only and cannot authorize a campaign.
"""
from copy import deepcopy
from datetime import date,timedelta
import importlib
import importlib.util
import json
import math
from pathlib import Path
import pickle
from time import perf_counter

from .a_engine import digest
from .m_engine import file_record,_write
from .release_p1_production import OriginalP1Stages,production_backend,require_production_acceptance

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'docs/v42_unified_aidc_mess_research_20261014'
STAGES=('INPUT','A1','M1','A2','M2','K48_M2','ACTUAL','FRESH_AC','AUDIT')
PLANNING_STAGES=('INPUT','A1','M1','A2','M2')
GATE_CONTRACT='SLOTTED_SETTLED_ORIGINAL_PR223_V1'
TERMINAL={'FULL_PASS','PHYSICAL_FAIL','TIME_LIMIT_NO_FEASIBLE','OPTIMALITY_TARGET_UNMET',
    'INPUT_UNAVAILABLE','NOT_CERTIFIED','NOT_RUN'}


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def may_dates():return [(date(2025,5,1)+timedelta(days=k)).isoformat() for k in range(31)]
def _needs_full96_launch(plan):return any(day!='2025-05-01' for day in plan.get('dates',[]))


def production_sources():
    paths=['release_p1_acceptance.py','release_p1_production.py','release_production_budget.py',
        'release_production_campaign.py','release_date_case.py','release_initial_states.py',
        'release_ac_contract.py','research_presite_contract.py','research_presite_actual.py',
        'rc02_prefix_cache.py','release_date_execution.py']
    for name in ('research_presite_transfer_literature.py','release_production_actual.py',
            'release_private_actual_inputs.py','release_date_ac.py'):
        if (Path(__file__).parent/name).exists():paths.append(name)
    return [file_record(Path(__file__).parent/p) for p in paths]


def _actual_factory():
    name='v42_integration.release_production_actual'
    if importlib.util.find_spec(name) is None:return None
    module=importlib.import_module(name)
    if not all(callable(getattr(module,n,None)) for n in ('run_production_actual','run_production_fresh')):return None
    return module


def _checked_document(record):
    if file_record(record['path'])!=record:raise ValueError('PINNED_PLANNING_CHECKPOINT_BYTES_DRIFT')
    return read(record['path'])


def require_planning_checkpoint(record,*,source_case):
    """Authenticate completed real planning and its consumed Native ledger.

    This only reads files. It never runs a factory, unpickles a model, restores
    a solver, or trusts a caller's assertion that a stage was imported.
    """
    from .release_production_budget import require_authorization
    state=_checked_document(record);day=source_case['day'];identity=source_case['source_identity']
    origin=state.get('identity',{})
    if (state.get('day')!=day or state.get('status')!='FULL_PASS'
            or state.get('evidence_scope')!='REAL_PRODUCTION'
            or origin.get('required_stages')!=list(PLANNING_STAGES)):
        raise ValueError('REAL_COMPLETE_P1_PLANNING_CHECKPOINT_REQUIRED')
    source_records=origin.get('production_sources',[])
    required={str((Path(__file__).parent/name).resolve()) for name in
        ('release_p1_acceptance.py','release_p1_production.py','release_production_budget.py',
        'release_production_campaign.py','release_date_case.py','release_initial_states.py')}
    if (not required.issubset({r.get('path') for r in source_records})
            or any(file_record(r['path'])!=r for r in source_records)):
        raise ValueError('PLANNING_EXECUTED_SOURCE_BYTES_DRIFT')
    historical=origin.get('historical_read_only',[])
    if len(historical)<2 or any(file_record(r['path'])!=r for r in historical):
        raise ValueError('PLANNING_HISTORICAL_READ_ONLY_LEDGER_DRIFT')
    budget_record=state['completed_native_budget'];budget=_checked_document(budget_record)
    approval=budget['authorization_document'];require_authorization(approval)
    if (budget.get('inflight') is not None or budget.get('active_stage_context') is not None
            or origin.get('authorization_sha')!=digest(approval)
            or budget.get('release_identity',{}).get('authorization_sha')!=digest(approval)
            or Path(approval['authorized_ledger_path']).resolve()!=Path(budget_record['path']).resolve()
            or source_case not in approval.get('authorized_date_cases',[])
            or origin.get('native_budget_ledger_path')!=str(Path(budget_record['path']).resolve())
            or budget.get('release_identity',{}).get('historical_read_only')!=historical):
        raise ValueError('PLANNING_CONSUMED_NATIVE_LEDGER_SOURCE_OR_INFLIGHT_DRIFT')
    claim=_checked_document(budget['release_identity']['authorization_claim'])
    if claim!=dict(authorization_sha=digest(approval),authorized_ledger_path=str(Path(budget_record['path']).resolve())):
        raise ValueError('PLANNING_NATIVE_AUTHORIZATION_CLAIM_DRIFT')
    rows=state.get('stages',{});previous=None
    for stage in PLANNING_STAGES:
        row=rows[stage]
        _validate_row(row,stage=stage,day=day,parent_sha=None if previous is None else digest(previous['result']))
        if row.get('executed') is not True or row['status']!='FULL_PASS' or not row.get('raw_records'):
            raise ValueError('PLANNING_ALL_ORIGINAL_FULL_RAW_STAGES_REQUIRED')
        if stage=='INPUT':
            if (row['result'].get('identity')!=identity or row['result'].get('source_sha')!=source_case['source_sha']
                    or row['result'].get('initial_state_sha')!=identity['initial_state_sha']):
                raise ValueError('PLANNING_CURRENT_D0_INPUT_SOURCE_CASE_DRIFT')
            manifests=[r for r in row['raw_records'] if Path(r['path']).name=='D0_CASE_MANIFEST.json']
            if len(manifests)!=1:raise ValueError('PLANNING_LITERAL_D0_MANIFEST_REQUIRED')
            manifest=_checked_document(manifests[0])
            from .release_date_case import require_date_case
            require_date_case(manifest)
            if (manifest['identity']!=identity or manifest['source_sha']!=source_case['source_sha']
                    or manifest['manifest_sha']!=row['result'].get('manifest_sha')):
                raise ValueError('PLANNING_RAW_CURRENT_D0_MANIFEST_DRIFT')
        else:
            receipt=row['acceptance']
            require_production_acceptance(receipt,stage=stage,identity=identity,result=row['result'])
            if receipt.get('source_sha')!=source_case['source_sha']:
                raise ValueError('PLANNING_STAGE_SOURCE_SHA_DRIFT')
            certificate=receipt.get('Original_FULL',{})
            if certificate.get('PASS') is not True:
                raise ValueError('PLANNING_LITERAL_ORIGINAL_FULL_CERTIFICATE_REQUIRED')
            if stage in ('A1','A2'):
                from .coordinator import _full_a
                _full_a(row['result'])
                residual=certificate.get('FULL_max_residual',math.inf)
                if (type(residual) not in (int,float) or not math.isfinite(residual) or not 0<=residual<=1e-5
                        or row['result'].get('source_identity')!=identity
                        or row['result'].get('D0_input_sha')!=rows['INPUT']['result'].get('input_sha')
                        or row['result'].get('case_sha')!=receipt['stage_case_sha']
                        or certificate.get('point_sha256')!=row['result'].get('FULL_point_replay',{}).get('point_sha256')):
                    raise ValueError('PLANNING_A_LITERAL_FULL_POINT_RESIDUAL_DRIFT')
            else:
                from .coordinator import _full_m
                _full_m(row['result'])
                original=certificate.get('original_matrix_and_96_slot_physical_replay',{})
                if (original.get('PASS') is not True or original.get('case_sha')!=receipt['stage_case_sha']
                        or certificate.get('strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact') is not True):
                    raise ValueError('PLANNING_M_LITERAL_FULL_PHYSICAL_INTEGER_CERTIFICATE_DRIFT')
                if row.get('prepared_case') not in row['raw_records']:
                    raise ValueError('PLANNING_CURRENT_M_CASE_PACKET_NOT_PINNED')
            if stage!='A1' and receipt.get('parent_acceptance_sha')!=previous['acceptance']['acceptance_sha']:
                raise ValueError('PLANNING_ORIGINAL_FULL_ANCESTOR_CHAIN_DRIFT')
            if stage in ('M1','M2'):
                if receipt['AIDC_anchor']!=previous['acceptance']['AIDC_anchor']:
                    raise ValueError('PLANNING_FIXED_AIDC_ANCHOR_DRIFT')
            elif stage=='A2' and receipt['MESS_anchor']!=previous['acceptance']['MESS_anchor']:
                raise ValueError('PLANNING_A2_FIXED_M1_ANCHOR_DRIFT')
        previous=row
    calls=budget.get('calls',[]);charged=0.
    for call in calls:
        cost=call.get('charged_seconds',call.get('measured_seconds',0.))
        if type(cost) not in (int,float) or not math.isfinite(cost) or cost<0 or call.get('P2_call') is not False:
            raise ValueError('PLANNING_NATIVE_FINITE_COST_OR_P2_DRIFT')
        if call.get('solver')!='AC':charged+=cost
        context=call.get('stage_context',{})
        if context.get('day')!=day:continue
        stage=context.get('stage')
        if stage not in ('A1','M1','A2','M2'):
            raise ValueError('PLANNING_UNEXPECTED_NATIVE_STAGE')
        accepted=rows[stage];parent='INPUT' if stage=='A1' else 'A1' if stage=='M1' else 'M1' if stage=='A2' else 'A2'
        parent_sha=rows['INPUT']['result']['manifest_sha'] if stage=='A1' else digest(rows[parent]['result'])
        if (context.get('source_sha')!=source_case['source_sha']
                or context.get('stage_case_sha')!=accepted['acceptance']['stage_case_sha']
                or context.get('parent_result_sha')!=parent_sha
                or not call.get('label','').startswith('RELEASE_P1:'+stage+':')
                or 'P2' in call.get('label','').upper()):
            raise ValueError('PLANNING_NATIVE_SOURCE_CASE_PARENT_BINDING_DRIFT')
        if call.get('solver')=='GUROBI':
            binding=call.get('native_binding',{})
            if (binding.get('Threads')!=1 or binding.get('objective_sense')!=1
                    or not binding.get('matrix_sha') or not binding.get('domain_sha')):
                raise ValueError('PLANNING_NATIVE_MODEL_BINDING_DRIFT')
            runtime=call.get('Native_Runtime')
            if runtime is not None and (type(runtime) not in (int,float) or not math.isfinite(runtime)
                    or runtime<0 or not math.isclose(runtime,cost,rel_tol=1e-12,abs_tol=1e-7)):
                raise ValueError('PLANNING_NATIVE_RUNTIME_AND_CHARGE_DRIFT')
    if not math.isclose(charged,budget.get('conservative_solve_seconds',math.nan),rel_tol=1e-12,abs_tol=1e-7):
        raise ValueError('PLANNING_NATIVE_TOTAL_COST_DRIFT')
    for stage in ('A1','M1','A2','M2'):
        if stage=='A1' and day=='2025-05-01':continue
        stage_calls=[c for c in calls if c.get('stage_context',{}).get('day')==day
            and c.get('stage_context',{}).get('stage')==stage]
        if not stage_calls:raise ValueError('PLANNING_STAGE_HAS_NO_NATIVE_OR_SOLVER_LEDGER_EVIDENCE')
        if stage in ('A1','A2') and rows[stage]['result'].get('Native_call') not in stage_calls:
            raise ValueError('PLANNING_A_P1_NATIVE_CALL_NOT_IN_CONSUMED_LEDGER')
    ancestors={stage+'_'+kind:rows[stage][kind] for stage in ('A2','M2') for kind in ('result','acceptance')}
    return dict(record=record,state=state,ancestors=ancestors,consumed_budget=budget_record,
        verified_imported_stages=list(PLANNING_STAGES),Native_calls=0,model_builds=0)


def _verified_imports(plan,authorization,blockers):
    imports={};records=plan.get('planning_checkpoints',{})
    if not isinstance(records,dict):
        blockers.append('PLANNING_CHECKPOINT_MAPPING_REQUIRED');return imports
    for day,record in records.items():
        if day not in plan.get('dates',[]):
            blockers.append('PLANNING_IMPORT_DATE_NOT_REQUESTED:'+day);continue
        authorities=[a for a in authorization.get('authorized_date_cases',[]) if a.get('day')==day]
        try:
            if len(authorities)!=1:raise ValueError('EXACT_APPROVED_DATE_SOURCE_AUTHORITY_REQUIRED')
            imports[day]=require_planning_checkpoint(record,source_case=authorities[0])
        except (OSError,ValueError,TypeError,KeyError,RuntimeError) as exc:
            blockers.append('PLANNING_CHECKPOINT_NOT_CERTIFIED:'+day+':'+str(exc))
    return imports


def _resolved_actual_gate(plan,gate,blockers):
    answer=deepcopy(gate)
    policies=plan.get('Actual_policy_by_day',gate.get('actual_policy_by_day'))
    if 'Actual_policy_by_day' in plan and 'actual_policy_by_day' in gate and policies!=gate['actual_policy_by_day']:
        blockers.append('PLAN_AND_GATE_DATED_ACTUAL_POLICY_MAPPING_DRIFT')
    if policies is not None:
        if (not isinstance(policies,dict)
                or any(day not in policies or not isinstance(policies[day],dict) for day in plan.get('dates',[]))):
            blockers.append('EXACT_ACTUAL_POLICY_FOR_EVERY_REQUESTED_DAY_REQUIRED')
        else:answer['actual_policy_by_day']=deepcopy(policies)
    full=gate.get('full96_evidence');alias=gate.get('may01_full96_evidence')
    if full is not None and alias is not None and full!=alias:
        blockers.append('MAY01_FULL96_EVIDENCE_ALIASES_MUST_MATCH')
    if full is None and alias is not None:answer['full96_evidence']=alias
    return answer


def preflight(plan,authorization,gate,*,planning_only=False):
    """Report every blocker; an input inventory is not execution certification."""
    if plan.get('schema')=='TABLE_V_FOUR_ARM_PRODUCTION_PLAN_V1':
        if planning_only:raise ValueError('TABLE_V_FOUR_ARM_SCOPE_REQUIRED')
        from .table_v_campaign import preflight_table_v_plan
        return preflight_table_v_plan(plan,gate)
    from .release_production_budget import require_authorization
    blockers=[]
    try:require_authorization(authorization)
    except (PermissionError,ValueError,KeyError,TypeError) as exc:blockers.append(str(exc))
    if (authorization.get('approved_plan_sha') is not None
            and authorization['approved_plan_sha']!=digest(plan)):
        blockers.append('APPROVAL_BOUND_EXACT_PLAN_SHA_DRIFT')
    imports=_verified_imports(plan,authorization,blockers)
    if planning_only and imports:
        blockers.append('COMPLETED_PLANNING_IMPORT_REQUIRES_CONTINUATION_SCOPE')
    if (plan.get('schema')!='REAL_PRODUCTION_P1_CAMPAIGN_PLAN_V1' or plan.get('Worker')!=1
            or plan.get('Threads')!=1 or plan.get('P2_calls')!=0 or plan.get('automatic_start') is not False
            or not plan.get('dates') or len(set(plan['dates']))!=len(plan['dates'])
            or any(day not in may_dates() for day in plan.get('dates',[]))):
        blockers.append('SERIAL_EXPLICIT_P1_ONLY_MAY_DATE_PLAN_REQUIRED')
    needed=set() if planning_only else {'K48_M2'}
    remaining_dates=set(plan.get('dates',[]))-set(imports)
    if remaining_dates:needed.update(('M1','A2','M2'))
    if any(day!='2025-05-01' for day in remaining_dates):needed.add('A1')
    missing=needed-set(authorization.get('stage_caps_seconds',{}))
    if missing:blockers.append('REQUIRED_STAGE_BUDGET_CAPS_MISSING:'+','.join(sorted(missing)))
    approved_days={row.get('day') for row in authorization.get('allowed_stage_bindings',[])
        +authorization.get('authorized_date_cases',[])}
    if set(plan.get('dates',[]))-approved_days:
        blockers.append('ALL_REQUESTED_INDEPENDENT_DATES_REQUIRE_EXPLICIT_AUTHORITY')
    if authorization.get('policy_sha')!=plan.get('policy_sha') or not plan.get('policy_sha'):
        blockers.append('EXACT_APPROVED_PLANNING_POLICY_SHA_REQUIRED' if planning_only else 'EXACT_APPROVED_ACTUAL_POLICY_SHA_REQUIRED')
    if plan.get('policy_record') is not None:
        try:
            policy=_checked_document(plan['policy_record'])
            if (digest(policy)!=plan.get('policy_sha')
                    or authorization.get('policy_record')!=plan['policy_record']):
                blockers.append('APPROVED_POLICY_DOCUMENT_CONTENT_OR_RECORD_DRIFT')
        except (OSError,ValueError,TypeError,KeyError) as exc:
            blockers.append('APPROVED_POLICY_DOCUMENT_BYTES_NOT_VERIFIED:'+str(exc))
    if not planning_only:
        gate=_resolved_actual_gate(plan,gate,blockers)
        _physical_preflight(plan,authorization,gate,blockers,imports)
    if plan.get('source_snapshot')!=production_sources():blockers.append('PRODUCTION_SOURCE_SNAPSHOT_MISSING_OR_DRIFT')
    if not planning_only:
        actual=_actual_factory()
        if actual is None:blockers.append('MISSING_PRODUCTION_ACTUAL_FACTORY')
        else:
            supported=getattr(actual,'SUPPORTED_PRODUCTION_DAYS',('2025-05-01',))
            if any(day not in supported for day in plan.get('dates',[])):
                blockers.append('DATE_SPECIFIC_ACTUAL_HANDOFF_NOT_CERTIFIED_FOR_ALL_REQUESTED_DAYS')
        # Original K48's historical hardcoded packet cannot be silently adopted.
        if not callable(getattr(OriginalP1Stages,'execute_current_k48',None)):
            blockers.append('CURRENT_CASE_K48_INCLUSION_AND_EXECUTOR_NOT_CERTIFIED')
        if _needs_full96_launch(plan) and gate.get('May01_integrated_Full96_Fresh')!='PASS':
            blockers.append('MAY01_INTEGRATED_FULL96_BEFORE_MAY31_REQUIRED')
    return dict(status='READY_TO_REQUEST_EXPLICIT_EXECUTION' if not blockers else 'CAMPAIGN_BLOCKED_WITH_EXACT_REASONS',
        blockers=blockers,Native_calls=0,model_builds=0,Actual_runs=0,
        source_records=production_sources(),P2_calls=0,automatic_start=False,
        execution_scope='PLANNING_P1_ONLY' if planning_only else 'FULL_PRODUCTION_CAMPAIGN',
        required_stages=list(PLANNING_STAGES if planning_only else STAGES),
        verified_planning_import_dates=sorted(imports),
        Gate_contract=GATE_CONTRACT,ASOF_substep_diagnostic_is_global_gate=False,
        K48_current_case_Global_LB=None,K48_not_certified_does_not_block_planning=planning_only,
        static_wiring_is_execution_certificate=False)


def _physical_preflight(plan,authorization,gate,blockers,imports):
    # The user's physical Gate is the original 15-minute settled measurement.
    # Substep/ASOF diagnostics remain evidence and cannot veto this contract.
    if gate.get('Gate_contract')!=GATE_CONTRACT:
        blockers.append('ORIGINAL_SLOTTED_SETTLED_GATE_CONTRACT_REQUIRED')
    if gate.get('May01_16slot_GPU_QoS_Fresh')!='PASS':blockers.append('MAY01_CANARY_PHYSICAL_GATE_NOT_PASS')
    canary=gate.get('settled_source_case')
    if (not isinstance(canary,dict) or canary.get('day')!='2025-05-01'
            or not canary.get('source_sha') or not canary.get('source_identity')):
        blockers.append('CURRENT_D0_SETTLED_CANARY_SOURCE_CASE_BINDING_REQUIRED')
    if gate.get('future_information_leak_count')!=0:blockers.append('CAUSAL_CONTROLLER_GATE_REQUIRED')
    policies=gate.get('actual_policy_by_day',{})
    if not isinstance(policies,dict):policies={}
    actual_policy=policies.get('2025-05-01',gate.get('may01_actual_policy',gate.get('actual_policy')))
    if not isinstance(actual_policy,dict):blockers.append('EXPLICIT_CURRENT_ACTUAL_POLICY_REQUIRED')
    if 'Actual_policy' in plan and plan['Actual_policy']!=actual_policy:
        blockers.append('PLAN_AND_SETTLED_GATE_ACTUAL_POLICY_DRIFT')
    imported=imports.get('2025-05-01')
    if not imported and isinstance(canary,dict) and gate.get('planning_checkpoint'):
        try:imported=require_planning_checkpoint(gate['planning_checkpoint'],source_case=canary)
        except (OSError,ValueError,KeyError,TypeError,RuntimeError) as exc:
            blockers.append('MAY01_LAUNCH_PLANNING_CHECKPOINT_NOT_CERTIFIED:'+str(exc))
    if not imported or gate.get('planning_checkpoint')!=imported['record']:
        blockers.append('SETTLED_GATE_AND_IMPORTED_PLANNING_CHECKPOINT_MUST_MATCH')
    elif (not isinstance(canary,dict)
            or imported['state']['stages']['INPUT']['result']['identity']!=canary.get('source_identity')
            or imported['state']['stages']['INPUT']['result']['source_sha']!=canary.get('source_sha')):
        blockers.append('CURRENT_D0_SETTLED_CANARY_SOURCE_CASE_BINDING_REQUIRED')
    if gate.get('official_contract_authorized') is False:
        blockers.append('ORIGINAL_SETTLED_ACTUAL_CONTRACT_EXPLICITLY_REJECTED')
    evidence=gate.get('physical_evidence')
    if not isinstance(evidence,dict) or not evidence.get('path'):
        blockers.append('PHYSICAL_GATE_RAW_EVIDENCE_SHA_REQUIRED')
    else:
        try:
            if file_record(evidence['path'])!=evidence:
                blockers.append('PHYSICAL_GATE_RAW_BYTES_DRIFT')
            else:
                from .release_ac_contract import require_current_settled_evidence
                # Read the actual receipt/slot arrays and current A2/M2 FULL
                # ancestry. A caller's current-case header cannot relabel an
                # old PR223 PASS, nor turn a 16-slot receipt into Full96.
                if imported:
                    require_current_settled_evidence(evidence,source_case=canary,
                        ancestors=imported['ancestors'],slots=16,expected_actual_policy=actual_policy)
        except OSError:blockers.append('PHYSICAL_GATE_RAW_EVIDENCE_MISSING')
        except (ValueError,KeyError,TypeError,RuntimeError) as exc:
            blockers.append('PHYSICAL_GATE_RAW_BODY_NOT_CERTIFIED:'+str(exc))
    if _needs_full96_launch(plan):
        evidence96=gate.get('full96_evidence')
        if not isinstance(evidence96,dict):
            blockers.append('CURRENT_D0_FULL96_SETTLED_RAW_EVIDENCE_REQUIRED')
        elif imported:
            try:
                from .release_ac_contract import require_current_settled_evidence
                require_current_settled_evidence(evidence96,source_case=canary,
                    ancestors=imported['ancestors'],slots=96,expected_actual_policy=actual_policy)
            except (OSError,ValueError,KeyError,TypeError,RuntimeError) as exc:
                blockers.append('FULL96_SETTLED_RAW_BODY_NOT_CERTIFIED:'+str(exc))


def _validate_row(row,*,stage,day,parent_sha):
    if (row.get('status') not in TERMINAL or row.get('day')!=day or row.get('stage')!=stage
            or row.get('input_result_sha')!=parent_sha or row.get('P2_calls')!=0
            or row.get('result_sha')!=digest(row.get('result'))
            or row.get('acceptance') is not None and row.get('acceptance_sha')!=digest(row['acceptance'])):
        raise ValueError('PRODUCTION_STAGE_CHECKPOINT_PARENT_RESULT_OR_P2_DRIFT')
    for record in row.get('raw_records',[]):
        if file_record(record['path'])!=record:raise ValueError('PRODUCTION_STAGE_RAW_BYTES_DRIFT')
    return row


def _date_loop(*,dates,folder,identity,dispatch,restore=None,evidence_scope,stages=STAGES,close_day=None):
    """Internal engine. Public production fixes dispatch to _RealDispatcher."""
    if evidence_scope not in ('REAL_PRODUCTION','NAMED_CHECKPOINT_FIXTURE'):
        raise ValueError('EXPLICIT_EXECUTION_EVIDENCE_SCOPE_REQUIRED')
    root=Path(folder);root.mkdir(parents=True,exist_ok=True);reports=[]
    for day in dates:
        try:
            report=_execute_date(day=day,root=root,identity=identity,dispatch=dispatch,restore=restore,
                evidence_scope=evidence_scope,stages=stages)
            reports.append(report)
        finally:
            if close_day:close_day(day)
    return reports


def _execute_date(*,day,root,identity,dispatch,restore,evidence_scope,stages):
    path=root/day/'DATE_LEDGER.json'
    state=read(path) if path.exists() else dict(day=day,identity=identity,stages={},status='NOT_RUN',evidence_scope=evidence_scope)
    if state['identity']!=identity:raise ValueError('PRODUCTION_RESUME_SOURCE_PLAN_OR_AUTHORIZATION_DRIFT')
    prior=None;failed=False
    for stage in stages:
        parent_sha=None if prior is None else digest(prior['result'])
        old=state['stages'].get(stage)
        if old and old.get('executed'):
            try:
                _validate_row(old,stage=stage,day=day,parent_sha=parent_sha)
                if restore:restore(day,stage,old)
                prior=old;failed=old['status']!='FULL_PASS'
            except Exception as exc:
                state['status']='NOT_CERTIFIED';state['resume_error']=str(exc);failed=True
            if failed:break
            continue
        attempt=root/day/stage
        if attempt.exists():
            state['status']='NOT_CERTIFIED';state['interruption']='UNRECONCILED_STAGE_ATTEMPT:'+stage;failed=True;break
        attempt.mkdir(parents=True)
        _write(attempt/'ATTEMPT_STARTED.json',dict(day=day,stage=stage,input_result_sha=parent_sha,
            identity=identity,solver_success_not_assumed=True))
        began=perf_counter()
        try:
            answer=dispatch(day=day,stage=stage,previous=prior,output=attempt)
            row=dict(day=day,stage=stage,executed=True,input_result_sha=parent_sha,P2_calls=0,**answer)
            row['result_sha']=digest(row['result'])
            if row.get('acceptance') is not None:row['acceptance_sha']=digest(row['acceptance'])
            _validate_row(row,stage=stage,day=day,parent_sha=parent_sha)
        except Exception as exc:
            row=dict(day=day,stage=stage,executed=True,input_result_sha=parent_sha,P2_calls=0,
                status='INPUT_UNAVAILABLE' if stage=='INPUT' else 'NOT_CERTIFIED',
                result=dict(error_type=type(exc).__name__,error=str(exc),raw_preserved=True))
            row['result_sha']=digest(row['result'])
        row['stage_wall_seconds']=perf_counter()-began
        row['Native_and_build_times_are_nested_in_stage_wall']=True
        _write(attempt/'STAGE_RESULT.json',row)
        state['stages'][stage]=row;state['status']=row['status'];_write(path,state);prior=row
        if row['status']!='FULL_PASS':failed=True;break
    if failed:
        for stage in stages:
            if stage not in state['stages']:state['stages'][stage]=dict(executed=False,status='NOT_RUN',reason='UPSTREAM_STAGE_NOT_FULL_ACCEPTED')
    else:state['status']='FULL_PASS'
    _write(path,state)
    return dict(day=day,status=state['status'],ledger=file_record(path))


def _build_admission(budget,*,stage,case_sha=None):
    from .partial_canary import resource_snapshot
    state=resource_snapshot();memory=state['memory']
    if (memory['AvailableMBytes']<8192 or memory['PercentCommittedBytesInUse']>=75
            or budget.worker_lock.exists()):raise RuntimeError('PRODUCTION_PREBUILD_RAM_OR_WORKER_GATE')
    return dict(status='PASS',operation='D0_A_NATIVE0_BUILD' if stage.startswith('A') else 'CURRENT_M_NATIVE0_BUILD',
        stage=stage,case_sha=case_sha,concurrent_heavy_solver=False,resource=state)


class _RealDispatcher:
    def __init__(self,plan,budget,gate):
        self.plan,self.budget,self.gate=plan,budget,gate
        self.contexts={};self.engines={};self.results={};self.cases={}

    def _context(self,day):return self.contexts[day],self.engines[day]

    def release_day(self,day):
        for key in [key for key in self.cases if key[0]==day]:self.cases.pop(key,None)
        for values in (self.contexts,self.engines,self.results):values.pop(day,None)
        import gc
        gc.collect()

    def _day_gate(self,day):
        errors=[];answer=_resolved_actual_gate(self.plan,self.gate,errors)
        if errors:raise ValueError(';'.join(errors))
        policies=answer.get('actual_policy_by_day',{})
        may01=policies.get('2025-05-01',answer.get('may01_actual_policy',answer.get('actual_policy')))
        answer['may01_actual_policy']=deepcopy(may01)
        if policies:
            if day not in policies:raise ValueError('CURRENT_DAY_EXACT_ACTUAL_POLICY_REQUIRED')
            answer['actual_policy']=deepcopy(policies[day])
        evidence_by_day=answer.get('physical_evidence_by_day',{})
        if day in evidence_by_day:answer['physical_evidence']=deepcopy(evidence_by_day[day])
        return answer

    def __call__(self,*,day,stage,previous,output):
        from .release_date_case import load_date_case
        if stage=='INPUT':
            source=Path(self.plan['compiled_case_root'])/day/'CASE'
            context=load_date_case(day,source,call_cap=max(self.budget.authorization['stage_caps_seconds'].values()))
            self.contexts[day]=context;self.engines[day]=OriginalP1Stages(context,self.budget)
            manifest=context['manifest']
            result=dict(day=day,identity=manifest['identity'],source_sha=manifest['source_sha'],
                manifest_sha=manifest['manifest_sha'],initial_state_sha=manifest['identity']['initial_state_sha'],
                input_sha=context['input_audit']['a_input_sha'],
                independent_D0=True,prior_day_carry_imported=False,source_folder=str(source))
            answer=dict(status='FULL_PASS',result=result,raw_records=[file_record(source/'D0_CASE_MANIFEST.json')])
        else:
            context,engine=self._context(day);cap=self.budget.authorization['stage_caps_seconds'].get(stage)
            if stage=='A1':
                if day=='2025-05-01':result,receipt=engine.imported_a1()
                else:
                    case=engine.prepare_a1(output/'ORIGINAL_A')
                    self.budget.bind_input_case(day=day,stage_case_sha=case.case_sha,manifest=context['manifest'])
                    result,receipt=engine.execute_a1(case,build_admission=_build_admission(self.budget,stage='A1',case_sha=case.case_sha),cap=cap)
                from .release_p1_acceptance import saved_a1
                raw=saved_a1()['immutable_records'] if day=='2025-05-01' else [file_record(case.output/name)
                    for name in ('P1_ONLY_RESULT.json','P1_ONLY_POINT.npz') if (case.output/name).exists()]
                answer=dict(status='FULL_PASS' if receipt else result.get('status','NOT_CERTIFIED'),
                    result=result,acceptance=receipt,raw_records=raw)
            elif stage in ('M1','M2'):
                parent=previous['result'];accepted=previous['acceptance']
                cached=self.plan.get('prepared_M1_packet') if day=='2025-05-01' and stage=='M1' else None
                if cached:
                    _build_admission(self.budget,stage=stage)
                    case=engine.adopt_prepared_m(cached,parent,accepted,stage=stage)
                    packet_record=cached
                else:
                    with self.budget.capture_native_methods():
                        case=engine.prepare_m(stage,parent,accepted,output/'ORIGINAL_M',
                            build_admission=_build_admission(self.budget,stage=stage))
                    packet=output/'CURRENT_M_CASE.pkl'
                    with packet.open('xb') as stream:pickle.dump(case,stream,pickle.HIGHEST_PROTOCOL)
                    packet_record=file_record(packet)
                self.cases[day,stage]=case
                self.budget.bind_accepted_parent(day=day,stage=stage,stage_case_sha=case.case_sha,
                    source_sha=engine.source_sha,parent_result=parent,parent_acceptance=accepted,source_identity=engine.identity)
                result,receipt,_=engine.execute_m(stage,case,parent,accepted,stage_total_cap=cap)
                raw=[packet_record]
                for entry in result.get('incumbent_registry',[]):
                    raw.extend([entry['raw'],file_record(Path(entry['raw']['path']).with_suffix('.REPLAY.json'))])
                answer=dict(status='FULL_PASS' if receipt else result.get('status','NOT_CERTIFIED'),
                    result=result,acceptance=receipt,raw_records=raw,
                    prepared_case=packet_record)
            elif stage=='A2':
                case=engine.prepare_a2(previous['result'],previous['acceptance'],output/'ORIGINAL_A')
                self.budget.bind_accepted_parent(day=day,stage='A2',stage_case_sha=case.case_sha,source_sha=engine.source_sha,
                    parent_result=previous['result'],parent_acceptance=previous['acceptance'],source_identity=engine.identity)
                result,receipt=engine.execute_a2(case,previous['result'],previous['acceptance'],
                    build_admission=_build_admission(self.budget,stage='A2',case_sha=case.case_sha),cap=cap)
                if receipt:
                    self.cases.pop((day,'M1'),None)
                    import gc
                    gc.collect()
                raw=[file_record(case.output/name) for name in ('P1_ONLY_RESULT.json','P1_ONLY_POINT.npz') if (case.output/name).exists()]
                answer=dict(status='FULL_PASS' if receipt else result.get('status','NOT_CERTIFIED'),
                    result=result,acceptance=receipt,raw_records=raw)
            elif stage=='K48_M2':
                # No such method is admitted until its current-case inclusion
                # and actual native-budget path have been implemented/reviewed.
                function=getattr(engine,'execute_current_k48',None)
                if function is None:raise RuntimeError('CURRENT_CASE_K48_INCLUSION_AND_EXECUTOR_NOT_CERTIFIED')
                answer=function(self.cases[day,'M2'],previous,output=output,cap=cap)
            elif stage in ('ACTUAL','FRESH_AC'):
                factory=_actual_factory()
                if factory is None:raise RuntimeError('MISSING_PRODUCTION_ACTUAL_FACTORY')
                a=self.results[day]['A2'];m=self.results[day]['M2']
                local_gate=self._day_gate(day)
                if stage=='ACTUAL':
                    answer=factory.run_production_actual(context=context,a_result=a['result'],a_acceptance=a['acceptance'],
                        m_result=m['result'],m_acceptance=m['acceptance'],output=output,slots=96,gate=local_gate)
                else:
                    answer=factory.run_production_fresh(context=context,actual_result=previous['result'],
                        m_result=m['result'],m_acceptance=m['acceptance'],output=output,slots=96,gate=local_gate)
            elif stage=='AUDIT':
                if previous['status']!='FULL_PASS':raise ValueError('FRESH_FULL_PASS_REQUIRED')
                answer=dict(status='FULL_PASS',result=dict(day=day,all_original_stage_FULL=True,P2_calls=0,
                    independent_day=True,historical_UB_LB_transferred=False))
            else:raise ValueError('UNKNOWN_ORIGINAL_STAGE')
        self.results.setdefault(day,{})[stage]=answer
        return answer

    def restore(self,day,stage,row):
        if stage=='INPUT':
            self(day=day,stage='INPUT',previous=None,output=Path(row['result']['source_folder']))
        else:
            self.results.setdefault(day,{})[stage]={k:v for k,v in row.items() if k not in ('executed','result_sha','acceptance_sha')}
            if stage in ('A1','A2','M1','M2'):
                context,engine=self._context(day)
                require_production_acceptance(row['acceptance'],stage=stage,identity=context['manifest']['identity'],result=row['result'])
                if stage in ('M1','M2'):
                    parent=self.results[day]['A1' if stage=='M1' else 'A2']
                    _build_admission(self.budget,stage=stage)
                    case=engine.adopt_prepared_m(row['prepared_case'],parent['result'],parent['acceptance'],stage=stage)
                    # Re-establish only the exact issuance/output anchor state.
                    rebound=context['bind_m_result'](row['result'])
                    if digest(rebound)!=digest(row['result']):raise ValueError('RESUME_M_RESULT_BINDING_DRIFT')
                    self.cases[day,stage]=case
                elif stage=='A2':
                    # Only M2 is needed by final K48/Actual. Its verified M1
                    # issuance metadata remains in the original factory.
                    self.cases.pop((day,'M1'),None)
                    import gc
                    gc.collect()


def run_production(plan,*,authorization,gate,folder,budget_ledger,backend='ORIGINAL',**injected):
    began=perf_counter()
    production_backend(backend)
    if injected:raise ValueError('PRODUCTION_INJECTED_OR_DUMMY_EXECUTORS_FORBIDDEN')
    if plan.get('schema')=='TABLE_V_FOUR_ARM_PRODUCTION_PLAN_V1':
        from .table_v_campaign import run_table_v_production
        return run_table_v_production(plan,authorization=authorization,gate=gate,folder=folder,budget_ledger=budget_ledger)
    readiness=preflight(plan,authorization,gate)
    if readiness['blockers']:raise PermissionError(';'.join(readiness['blockers']))
    result=_run_real(plan,authorization=authorization,gate=gate,folder=folder,budget_ledger=budget_ledger,stages=STAGES)
    return dict(result,total_invocation_wall_seconds=perf_counter()-began,preflight_and_restoration_included=True,
        Native_build_and_stage_times_are_nested=True)


def run_planning_p1(plan,*,authorization,folder,budget_ledger,backend='ORIGINAL',**injected):
    """Run only A1->M1->A2->M2 after a new explicit Native approval.

    The settled canary needs the resulting M2 plan. It cannot be a prerequisite
    for generating that plan. This path never calls Actual, Fresh, or K48.
    """
    if plan.get('schema')=='TABLE_V_FOUR_ARM_PRODUCTION_PLAN_V1':
        raise PermissionError('TABLE_V_REQUIRES_FULL_ARM_PRODUCTION_LAUNCH_GATE')
    began=perf_counter();production_backend(backend)
    if injected:raise ValueError('PRODUCTION_INJECTED_OR_DUMMY_EXECUTORS_FORBIDDEN')
    readiness=preflight(plan,authorization,{},planning_only=True)
    if readiness['blockers']:raise PermissionError(';'.join(readiness['blockers']))
    result=_run_real(plan,authorization=authorization,gate={},folder=folder,budget_ledger=budget_ledger,stages=PLANNING_STAGES)
    return dict(result,total_invocation_wall_seconds=perf_counter()-began,preflight_and_restoration_included=True,
        Native_build_and_stage_times_are_nested=True)


def _run_real(plan,*,authorization,gate,folder,budget_ledger,stages):
    from .release_production_budget import ReleaseProductionBudget
    errors=[];imports=_verified_imports(plan,authorization,errors)
    if errors:raise PermissionError(';'.join(errors))
    historical=[BASE/'UNIFIED_NATIVE_RUNTIME_LEDGER.json',
        BASE/'RELEASE_RECOVERY_20261015/RC01/A1_P1_120/SEPARATE_NATIVE_LEDGER_180.json']
    for proof in imports.values():
        path=Path(proof['consumed_budget']['path'])
        if path not in historical:historical.append(path)
    if stages==STAGES and gate.get('planning_checkpoint') and gate.get('settled_source_case'):
        launch=require_planning_checkpoint(gate['planning_checkpoint'],source_case=gate['settled_source_case'])
        path=Path(launch['consumed_budget']['path'])
        if path not in historical:historical.append(path)
    budget=ReleaseProductionBudget(budget_ledger,authorization=authorization,historical_ledgers=historical)
    identity=dict(plan_sha=digest(plan),authorization_sha=digest(authorization),gate_sha=digest(gate),
        production_sources=production_sources(),historical_read_only=[file_record(p) for p in historical],
        required_stages=list(stages),native_budget_ledger_path=str(Path(budget_ledger).resolve()))
    for day,proof in imports.items():
        _seed_planning_import(folder,day,proof,identity)
    dispatcher=_RealDispatcher(plan,budget,gate)
    reports=_date_loop(dates=plan['dates'],folder=folder,identity=identity,dispatch=dispatcher,
        restore=dispatcher.restore,evidence_scope='REAL_PRODUCTION',stages=stages,close_day=dispatcher.release_day)
    if any(file_record(r['path'])!=r for r in identity['production_sources']+identity['historical_read_only']):
        raise ValueError('PRODUCTION_EXECUTED_SOURCE_OR_READ_ONLY_NATIVE_LEDGER_DRIFT')
    # Planning and a future K48/Actual run use different approvals/ledgers.
    # Pin the final consumed planning ledger after all dates stop mutating it.
    completed_budget=file_record(budget.path)
    for report in reports:
        path=Path(report['ledger']['path']);state=read(path)
        state['completed_native_budget']=completed_budget
        _write(path,state);report['ledger']=file_record(path)
    return dict(status='EXECUTED_RECORDED_DATE_STATUSES',dates=reports,P2_calls=0,Worker=1,Threads=1,
        execution_scope='PLANNING_P1_ONLY' if stages==PLANNING_STAGES else 'FULL_PRODUCTION_CAMPAIGN',
        K48_current_case_Global_LB=None,
        Actual96_and_Fresh_certified=stages==STAGES and all(r['status']=='FULL_PASS' for r in reports))


def _seed_planning_import(folder,day,proof,identity):
    path=Path(folder)/day/'DATE_LEDGER.json'
    if path.exists():return
    rows={stage:deepcopy(proof['state']['stages'][stage]) for stage in PLANNING_STAGES}
    for row in rows.values():
        row['imported_from_planning_checkpoint']=proof['record']
        row['Native_calls_this_import']=0
    _write(path,dict(day=day,identity=identity,stages=rows,status='FULL_PASS',evidence_scope='REAL_PRODUCTION',
        imported_planning_checkpoint=proof['record'],imported_planning_consumed_budget=proof['consumed_budget'],
        imported_planning_Native_calls=0))


def fixture_checkpoint_loop(*,dates,folder,dispatch,identity=None,restore=None,evidence_scope,planning_only=False,close_day=None):
    if evidence_scope!='NAMED_CHECKPOINT_FIXTURE':raise ValueError('DUMMY_ONLY_NAMED_FIXTURE_NEVER_PRODUCTION')
    return _date_loop(dates=dates,folder=folder,identity=identity or {'fixture':True},dispatch=dispatch,
        restore=restore,evidence_scope=evidence_scope,stages=PLANNING_STAGES if planning_only else STAGES,close_day=close_day)
