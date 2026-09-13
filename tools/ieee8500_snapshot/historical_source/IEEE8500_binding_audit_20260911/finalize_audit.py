import hashlib,json,time
from pathlib import Path
import psutil
H=Path(__file__).parent;P=H.parent/'IEEE8500_production_20260911'
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
cache={}
def sha(p):
    p=Path(p);key=str(p.resolve())
    if key not in cache:
        h=hashlib.sha256()
        with p.open('rb') as f:
            for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
        cache[key]=h.hexdigest()
    return cache[key]
def save(name,v):(H/name).write_text(json.dumps(v,indent=2,ensure_ascii=False),encoding='utf-8')
checks=[]
for name,path in [('preserved_stopped_production',H/'PRESERVED_PRODUCTION_SHA256.json'),('preexisting_source_topology_PCC_operating_authorities',P/'PROTECTED_AUTHORITIES_BEFORE.json'),('execution_inputs_code_coefficients',P/'PRODUCTION_EXECUTION_FREEZE.json'),('execution_v2_adapter',P/'PRODUCTION_EXECUTION_V2_FREEZE.json'),('read_only_audit_inputs',H/'READ_ONLY_SOURCE_SHA256.json')]:
    v=load(path);rows=v if isinstance(v,list) else v['files'];bad=[]
    for r in rows:
        p=Path(r['path'])
        if not p.exists():bad.append(dict(path=str(p),reason='MISSING'))
        elif sha(p)!=r['sha256']:bad.append(dict(path=str(p),reason='SHA256_MISMATCH',expected=r['sha256'],observed=sha(p)))
    checks.append(dict(scope=name,files_checked=len(rows),mismatches=bad,status='PASS' if not bad else 'FAIL'))
    print(name,len(rows),'drift',len(bad),flush=True)
running=[]
for p in psutil.process_iter(['pid','name','cmdline']):
    cmd=' '.join(p.info['cmdline'] or [])
    if (p.info['name'] or '').lower() in ('python.exe','pythonw.exe') and any(x in cmd for x in ['production_campaign.py','production_campaign_v2.py']):running.append(dict(pid=p.pid,command=cmd))
state=load(P/'CAMPAIGN_STATUS.json');stop=load(H/'GRACEFUL_STOP_RECEIPT.json')
checkpoints=[]
for p in sorted((P/'policies/B1/checkpoints').glob('*.json')):
    x=load(p);checkpoints.append(dict(path=str(p),sha256=sha(p),checkpoint_seconds=x['checkpoint_seconds'],actual_elapsed_seconds=x['actual_elapsed_seconds'],label='NONAUTHORITATIVE_PRE_AIDC_BINDING_AUDIT'))
save('PRESERVATION_VERIFICATION.json',dict(status='PASS' if all(c['status']=='PASS' for c in checks) and not running else 'FAIL',hash_checks=checks,running_production_processes=running,campaign_stop_status=state['status'],campaign_stop_exception=state.get('error'),B2_B3_not_started=not any((P/'policies'/x).exists() for x in ['B2','B3_M1','B3_A1','B3_MF']),saved_B1_checkpoints=checkpoints,graceful_stop=stop))
a=load(H/'BINDING_AUDIT.json');c=a['counts']
lines=['# IEEE8500 AIDC production binding audit — FAIL-CLOSE','',
'현재 실행과 그 산출물의 분류는 **NONAUTHORITATIVE_PRE_AIDC_BINDING_AUDIT**이다. Scientific result로 사용할 수 없으며 B0/B1/B2/B3 재실행도 금지한다. 이전 preflight PASS는 최종 V41R4 AIDC binding PASS를 의미하지 않는다.','',
'PID 50600에 Windows CTRL_C_EVENT를 전달했다. Python KeyboardInterrupt가 campaign 예외 처리 및 finally 정리 경로를 거쳐 프로세스가 종료되었다. 강제 kill은 사용하지 않았다. B1 도중 정지했으며 B2/B3는 시작되지 않았다. 기존 파일은 원위치에 보존했고 분류용 sidecar만 추가했다.','',
'| 항목 | 실행에서 독립 집계 | 요청한 production contract |','|---|---:|---:|',
f'| Installed GPU capacity | {a["installed_GPU_capacity"]} | 780 (capacity authority 일치) |',
f'| Reference jobs | {c["jobs"]} | 같은 날짜의 reference UID와 일치 |',
f'| Jobs with temporal options | {c["jobs_with_temporal_options"]} | 452 — 불일치 |',
f'| Jobs with spatial options | {c["jobs_with_spatial_options"]} | 동일 optimizer 정의로 집계 |',
f'| Jobs with migration options | {c["jobs_with_migration_options"]} | checkpoint >= 0 옵션 존재 |',
f'| Restored temporal candidates | {c["restored_temporal_candidate_count"]:,} | 117,252 — 불일치 |',
f'| Base candidates | {c["base_candidate_count"]:,} | 4,772,575 — 불일치 |',
f'| Total candidate universe | {c["total_candidate_count"]:,} | 4,889,827 — 불일치 |',
f'| PARTIAL/shared jobs included | {c["PARTIAL_shared_jobs"]} / {c["jobs"]} | 포함 확인 |','',
'Temporal jobs는 한 job의 서로 다른 option.start가 2개 이상인 경우, spatial jobs는 서로 다른 option.site가 2개 이상인 경우로 집계했다. 이는 기존 v40g.optimizer domain_counts 정의와 같다. Migration은 issue 시점 RUNNING에 한정하지 않으며, PENDING에서 첫 checkpoint 이후 migration이 가능한 작업도 포함한다. Standalone non-migration relocation이 있는 작업은 147개이고, candidate manifest의 initial-placement relocation 정의에서는 261개이다. 서로 다른 정의를 혼용하지 않았다.','',
'PARTIAL/shared는 requested_gpus < 4 × requested_nodes 규칙으로 원본 job ledger에서 다시 계산했다. 361개가 reference와 candidate universe에 모두 포함되며, temporal 39개 / spatial 311개 / migration 311개이다. Aggregate GPU occupancy에 포함되고 별도 shared-job 시설 전력을 추가하는 모델은 사용하지 않는다.','',
'GPU capacity vector (AIDC01–AIDC12): 80, 40, 80, 40, 100, 80, 40, 80, 40, 80, 40, 80. 합계 780 GPU. 일부 legacy module 상수의 624 값과 달리 실행의 site power 함수에는 frozen capacity 780 vector가 명시적으로 전달된다.','',
'날짜별 authority를 구분해야 한다. 실제 IEEE8500은 frozen operating date 2025-05-21의 V41R4 daily domain을 읽었고, 이 artifact 자체는 39 / 16,392 / 1,341,947로 동결되어 있다. 요구된 452 / 117,252 / 4,889,827은 로컬 V41R3-restored/V41R4 lineage의 2025-05-04 authority에 존재한다. V41R4 May runtime은 일별 domain 수치로 temporal 상수를 바인딩한다. 따라서 후보 수 차이를 곧바로 temporal 옵션 삭제로 해석할 수는 없다. 실제 May21 base 후보는 모두 보존되었다. 다만 현재 요청의 기대 contract와 다르므로 FAIL-CLOSE이며, 날짜나 workload를 교체하거나 기대 수치를 재해석해 PASS로 승인하지 않았다.','',
'확인된 모델 불일치:','',
'- 기존 B1은 v40g.optimizer의 공동 모델과 BoundedLex를 사용하며, B3-A1은 v41r4_b3_equivalent adapter로 같은 B1 모델을 재사용한다. IEEE8500은 새 aidc_search8500의 rotating 8/12/16-job neighborhood 모델을 사용했다. 이는 feeder/PCC/coefficient/operating-point 변경 범위를 넘는다.',
'- 기존 P1→P2→P3→P4→P5 단계별 solve와 상위 objective lock이 IEEE8500에서는 주로 P1, 매 다섯 번째 neighborhood의 P2, 그리고 acceptance 단계의 P3/P4/P5 비교로 대체되었다. 4-hour budget 변경 허용은 이 절차 변경을 승인한 것이 아니다.',
'- 기존 P5는 frozen original cohort rank를 사용하지만 IEEE8500 vector는 sorted 개별 UID rank를 사용한다. 같은 옵션·비용을 공유하는 non-migration cohort의 충분조건 witness 21개를 확인했다. 따라서 P5 coefficient도 동일하지 않다.',
'- IEEE8500이 기존 materialize/audit, power 및 reserve 함수를 일부 사용하고 exact AC에서 feasible하더라도 위 model/objective identity 위반을 해소하지 못한다.','',
'아래 SHA256은 파일 bytes의 SHA256이다. candidate_set_SHA는 압축 해제된 JSONL stream의 별도 SHA256이다. 모든 입력은 읽기 전용으로 조사했고 모델 import/optimization/OpenDSS 재실행은 하지 않았다. 기존 May B1/B2/B3 performance 및 Actual 데이터는 읽지 않았다.','',
'## Workload/reference 및 후보 authority','',
'| Source | SHA256 |','|---|---|']
records=[a['workload_reference'],a['workload_service_authority'],a['workload_input_receipt'],a['ML_snapshot'],a['PARTIAL_shared']['source_ledger'],a['daily_domain'],a['candidate_compressed_artifact'],a['expected_contract_local_evidence']['authority']]
records += [r for r in load(H/'READ_ONLY_SOURCE_SHA256.json')['files'] if r['path'].endswith('V41R2_780GPU_CAPACITY_AUTHORITY.json')]
def row(r):return '| ['+Path(r['path']).name+'](<'+r['path'].replace('\\','/')+'>) | `'+r['sha256']+'` |'
lines += [row(r) for r in records]
lines += ['',f'Combined decompressed candidate stream SHA256: `{a["candidate_decompressed_stream_sha256"]}`',f'Base decompressed candidate stream SHA256: `{a["base_decompressed_stream_sha256"]}`','','## AIDC power-model authority/source SHA256','','P_IT(site, active GPU) = [site capacity × 104.1606964512843 W + active GPU × 547.7239090195797 W] / 1000. PCC power는 frozen C1 및 선택일 D−1 weather를 적용하며 Q는 기존 PF 관계를 따른다. 입력/함수의 동일 SHA는 확인했으나 이 사실만으로 전체 optimization binding을 PASS로 처리하지 않는다.','','| Source | SHA256 |','|---|---|']
lines += [row(r) for r in a['AIDC_power_sources']]
lines += ['','## V41R4 B1/A1 model/objective/constraint source SHA256','','| Source | SHA256 |','|---|---|']+[row(r) for r in a['B1_A1_V41R4_production_sources']]
lines += ['','## 실제 IEEE8500 실행 source SHA256','','| Source | SHA256 |','|---|---|']+[row(r) for r in a['IEEE8500_executed_sources']]
lines += ['','## 정지 및 evidence 보존','','| Scope | Files | SHA drift |','|---|---:|---:|']+[f'| {x["scope"]} | {x["files_checked"]} | {len(x["mismatches"])} |' for x in checks]
lines += ['',f'현재 production PID 존재: {bool(running)}. 보존된 checkpoint: 30 min, 1 h. 2 h / 4 h checkpoint는 정지 전에 도달하지 않아 생성되지 않았다. 불완전한 run을 4-hour completed result로 사용하지 않는다.','',
'[정지 증거](<'+str(H/'GRACEFUL_STOP_RECEIPT.json').replace('\\','/')+'>), [보존 검증](<'+str(H/'PRESERVATION_VERIFICATION.json').replace('\\','/')+'>), [전체 보존 SHA manifest](<'+str(H/'PRESERVED_PRODUCTION_SHA256.json').replace('\\','/')+'>), [job별 집계](<'+str(H/'PER_JOB_BINDING_CENSUS.json').replace('\\','/')+'>).','',
'이 감사는 진단 결과만 작성했다. AIDC/MESS scale, topology, host/PCC mapping, stress authority 및 V41R4 원본 코드는 수정하지 않았다. Binding audit가 PASS하기 전 모든 policy 재실행을 금지한다.']
(H/'BINDING_AUDIT_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
files=[dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(H.iterdir()) if p.is_file() and p.name not in ['AUDIT_FREEZE_MANIFEST.json','AUDIT_FREEZE_MANIFEST.sha256']]
save('AUDIT_FREEZE_MANIFEST.json',dict(status='FAIL_CLOSE',classification='NONAUTHORITATIVE_PRE_AIDC_BINDING_AUDIT',files=files))
(H/'AUDIT_FREEZE_MANIFEST.sha256').write_text(sha(H/'AUDIT_FREEZE_MANIFEST.json')+'  AUDIT_FREEZE_MANIFEST.json\n',encoding='ascii')
print('AUDIT_REPORT_COMPLETE',flush=True)
