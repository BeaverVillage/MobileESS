"""Immutable successor preparation; no scientific process or result mutation."""
from pathlib import Path
import sys,shutil
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,now
root=Path(r'D:\v42_svr11_may_20261011_04');old=Path(r'D:\v42_svr11_may_20261011_03')
assert not (root/'CAMPAIGN_MANIFEST.json').exists()
(root/'hardware').mkdir(parents=True,exist_ok=True)
for p in (old/'hardware').iterdir():
    if p.is_file():shutil.copyfile(p,root/'hardware'/p.name)
atomic(root/'PREDECESSOR_DRAIN_CONTRACT.json',dict(schema='SVR11_PREDECESSOR_DRAIN_CONTRACT_V1',
    manifest=record(old/'CAMPAIGN_MANIFEST.json'),source_SHA=read(old/'CAMPAIGN_MANIFEST.json')['execution_SHA'],
    dispatch_quiescence=record(old/'DISPATCH_QUIESCENCE_FOR_CONTEXT_FIX.json'),
    reason='Observed model MemoryError; retire completed independently compiled probes without changing physics',
    all_old_results_preserved=True,old_results_promoted=False,healthy_workers_terminated=0,UTC=now()))
atomic(root/'CONTEXT_RETENTION_DIAGNOSIS.json',dict(schema='SVR11_PROBE_CONTEXT_RETENTION_DIAGNOSIS_V1',
    retained_empty_contexts_after_gc=8,original_registries_before=[1,1],original_registries_after=[9,9],
    corrected_registries_after=[1,1],corrected_empty_contexts_alive=0,diagnosis_compile_calls=0,diagnosis_AC_calls=0,
    observed_MemoryError_results=[record(Path(r'D:\v42_svr11_may_20261011_02')/'dates/B2'/d/'attempts/attempt_01/RESULT.json')
        for d in ('2025-05-01','2025-05-02','2025-05-03')],
    remedy='Detach exact completed context owners; preserve existing CFFI automatic ctx_Dispose; no raw pointer release',
    independent_source_initial_context_per_probe_preserved=True,forecast_prefix_and_measurement_unchanged=True,
    no_new_algorithm=True,healthy_worker_terminated=0,UTC=now()))
