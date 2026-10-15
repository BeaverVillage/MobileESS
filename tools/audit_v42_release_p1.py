"""Read-only closure of the single executed P1; no optimize or new model."""
from pathlib import Path
import json
import re
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import _write,file_record,vector_sha
from v42_integration.unified_contract import digest
from v42_integration.coordinator import _full_a
OUT=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC01'


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    p=OUT/'A1_P1_120';target=p/'INDEPENDENT_P1_ACCEPTANCE.json'
    if target.exists():raise FileExistsError('P1_AUDIT_MUST_NOT_OVERWRITE')
    result=read(p/'A1_P1_RESULT.json');certificate=read(p/'PREOPTIMIZE_EXACT_MODEL_CERTIFICATE.json')
    source=read(p/'EXECUTED_ADAPTER_SOURCE.json')
    assert all(file_record(r['path'])==r for r in source['files']+source['frozen_planning_Source13'])
    old=ROOT/'docs/v42_unified_aidc_mess_research_20261014/UNIFIED_NATIVE_RUNTIME_LEDGER.json'
    assert result['canonical_before']==result['canonical_after']==file_record(old)
    ledger=read(p/'SEPARATE_NATIVE_LEDGER_180.json');assert ledger['limit_seconds']==180 and len(ledger['calls'])==1
    assert ledger['authorization_consumed'] is True and ledger['inflight'] is None
    assert ledger['calls'][0]['label']=='D0_A1_P1_RELEASE_120_20261015' and ledger['calls'][0]['cap_seconds']==120.
    assert result['Native_calls']==1 and not result['forbidden_native_attempts']
    assert result['P1_acceptance'] is True and result['FULL_feasible'] is True
    assert result['FULL_point_replay']['FULL_max_residual']<=1e-5
    with np.load(p/'SOLVE/POINT.npz',allow_pickle=False) as packet:point=packet['point']
    assert vector_sha(point)==result['FULL_point_replay']['point_sha256']
    assert len(result['selected_jobs'])+len(result['initial_Q50_expired_physical_holds'])==1624
    assert result['all_initial_UIDs_accounted_for'] is True
    assert result['selected_Known_GPU_coupling_replay']['maximum_residual']==0.
    _full_a(result)
    log=(p/'SOLVE/NATIVE_SOLVER.log').read_text(encoding='utf8')
    extract=lambda pattern:[float(v) for v in re.findall(pattern,log)]
    prior=read(old);used=ledger['conservative_solve_seconds']
    audit=dict(status='PASS_P1_ONLY',P1_certified=True,P2='NOT_RUN',M1_A2_M2_K48='NOT_RUN',
        exact_math_certificate=file_record(p/'PREOPTIMIZE_EXACT_MODEL_CERTIFICATE.json'),
        Source13_and_executed_adapter_preserved=True,point=file_record(p/'SOLVE/POINT.npz'),
        Original_FULL_residual=result['FULL_point_replay']['FULL_max_residual'],initial_UIDs_preserved=1624,
        positive_remaining_scheduled_UIDs=len(result['selected_jobs']),expired_running_physical_holds=len(result['initial_Q50_expired_physical_holds']),
        SolCount=result['SolCount'],objective=result['objective'],bound=result['bound'],gap=result['gap'],
        bound_scope=result['bound_scope'],presolve_seconds=extract(r'Presolve time:\s*([\d.]+)s'),
        root_relaxation_seconds=extract(r'Root relaxation:.*?,\s*([\d.]+) seconds'),
        barrier_cumulative_seconds=extract(r'Barrier solved model in \d+ iterations and ([\d.]+) seconds'),
        crossover_seconds=extract(r'Crossover time:\s*([\d.]+) seconds'),
        phase_times_overlap_not_additive=True,Native_seconds=used,build_solve_audit_wall_seconds=result['total_build_solve_audit_wall_seconds'],
        resource_peak=result['resource_peak'],canonical_used_seconds=prior['conservative_solve_seconds'],
        new_ledger_limit_seconds=180.,new_ledger_remaining_seconds=180.-used,
        two_ledgers_total_used_seconds=prior['conservative_solve_seconds']+used,
        unused_new_balance_authorizes_additional_calls=False,permission_max_calls=1,permission_calls_used=1,
        historical_model_not_copied_as_current_result=True,followup_permission='REQUIRED_FOR_P2_M1_A2_M2_K48')
    _write(target,audit);print(json.dumps(audit,indent=2))


if __name__=='__main__':main()
