"""Report an unexecuted successor honestly while origin Workers continue."""
from pathlib import Path
import sys,shutil,subprocess,json,urllib.request
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,digest,now
from v42_common_campaign.authority import source_files
origin=Path(r'D:\v42_svr11_may_20261011_06');root=Path(r'D:\v42_svr11_may_20261011_08')
assert not (root/'CAMPAIGN_MANIFEST.json').exists()
folder=SOURCE/'docs/v42_svr11_final_20261011/pending08_snapshot';folder.mkdir(exist_ok=True)
for base,names in ((origin,('CAMPAIGN_LEDGER.json','SUPERVISOR_PROCESS.json','LIVE_OBSERVATION.json',
    'FORECAST_JUNCTION_RECEIPT_DIAGNOSIS.json','DISPATCH_QUIESCENCE_FOR_FORECAST_RECEIPT_FIX.json')),
    (root,('COEFFICIENT_IO_EQUIVALENCE.json','PREDECESSOR_DRAIN_CONTRACT.json'))):
    for n in names:shutil.copyfile(base/n,folder/n)
with urllib.request.urlopen('http://127.0.0.1:8796/api/state',timeout=10) as response:state=json.load(response)
assert Path(state['root'])==origin
atomic(folder/'MONITOR_STATE.json',state)
snapshot=dict(UTC=now(),current_execution_root=str(origin),current_execution_SHA=state['source_SHA'],
    counts=state['counts'],workers=state['workers'],pending_root=str(root),pending_checkout=str(SOURCE),
    pending_scientific_SHA=digest(source_files()),pending_scientific_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip(),
    pending_source_released=False,pending_scientific_workers_started=0,additional_healthy_workers_terminated=0,
    original_results_SHA_Runtime_preserved=True,tests='35 passed',handoff37='31 verified B0 only; B2 first six not all PASS')
atomic(folder/'SNAPSHOT.json',snapshot)
p=SOURCE/'docs/v42_svr11_final_20261011/README.md';text=p.read_text(encoding='utf8')
marker='\n\n# SVR11 official May 2025 campaign'
if text.startswith('Current official'):text=text[text.index(marker)+2:]
intro=f'''Current execution is **Epoch06**, Root `{origin}`, SHA `{state['source_SHA']}`. B0 all31 verified PASS are preserved. B2 May01–03 are technical FAIL after accepted M and Forecast96 replay: final source receipt comparison mistakenly treats the historical C: junction and identical canonical D: file as changed. [Diagnosis](pending08_snapshot/FORECAST_JUNCTION_RECEIPT_DIAGNOSIS.json) proves exact same SHA/length; no tolerance or physical-rating relaxation.

**Epoch08 is staged, not yet released or running.** Candidate commit `{snapshot['pending_scientific_commit']}`, Source bytes `{snapshot['pending_scientific_SHA']}`, Root `{root}`. It applies the same canonical path rule already used by checked() at the final Forecast recheck, plus an exact NPZ field-read cache. All96 actual coefficient values are bitwise equal; measured loading44.30s→0.80s with96→1 decompressions per field. This is a loader measurement, not a claim about full campaign speed.35 relevant tests PASS, including real-junction acceptance, changed content rejection, native clock equality, lifetime, reuse and Anytime/FAIL-CONTINUE.

The Epoch06 dispatcher alone is intentionally quiesced for safe handoff; May04–06 healthy model Workers continue naturally. Once those models reach96 slots, all six complete models (576 slots with original generation SHA04/06) and B0 all31 enter the frozen successor. Migration waits for every origin Worker before successor dispatch. Diagnosed technical FAIL dates retain original positive Native Runtime and receive bounded fresh Native0 attempts after actual following-date assignment; independent later dates also run. No Worker/Solver hot-patch or additional interruption. Epoch07 was an unexecuted candidate with failed predecessor inventory admission; its manifest and explicit isolation evidence are preserved and it must never run.

[Pending snapshot](pending08_snapshot/SNAPSHOT.json), [live origin ledger](pending08_snapshot/CAMPAIGN_LEDGER.json), [safe dispatcher quiescence](pending08_snapshot/DISPATCH_QUIESCENCE_FOR_FORECAST_RECEIPT_FIX.json), [exact coefficient equivalence](pending08_snapshot/COEFFICIENT_IO_EQUIVALENCE.json). Monitor remains http://127.0.0.1:8796 on the actual Epoch06 Workers until successor release. Handoff37 and monthly completion are not claimed. Earlier descriptions are historical.

'''
p.write_bytes((intro+text).encode())
body=f'''Fix slow SVR11 model loading and a false Forecast mutation check, while preserving completed work and live Solvers. Epoch06 actually restarted under the user's one-time authorization, reusing31 verified B0 dates and151 completed model slots. All first3 B2 models finished96 slots and M produced accepted feasible points, then a final receipt recheck incorrectly rejected a C: junction/D: path alias with identical SHA and size. Original FAIL/Native Runtime and all evidence are retained; FAIL-CONTINUE actually allocated May04–06.

Epoch08 candidate `{snapshot['pending_scientific_commit']}` / Source bytes `{snapshot['pending_scientific_SHA']}` is staged, not released or running. Normalize only the equivalent receipt path, retain exact SHA/length; cache immutable NPZ fields once while preserving detached per-slot copies. Real96-slot values are bitwise identical, loader44.30s→0.80s (not full campaign speed).35 relevant tests PASS. Model equations, native solve order, U4/A settings, physical ratings and budgets stay unchanged.

Current Epoch06 Root `{origin}` has {state['counts']['PASS']}PASS/{state['counts']['FAIL']}FAIL and healthy May04–06 Workers. Quiesce only its dispatcher; preserve Workers until natural completion, freeze all576 model slots plus B0 all31 into Epoch08 Root `{root}`, then migrate with bounded Native0 technical retries after next-date assignment and continue B0→B2→B1→B3. Existing monitor/Windows/hourly are retained and retargeted after release; no duplicate task or healthy Solver interruption. Epoch07 never ran and is isolated. Handoff remains31/37; monthly completion and successor execution are not claimed. Evidence: docs/v42_svr11_final_20261011/pending08_snapshot/. May2025 is retrospective, not an independent holdout.
'''
(root/'DRAFT_PR_BODY.md').write_bytes(body.encode())
print(json.dumps(snapshot,ensure_ascii=False))
