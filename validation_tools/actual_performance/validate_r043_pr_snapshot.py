"""Run focused immutable-source and monitor regressions without dispatching cases."""
from pathlib import Path
import argparse,json,sys,time

REPO=Path(__file__).resolve().parents[2]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source-root',type=Path,default=Path('D:/v44_r022_rowgen_20261017'))
    parser.add_argument('--output',type=Path,default=REPO/'docs/v44/r043_release_20261019/validation')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    # Load the sealed production package before pytest imports test modules.
    # It selects the existing byte-pinned scientific checkout, just as the live
    # entry point does. No Native/Actual/campaign dispatcher is invoked here.
    sys.path.insert(0,str(args.source_root))
    import v44_recovery_r043
    import pytest
    names=[
        'actual_audit_encoding','actual_audit_light','actual_bank_gate','actual_content_store','actual_control_key',
        'actual_performance_copy','actual_performance_memo_copy','actual_prefix','actual_queue_light','actual_record_light',
        'audit_archive','audit_chunk_store','audit_storage_maintenance',
        'r038_batch','r039_latency','r040_isolation','r041_prepare','r042_autostart','r043_owner',
        'recovery_r033','recovery_r034','recovery_r035','recovery_r037','storage_review_hold',
        'week2_dispatch','week2_sequence','monitor_bounds','monitor_live','monitor_phi_display','monitor_result_matrix']
    tests=[str(REPO/'tests'/f'test_v44_{n}.py') for n in names]
    started=time.monotonic()
    code=pytest.main([*tests,'-q','-p','no:cacheprovider',f'--junitxml={args.output / "REGRESSION.xml"}',
        '--basetemp=D:/MobileESS_V44/test_tmp/pr_r043_regressions_20261019'])
    (args.output/'RUN.json').write_text(json.dumps(dict(exit_code=int(code),elapsed_seconds=time.monotonic()-started,
        source_root=str(args.source_root),snapshot_root=str(REPO),test_files=tests,
        campaign_dispatch_invoked=False,live_scientific_sources_modified=False),indent=2),encoding='utf8')
    return int(code)

if __name__=='__main__':raise SystemExit(main())
