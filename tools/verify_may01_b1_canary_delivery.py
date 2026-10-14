"""Verify stopped Canary evidence and preserve exact setup files compressed."""
from pathlib import Path
import argparse,gzip,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.partial_canary import PARENT,CORE_FILES

REQUIRED=('MAY01_B1_CANARY_FINAL_KO.md','A1_KNOWN_OPTIMIZATION_RECEIPT.json',
 'PARTIAL_POLICY_COVERAGE_AUDIT.json','UNKNOWN_FROZEN_POLICY_SHA.json','KNOWN_ALLOCATION_UID.csv',
 'UNKNOWN_POLICY_EXECUTION_UID.csv','MIGRATION_FUNNEL.csv','PREPLACE_MIGRATION_ABLATION.csv',
 'R0_R1_R2_R3_COMPARISON.csv','UNKNOWN_FALLBACK_EXECUTION_AUDIT.json','PARTIAL_ACTUAL_POWER_COMPARISON.csv',
 'PARTIAL_FRESH_AC_COMPARISON.json','NATIVE_AND_WALL_RUNTIME_LEDGER.json','SOURCE_CASE_POLICY_MANIFEST.json')


def main(out):
    for name in CORE_FILES:
        assert (ROOT/'v42_integration'/name).read_bytes()==subprocess.check_output(['git','show',PARENT+':v42_integration/'+name],cwd=ROOT)
    contract=json.loads((out/'BUDGET_ATTRIBUTION_FREEZE.json').read_text())
    assert contract['canary_runner_source_sha']==hashlib.sha256((ROOT/'v42_integration/partial_canary.py').read_bytes()).hexdigest()
    for record in contract['old_ledger_receipts']:
        raw=Path(record['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==record['sha256']
    runtime=json.loads((out/'NATIVE_AND_WALL_RUNTIME_LEDGER.json').read_text())
    assert runtime['runtime_recorded']==0 and not runtime['new_B1_Research_ledger']['calls']
    assert runtime['new_B1_Research_ledger']['inflight'] is None
    assert runtime['watchdog']['wall_seconds']<=900 and runtime['watchdog']['external_workers_terminated']==0
    assert runtime['watchdog']['stop_reason']=='STAGE_WALL_LIMIT_A1_BUILD_AND_NATIVE'
    receipt=json.loads((out/'A1_KNOWN_OPTIMIZATION_RECEIPT.json').read_text())
    assert receipt['status']=='A1_NO_ACCEPTABLE_INCUMBENT' and not receipt['Native_Optimize_reached']
    compressed=[]
    for label in ('CASE','PREFLIGHT_ONLY/CASE','RUN_ATTEMPT02/CASE'):
        directory=out/label
        if not directory.exists():continue
        for path in sorted(directory.rglob('*')):
            if not path.is_file():continue
            target=out/'compressed_setup'/Path(label.replace('/','_'))/path.relative_to(directory)
            target=target.with_suffix(target.suffix+'.gz');target.parent.mkdir(parents=True,exist_ok=True)
            raw=path.read_bytes();target.write_bytes(gzip.compress(raw,mtime=0))
            assert gzip.decompress(target.read_bytes())==raw
            compressed.append(dict(original=str(path.relative_to(out)),payload=str(target.relative_to(out)),
                decompressed_sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)))
    artifacts=[]
    for name in REQUIRED:
        path=out/name;assert path.is_file() and path.stat().st_size
        artifacts.append(dict(file=name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size))
    result=dict(PASS=True,required_artifact_count=len(REQUIRED),artifacts=artifacts,compressed_setup=compressed,
        PR228_core_unchanged=True,old_Native_ledger_bytes_preserved=True,Native_Optimize_calls=0,
        Canary_attempt_wall_seconds=runtime['watchdog']['wall_seconds'],Actual_compared_policies=0,
        no_NEW_A1_performance_or_Full96_PASS_claim=True)
    (out/'DELIVERY_VERIFICATION.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(dict(PASS=True,required_artifact_count=14,compressed_setup_files=len(compressed),Native_calls=0)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);main(parser.parse_args().output)
