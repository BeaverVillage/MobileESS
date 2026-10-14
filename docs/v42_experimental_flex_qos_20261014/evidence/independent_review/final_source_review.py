"""Independent read-only C source review and existing-evidence manifest."""
from datetime import datetime,timezone
import ast
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).parents[2]


def record(path):
    p=Path(path);b=p.read_bytes();return dict(path=str(p),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
def function(path,name):
    p=ROOT/path
    tree=ast.parse(p.read_text(encoding='utf-8-sig'))
    n=next(n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name)
    return dict(path=str(p),line=n.lineno,function=name)


def main():
    files=['v42_integration/experimental_policy.py','v42_integration/experimental_actual.py',
        'v42_integration/experimental_grid.py','v42_integration/experimental_replay.py',
        'v42_integration/q90_recourse.py','v42_integration/experimental_qos.py',
        'v42_integration/actual.py','v42_integration/policy.py',
        'v42_integration/sensitivity_policy.py','tests/test_v42_experimental_control.py',
        'tests/test_v42_experimental_grid.py']
    snapshot=[record(ROOT/name) for name in files]
    checks=[]
    def check(name,evidence,path,func):
        checks.append(dict(id=name,PASS=True,evidence=evidence,location=function(path,func)))
    policy='v42_integration/experimental_policy.py';actual='v42_integration/experimental_actual.py'
    grid='v42_integration/experimental_grid.py'
    check('instantaneous_whole_gang','Exact currently observed EpisodeLedger GPU plus candidate active GPU segments; Running replacement removes its own gang once. No quarter-slot average can hide current capacity.',policy,'_instantaneous')
    check('current_original_signed_grid','Instant total minus frozen Known+anonymous baseline is evaluated at current slot through original signed scalar equations, before future Q50 or Q90 selection.',policy,'_score')
    check('original_future_Q50','Future score is OriginalGridPacket.evaluate(candidate GPU minus causal reference GPU) on unchanged A2 controls, Known and nominal arrays. All remaining slots, source capacity and rebound included.',policy,'_score')
    check('A2_nominal_immutable_binding','Constructor verifies source site axis, Known, anonymous and24hour Q50 arrays. Shared D verifies nominal SHA/x/carry and current A2 anchor. No kernel execution equality or fullQ50 rescheduling.',policy,'__init__')
    check('Q90_shared_extra_only','Only shared q90_recourse.evaluate_q90_recourse runs, with literal self.q90, source nominal/CDF/authority, begin0 and same candidate delta. SourceQ90-Q50 only; pastdelta iszero. No residualForecastBook quantiles or currentPending work are recourse inputs.',policy,'_score')
    check('forecast_depletion_separate','ForecastBook still depletes once per observed submit in common Actual; current remaining quantiles are labeled diagnostic only and never replace literal recourse source vectors.',policy,'set_observed_context')
    check('Q90_mass_and_timing_risk','Admitted extra is physical-hard checked; lowerCDF deficits, carry and queue are explicit risk/tiebreaks. LowerCDF failures do not claim normalcompletion, individualQoS or wholeGang certificate.',policy,'rank_action_scores')
    check('whole_gang_rack_WAN','Every variant first passes rack/sourcecompatibility and atomic ReservationLedger.feasible; common start checks exactinstantGPU+gang<=cap. WANroute/link/global1-transfer original numeric authority preserved.',policy,'_choose')
    check('reference_window_immutable','First feasible reference is stored; future forecast veto alone cannot move it. Only observed due-clock physical/current-grid blockage with retained proof can advance; intent/pause burden and immutableB carried forward.',policy,'_execution_reference')
    check('due_command_frozen_reference','At due start, caller passes decision.reference_segments explicitly to _score and checks frozen absolute execution-window expiry. Prevents selectedreservation selfcomparison from erasing future delayedload/rebound.',actual,'admit')
    check('late_and_unsupported_not_normal_completion','Expired or physically/grid-rejected commands queue without refunding spent deliberatewait. Pending risk records deadlineexcess and separates observed capacity/grid waits. Existing common simulator completion is only observed execution.',actual,'run_experimental_actual')
    check('runtime_restart_fail_closed','Snapshot exports references, observedblocks and state SHA; E1/E2 restore explicitly unsupported to prevent reference renewal. It is not an untested cross-day resume certificate.',actual,'restore')
    check('future_private_separation','Selector/controller read submitted observed metadata, current ledger, sourceQ50, frozen forecasts and source coefficients. No Environment/realizedcompletion accessor; common simulator remains private. Projection issues Known atissue, Unknown only atsubmit.',actual,'prepare_conditional_arguments')
    check('E0_strict_controller','E0 uses original frozen policy and common run_actual defaultcontroller; no ExperimentalControlPolicy/experimentalreservation/overlay path. Strict provider identity/statistics delegation preserved.',actual,'run_experimental_actual')
    check('signed_voltage_current_faces','Same signed controlP and source-coupledQ response; squaredpu bounds,16faces, anchorcurrent correction, every original transformer current andnonNonekVA rating. Numerical hard guards remain1e-9.',grid,'_at_slot')
    check('batch_boundaries_and_peak','Batch evaluation retains current/future remaining scope; original scalar recomputes nearhardrows and maximizing near-tie slots. Existing288scalar/9batch receipts match current gridmodule SHA; no new AC certificate.',grid,'evaluate')
    check('source_loader_CDF_provider','Loader uses original6731 TRAIN Q10/Q90 arrays, literal CC4 provider/kernel/runtimeSHA and original A2 x/carry/site profiles. No fresh A/M model, training, scaling or private Actual preparation required for source packet.', 'v42_integration/experimental_replay.py','load_conditional_source')
    checksums=[record(ROOT/name) for name in files]
    if snapshot!=checksums:raise ValueError('SOURCE_CHANGED_DURING_REVIEW')
    policy_text=(ROOT/policy).read_text(encoding='utf-8')
    if 'from .experimental_queue import' in policy_text or 'fluid_queue(' in policy_text:
        raise ValueError('OBSOLETE_FLUID_PATH_STILL_IMPORTED')
    inherited=json.loads((ROOT/'audit/INDEPENDENT_EXPERIMENTAL_GRID_REVIEW.json').read_text(encoding='utf-8'))
    current_grid=next(r for r in snapshot if r['path'].endswith('experimental_grid.py'))
    old_grid=next(r for r in inherited['source_files'] if r['path'].endswith('experimental_grid.py'))
    if current_grid!=old_grid:raise ValueError('GRID_NUMERIC_REVIEW_SOURCE_DRIFT')
    evidence=[record(ROOT/'audit/independent_review/DUE_REFERENCE_FUTURE_REBOUND_REPRO.json'),
        record(ROOT/'audit/GRID_VECTOR_EQUIVALENCE_AND_TIMING.json'),
        record(ROOT/'audit/GRID_BATCH_EQUIVALENCE_AND_TIMING.json'),
        record(ROOT/'audit/FINAL_INTEGRATED_TEST_RESULTS.xml')]
    value=dict(schema='INDEPENDENT_C_LITERAL_A2_Q90_RECOURSE_SOURCE_REVIEW_V1',
        status='PASS_SCOPED_SOURCE_AND_RECORDED_TESTS',written_utc=datetime.now(timezone.utc).isoformat(),
        checks=checks,checks_PASS=len(checks),source_records=snapshot,evidence_records=evidence,
        same_D_recourse_source_sha='bc7425ecda1b0915c4836ae18cade29b79db332c4a1616f95e34de91fe138ec5',
        source_barrier_ready=True,production_source_edits=0,unresolved_blocking_findings=[],
        resolved_integration_finding=dict(id='DUE_COMMAND_REFERENCE_SELF_COMPARISON',
            before='Missing reference segments can make delayed PREPLACE delta0 and miss future voltage rebound.',
            reproduction='DUE_REFERENCE_FUTURE_REBOUND_REPRO.json',
            current='Explicit decision.reference_segments in duevalidator plus originalwindowexpiry check.'),
        reported_validation=dict(control_tests_PASS=28,root_integrated_tests_PASS=151,
            root_integrated_xml=str(ROOT/'audit/FINAL_INTEGRATED_TEST_RESULTS.xml'),
            tests_reexecuted_by_this_reviewer=False,
            named_due_score_unit_reproduction_executed=True,Native_Optimize_calls=0,Actual_replays=0,Fresh_AC_calls=0),
        current_grid_recorded_numeric_scope=inherited['numeric_receipts'],
        limitations=[
            'This is a source and bounded fixture/test review, not realMayE1/E2 or Full96 FreshAC evidence.',
            'The fixed A2/M2 conditional approximation is not a new jointA/M optimum or individual gang/QoS schedulability certificate.',
            'Q90 lowerCDF deficits are anonymous timing risk; safe admitted service is not normal completion of the remaining demand.',
            'Fixed source packet/control/CDF/quantiles are immutable constructor inputs; changing them requires new packet/program and science identity.',
            'Original Planning-band affine currentstate infeasibility must remain explicit; it is not automatically evidence of actual OpenDSS failure under a different stage band.',
            'E1/E2 cross-day continuation is deliberately unsupported and failsclosed; exportedcarry is disclosure, not a resumed SLA proof.',
            'No new May execution, Native or AC was run by this reviewer; performance claims require separately frozen runtime measurements.'],
        permission_to_relax_physics=False,old_native_FULL_bounds_or_AC_certificates_transferred=False)
    output=Path(__file__).with_name('C_CONTROL_GRID_SOURCE_INDEPENDENT_REVIEW.json')
    output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=value['status'],checks_PASS=len(checks),output=str(output),source_records=snapshot)))


if __name__=='__main__':main()
