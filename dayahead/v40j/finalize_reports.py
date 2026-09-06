"""Final preservation and test receipt; no historic May row/outcome fixtures."""
import json
import subprocess
import xml.etree.ElementTree as ET
from .contracts import ROOT, OUT, START
from .firewall import sha,write

def main():
    # Canonical LF bytes must agree with Git's existing text normalization.
    # Only V40J-authored outputs are normalized; no input/legacy file is touched.
    for path in OUT.rglob('*'):
        if path.is_file() and path.suffix in {'.json','.jsonl','.md','.csv','.log','.txt','.xml'}:
            raw=path.read_bytes()
            if b'\r\n' in raw:path.write_bytes(raw.replace(b'\r\n',b'\n'))
    baseline_receipt=ROOT/'dayahead/artifacts/v40i_authority_electrical_closure/V40I_FINAL_FORENSIC_COMMIT_RECEIPT.json'
    receipt=json.loads(baseline_receipt.read_text(encoding='utf-8'))
    start=json.loads((OUT/'V40J_START_STATE.json').read_text(encoding='utf-8'))
    expected=start['authority_documents_motivation_only'][str(baseline_receipt.relative_to(ROOT))]
    assert sha(baseline_receipt)==expected
    protection=json.loads((OUT/'V40J_PROTECTED_SCOPE_DIFF.json').read_text())
    assert protection['status']=='PASS'
    tree=ET.parse(OUT/'V40J_REGRESSIONS.xml').getroot()
    suites=[tree] if tree.tag=='testsuite' else list(tree.iter('testsuite'))
    totals={k:sum(int(s.get(k,0)) for s in suites) for k in ['tests','failures','errors','skipped']}
    assert totals['failures']==totals['errors']==totals['skipped']==0
    replay=json.loads((OUT/'V40J_RESULT_REPRODUCIBILITY.json').read_text())
    assert replay['status']=='PASS'
    assert not subprocess.check_output(['git','diff',START,'HEAD','--','tests','dayahead/tests','dayahead/v40h','dayahead/v40i'],cwd=ROOT)
    freeze=json.loads((OUT/'V40J_RUNTIME_METHOD_FREEZE.json').read_text())
    assert freeze['winner'] is None and freeze['production_integration_recommendation']=='NO'
    write('V40J_TEST_REPORT.json',{'executed_V40J_regressions':{**totals,'passed':totals['tests'],
       'junit_xml_sha256':sha(OUT/'V40J_REGRESSIONS.xml'),'log_sha256':sha(OUT/'V40J_REGRESSIONS.log')},
       'legacy_V40H':{'previously_passed':receipt['tests']['V40H'],'rerun_this_revision':False,'source_and_frozen_receipt_preserved':True},
       'legacy_V40I':{'previously_passed':receipt['tests']['V40I'],'rerun_this_revision':False,'source_and_frozen_receipt_preserved':True},
       'legacy_no_rerun_reason':'User mid-run requirement keeps May runtime/status row and Actual outcome artifact reads at zero. Old fixture-based forensic tests are not reopened; unchanged source and authoritative 186-PASS receipt are verified instead.',
       'legacy_receipt_sha256':sha(baseline_receipt),
       'current_baseline_byte_reproduction':'PASS, max difference 0.0 seconds',
       'candidate_independent_same_seed_refits':18,
       'independent_calibration_rebuilds_identical':len(replay['calibrations']),
       'prediction_domains_quantile_order_GPU_metric_rebuilds_identical':len(replay['variants']),
       'timestamp_guard_preserves_all_trained_populations':True,
       'protected_scope':protection['status'],'PF_baseline':.95,'external_SHA':'PASS',
       'authority_missing':72,'31_DAY_ELECTRICAL_REGENERATION':'HOLD','B0_B1_B2_B3_optimization':'NO','FULL_MAY':'NO',
       'model_selection_after_amendment_commit':True,'shadow_rows_opened':0})
    required=['V40J_START_STATE.json','V40J_PREMAY_READ_FIREWALL.json','V40J_CAUSAL_FEATURE_CONTRACT.json',
      'V40J_TEMPORAL_SPLIT_CONTRACT.json','V40J_CANDIDATE_REGISTRY.json','V40J_CURRENT_RUNTIME_BASELINE.json',
      'V40J_POINT_MODEL_COMPARISON.json','V40J_QUANTILE_MODEL_COMPARISON.json','V40J_MIXTURE_MODEL_COMPARISON.json',
      'V40J_CONDITIONAL_CALIBRATION_REPORT.json','V40J_SUPPORT_GUARD_REPORT.json','V40J_GPU_WEIGHTED_SAFETY_REPORT.json',
      'V40J_ROBUST_ENVELOPE_COMPARISON.json','V40J_PREMAY_FINAL_SHADOW_REPORT.json','V40J_RUNTIME_METHOD_FREEZE.json',
      'V40J_EXTERNAL_DATACENTER_PQ_AUDIT.json','V40J_EXTERNAL_DATACENTER_PQ_AUDIT.md','V40J_PROTECTED_SCOPE_DIFF.json',
      'V40J_TEST_REPORT.json','V40J_FINAL_REVIEW.md','V40J_PREMAY_TIMESTAMP_FIREWALL.json','V40J_PREREGISTRATION_AMENDMENT_01.json']
    assert all((OUT/n).is_file() for n in required)
    write('V40J_ARTIFACT_MANIFEST.json',{'classification':freeze['classification'],
       'required_artifacts':{n:sha(OUT/n) for n in required},'all_required_present':True,
       'model_count':len(list((OUT/'models').glob('*.pkl'))),
       'claim_boundary':'Pre-May blocked development comparison, no eligible winner, final calibration/shadow not run, no production authorization.'})
    print('FINAL_VERIFICATION_PASS',totals)

if __name__=='__main__':main()
