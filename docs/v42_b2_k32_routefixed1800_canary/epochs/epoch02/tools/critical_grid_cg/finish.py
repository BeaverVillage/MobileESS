"""Assemble the completed study receipt from independently certified stages."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'docs/v42_critical_grid_cg'
UB = .6760534504652341
OLD_LB = .42547778318693985


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def finish():
    ledger = read(OUT/'NATIVE_LEDGER.json')
    hold = read(OUT/'POST_RUN_RESOURCE_HOLD.json')
    reuse = read(OUT/'PR210_REUSE_AUDIT.json')
    assert hold['PASS'] and reuse['PASS']
    stages = []
    for call in ledger['calls']:
        folder = Path(call['out'])
        cert = read(folder/'INDEPENDENT_CERTIFICATE.json')
        result = read(folder/'RESULT.json')
        model = read(folder/'NATIVE0.json')
        assert cert['PASS'] and cert['FULL_projection_subset_native_Joint']
        assert result['Native_optimize_calls'] == 1 and call['TimeLimit'] == 180
        stages.append(dict(stage=call['stage'], Global_LB=cert['Global_LB'],
                           ObjBound=cert['LB_new_certified'], ObjVal_reduced=result['ObjVal'],
                           global_gap=cert['global_gap'], Runtime=result['Runtime'],
                           optimize_wall_seconds=result['optimize_wall_seconds'],
                           model_extraction_seconds=model['model_extraction_seconds'],
                           model_build_seconds=result['model_build_seconds'],
                           dimensions=model['dimensions'],
                           certificate_sha256=sha(folder/'INDEPENDENT_CERTIFICATE.json'),
                           result_sha256=sha(folder/'RESULT.json')))
    assert 1 <= len(stages) <= 2
    last = read(Path(ledger['calls'][-1]['out'])/'INDEPENDENT_CERTIFICATE.json')
    lb = last['Global_LB']
    results = [read(Path(call['out'])/'RESULT.json') for call in ledger['calls']]
    write(OUT/'FINAL_RESULT.json', dict(
        PASS=True, classification=last['classification'], Global_LB=lb, LB_published=lb,
        LB_old=OLD_LB, UB=UB, delta_Joint16=lb-OLD_LB, global_gap=(UB-lb)/UB,
        stage2_increment=stages[1]['Global_LB']-stages[0]['Global_LB'] if len(stages)==2 else None,
        stage2_incumbent_rho_numerical_delta_no_new_UB=UB-results[1]['ObjVal'] if len(stages)==2 else None,
        stage2_U4_start_retained_only=bool(len(stages)==2 and results[1]['SolCount']==1),
        Gap_percent=100*(UB-lb)/UB, goal_LB=UB*.97, goal_3percent=lb>=UB*.97,
        stages=stages, additional_Native_calls=len(stages),
        requested_Native_seconds=sum(call['TimeLimit'] for call in ledger['calls']),
        actual_Native_Runtime=sum(r['Runtime'] for r in results),
        optimize_wall_seconds=sum(r['optimize_wall_seconds'] for r in results),
        peak_process_RSS_bytes=max(r['peak_process_RSS_bytes'] for r in results),
        peak_private_commit_bytes=max(r['peak_private_commit_bytes'] for r in results),
        peak_sampled_private_commit_bytes=max(r['peak_sampled_private_commit_bytes'] for r in results),
        MaxMemUsed_GB=max(r['MaxMemUsed_GB'] for r in results),
        minimum_RAM_available=min(r['minimum_RAM_available'] for r in results),
        minimum_commit_available=min(r['minimum_commit_available'] for r in results),
        full_MILP_calls=0, separate_LP_calls=0, campaign_calls=0, additional_dates=0,
        column_generation_calls=0, DW_calls=0, Benders_calls=0, weight_optimization_calls=0,
        exact_BB_trace_certificate=False, reduced_incumbent_promoted_to_FULL_UB=False,
        preserved_HOLD_Disabled_PAUSED=True,
        final_HOLD_audit_sha256=sha(OUT/'POST_RUN_RESOURCE_HOLD.json'),
        PR210_reuse_audit_sha256=sha(OUT/'PR210_REUSE_AUDIT.json'),
        final_ledger_sha256=sha(OUT/'NATIVE_LEDGER.json'),
        stop_reason='Authorized two-stage pilot completed; no third iteration or additional solver execution.',
        next_study_decision='Reject further expansion of the same fixed-quota policy: stage2 bound gain is nonmaterial and only the U4 start remains incumbent. Exact cut transport is validated, but 3% convergence and FULL feasibility remain unproved.'))
    write(OUT/'STAGE2_DECISION.json', dict(PASS=True, executed=len(stages)==2,
          pre_oracle_gate_sha256=sha(OUT/'STAGE2_PRE_ORACLE_GATE.json'),
          complete_admission_gate_sha256=sha(OUT/'iteration02/STAGE2_GATE.json') if len(stages)==2 else None,
          stop_after_stage=len(stages), no_further_solver_authorization=True))
    print(json.dumps(dict(PASS=True,classification=last['classification'],Global_LB=lb,
                         Gap_percent=100*(UB-lb)/UB,Native_calls=len(stages))))


if __name__ == '__main__':
    finish()
