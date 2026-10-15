"""Verify byte seals, independent counterfactual inputs and measured diagnostics."""
from pathlib import Path
import argparse,gzip,hashlib,json,subprocess,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.partial_canary import CORE_FILES,PARENT

REQUIRED=('TRAJECTORY_TRACKING_DESIGN_KO.md','PAPER_SECTION_V_METHOD_MAPPING.md',
 'DAYAHEAD_TRACKING_REFERENCE.npz','PLANNING_TARGET_IDENTITY.json','TRACKING_POLICY_SPEC.json',
 'TRACKING_JOB_DECISION_LEDGER.csv','KNOWN_PLANNING_ALLOCATION.csv','UNKNOWN_ACTUAL_ALLOCATION.csv',
 'MIGRATION_ELIGIBILITY_FUNNEL.csv','TRACKING_PCC_GPU_COMPARISON.csv','C0_C1_C2_C3_METRICS.csv',
 'PREPLACE_MIGRATION_ABLATION.csv','SOURCE_CASE_POLICY_SHA_MANIFEST.json',
 'SOLVER_AND_CONTROLLER_RUNTIME_LEDGER.json','FRESH_AC_STATUS.json','REGRESSION_RESULTS.json','FINAL_REVIEW_KO.md',
 'DAYAHEAD_TRACKING_REFERENCE_SHA.json')


def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def main(out):
    for name in CORE_FILES+('actual.py','actual_validation.py','dday_boundary.py','a_engine.py'):
        assert (ROOT/'v42_integration'/name).read_bytes()==subprocess.check_output(['git','show',PARENT+':v42_integration/'+name],cwd=ROOT)
    manifest=read(out/'SOURCE_CASE_POLICY_SHA_MANIFEST.json')
    for name,r in manifest['source_files'].items():
        assert hashlib.sha256((ROOT/'v42_integration'/name).read_bytes()).hexdigest()==r['sha256']
    runtime=read(out/'SOLVER_AND_CONTROLLER_RUNTIME_LEDGER.json')
    assert runtime['A1_Native_seconds']==0 and runtime['A1_inflight'] is None
    assert runtime['Native_retry_calls']==0
    assert runtime['cumulative_execution_wall_seconds']<=1200
    for r in runtime['old_ledgers_before']:
        assert hashlib.sha256(Path(r['path']).read_bytes()).hexdigest()==r['sha256']
    evidence=read(out/'COMPRESSED_EVIDENCE_MANIFEST.json')
    for r in evidence:
        raw=gzip.decompress((out/r['gzip']).read_bytes())
        assert len(raw)==r['bytes'] and hashlib.sha256(raw).hexdigest()==r['sha256']
    labels=[p.name[:2] for p in out.glob('C?_METRICS.json')]
    assert {'C0','C2'}<=set(labels)
    for label in labels:
        d=read(out/(label+'_METRICS.json'));a=np.load(out/(label+'_ACTUAL_ARRAYS.npz'),allow_pickle=False)
        np.testing.assert_allclose(a['GPU'],a['Known_GPU']+a['Unknown_GPU'],rtol=0,atol=1e-8)
        np.testing.assert_allclose(a['Compute'],a['Known_Compute']+a['Unknown_Compute'],rtol=0,atol=1e-8)
        assert a['GPU'].shape==(16,12) and d['known_unknown_overlap_UIDs']==0
        assert d['Known_command_SHA_unchanged'] and d['controller_global_optimizer_calls']==0
        assert d['QoS_intentional_budget_excess_UIDs']==0
        assert d['actual_power_from_occupancy'] and not d['Full96_Actual_PASS']
    ac=read(out/'FRESH_AC_STATUS.json')
    assert ac['status']=='PARTIAL_AC_NOT_AUTHORIZED' and ac['AC_rho'] is None and ac['AC_calls']==0
    reg=read(out/'REGRESSION_RESULTS.json');assert reg['PASS'] and reg['passed']==242
    files=[]
    for name in REQUIRED:
        p=out/name;assert p.is_file() and p.stat().st_size
        files.append(dict(file=name,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size))
    receipt=dict(PASS=True,required_artifacts=len(files),artifacts=files,executed_partial_diagnostics=labels,
        new_E1_A1_certified=False,original_core_byte_identity=True,historical_ledgers_byte_identity=True,
        measured_grid_hard_rows={l:len(read(out/(l+'_METRICS.json'))['grid']['hard_violations']) for l in labels},
        evidence_delivery_verification_is_not_grid_or_Full96_PASS=True,Native_calls=0,
        cumulative_execution_wall_seconds=runtime['cumulative_execution_wall_seconds'])
    (out/'DELIVERY_VERIFICATION.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in receipt.items() if k!='artifacts'}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);main(parser.parse_args().output)
