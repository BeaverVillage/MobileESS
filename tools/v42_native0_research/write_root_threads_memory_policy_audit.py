"""Read-only Root thread paths/actual receipts/system memory; no model imports."""
from pathlib import Path
from datetime import datetime,timezone
import ctypes,hashlib,json,subprocess
from ctypes import wintypes
import psutil

OUT=Path(r'D:\v42_root_analysis_audit_20261012')
SOURCE=Path(r'D:\v42_svr11_epoch18r_20261011')
NATIVE0=Path(r'D:\v42_dense_response_development_repair_20261011')
ROOT=Path(r'D:\v42_dense_response_root_measurement_20261011')
RESULT=NATIVE0/'dates/B2/2025-05-01/attempts/native0_restored/output'
def now():return datetime.now(timezone.utc).isoformat()
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def record(path):return dict(path=str(path),bytes=path.stat().st_size,sha256=sha(path))
def git(*args):return subprocess.check_output(['git',*args],cwd=SOURCE,text=True,encoding='utf-8').strip()
def gib(value):return value/1024**3
class PerformanceInformation(ctypes.Structure):
 _fields_=[('cb',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in (
  'CommitTotal','CommitLimit','CommitPeak','PhysicalTotal','PhysicalAvailable','SystemCache',
  'KernelTotal','KernelPaged','KernelNonpaged','PageSize')]+[(n,wintypes.DWORD) for n in ('HandleCount','ProcessCount','ThreadCount')]
def current_system_memory():
 p=PerformanceInformation();p.cb=ctypes.sizeof(p)
 if not ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(p),p.cb):raise ctypes.WinError()
 ram=psutil.virtual_memory()
 return dict(UTC=now(),RAM_total=ram.total,RAM_available=ram.available,RAM_used=ram.used,
  RAM_used_percent=ram.percent,Commit_total=p.CommitTotal*p.PageSize,Commit_limit=p.CommitLimit*p.PageSize,
  Commit_available=(p.CommitLimit-p.CommitTotal)*p.PageSize,Commit_peak=p.CommitPeak*p.PageSize)

paths=[
 ('v42_common_mess/model.py',37,42,'Builder defaultsThreads1, then resetsThreads1 after arbitrary numeric_parameters overrides.'),
 ('v42_common_mess/engine.py',23,27,'Unrestricted Full profile explicitly setsThreads1.'),
 ('v42_ultracompact/native_readback.py',7,10,'Root requested profileThreads1.'),
 ('v42_ultracompact/native_readback.py',27,33,'Actual readback must equal every ROOT_PARAMETERS value before Native entry.'),
 ('tools/validate_svr11_root180.py',49,70,'ProbeBudget rejects actualThreads!=1; applies actual cap/readback before optimize.'),
 ('tools/validate_svr11_dense_restore.py',321,330,'Native0 selected model is built with ROOT_PARAMETERS and actual readback is checked; optimize is denied.'),
 ('v42_common_mess/budget.py',38,54,'StageBudget only delegates measured time cap to parent; thread force remains builder/parent. No edits made.'),
 ('v42_may_campaign_native90/budget.py',82,94,'Campaign DateBudget forcesThreads1 before Native; includes A and M scopes, unchanged.'),
 ('v42_may_campaign_native90/execution.py',65,77,'Campaign execution guard rejects actualThreads!=1.'),
 ('v42_native/solver.py',83,89,'Native original solver forceThreads1 and measured remaining TimeLimit on each objective; unchanged.'),
 ('v42_bootstrap/m1.py',88,88,'Historical bootstrap common solve loop setsThreads1; unchanged.'),
 ('v42_m1_research/lb.py',151,158,'Inherited scientific builder setsThreads1; unchanged.'),
 ('v42_svr11/controller.py',20,23,'Dispatch request recordsThreads1; worker/concurrency policy unchanged.'),
 ('v42_common_mess/model.py',8,20,'Process RSS/private/high-water and actual RAM/commit counters are stored separately.'),
 ('v42_common_mess/engine.py',214,240,'Solver MemUsed/MaxMemUsed attributes differ from whole-process memory_after_native.'),
 ('v42_svr11/resources.py',13,32,'Windows GetPerformanceInfo commit counters and new-dispatch admission, no OS paging configuration change.')]
source_records=[]
for name,start,end,meaning in paths:
 source_records.append(dict(file=str(SOURCE/name),start=start,end=end,meaning=meaning,sha256=sha(SOURCE/name)))
readbacks=[]
for name in ('FINAL_NATIVE0_READBACK/ACTUAL_PARAMETERS.json',
 'INITIALIZATION/F1_STATIONARY_FULL_REPRESENTATIVES/ACTUAL_PARAMETERS_BEFORE_NATIVE.json',
 'FRESH_U4/ACTUAL_PARAMETERS_BEFORE_NATIVE.json','FULL_ROOT_ONCE/ACTUAL_PARAMETERS_BEFORE_NATIVE.json'):
 path=RESULT/name;packet=read(path);parameters=packet['actual_parameters']
 readbacks.append(dict(record(path),parameters={k:parameters[k] for k in (
  'Threads','Method','Crossover','NodeMethod','TimeLimit','FeasibilityTol','OptimalityTol','IntFeasTol',
  'NumericFocus','ScaleFlag','MIPGap','MIPGapAbs','NodefileStart','NodefileDir')},
  verification=packet.get('verification'),rows=packet['rows'],columns=packet['columns'],nonzeros=packet['nonzeros']))
full=read(RESULT/'FULL_ROOT_ONCE/RESULT.json');validation=read(ROOT/'ROOT180_VALIDATION.json');ledger=read(ROOT/'NATIVE_RUNTIME_LEDGER.json')
seal=read(ROOT/'SOURCE18_SEAL.json')
memory=full['memory_after_native'];live=current_system_memory()
native_calls=[{k:c[k] for k in ('track','label','effective_TimeLimit','Native_Runtime','Native_status','root_completed') if k in c} for c in ledger['calls']]
historical=read(OUT/'PR131_PRIMARY_REFERENCE_ONLY.json')
parent_matrix=read(OUT/'PR131_PARENT_SOURCE_MATRIX_IDENTITY.json')
resources={label:read(OUT/f'PR131_RESOURCE_ROOT_LP_METHOD2_{label}.json') for label in ('ORIGINAL','COMPACT')}
historical_source=[]
for source in historical['selected_source_diffs']:
 if source['filename'] not in ('v42_root_diagnostics/common.py','v42_root_diagnostics/worker.py'):continue
 lines=[];line_number=0
 for line in source['patch'].split('\n'):
  line=line.rstrip('\r')
  if line.startswith('@@'):
   import re
   line_number=int(re.search(r'\+(\d+)',line).group(1))-1
  elif line.startswith('+') and not line.startswith('+++'):
   line_number+=1
   if any(word in line for word in ('LP_POLICY=','MIP_POLICY=','Gurobi_Threads=','policy=dict')):lines.append(dict(line=line_number,text=line[1:]))
  elif line.startswith(' '):line_number+=1
 historical_source.append(dict(path=source['filename'],url=source['blob_url'],exact_head=historical['headRefOid'],selected_lines=lines))

checks=dict(all_actual_readbacks_Threads1=all(r['parameters']['Threads']==1 for r in readbacks),
 Full_readback_PASS=readbacks[-1]['verification']['PASS'] is True,
 Native0_readback_PASS=readbacks[0]['verification']['PASS'] is True,
 Full_TimeLimit600=readbacks[-1]['parameters']['TimeLimit']==600.,
 Root_source_SHA_matches=seal['source_SHA']==ledger['source_SHA']==validation['source_SHA']=='146bf39f5e4f9d720ef7118051edbcdc58b96ca3d83af31c3e7bd5349f1fecd8',
 current_thread_sources_match_execution_seal=all(sha(SOURCE/n)==seal['execution_sources'][n] for n in {p[0] for p in paths} if n.startswith('v42')),
 Root_report_INCOMPLETE=validation['classification']=='ROOT_INCOMPLETE' and validation['native_root_completion']['completed'] is False,
 single_Full_call=sum(c['track']=='M_FULL_MILP' for c in ledger['calls'])==1,
 current_worktree_clean=not git('status','--porcelain=v1'),
 historic_policy_actual_Threads4=all(r['Gurobi_Threads']==4 for r in resources.values()))
receipt=dict(schema='V42_ROOT_THREADS_AND_MEMORY_READ_ONLY_POLICY_AUDIT_V1',UTC=now(),PASS=all(checks.values()),checks=checks,
 source=record(ROOT/'SOURCE18_SEAL.json'),current_Git_HEAD=git('rev-parse','HEAD'),current_execution_SHA=seal['source_SHA'],
 prerequisite='Source19 Multi-Time static verdict officially CLOSED: candidate1 LP implied, added full rows0, Native0, MULTITIME_LB_UNPROVEN.',
 current_user_policy=dict(Threads=1,worker_policy='UNCHANGED_CURRENT_WORKERS',Threads2_or4_recommendation=False,
  Threads2_or4_run_authorized=False,new_heavy_analysis='NATIVE0_ONLY',VirtualMemory_or_paging_changes=False,
  StageBudget_A1_A2_NativeStop_userA_commonStop_changes=False),
 source_force_paths=source_records,actual_pre_Native_readbacks=readbacks,
 completed_native_runtime_ledger=record(ROOT/'NATIVE_RUNTIME_LEDGER.json'),completed_native_calls=native_calls,
 full_observation=dict(result=record(RESULT/'FULL_ROOT_ONCE/RESULT.json'),Native_Runtime=full['Native_Runtime'],
  requested_TimeLimit=600.,Native_status=full['Native_status'],Native_Work=full['Native_Work'],
  Root_status=full['Root_LP_status'],Root_incomplete_elapsed_seconds=full['Root_LP_seconds'],
  Root_completed_seconds=None,Presolve_seconds=full['Presolve_seconds'],Crossover_seconds=full['Crossover_seconds'],
  Solver_MemUsed_GB=full['Solver_MemUsed_GB'],Solver_MaxMemUsed_GB=full['Solver_MaxMemUsed_GB'],
  whole_process_and_system_after_native=memory,
  converted_GiB={k:gib(v) for k,v in memory.items()},
  RAM_used_percent_at_return=100*memory['RAM_used']/memory['RAM_total'],
  Commit_used_percent_at_return=100*memory['Commit_total']/memory['Commit_limit']),
 postvalidation_memory=validation['memory'],current_read_only_system_snapshot=live,
 metric_scope=[
  'Solver MemUsed/MaxMemUsed are solver attributes, not whole Python/CSR/proof/helper/baseline process memory.',
  'peak_RSS and peak_private_commit from Windows process memory_info are process-lifetime high-water counters: restore, verification, selected-model construction, initialization/U4/Full can contribute. They are not isolated Full600 interval peaks.',
  'RAM/commit at return, postvalidation, and current snapshot are distinct system-wide instants and include other processes. No synchronous whole-system RAM or commit peak trace is available in these saved snapshots.',
  'System Commit_peak is a global historical high-water counter, not timestamped to this Full run. Commit_peak==Commit_limit does not prove this Root run exhausted system commit.',
  'The user reports about90% memory with two workers. Its source/PIDs/timestamp and memory metric are not paired here with the single-process repaired Source18 Root telemetry. It is a separate user-reported operational constraint; no two-worker or multithread capacity is inferred from this Root.',
  'NodefileStart0.5/NodefileDir onD are existing solver disk policies; they do not establish low Root matrix/factor/process memory or authorize changing OS virtual memory.'
 ],
 PR131_reference_only=dict(primary=record(OUT/'PR131_PRIMARY_REFERENCE_ONLY.json'),url=historical['url'],exact_head=historical['headRefOid'],
  historical_matrix_identity=parent_matrix,historical_source_paths=historical_source,
  historical_LP_Method2_seconds=dict(Original=74.080,Compact=128.812),
  historical_MIP_original_Root_seconds=208.621,historical_MIP_compact_Root_complete=False,
  historical_resource_instant_RootLP={label:dict(UTC=r['utc'],Gurobi_Threads=r['Gurobi_Threads'],
   RAM=r['RAM'],independent_jobs_allowed=r['independent_jobs_allowed'],resource_contention_absence_required=r['RESOURCE_CONTENTION_ABSENCE_REQUIRED']) for label,r in resources.items()},
  current_transfer_rejected=True,
  reasons=[
   'Latest user withdrew higher-thread recommendation and requiresThreads1/currentworkers. Historical measurement is not authorization.',
   'PR131 uses different PR126 science/matrix/anchor and Original954560x316743/8282350NNZ or Compact972540x316839/12678118NNZ. Current Dense is715596x354277/7911369NNZ with different Forecast/SVR11 response.',
   'Historical fast74/129s results are fresh fully relaxed LPs; its MIP Root differed, Original208.621s and Compact incomplete at300s. Current result is one MIP Root601.897s with incomplete crossover.',
   'Historical LP_POLICY usesThreads4/NumericFocus1/FeasibilityTol1e-8/OptimalityTol1e-8; current actual Full usesThreads1/NumericFocus3/1e-9. No same-source controlledThreads-only comparison exists.',
   'Historical resource receipts are before-run system instants with~18–20GB RAM available and explicitly allow independent jobs. They are not matched whole-process peak or current two-worker memory evidence.',
   'PR131 was stopped after partial diagnostics; many arms and production wereNOT_RUN, and its body explicitly authorizes no further diagnostic solve. No current runtime or memory claim can be transferred.'
  ]),
 operations=dict(Native_calls_by_auditor=0,models_built=0,source_edits=0,thread_or_worker_config_mutations=0,
  StageBudget_A1_A2_NativeStop_userA_commonStop_edits=0,VirtualMemory_or_paging_mutations=0,
  old_LP_points_ingested=0,new_optimization_or_campaign_dispatch=0),
 conclusion='MAINTAIN_THREADS1_AND_CURRENT_WORKER_POLICY_NO_HIGHER_THREAD_RECOMMENDATION_OR_RUN')
path=OUT/'ROOT_THREADS_MEMORY_POLICY_PATH_AUDIT.json';path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
lines=['# Root thread paths and memory policy audit','',
 f"PASS:{receipt['PASS']}. KeepThreads1 and currentworker policy. NoThreads2/4 recommendation or run. Source executionSHA `{seal['source_SHA']}`; currentHEAD `{receipt['current_Git_HEAD']}`.",'',
 'Actual Native0, initialization, U4 and Full readbacks all reportThreads1. The common model forcibly resetsThreads1 after overrides, Full profile requests1, readback checks1, and ProbeBudget rejects any other value before Native. Campaign DateBudget/native/common builders also retain their existing1-thread guards. No runtime, StageBudget, A1/A2, NativeStop, userA/commonstop or worker configuration was changed.','',
 '| Current Source18 Full measurement | Recorded value |','|---|---:|',
 f"| Native Runtime / cap | {full['Native_Runtime']:.6f}s /600s |",
 f"| Root | INCOMPLETE; interrupted elapsed{full['Root_LP_seconds']:.2f}s; completionNULL |",
 f"| Whole-process lifetime peakRSS | {gib(memory['peak_RSS_bytes']):.3f}GiB |",
 f"| Whole-process lifetime peakprivate commit | {gib(memory['peak_private_commit_bytes']):.3f}GiB |",
 f"| Solver MaxMemUsed | {full['Solver_MaxMemUsed_GB']}GB (separate solver metric) |",
 f"| System RAM available at Native return | {gib(memory['RAM_available']):.3f}GiB |",
 f"| System commit headroom at Native return | {gib(memory['Commit_available']):.3f}GiB |",'',
 'Process peaks include all work in that process lifetime; system snapshots include other processes. A recorded global Commit_peak equal to limit has no Root-specific timestamp. The user’s two-worker≈90% observation is retained separately and provides no authorization to extrapolate one-process Root capacity or increase threads.','',
 'PR131 is historical reference only. Its74.080/128.812sMethod2 results were fully relaxed LPs atThreads4 on different matrices and looser precision; MIP Root was208.621s forOriginal and incomplete forCompact at300s. Concurrent jobs were allowed and resource receipts are pre-run instants. Its stopped partial study supplies neither a current controlledThreads comparison nor matched current memory peaks, and cannot override the latest1-thread policy.','',
 'Exact source line ranges and SHA records, all four actual readbacks, ledger/runtime, raw memory values, fresh read-only RAM/commit snapshot and primary PR131 references are in the JSON receipt. Native/model/source/config/paging actions by this auditor:0. Campaign remainsHOLD.','',
 'Source paths (unchanged SHA256):','']
for entry in source_records:
 lines.append(f"- [{Path(entry['file']).name}:{entry['start']}]({entry['file'].replace(chr(92),'/')}:{entry['start']}) — {entry['meaning']} SHA256 `{entry['sha256']}`")
lines+=['',f"Historical primary reference: [PR131]({historical['url']}), exacthead `{historical['headRefOid']}`. It authorizes no current run.",'']
path.with_suffix('.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
print(json.dumps(dict(PASS=receipt['PASS'],checks=checks,path=str(path),memory_peak_RSS_GiB=gib(memory['peak_RSS_bytes']),memory_peak_private_GiB=gib(memory['peak_private_commit_bytes']))))
