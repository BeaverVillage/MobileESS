"""Current Table V fixed-AIDC adapter to the unchanged PR222 MESS engine.

Reference is an explicit, audited schedule, not a fabricated A1 optimization.
Preparation constructs the original model and must be admitted by the supervisor.
Only execute() enters the separately authorized, arm-bound native budget.
"""
from copy import deepcopy
import math
from pathlib import Path

import numpy as np

from .a_engine import digest
from .coordinator import _full_m
from .m_engine import file_record, vector_sha, _write
from .release_p1_acceptance import prohibit_p2, require_acceptance
from .release_p1_production import StageSolveBridge


AIDC_KEYS = ('selected_jobs', 'AIDC_P_by_site', 'AIDC_Q_by_site',
             'CC4_service', 'CC4_carryout', 'anonymous_resource_envelope')
M_ACCEPTANCE_SCHEMA = 'TABLE_V_M_P1_FULL_ACCEPTANCE_V1'
REFERENCE_SCHEMA = 'TABLE_V_CAUSAL_REFERENCE_ACCEPTANCE_V1'


def require_aidc_anchor(result, sites):
    if any(key not in result for key in AIDC_KEYS):
        raise ValueError('TABLE_V_COMPLETE_AIDC_AND_CC4_REQUIRED')
    if result.get('aidc_anchor') != digest({key: result[key] for key in AIDC_KEYS}):
        raise ValueError('TABLE_V_AIDC_ANCHOR_DRIFT')
    sites = list(map(str, sites))
    if len(sites) != 12 or len(set(sites)) != 12:
        raise ValueError('TABLE_V_TWELVE_AIDC_SITES_REQUIRED')
    for key in ('AIDC_P_by_site', 'AIDC_Q_by_site'):
        if set(result[key]) != set(sites):
            raise ValueError('TABLE_V_AIDC_PQ_SITE_AXIS_DRIFT')
        try:
            values = np.asarray([result[key][site] for site in sites], dtype=float)
        except (ValueError, TypeError) as error:
            raise ValueError('TABLE_V_AIDC_PQ_96_SLOT_AXIS_DRIFT') from error
        if values.shape != (12, 96) or not np.isfinite(values).all():
            raise ValueError('TABLE_V_AIDC_PQ_96_SLOT_AXIS_DRIFT')
    return result['aidc_anchor']


def require_parent(context, arm, stage, result, acceptance):
    """Verify either real optimized A or a separate Reference authority."""
    manifest = context['manifest']
    require_aidc_anchor(result, sorted(context['data'][0]['capacities']))
    prohibit_p2(result)
    if arm == 'B2' and stage == 'M1':
        if (acceptance.get('schema') != REFERENCE_SCHEMA
                or acceptance.get('status') != 'REFERENCE_VALIDATED'
                or acceptance.get('source_identity') != manifest['identity']
                or acceptance.get('source_sha') != manifest['source_sha']
                or acceptance.get('result_sha') != digest(result)
                or acceptance.get('AIDC_anchor') != result['aidc_anchor']
                or acceptance.get('reference_service_obligations_validated') is not True
                or acceptance.get('FULL_optimization_claimed') is not False
                or acceptance.get('P2_calls') != 0
                or acceptance.get('acceptance_sha') != digest({k: v for k, v in acceptance.items()
                                                              if k != 'acceptance_sha'})
                or result.get('reference_schedule_only') is not True
                or result.get('reference_FULL_optimization_not_claimed') is not True):
            raise ValueError('TABLE_V_B2_REAL_REFERENCE_CERTIFICATE_REQUIRED')
        # Recompute the producer's causal/service/source proof; a header and a
        # self hash alone do not authorize an arbitrary Reference schedule.
        from .table_v_reference import require_reference_acceptance
        require_reference_acceptance(acceptance, identity=manifest['identity'], result=result)
    elif arm == 'B3' and stage in ('M1', 'M2'):
        require_acceptance(acceptance, stage='A1' if stage == 'M1' else 'A2',
                           source_identity=manifest['identity'], result=result)
        if (acceptance.get('source_sha') != manifest['source_sha']
                or acceptance.get('fixture') or acceptance.get('evidence_scope') != 'REAL_PRODUCTION'
                or result.get('FULL_feasible') is not True
                or result.get('FULL_point_replay', {}).get('PASS') is not True):
            raise ValueError('TABLE_V_B3_CURRENT_FULL_FLEX_A_PARENT_REQUIRED')
    else:
        raise ValueError('TABLE_V_ONLY_B2_M1_AND_B3_M1_M2_ALLOWED')
    return acceptance


def payload_for_m(context, arm, stage, aidc, acceptance):
    require_parent(context, arm, stage, aidc, acceptance)
    manifest = context['manifest']
    sites = sorted(context['data'][0]['capacities'])
    planning = dict(sites=sites,
        PCC_P_kw=np.asarray([aidc['AIDC_P_by_site'][s] for s in sites], float).T.tolist(),
        PCC_Q_kvar=np.asarray([aidc['AIDC_Q_by_site'][s] for s in sites], float).T.tolist(),
        complete_AIDC_anchor=aidc['aidc_anchor'], CC4_service=aidc['CC4_service'],
        CC4_carryout=aidc['CC4_carryout'], anonymous_resource_envelope=aidc['anonymous_resource_envelope'])
    return dict(bundle=context['data'][0], planning=planning,
        identity=dict(PASS=True, day='2025-05-01', arm=arm, stage=stage,
            AIDC_anchor=aidc['aidc_anchor'], QoS_SHA=context['backlog']['contract_sha'],
            parent_case_sha=manifest['identity']['case_sha'], source_sha=manifest['source_sha'],
            parent_acceptance_sha=acceptance['acceptance_sha'], parent_result_sha=digest(aidc),
            reference_schedule_only=arm == 'B2'))


def require_build_admission(admission, *, arm, stage):
    if (admission.get('status') != 'PASS' or admission.get('arm') != arm
            or admission.get('stage') != stage
            or admission.get('operation') != 'CURRENT_M_NATIVE0_BUILD'
            or admission.get('concurrent_heavy_solver') is not False
            or admission.get('supervisor_serial_window') is not True):
        raise ValueError('TABLE_V_SUPERVISOR_SERIAL_M_BUILD_ADMISSION_REQUIRED')


def require_m_acceptance(receipt, *, result=None, identity=None, arm=None, stage=None):
    if (receipt.get('schema') != M_ACCEPTANCE_SCHEMA or receipt.get('status') != 'FULL_PASS'
            or receipt.get('P2_calls') != 0 or receipt.get('P2_optimized') is not False
            or receipt.get('acceptance_sha') != digest({k: v for k, v in receipt.items() if k != 'acceptance_sha'})
            or result is not None and receipt.get('result_sha') != digest(result)
            or identity is not None and receipt.get('source_identity') != identity
            or arm is not None and receipt.get('arm') != arm
            or stage is not None and receipt.get('stage') != stage):
        raise ValueError('TABLE_V_CURRENT_M_FULL_ACCEPTANCE_REQUIRED')
    if receipt.get('fixture') or receipt.get('evidence_scope') != 'REAL_PRODUCTION':
        raise ValueError('TABLE_V_PRODUCTION_M_FIXTURE_FORBIDDEN')
    full = receipt.get('Original_FULL', {})
    physical = full.get('original_matrix_and_96_slot_physical_replay', {})
    raw, replay_record = receipt.get('raw_point', {}), receipt.get('raw_replay', {})
    if (full.get('PASS') is not True
            or full.get('strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact') is not True
            or physical.get('PASS') is not True or physical.get('case_sha') != receipt['stage_case_sha']
            or not raw.get('path') or not replay_record.get('path')
            or file_record(raw['path']) != raw or file_record(replay_record['path']) != replay_record
            or full.get('point_path') != raw['path']
            or full.get('point_file_sha256') != raw['sha256']):
        raise ValueError('TABLE_V_CURRENT_LITERAL_RAW_FULL_REPLAY_BYTES_REQUIRED')
    import json
    if json.loads(Path(replay_record['path']).read_text(encoding='utf-8')) != full:
        raise ValueError('TABLE_V_FULL_REPLAY_BODY_DIFFERS_FROM_SOURCE_FILE')
    with np.load(raw['path'], allow_pickle=False) as z:
        if z.files != ['point']:
            raise ValueError('TABLE_V_RAW_POINT_PACKET_AXIS_DRIFT')
        point = z['point']
        if (point.dtype != np.dtype('float64') or point.ndim != 1 or not np.isfinite(point).all()
                or vector_sha(point) != full.get('point_vector_sha256')):
            raise ValueError('TABLE_V_CURRENT_RAW_POINT_VECTOR_DRIFT')
    if result is not None:
        prohibit_p2(result)
        plan = _full_m(result)
        if (result.get('case_sha') != receipt['stage_case_sha'] or result.get('arm') != receipt['arm']
                or result.get('stage') != receipt['stage']
                or result.get('D0_source_identity') != receipt['source_identity']
                or result.get('D0_fixed_AIDC_anchor') != receipt['AIDC_anchor']
                or result.get('binding', {}).get('aidc_anchor') != receipt['AIDC_anchor']
                or plan.get('case_sha') != receipt['stage_case_sha'] or plan['plan_sha'] != receipt['MESS_anchor']
                or plan.get('point_vector_sha256') != full.get('point_vector_sha256')):
            raise ValueError('TABLE_V_M_RESULT_FULL_PLAN_SOURCE_CASE_ANCHOR_DRIFT')
    return receipt


def require_full_plan_axes(case, plan):
    sites, units = set(map(str, case.graph[0])), set(map(str, case.graph[1]))
    if len(sites) != 24 or len(units) != 4:
        raise ValueError('TABLE_V_ORIGINAL_FOUR_MESS_24_SITES_REQUIRED')
    for key in ('P_by_site', 'Q_by_site'):
        if set(plan.get(key, {})) != sites:
            raise ValueError('TABLE_V_ALL_IDC_AND_STA_PQ_HANDOFF_REQUIRED')
        values = np.asarray([plan[key][site] for site in sorted(sites)], float)
        if values.shape != (24, 96) or not np.isfinite(values).all():
            raise ValueError('TABLE_V_ALL_MESS_SITE_96_SLOT_PQ_REQUIRED')
    for key, length in (('SOC', 97), ('Mode', 96)):
        if set(plan.get(key, {})) != units:
            raise ValueError('TABLE_V_FOUR_UNIT_SOC_MODE_HANDOFF_REQUIRED')
        values = np.asarray([plan[key][unit] for unit in sorted(units)], float)
        if values.shape != (4, length) or not np.isfinite(values).all():
            raise ValueError('TABLE_V_UNIT_SOC_MODE_TIME_AXIS_DRIFT')
    if set(plan.get('routes', {})) != units:
        raise ValueError('TABLE_V_FOUR_UNIT_COMPLETE_ROUTE_HANDOFF_REQUIRED')


def require_real_budget(budget, kind):
    from .table_v_budget import TableVStageBudget
    methods = ('arm_context', 'bind_table_v_case', 'phase', 'solve', 'capture_native_methods',
               'used', 'remaining', 'record_external', 'cost')
    if (type(budget) is not TableVStageBudget
            or getattr(budget, 'authorization', {}).get('budget_kind') != kind
            or any(getattr(getattr(budget, name, None), '__func__', None) is not getattr(TableVStageBudget, name)
                   for name in methods)):
        raise ValueError('TABLE_V_REAL_SUPERVISOR_BUDGET_REQUIRED_NO_FIXTURE_OR_OVERRIDE')


class TableVMessStages:
    """A source-bound sibling factory; no Basic cache or historical point IO."""
    def __init__(self, context, budget):
        from .table_v_flex_planning import require_flex_context
        require_flex_context(context)
        require_real_budget(budget, 'PLANNING_NATIVE')
        self.context, self.budget = context, budget
        self.manifest = deepcopy(context['manifest'])
        self.issued = {}

    def _context(self):
        from .table_v_flex_planning import require_flex_context
        require_flex_context(self.context)
        require_real_budget(self.budget, 'PLANNING_NATIVE')
        if self.context['manifest'] != self.manifest:
            raise ValueError('TABLE_V_CONTEXT_CHANGED_AFTER_BINDING')

    def prepare(self, arm, stage, aidc, parent_acceptance, output, *, build_admission, progress=None):
        self._context()
        require_build_admission(build_admission, arm=arm, stage=stage)
        payload = payload_for_m(self.context, arm, stage, aidc, parent_acceptance)
        from v42_may_campaign_native90.m_model import build_case
        from .m_candidates import generate
        from .m_engine import export_plan
        physical = self.context['materialize_physical']()['physical']
        if (Path(output) / 'SCIENTIFIC_CASE_IDENTITY.json').exists():
            raise ValueError('TABLE_V_M_PREPARATION_EXISTS_DO_NOT_REBUILD_OR_OVERWRITE')
        with self.budget.capture_native_methods():
            case = build_case(payload, dict(day='2025-05-01', arm=arm, stage=stage, output=str(output)),
                              progress=progress, integration_context=physical)
        identity = self.manifest['identity']
        case.identity.update(arm=arm, stage=stage, aidc_anchor=aidc['aidc_anchor'],
            qos_sha=self.context['backlog']['contract_sha'],
            science_sha=identity.get('science_sha'), D0_parent_case_sha=identity['case_sha'],
            D0_source_sha=self.manifest['source_sha'],
            physical_sha=self.manifest['physical_sha'], time_axis_sha=self.manifest['time_axis_sha'],
            cc4_sha=identity.get('cc4_sha'), runtime_sha=identity.get('runtime_sha'),
            table_v_parent_acceptance_sha=parent_acceptance['acceptance_sha'],
            table_v_parent_result_sha=digest(aidc), reference_schedule_only=arm == 'B2')
        case.case_sha = digest(case.identity)
        case.candidate_generator, case.plan_exporter = generate, export_plan
        case.mess_stage_budget_seconds = 0.
        self.issued[case.case_sha] = dict(arm=arm, stage=stage, AIDC_anchor=aidc['aidc_anchor'],
            parent_acceptance_sha=parent_acceptance['acceptance_sha'], parent_result_sha=digest(aidc))
        _write(Path(output) / 'TABLE_V_FIXED_AIDC_BINDING.json', payload['identity'])
        _write(Path(output) / 'SCIENTIFIC_CASE_IDENTITY.json', dict(case_sha=case.case_sha, **case.identity))
        return case

    def execute(self, arm, stage, case, aidc, parent_acceptance, *, stage_total_cap=1800.,
                initial_point=None, incumbent_registry=()):
        self._context()
        require_parent(self.context, arm, stage, aidc, parent_acceptance)
        from .m_engine import optimize_mess, strict_full, export_plan, _native_joint
        from .m_candidates import generate
        from v42_may_campaign_native90.m_model import verify_case
        expected = dict(arm=arm, stage=stage, AIDC_anchor=aidc['aidc_anchor'],
            parent_acceptance_sha=parent_acceptance['acceptance_sha'], parent_result_sha=digest(aidc))
        if (self.issued.get(case.case_sha) != expected
                or digest(case.identity) != case.case_sha
                or case.identity.get('arm') != arm or case.identity.get('stage') != stage
                or case.identity.get('aidc_anchor') != aidc['aidc_anchor']
                or case.identity.get('D0_source_sha') != self.manifest['source_sha']
                or case.candidate_generator is not generate or case.plan_exporter is not export_plan
                or getattr(case, 'joint_solver', _native_joint) is not _native_joint
                or getattr(case, 'strict_validator', strict_full) is not strict_full
                or getattr(case, 'cold_initializer', None) is not None
                or hasattr(case, 'candidate_pools')
                or not math.isfinite(float(stage_total_cap)) or not 0 < stage_total_cap <= 1800):
            raise ValueError('TABLE_V_UNCHANGED_OFFICIAL_M_ENGINE_AND_CURRENT_CASE_REQUIRED')
        verify_case(case)
        case.mess_stage_budget_seconds = float(stage_total_cap)
        bridge = StageSolveBridge(self.budget, stage)
        with self.budget.arm_context(arm):
            with self.budget.phase(stage, case.case_sha, self.manifest['source_sha'], digest(aidc), day='2025-05-01'):
                with self.budget.capture_native_methods():
                    result, point = optimize_mess(case, initial_point, incumbent_registry, bridge)
        prohibit_p2(result)
        result['release_build_costs'] = bridge.build_costs
        if result.get('FULL_validated') is not True:
            return result, None, point
        result = deepcopy(result)
        plan = _full_m(result)
        require_full_plan_axes(case, plan)
        if plan.get('case_sha') != case.case_sha:
            raise ValueError('TABLE_V_M_FULL_PLAN_CASE_DRIFT')
        result.update(D0_source_identity=deepcopy(self.manifest['identity']),
            D0_fixed_AIDC_anchor=aidc['aidc_anchor'], table_v_parent_acceptance_sha=parent_acceptance['acceptance_sha'])
        bank = [r for r in result['incumbent_registry'] if r['origin'] == 'CASE_FULL_BANK_GLOBAL']
        if len(bank) != 1 or file_record(bank[0]['raw']['path']) != bank[0]['raw']:
            raise ValueError('TABLE_V_CURRENT_RAW_FULL_INCUMBENT_BYTES_REQUIRED')
        import json
        certificate = json.loads(Path(bank[0]['raw']['path']).with_suffix('.REPLAY.json').read_text(encoding='utf-8'))
        if (certificate.get('PASS') is not True
                or certificate.get('strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact') is not True
                or certificate.get('original_matrix_and_96_slot_physical_replay', {}).get('case_sha') != case.case_sha
                or certificate.get('original_matrix_and_96_slot_physical_replay', {}).get('PASS') is not True):
            raise ValueError('TABLE_V_ORIGINAL_FULL_PHYSICAL_REPLAY_REQUIRED')
        receipt = dict(schema=M_ACCEPTANCE_SCHEMA, status='FULL_PASS', arm=arm, stage=stage,
            stage_case_sha=case.case_sha, source_identity=deepcopy(self.manifest['identity']),
            source_sha=self.manifest['source_sha'], AIDC_anchor=aidc['aidc_anchor'], MESS_anchor=plan['plan_sha'],
            result_sha=digest(result), parent_acceptance_sha=parent_acceptance['acceptance_sha'],
            Original_FULL=certificate, P1_only=True, P2_calls=0, P2_optimized=False,
            raw_point=bank[0]['raw'], raw_replay=file_record(Path(bank[0]['raw']['path']).with_suffix('.REPLAY.json')),
            UB_algorithm='ADAPTIVE_BEAM_4_JOINT_ORIGINAL_FULL_INCUMBENT_REGISTRY',
            restricted_pool_ObjBound_is_Global_LB=False, K48_Global_LB=None,
            physical_evaluation_allowed=True, global_optimality_status='K48_NOT_RUN',
            evidence_scope='REAL_PRODUCTION', fixture=False)
        receipt['acceptance_sha'] = digest(receipt)
        require_m_acceptance(receipt, result=result, identity=self.manifest['identity'], arm=arm, stage=stage)
        _write(case.output / 'TABLE_V_M_RESULT.json', result)
        _write(case.output / 'TABLE_V_M_ACCEPTANCE.json', receipt)
        return result, receipt, point

    def execute_k48(self, arm, stage, case, m_result, m_acceptance, point, *,
                    k48_budget, output, build_admission):
        """Separate current-case K48 ledger; never consumes the M UB allowance."""
        self._context()
        from .table_v_k48 import run_current_k48
        require_real_budget(k48_budget, 'K48_SEPARATE')
        if (k48_budget is self.budget
                or stage not in ('M1', 'M2')
                or build_admission.get('status') != 'PASS'
                or build_admission.get('operation') != 'CURRENT_K48_NATIVE_BUILD'
                or build_admission.get('arm') != arm or build_admission.get('stage') != stage
                or build_admission.get('supervisor_serial_window') is not True
                or build_admission.get('concurrent_heavy_solver') is not False):
            raise ValueError('TABLE_V_SEPARATE_K48_APPROVAL_AND_SERIAL_RAM_ADMISSION_REQUIRED')
        require_m_acceptance(m_acceptance, result=m_result, identity=self.manifest['identity'], arm=arm, stage=stage)
        if (m_acceptance['stage_case_sha'] != case.case_sha
                or case.identity['arm'] != arm or case.identity['stage'] != stage
                or case.identity['aidc_anchor'] != m_acceptance['AIDC_anchor']):
            raise ValueError('TABLE_V_K48_SAME_CURRENT_FULL_M_CASE_REQUIRED')
        k_stage = 'K48_'+stage
        k48_budget.bind_table_v_case(arm=arm, stage=k_stage, stage_case_sha=case.case_sha,
            source_sha=self.manifest['source_sha'], parent_result=m_result,
            source_identity=self.manifest['identity'], parent_acceptance=m_acceptance)
        with k48_budget.arm_context(arm):
            with k48_budget.phase(k_stage, case.case_sha, self.manifest['source_sha'], digest(m_result), day='2025-05-01'):
                with k48_budget.capture_native_methods():
                    return run_current_k48(case, point, k48_budget, output)
