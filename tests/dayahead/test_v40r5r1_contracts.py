import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dayahead.v40r5r1.evaluate import *

def main():
    checks = []
    def check(name, value):
        assert value, name
        checks.append(name)
    frozen = read(OUT/'V40R5R1_R5_REFERENCE_FREEZE.json')
    for name, commit in [('R5 scientific',SCIENCE),('R5 receipt',BASE),('preregistration',PRE),('CAL freeze',CAL)]:
        check(name, git('rev-parse',commit)==commit)
        git('merge-base','--is-ancestor',commit,'HEAD')
    check('isolated branch',git('branch','--show-current')=='codex/v40r5r1-zero-inflation-aware-gate-correction')
    check('R5 frozen hashes',all(sha(ROOT/p)==h for p,h in frozen['frozen_files'].items()))
    check('R5 classification',frozen['classification']=='V40R5_BODY_FORECAST_INSUFFICIENT')
    check('R5 not selected',frozen['selected_model'] is None)
    check('full inherited protected scope',not snapshot()['protected_git_diff'])
    actual,_ = calculate(); saved=pd.read_csv(OUT/'V40R5R1_BODY_REEVALUATION.csv')
    pd.testing.assert_frame_equal(actual,saved,check_exact=False,rtol=1e-12,atol=1e-12)
    check('recomputed frozen prediction metrics',True)
    check('coverage partition identity',(actual.coverage_identity_abs_error<1e-14).all())
    contract=read(OUT/'V40R5R1_CORRECTED_EVALUATION_CONTRACT.json')
    check('positive bounds',contract['positive_Q90_coverage_bounds']==[.9,.95])
    check('overall diagnostic only',contract['overall_coverage']=='DIAGNOSTIC_ONLY_NO_UPPER_REJECTION')
    check('no new model/calibration',contract['model_fits']==contract['calibration_fits']==0)
    interp=read(OUT/'V40R5R1_INTERPRETATION.json')
    for key in ['FULL_R5_PIPELINE_SELECTED','OPTIMIZER_INTEGRATION','PRODUCTION_READY']:
        check(key,interp[key]=='NO')
    check('classification',interp['classification']==CLASSIFICATION)
    check('zero-inflation finding retained',read(OUT/'V40R5R1_ZERO_INFLATION_FEASIBILITY_AUDIT.json')['independent_finding_preserved']=='BODY_GATE_STRUCTURAL_INCOMPATIBILITY_DUE_TO_ZERO_INFLATION')
    check('no May/shadow reads',interp['May_scientific_reads']==interp['shadow_scientific_reads']==0)
    if '--closure' in sys.argv:
        check('receipt present',(OUT/'V40R5R1_FINAL_COMMIT_RECEIPT.json').exists())
        check('final Git clean',git('status','--porcelain')=='')
    report={'passed':len(checks),'failed':0,'checks':checks,'read_only':'--read-only' in sys.argv}
    if '--read-only' not in sys.argv: dump('TEST_REPORT',report)
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
