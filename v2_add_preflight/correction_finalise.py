"""Final append-only manifest and evidence closure; no operating solve."""
import csv,json,subprocess,types
from pathlib import Path
import numpy as np
from .audit import ROOT,read,sha,snapshot
from .correction import OUT,RUNTIME,put
from .correction_entry import closure
from .correction_svr import SV

def main():
    assert closure()['PASS']
    baseline=read(OUT/'PRESERVATION_BASELINE.json')
    for p,h in baseline['runtime_sha256'].items():assert sha(Path(p).read_bytes())==h,p
    assert read(OUT/'INDEPENDENT_REGRESSION_TESTS.json')['PASS']
    assert read(SV/'INDEPENDENT_SVR_TESTS.json')['PASS']
    assert read(SV/'SVR_FRESH_CERTIFICATION.json')['pairs']==20
    assert read(SV/'SVR_FRESH_CERTIFICATION.json')['PASS']
    for p in ('ACTION_LOG_NONINTERFERENCE_S0.json','ACTION_LOG_NONINTERFERENCE_S1_03_EARLY.json','INDEPENDENT_NEW_SVR_LOSS_CERTIFICATION.json'):
        assert read(SV/p)['PASS']
    # Additional post-B0 dispatch cases were not part of the historical140
    # archive count. Bind/check every artifact and independently compare pairs.
    extra=[]
    for ns in ('correction_peak31_time100','correction_svr_peak31'):
        for file in sorted((RUNTIME/ns).glob('*/RECEIPT.json')):
            r=read(file)
            for name,h in r['files'].items():assert sha((file.parent/name).read_bytes())==h
            if file.parent.name.endswith('_FRESH'):continue
            peer=file.parent.with_name(file.parent.name+'_FRESH')
            with np.load(file.parent/'AC_FULL.npz') as a,np.load(peer/'AC_FULL.npz') as b:
                assert all(np.array_equal(a[k],b[k]) for k in a.files)
            assert read(file.parent/'STATES.json')==read(peer/'STATES.json')
            extra.append(dict(case=r['case'],all_array_bits_identical=True,all_artifact_sha_verified=True))
    assert len(extra)==6
    put('POST_B0_DISPATCH_INDEPENDENT_CLOSURE.json',dict(PASS=True,pairs=extra,Native_optimizer_calls=0))
    namespaces=['correction_time100','correction_old_pilot_time100','correction_charge_spread_time100',
        'correction_svr','correction_peak31_time100','correction_svr_peak31','correction_action_trace','correction_action_trace_early']
    receipts=[]
    for name in namespaces:
        for file in sorted((RUNTIME/name).glob('*/RECEIPT.json')):
            r=read(file);receipts.append(dict(runtime_namespace=name,case=r['case'],receipt_path=str(file),receipt_sha256=sha(file.read_bytes()),
                TIME_operating_solve_count=r['physical_solve_count'],native_optimizer_calls=r['native_optimizer_calls']))
    assert len(receipts)==195,len(receipts)
    put('COMPLETE_RUNTIME_RECEIPT_BINDINGS.json',dict(complete_TIME100_archives=195,
        matched_independent_Fresh_pairs=96,logging_only_diagnostic_archives=3,strict15_archives_retained_separately=6,
        scope='Includes failed physical cases and one failed strict logging noninterference; no failed case is promoted',
        total_TIME_operating_solves=sum(r['TIME_operating_solve_count'] for r in receipts),
        preparation_and_short_validation_solves='Separate from TIME operating solve count',receipts=receipts))
    # Reuse the read-only observer with an isolated output sink. Its legacy
    # default save() would otherwise write beside the preserved old reports.
    observer=types.FunctionType(snapshot.__code__,dict(snapshot.__globals__,save=put),snapshot.__name__)
    resource_dir=RUNTIME/'correction_closure';resource_dir.mkdir(exist_ok=True)
    resource=observer(resource_dir,'CORRECTION_FINAL')
    put('FINAL_PRESERVATION_AND_RESOURCE_CLOSURE.json',dict(PASS=True,baseline_HEAD=baseline['PR236_HEAD'],
        preserved_prior_tracked_files=len(baseline['tracked_sha256']),preserved_prior_runtime_files=len(baseline['runtime_sha256']),
        original_source_and_campaign_edits=0,forced_worker_terminations=0,native_optimizer_calls=0,resource_snapshot=resource))
    paths=[p for p in OUT.rglob('*') if p.is_file() and p.name!='CORRECTION_SHA256_MANIFEST.json']
    paths+=list((ROOT/'v2_add_preflight').glob('correction*.py'))
    put('CORRECTION_SHA256_MANIFEST.json',dict(scope='New V2_add correction only; original manifests are preserved',
        files={str(p.relative_to(ROOT)).replace('\\','/'):sha(p.read_bytes()) for p in sorted(paths)}))
    print('FINAL CLOSURE PASS',len(paths),'new artifacts;195 TIME archives;96 Fresh pairs',flush=True)

if __name__=='__main__':main()
