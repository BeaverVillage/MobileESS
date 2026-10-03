"""Bind amended interpretations to immutable execution and stored point bytes."""
from .common import ROOT,OUT,POLICY,read,write,sha
from v42_postsolve.contract import contract

def run():
    result=read(OUT/'M1_DEGENMOVES0_SOLVE_RESULT.json')
    certificate=read(OUT/'M1_CERTIFICATE_RECLASSIFIED.json');run=certificate['run_identity']
    assert read(OUT/'V42_POSTSOLVE_NUMERICAL_TOLERANCE_CONTRACT.json')==contract()
    assert result['settings']==POLICY==run['solver_policy']
    assert run['solve_log_sha256']==sha(OUT/'M1_DEGENMOVES0_SOLVE.log')
    assert run['solve_result_sha256']==sha(OUT/'M1_DEGENMOVES0_SOLVE_RESULT.json')
    pair=read(OUT/'M1_MODEL_IDENTITY_PR134_PAIR.json')
    assert pair['reference']==pair['current']==run['model_identity'] and pair['post_P1_scientific_payload_equal']
    assert run['A1_freeze_sha256']==pair['A1_freeze_sha256'] and run['NormalAmps_authority_sha256']==pair['NormalAmps_authority_sha256']
    numbers=read(OUT/'CURRENT_INCUMBENT_NUMERICAL_REAUDIT.json');physics=read(OUT/'CURRENT_INCUMBENT_PHYSICAL_REAUDIT.json')
    original=read(OUT/'M1_P1_ALL_INCUMBENT_AUDITS.json')
    for record,p,old in zip(numbers['records'],physics['records'],original['records'],strict=True):
        assert record['point_sha256']==p['point_sha256']==old['point_sha256']
        assert sha(OUT/'RAW_POINTS'/f"M1_P1_INCUMBENT_{record['index']}.npz")==old['point_sha256']
        assert record['NUMERICAL_AUDIT_PASS'] and p['PHYSICAL_AUDIT_PASS'] and record['solver_accepted']
        fresh=record['numerical']['full_unreduced_matrix_audit'];prior=old['validation']['full_unreduced_matrix_audit']
        assert all(fresh[k]==prior[k] for k in prior if k!='PASS')
        assert not p['physical']['raw_grid']['numerical_tolerance_added_to_ratings']
        assert p['physical']['raw_grid']['physical_audit_tolerance']==1e-5
    assert certificate['UB']==min(r['objective'] for r in numbers['records'])==result['raw_solver_UB']
    assert certificate['LB']==result['LB'] and result['valid_global_LB']
    assert certificate['gap']==(certificate['UB']-certificate['LB'])/abs(certificate['UB'])>.005
    assert not certificate['M1_P1_ACCEPTED'] and not certificate['old_bounds_used'] and not certificate['CURRENT_SOLVE_START_USED']
    assert run['bound_provenance']=='same_completed_solve' and certificate['new_optimize_calls']==0
    start=read(OUT/'ZERO_ACTION_START_TOLERANCE_REAUDIT.json')
    assert start['M1_ZERO_ACTION_START_VALID'] and start['NUMERICAL_AUDIT_PASS'] and start['PHYSICAL_AUDIT_PASS']
    assert sha(OUT/'RAW_POINTS/ZERO_ACTION_CANDIDATE.npz')==start['candidate_sha256']
    assert not start['CURRENT_SOLVE_START_USED'] and not result['Start_used'] and start['repair_calls']==0
    preserved=read(OUT/'AMENDMENT_EVIDENCE_PRESERVATION_AUDIT.json')
    assert all(sha(OUT/name)==digest for name,digest in preserved['checksums'].items())
    retrospective=read(OUT/'TOLERANCE_RETROSPECTIVE_CONSISTENCY_AUDIT.json')
    assert retrospective['PASS'] and not retrospective['A1']['acceptance_reversed']
    assert not retrospective['A1']['full_A1_rows_recomputed']
    files=[ROOT/'v42_postsolve/contract.py',ROOT/'v42_postsolve/__init__.py',ROOT/'v42_degen/reaudit.py']
    write('RECLASSIFIED_CERTIFICATE_FINAL_AUDIT.json',dict(PASS=True,checked_incumbents=len(numbers['records']),all_raw_residuals_reproduced=True,point_bytes_preserved=True,both_independent_audits_PASS=True,same_completed_solve_bounds_only=True,old_bounds_used=False,physical_limits_changed=False,solver_parameters_unchanged=True,current_solve_Start_used=False,zero_action_Start_reclassified_valid=True,validator_sources=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)) for p in files],solver_result_sha256=run['solve_result_sha256'],solver_log_sha256=run['solve_log_sha256'],reclassified_certificate_sha256=sha(OUT/'M1_CERTIFICATE_RECLASSIFIED.json'),new_optimize_calls=0,retrospective_A1_available_evidence_PASS=True,full_A1_matrix_reaudit_not_claimed=True))
    print('RECLASSIFIED_CERTIFICATE_FINAL_PASS',flush=True)

if __name__=='__main__':run()
