"""May01 prestart dispatcher. No official optimizer is enabled by preparation.

The historical delayed master is intentionally absent. Stage readiness is
case-specific and cannot be inferred from fixed-B0 M1 or a fixture result.
"""
import ast,sys
from .static_common import *
from v44.stages import CHAINS

def request(day,arm):
    if day!='2025-05-01':raise PermissionError('MAY01_ONLY')
    if arm not in CHAINS:raise ValueError('ORIGINAL_ARM_REQUIRED')
    return list(CHAINS[arm])

def native0():
    from .static_native import build
    return build()

def campaign(approval=None):
    p=OUT/'FINAL_PRESTART_GO_NO_GO.json'
    if not p.exists() or read(p).get('status')!='READY_FOR_MAY01_CAMPAIGN_APPROVAL':
        raise PermissionError('PRESTART_BLOCKED_WITH_EVIDENCE')
    # A readiness string cannot invent missing scientific handlers. No permit
    # is written, old IEEE123 worker started, or native ledger touched here.
    raise PermissionError('CERTIFIED_CURRENT_CASE_STAGE_HANDLERS_AND_NEW_USER_CAMPAIGN_APPROVAL_REQUIRED')

def interfaces():
    init();old=read(DOC/'integration/CAMPAIGN_EXECUTION_HOLD.json')
    original=read(OUT/'V44_R043_ALGORITHM_IDENTITY_AUDIT.json')
    current_axes=read(OUT/'SOURCE_YY_GRID_AXES.json') if (OUT/'SOURCE_YY_GRID_AXES.json').exists() else {}
    blockers=[
        dict(stage='A1',status='BLOCKED',cause='Original A builder consumes original_coefficients_for_day + IEEE123 physical_authority. New72-axis Source-YY grid, complete variable Job domain/current-AC and source QoS acceptance have not been bound.',
            required='Variable-AIDC FULL Native0 plus original independent all-Job validation; fixed-B0 screening is invalid for this domain.'),
        dict(stage='M1',status='PREPARATION_ONLY',cause='Source-YY fixed-B0 static Native0 is independently measured. Original r043 K48/Beam helper metadata requires unit-pivot response bindings and source physical row labels; sparse scaled IEEE8500 helpers need a certified representation adapter.',
            required='Same Case/Domain original K48 metadata/projection, Beam and Joint Native0; no delayed grid master.'),
        dict(stage='A2',status='BLOCKED_DEPENDENCY',cause='No accepted current Source-YY M1 plan or variable-AIDC full stage. Original require_m1 and fixed plan SHA must be retained.',
            required='Complete A2 Native0 with exact adopted M1 P/Q/Route; original FULL Job acceptance.'),
        dict(stage='M2',status='BLOCKED_DEPENDENCY',cause='No accepted current A2 anchor. Fixed-B0 M1 bounds and coefficients cannot certify a changed A2 load.',
            required='Rebind same-day A2 affine anchor and regenerate static bounds/proofs; original M1 algorithm reused.')]
    put('A1_M1_A2_M2_ORIGINAL_STAGE_INTEGRATION.json',dict(PASS=False,
        chains={a:request('2025-05-01',a) for a in CHAINS},stage_results=blockers,
        same_case_required=True,variable_AIDC_not_forced_to_B0=True,old414_cache_accepted=False,
        source_job_policy_relaxed=False,MESS8_route_domain_retained=True,
        budgets=old['budgets'],runtime_settings=old['original_r043_overlay'],
        stage_fixture_success_is_not_FULL_PASS=True,official_campaign_executed=False))
    put('K48_BEAM_JOINT_ALGORITHM_PRESERVATION.json',dict(original_sources_unchanged=original['algorithm_source_unchanged'],
        original_K16_K32_K48_pricing_allowed=True,new_Grid_pricing_allowed=False,
        original_Beam_width=[12,16],original_Beam_heuristic_MOVE_depth=4,
        original_DirectJoint_route_lift_preserved=True,all8_route_choices_must_remain_free=True,
        current_Source_YY_Case_interface_PASS=False,
        actual_grid_axes=dict(controls=len(current_axes.get('controls',[])),
            transformer_current=len(current_axes.get('transformer_current',[]))),
        original_guards=dict(Planning_RegControl=7,original_transformer_current_rows_per_slot=120,
            build_blocks_units=4,Geometry_helper_pivot=1.,thermal_row_name='line_thermal_face[t,branch,face]'),
        new_case_needs_explicit_dimension_and_representation_adapter=True,
        K48_LB=None,Joint_UB=None,Global_Gap=None,
        absence_of_numerical_bounds_before_campaign_is_not_itself_a_blocker=True,
        reason='Current FULL case/metadata/validator interface has not passed; no IEEE123 bound transferred.'))
    return blockers

def no_cg_proof():
    paths=['static_execution.py','static_native.py','static_screen.py','static_mobility.py','static_coefficients.py','static_pack.py','static_verify.py',
        'static_transport_verify.py','static_sequence.py','static_helper_view.py','static_interface_probe.py']
    bad=[];calls=[]
    forbidden={'DelayedMaster','LiteralMaster','refine','iterate','certify_candidate','add_ids'}
    for name in paths:
        p=ROOT/'v2_add_preflight'/name;tree=ast.parse(p.read_text(encoding='utf-8'))
        for n in ast.walk(tree):
            if isinstance(n,(ast.Import,ast.ImportFrom)):
                text=ast.unparse(n)
                if 'may01_oracle' in text or 'may01_exact_native' in text:bad.append(dict(file=name,line=n.lineno,text=text))
            if isinstance(n,ast.Call):
                symbol=n.func.attr if isinstance(n.func,ast.Attribute) else n.func.id if isinstance(n.func,ast.Name) else ''
                if symbol in forbidden:bad.append(dict(file=name,line=n.lineno,text=ast.unparse(n.func)))
                if symbol in ('optimize','presolve'):calls.append(dict(file=name,line=n.lineno,text=ast.unparse(n.func)))
    assert not bad and not calls
    assert 'v2_add_preflight.may01_oracle' not in sys.modules
    assert 'v2_add_preflight.may01_exact_native' not in sys.modules
    return put('NO_NEW_GRID_CONSTRAINT_GENERATION_PROOF.json',dict(PASS=True,
        scope='New May01 prestart dispatcher and complete-static preparation; production execution remains disabled',
        forbidden_calls_or_imports=bad,new_native_optimize_or_presolve_calls=calls,
        inspected_sources=[record(ROOT/'v2_add_preflight'/p) for p in paths],
        historical_delayed_master_preserved=True,historical_delayed_master_official_path=False,
        old431255_master_is_static_COMPLETE=False,original_K48_pricing_unchanged=True,
        original_pinned_Geometry_helpers_are_not_new_CG=True,
        retained_rows_added_before_solver_only=True,callbacks_or_lazy_grid_rows=0,
        production_stage_integration_claimed=False))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['interfaces','proof','native0','campaign']);p.add_argument('--approval')
    a=p.parse_args()
    {'interfaces':interfaces,'proof':no_cg_proof,'native0':native0,'campaign':lambda:campaign(a.approval)}[a.mode]()
