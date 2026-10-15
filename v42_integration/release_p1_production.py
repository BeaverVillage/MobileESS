"""Additive original-production P1-only stages; no automatic Heavy dispatch.

Only the original A builder/exporter and M Beam/4-Joint/FULL engine are used.
K48 remains blocked for a changed case until its literal inclusion packet has
been independently rebound. The historical K48 globals are never repurposed.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import inspect
import math
import pickle
from pathlib import Path
from time import perf_counter

import numpy as np

from .a_engine import digest
from .m_engine import file_record, _write
from .release_p1_acceptance import accept_a, accept_m, require_acceptance, saved_a1, prohibit_p2


def production_backend(backend='ORIGINAL'):
    if backend != 'ORIGINAL':
        raise ValueError('PRODUCTION_DUMMY_EXECUTOR_FORBIDDEN_FIXTURE_ONLY')


def verify_context(context,stage=None):
    manifest=context['manifest']
    if manifest.get('schema')=='D0_STATE_CONDITIONED_PLANNING_CASE_V1':
        from .d0_case import require_case
        return require_case(manifest,stage=stage)
    if manifest.get('schema')=='D0_INDEPENDENT_DATE_PLANNING_CASE_V1':
        from .release_date_case import require_date_case
        if (context.get('production_case_verifier') is not require_date_case
                or context.get('require_case') is not require_date_case):
            raise ValueError('PRODUCTION_ORIGINAL_DATE_COMPILER_GUARD_REQUIRED_NO_DUMMY')
        return require_date_case(manifest,stage=stage)
    # A date-specific production compiler must expose its real, reviewed
    # guard. Arbitrary callbacks or fixture manifests cannot waive this gate.
    raise ValueError('PRODUCTION_DATE_SPECIFIC_REAL_CASE_COMPILER_NOT_CONNECTED')


def source_function(function):
    return dict(module=function.__module__, name=function.__qualname__,
        source=file_record(inspect.getsourcefile(function)))


class StageSolveBridge:
    """Adapt the unchanged M core to the supervisor's phase-bound ledger.

    A single outer ``budget.phase`` binds Source/Case/Stage/parent. Root computes
    actual native matrix/domain/objective identity inside every solve. This
    bridge never calls model.optimize itself or restores its native method.
    """
    def __init__(self, budget, stage):
        if stage not in ('A1','A2','M1','M2','K48_M1','K48_M2'):
            raise ValueError('PRODUCTION_EXPLICIT_STAGE_REQUIRED')
        self.parent, self.stage = budget, stage
        self.build_costs=[]

    def solve(self, model, *, label, cap, callback=None):
        if 'P2' in label.upper():
            raise ValueError('RELEASE_P2_ABSOLUTELY_FORBIDDEN')
        if not math.isfinite(float(cap)) or cap <= 0:
            raise ValueError('PRODUCTION_FINITE_POSITIVE_CAP_REQUIRED')
        return self.parent.solve(model, label=f'RELEASE_P1:{self.stage}:{label}',cap=cap,callback=callback)

    def native_optimize(self, model, callback=None, *, component='UB',track='M',label='',requested_seconds=None):
        if 'P2' in (component+track+label).upper():raise ValueError('RELEASE_P2_ABSOLUTELY_FORBIDDEN')
        return self.solve(model,label=track+':'+label,cap=requested_seconds,callback=callback)

    def remaining(self, reserve=0.):return self.parent.remaining(reserve=reserve)
    def used(self):return self.parent.used()
    @property
    def calls(self):return self.parent.calls
    @contextmanager
    def cost(self,*args,**kwargs):
        began=perf_counter()
        try:yield
        finally:self.build_costs.append(dict(stage=self.stage,labels=list(args),
            wall_seconds=perf_counter()-began,nested_in_stage_wall=True,
            charged_as_native_or_score_seconds=False))
    def record_external(self,label,seconds,**kwargs):
        if 'P2' in label.upper():raise ValueError('RELEASE_P2_ABSOLUTELY_FORBIDDEN')
        return self.parent.record_external(f'RELEASE_P1:{self.stage}:'+label,seconds,**kwargs)


def require_production_acceptance(receipt, *, stage, identity, result):
    require_acceptance(receipt,stage=stage,source_identity=identity,result=result)
    if receipt.get('fixture') or receipt.get('evidence_scope')!='REAL_PRODUCTION':
        raise ValueError('PRODUCTION_NAMED_FIXTURE_RESULT_FORBIDDEN')


class OriginalP1Stages:
    def __init__(self, context, budget, *, backend='ORIGINAL'):
        production_backend(backend)
        from .release_production_budget import ReleaseProductionBudget
        if type(budget) is not ReleaseProductionBudget or any(
                getattr(getattr(budget,name,None),'__func__',None) is not getattr(ReleaseProductionBudget,name)
                for name in ('phase','solve','capture_native_methods','used','remaining','cost','record_external')):
            raise ValueError('PRODUCTION_REAL_BUDGET_REQUIRED_NO_DUMMY_OR_METHOD_OVERRIDE')
        verify_context(context)
        self.context,self.budget=context,budget
        self.identity=context['manifest']['identity'];self.source_sha=context['manifest']['source_sha']
        axis=context['manifest']['time_axis']
        self.day=datetime.fromtimestamp(axis['evaluation_begin_seconds'],timezone(timedelta(hours=10))).date().isoformat()
        if not all(callable(getattr(budget,name,None)) for name in
                ('phase','solve','capture_native_methods','used','remaining','cost','record_external')):
            raise ValueError('SUPERVISOR_PRODUCTION_BUDGET_API_REQUIRED')
        allowed={str((Path(__file__).parent/name).resolve()) for name in ('d0_case.py','release_date_case.py')}
        self.factories={key:context[key] for key in ('make_a_case','make_m_case','bind_m_result')}
        for key,function in self.factories.items():
            if (not inspect.isfunction(function) or str(Path(inspect.getsourcefile(function)).resolve()) not in allowed
                    or function.__module__ not in ('v42_integration.d0_case','v42_integration.release_date_case')):
                raise ValueError('PRODUCTION_ORIGINAL_SOURCE_FACTORY_REQUIRED_NO_DUMMY:'+key)

    def _factories_unchanged(self):
        if any(self.context[key] is not function for key,function in self.factories.items()):
            raise ValueError('PRODUCTION_CASE_FACTORY_REPLACED_AFTER_SOURCE_VERIFICATION')

    def imported_a1(self):
        self._factories_unchanged()
        if self.day!='2025-05-01':raise ValueError('PRODUCTION_MAY01_SAVED_A1_CANNOT_TRANSFER_TO_ANOTHER_DATE')
        saved=saved_a1()
        if (saved['manifest']['identity']!=self.identity or saved['manifest']['source_sha']!=self.source_sha
                or saved['input_audit']['a_input_sha']!=self.context['input_audit']['a_input_sha']):
            raise ValueError('PRODUCTION_SAVED_A1_CURRENT_SOURCE_CASE_REQUIRED')
        return saved['result'],saved['acceptance']

    def prepare_a1(self,folder):
        self._factories_unchanged()
        verify_context(self.context,stage='A1')
        if self.day=='2025-05-01':
            raise ValueError('PRODUCTION_MAY01_A1_ALREADY_EXECUTED_IMPORT_SAVED_NO_DUPLICATE')
        return self.context['make_a_case']('A1',folder=folder)

    def prepare_m(self,stage,a_result,a_acceptance,folder,*,build_admission):
        self._factories_unchanged()
        expected='A1' if stage=='M1' else 'A2'
        require_production_acceptance(a_acceptance,stage=expected,identity=self.identity,result=a_result)
        if (build_admission.get('operation')!='CURRENT_M_NATIVE0_BUILD' or build_admission.get('status')!='PASS'
                or build_admission.get('stage')!=stage or build_admission.get('concurrent_heavy_solver') is not False):
            raise ValueError('PRODUCTION_SUPERVISOR_M_NATIVE0_RAM_ADMISSION_REQUIRED')
        return self.context['make_m_case'](stage,a_result,Path(folder))

    def adopt_prepared_m(self,packet_record,a_result,a_acceptance,*,stage):
        """Restore an authenticated factory checkpoint without a second build.

        The original factories keep only issuance metadata in a shared closure.
        Restore exactly that metadata after the current matrix/domain/Source
        proof is checked. No row, bound, objective or producer code is changed.
        """
        self._factories_unchanged()
        expected='A1' if stage=='M1' else 'A2'
        require_production_acceptance(a_acceptance,stage=expected,identity=self.identity,result=a_result)
        if file_record(packet_record['path'])!=packet_record:
            raise ValueError('PRODUCTION_PREPARED_M_PACKET_BYTE_DRIFT')
        with Path(packet_record['path']).open('rb') as stream:case=pickle.load(stream)
        from v42_may_campaign_native90.m_model import CampaignMCase,verify_case
        if (type(case) is not CampaignMCase or case.identity.get('stage')!=stage
                or case.identity.get('aidc_anchor')!=a_acceptance['AIDC_anchor']
                or case.identity.get('D0_source_sha')!=self.source_sha
                or case.identity.get('D0_parent_case_sha')!=self.identity['case_sha']
                or case.identity.get('day')!=self.day
                or any(case.identity.get(key)!=self.identity[key] for key in
                    ('science_sha','cc4_sha','runtime_sha'))
                or case.identity.get('physical_sha')!=self.context['manifest']['physical_sha']
                or case.identity.get('time_axis_sha')!=self.context['manifest']['time_axis_sha']):
            raise ValueError('PRODUCTION_PREPARED_M_SOURCE_CASE_ANCHOR_DRIFT')
        verify_case(case)
        factory=self.factories['make_m_case'];closed=inspect.getclosurevars(factory).nonlocals
        registry=closed.get('issued_m_cases',closed.get('issued_m'))
        binder=inspect.getclosurevars(self.factories['bind_m_result']).nonlocals
        linked=binder.get('issued_m_cases',binder.get('issued_m'))
        if not isinstance(registry,dict) or linked is not registry:
            raise ValueError('PRODUCTION_ORIGINAL_FACTORY_ISSUANCE_CHECKPOINT_LAYOUT_CHANGED')
        item=dict(stage=stage,AIDC_anchor=a_acceptance['AIDC_anchor'],output_MESS_anchor=None)
        if case.case_sha in registry and registry[case.case_sha]!=item:
            raise ValueError('PRODUCTION_FACTORY_ISSUANCE_ALREADY_BOUND_DIFFERENT_RESULT')
        registry[case.case_sha]=item
        return case

    def execute_m(self,stage,case,a_result,a_acceptance,*,stage_total_cap,
            initial_point=None,incumbent_registry=()):
        self._factories_unchanged()
        from .m_engine import optimize_mess,strict_full,export_plan,_native_joint
        from .m_candidates import generate
        from .release_p1_acceptance import read
        verify_context(self.context,stage=stage)
        expected='A1' if stage=='M1' else 'A2'
        require_production_acceptance(a_acceptance,stage=expected,identity=self.identity,result=a_result)
        if (stage not in ('M1','M2') or case.identity.get('stage')!=stage
                or case.identity.get('aidc_anchor')!=a_acceptance['AIDC_anchor']
                or case.identity.get('D0_source_sha')!=self.source_sha
                or getattr(case,'candidate_generator',None) is not generate
                or getattr(case,'plan_exporter',None) is not export_plan
                or getattr(case,'joint_solver',_native_joint) is not _native_joint
                or getattr(case,'strict_validator',strict_full) is not strict_full
                or getattr(case,'cold_initializer',None) is not None
                or not math.isfinite(float(stage_total_cap)) or stage_total_cap<=0):
            raise ValueError('PRODUCTION_ORIGINAL_BEAM_JOINT_FULL_ENGINE_REQUIRED')
        # Operational cap only; no objective, beam score or physics is changed.
        case.mess_stage_budget_seconds=float(stage_total_cap)
        bridge=StageSolveBridge(self.budget,stage)
        with self.budget.phase(stage,case.case_sha,self.source_sha,digest(a_result),day=self.day):
            with self.budget.capture_native_methods():
                result,point=optimize_mess(case,initial_point,incumbent_registry,bridge)
        prohibit_p2(result)
        if result.get('FULL_validated') is not True:
            native=result.get('native_call') or {}
            result['status']='TIME_LIMIT_NO_FEASIBLE' if native.get('native_status')==9 else 'NOT_CERTIFIED'
            result['release_build_costs']=bridge.build_costs
            return result,None,point
        result=self.context['bind_m_result'](result)
        result['release_build_costs']=bridge.build_costs
        # The core writes the literal point and its original FULL replay. Bind
        # these bytes rather than trusting the result's FULL boolean alone.
        registry=result['incumbent_registry']
        global_entries=[r for r in registry if r['origin']=='CASE_FULL_BANK_GLOBAL']
        if len(global_entries)!=1:raise ValueError('PRODUCTION_CURRENT_RAW_FULL_INCUMBENT_REQUIRED')
        item=global_entries[0]
        if file_record(item['raw']['path'])!=item['raw']:raise ValueError('PRODUCTION_M_RAW_POINT_BYTES_DRIFT')
        certificate=read(Path(item['raw']['path']).with_suffix('.REPLAY.json'))
        receipt=accept_m(result,stage=stage,source_identity=self.identity,source_sha=self.source_sha,
            parent_a=a_acceptance,parent_result=a_result,stage_case_sha=case.case_sha,full_certificate=certificate)
        return result,receipt,point

    def prepare_a2(self,m_result,m_acceptance,folder):
        self._factories_unchanged()
        require_production_acceptance(m_acceptance,stage='M1',identity=self.identity,result=m_result)
        return self.context['make_a_case']('A2',fixed_mess=m_result['mess'],folder=folder,upstream_m_result=m_result)

    def execute_a2(self,case,m_result,m_acceptance,*,build_admission,cap):
        return self._execute_a('A2',case,m_result,m_acceptance,build_admission=build_admission,cap=cap)

    def execute_a1(self,case,*,build_admission,cap):
        if self.day=='2025-05-01':
            raise ValueError('PRODUCTION_MAY01_A1_ALREADY_EXECUTED_IMPORT_SAVED_NO_DUPLICATE')
        return self._execute_a('A1',case,None,None,build_admission=build_admission,cap=cap)

    def _execute_a(self,stage,case,parent_result,parent_acceptance,*,build_admission,cap):
        """One original P1 optimize; the legacy multi-pass solver is not called."""
        self._factories_unchanged()
        import gurobipy as gp
        from .d0_a_planning import build_d0_native_model,_export_d0_point
        from .d0_resource import native_binding
        from .a_seed import full_replay
        from .m_engine import vector_sha
        from v42_root.native import reconstruct
        from v42_a_stage_domain_v2.solver_policy import solver_policy,apply_policy
        from v42_b3_joint.numerical_policy import apply_native_precision
        verify_context(self.context,stage=stage)
        if stage=='A2':
            require_production_acceptance(parent_acceptance,stage='M1',identity=self.identity,result=parent_result)
            mess_anchor=parent_acceptance['MESS_anchor']
        elif stage=='A1':
            # Date factories materialize physics lazily and do not expose an
            # initial_mess top-level context key. The authenticated factory
            # already bound its zero/STAY anchor in this exact A1 case.
            mess_anchor=case.grid.fixed_mess['plan_sha']
        else:raise ValueError('PRODUCTION_A1_A2_ONLY')
        if case.stage!=stage or case.grid.fixed_mess['plan_sha']!=mess_anchor:
            raise ValueError('PRODUCTION_CURRENT_A_FIXED_MESS_REQUIRED')
        expected_case=digest(dict(parent=self.identity['case_sha'],stage=stage,
            input_MESS_anchor=mess_anchor,backlog_contract=self.context['backlog']['contract_sha']))
        if case.case_sha!=expected_case:
            raise ValueError('PRODUCTION_A_STAGE_SOURCE_PARENT_ANCHOR_CASE_DRIFT')
        if any((Path(case.output)/name).exists() for name in ('P1_ONLY_RESULT.json','P1_ONLY_POINT.npz','P1_ONLY_ACCEPTANCE.json')):
            raise FileExistsError('PRODUCTION_P1_ATTEMPT_ALREADY_EXISTS_NO_RETRY_OR_OVERWRITE')
        built=None
        parent_sha=digest(parent_result) if parent_result is not None else self.context['manifest']['manifest_sha']
        with self.budget.phase(stage,case.case_sha,self.source_sha,parent_sha,day=self.day):
            with self.budget.capture_native_methods():
                try:
                    built=build_d0_native_model(case,build_admission=build_admission)
                    model=built[0];model.setObjective(dict(built[2])['rho'],gp.GRB.MINIMIZE);model.update()
                    policy=solver_policy(gp);apply_policy(model,policy,gp)
                    numerical=apply_native_precision(model,day=case.data[0]['day'],stage=stage,component='ORIGINAL_P1')
                    original_binding=native_binding(model)
                    call=StageSolveBridge(self.budget,stage).solve(model,label='ORIGINAL_P1',cap=cap)
                    result=dict(stage=stage,arm='B3',case_sha=case.case_sha,source_identity=deepcopy(self.identity),
                        D0_input_sha=self.context['input_audit']['a_input_sha'],input_MESS_anchor=mess_anchor,
                        D0_issue_seconds=self.context['input_audit']['issue_seconds'],P2_calls=0,P2='NOT_RUN',
                        objective=float(model.ObjVal) if model.SolCount else None,
                        bound=float(model.ObjBound) if math.isfinite(float(model.ObjBound)) else None,
                        gap=float(model.MIPGap) if model.SolCount else None,Native_call=call,FULL_feasible=False,
                        native_binding=original_binding,solver_policy=policy,numerical_policy=numerical,
                        domain_scope='COMPLETE_D0_SOURCE_AUTHORIZED_BASIC_DOMAIN',
                        unrestricted_original_migration_global_optimality=False)
                    if not model.SolCount:
                        result['status']='TIME_LIMIT_NO_FEASIBLE' if model.Status==gp.GRB.TIME_LIMIT else 'NOT_CERTIFIED'
                        _write(Path(case.output)/'P1_ONLY_RESULT.json',result)
                        return result,None
                    point=np.asarray(model.getAttr('X'),float);full=full_replay(model,point)
                    if not full['PASS']:raise ValueError('PRODUCTION_A2_ORIGINAL_FULL_REPLAY_FAILED')
                    result.update(_export_d0_point(case,built,point,reconstruct(built[1],built[5])))
                    np.savez_compressed(Path(case.output)/'P1_ONLY_POINT.npz',point=point)
                    receipt=accept_a(result,stage=stage,stage_case_sha=case.case_sha,source_identity=self.identity,
                        source_sha=self.source_sha,input_sha=self.context['input_audit']['a_input_sha'],
                        input_mess_anchor=mess_anchor,native_binding=original_binding,
                        point_sha=vector_sha(point),original_full=full,parent_acceptance=parent_acceptance)
                    _write(Path(case.output)/'P1_ONLY_RESULT.json',result)
                    _write(Path(case.output)/'P1_ONLY_ACCEPTANCE.json',receipt)
                    return result,receipt
                finally:
                    if built is not None:built[0].dispose()


def current_k48_gate(*,stage,stage_case_sha,source_sha,full_matrix_sha,full_domain_sha,
        independent_inclusion=None):
    """The historical K48 domain is kept; no fake generic proof authorizes it."""
    from tools.critical_grid_cg import oracle,verify,pilot
    source=dict(
        oracle=file_record(oracle.__file__),verifier=file_record(verify.__file__),pilot=file_record(pilot.__file__))
    same=(stage_case_sha==oracle.CASE and full_matrix_sha==verify.FULL_MATRIX and full_domain_sha==verify.FULL_DOMAIN)
    return dict(status='NOT_CERTIFIED',stage=stage,stage_case_sha=stage_case_sha,source_sha=source_sha,
        original_K48_sources=source,original_K48_case_sha=oracle.CASE,
        source_specific_original_case_equal=same,current_case_inclusion_verified=False,
        supplied_receipt_not_trusted_without_literal_replay=independent_inclusion is not None,
        reason='CURRENT_D0_K48_FULL_PROJECTION_INCLUSION_AND_PARAMETERIZED_PACKET_NOT_AVAILABLE',
        Global_LB=None,historical_LB_transferred=False,Native_calls=0)


def production_wiring():
    """Actual source identities; function presence is not execution evidence."""
    from .d0_a_planning import build_d0_native_model,_export_d0_point
    from .m_engine import optimize_mess,strict_full
    from .m_candidates import generate
    from .d0_execution import require_d0_actual_handoff,run_d0_current_actual
    from .actual import run_actual
    from .actual_validation import fresh_ac_minimum
    from .release_actual import ReleaseController
    functions=(build_d0_native_model,_export_d0_point,optimize_mess,generate,strict_full,
        require_d0_actual_handoff,run_d0_current_actual,run_actual,fresh_ac_minimum,ReleaseController)
    return dict(status='STATIC_ORIGINAL_CALL_PATHS_IDENTIFIED_ONLY',
        functions=[source_function(f) for f in functions],P2_calls=0,
        A1='SAVED_CURRENT_ORIGINAL_FULL_P1',M1='ORIGINAL_FACTORY_NATIVE0_PROOF_REQUIRED',
        A2='ORIGINAL_BUILDER_SINGLE_P1_ADDITIVE_WRAPPER_NOT_EXECUTED',
        M2='ORIGINAL_BEAM_JOINT_FULL_NOT_EXECUTED',K48='CURRENT_CASE_INCLUSION_PACKET_NOT_CERTIFIED',
        Actual_controller='FINAL_A2_M2_AND_CURRENT_AC_POLICY_PACKET_NOT_EXECUTED',
        Fresh_OpenDSS='ORIGINAL_EVALUATOR_IDENTIFIED_NOT_EXECUTED',
        PR223_reference_fixed_M2_promoted=False,production_execution_certified=False,
        Dummy_in_production_allowed=False,fixture_is_production_evidence=False)
