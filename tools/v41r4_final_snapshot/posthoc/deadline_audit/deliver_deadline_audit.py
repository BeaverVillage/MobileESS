from audit_deadlines import *
import statistics

def load(name):return json.loads((HERE/name).read_text(encoding='utf-8'))
def link(path,lo,hi=None):return f'[{path}:{lo}](https://github.com/BeaverVillage/MobileESS/blob/{COMMIT}/{path}#L{lo}'+(f'-L{hi}' if hi else '')+')'
def csv_write(out,name,rows):
    with (out/name).open('x',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader()
        for row in rows:
            writer.writerow({k:('TRUE' if v else 'FALSE') if isinstance(v,bool) else json.dumps(v,ensure_ascii=False,separators=(',',':')) if isinstance(v,(list,dict)) else v for k,v in row.items()})
def table(rows,columns):
    return '\n'.join(['| '+' | '.join(label for key,label in columns)+' |','| '+' | '.join('---' for _ in columns)+' |']+
        ['| '+' | '.join(str(row[key]) for key,_ in columns)+' |' for row in rows])

def main():
    scan=load('field_scan.json');coverage=load('job_field_coverage.json'); units=load('population_units.json'); records=load('computed_records.json')
    requests=load('request_input_checks.json'); bindings=load('method_hash_bindings.json'); sources=load('method_sources.json'); candidates=load('candidate_artifact_checks.json')
    assert not coverage['explicit_deadline_fields']
    assert len(requests)==124 and all(r['status']=='SCANNED' and not r['deadline_fields'] and not r['metadata_deadline_hits'] for r in requests)
    assert len(candidates)==677 and all(not r['candidate_deadline_columns'] for r in candidates)
    candidate_lookup={(r['day'],r['policy'],r['job_uid']):r for r in candidates}
    for row in records:
        source=candidate_lookup[(row['day'],row['policy'],row['job_uid'])]
        row['state_at_D00']=source['state_at_D00']
        row['migration_candidate_source_type']=source['source_type']
        row['candidate_audit_source_inside_archive']=source['member']
    flagged=[r for r in records if r['terminal_deferral_flagged']]
    assert len(flagged)==619 and len(records)==677
    # Review gate: only established diagnostic/solver-budget keys may appear in scan.
    # Exact scan findings are manually classified in the report and retained in manifest.
    reviewed=load('scan_review.json'); assert reviewed['status']=='REVIEWED_NO_JOB_DEADLINE_AUTHORITY'
    summary=[]
    for policy in ('B1','B3','ALL'):
        select=lambda rows:[r for r in rows if policy=='ALL' or r['policy']==policy]
        fs=select(flagged); ms=select(records); us=select(units)
        uid_days=collections.defaultdict(set)
        for r in fs:uid_days[r['job_uid']].add(r['day'])
        summary.append(dict(policy=policy,flagged_records=len(fs),unique_jobs=len(uid_days),
            deadline_authority_available=0,within_deadline=NA,at_deadline=NA,deadline_violations=NA,
            unavailable_deadline_records=len(fs),min_slack_h=NA,median_slack_h=NA,mean_slack_h=NA,P10_slack_h=NA,P90_slack_h=NA,max_slack_h=NA,
            maximum_violation_h=NA,total_migrations=len(ms),unique_migrated_job_uids=len({r['job_uid'] for r in ms}),
            all_migrations_deadline_authority_available=0,all_migrations_within_deadline=NA,all_migrations_deadline_violations=NA,
            all_migrations_deadline_unavailable=len(ms),all_selected_job_policy_day_records=sum(r['selected_jobs'] for r in us),
            all_selected_jobs_with_explicit_deadline_field=sum(r['selected_jobs_with_explicit_deadline_field'] for r in us),
            flagged_unique_job_day_count=sum(map(len,uid_days.values())),flagged_uids_repeated_across_days=sum(len(v)>1 for v in uid_days.values()),
            diagnostic_flagged_completion_le_RW=sum(r['diagnostic_completion_le_RW'] for r in fs),
            diagnostic_flagged_completion_eq_RW=sum(r['optimized_completion_slot']==r['RW_completion_slot'] for r in fs),
            diagnostic_flagged_completion_gt_RW=sum(not r['diagnostic_completion_le_RW'] for r in fs),
            diagnostic_all_migrations_completion_le_RW=sum(r['diagnostic_completion_le_RW'] for r in ms),
            diagnostic_all_migrations_completion_gt_RW=sum(not r['diagnostic_completion_le_RW'] for r in ms),
            diagnostic_min_RW_minus_completion_h=min(r['diagnostic_RW_minus_completion_hours'] for r in fs),
            classification='DEADLINE_AUTHORITY_NOT_ESTABLISHED',candidate_job_specific_deadline_checked=False))
    uid_days=collections.defaultdict(set)
    for r in flagged:uid_days[r['job_uid']].add(r['day'])
    repeated={uid:sorted(ds) for uid,ds in uid_days.items() if len(ds)>1}
    worst=sorted(flagged,key=lambda r:(r['diagnostic_RW_minus_completion_hours'],r['day'],r['policy'],r['job_uid']))[:20]
    worstcols=[('day','day'),('policy','policy'),('job_uid','job_uid'),('requested_GPU','GPU'),('reference_completion_slot','B0 end'),('RW_completion_slot','RW reference end'),('optimized_completion_slot','final end'),('diagnostic_RW_minus_completion_hours','RW minus final (h; diagnostic)'),('post_horizon_GPUh','post-H GPUh')]
    case=[r for r in flagged if (r['day'],r['job_uid']) in [('2025-05-15','8952973'),('2025-05-01','8571256')]]
    assert all(r['authoritative_deadline_slot']==NA and r['within_deadline']==NA for r in records)
    stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S');out=CORRECTED/f'deadline_audit_{stamp}'
    preserved={str(p):dict(sha256=digest(p.read_bytes()),size=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns) for p in CORRECTED.iterdir() if p.is_file()}
    out.mkdir(exist_ok=False)
    csv_write(out,'01_FLAGGED_619_DEADLINE_AUDIT.csv',flagged)
    csv_write(out,'02_ALL_MIGRATIONS_DEADLINE_AUDIT.csv',records)
    csv_write(out,'03_DEADLINE_SUMMARY.csv',summary)
    fields_text='\n'.join(f'- `{k}`: {v["member_count"]} archive members; {v["key_occurrences"]} key occurrences.' for k,v in sorted(scan['JSON_deadline_key_findings'].items())) or '- No matching JSON keys.'
    parquet_text='\n'.join(f'- `{name}`: '+', '.join(f'`{key}` ({v["nonnull_rows"]}/{v["rows"]} non-null diagnostic values)' for key,v in d['deadline_fields'].items()) for name,d in scan['parquet_schemas'].items() if d['deadline_fields']) or '- No matching Parquet columns.'
    evidence=f'''FINAL_DEADLINE_AUDIT_CLASSIFICATION: C

DEADLINE_AUTHORITY_NOT_ESTABLISHED

## Authority boundary

All numeric results come from the one final raw tar.gz identified in the manifest. The entire compressed archive and every member were freshly streamed and hashed. Subsequent byte reads from the extraction cache were accepted only after matching that fresh per-member size and SHA256; this cache was used solely as a verified mirror of the tar archive. Existing reaudit CSV is used for cohort keys only. PR #42 at `{COMMIT}` is used only for method semantics. Original upstream paths embedded in manifests were treated as provenance strings; no external workspace result was opened. The archive does not contain the original `V37_R4A_JOB_LEDGER.parquet`, `V37_R4A_D1_SNAPSHOT.parquet`, or `COMMON_INPUT_RECEIPT.json` bodies. Their construction is traced statically in PR source, not numerically supplemented from another workspace.

The four executable method files domain.py, migration.py, terminal.py and temporal_restore.py match the SHA256 in all 31 archived DAILY_DOMAIN_AUTHORITY files: 124/124 comparisons. Other PR sources below explain their lineage; they are not represented as separately hash-bound source files where that binding is unavailable. The user contract text is supporting method evidence in PR; archived hashes of the active implementations provide the execution binding.

## What the fields actually mean

| Field/boundary | Established meaning | Job-specific latest permitted completion? |
| --- | --- | --- |
| ISSUE_BEGIN=24, ISSUE_END=120 | Half-open D-day evaluation interval [24,120), 96 fifteen-minute slots | No |
| B0 reference completion | max end of same-day frozen B0 compute_segments | No |
| optimized/final completion | max end of final accepted DA compute_segments | Outcome, not a permission bound |
| RW_completion_slot | Completion of engineered requested-walltime reference scheduling, inherited from RW_scheduled_completion | Not established for checkpoint migration |
| RSP_start_slot | Current common Q90 reference earliest scheduled start, rematerialized under current capacity | Start reference, not completion deadline |
| safe_duration_slots/seconds | Frozen planned compute-service duration (PENDING current causal Q90; RUNNING requested remaining); segments preserve slots | Duration, not absolute due time |
| requested walltime / requested_seconds | Scheduler request duration; normalize converts wallclock_req to seconds | No archive-backed absolute deadline or interruption accounting rule |
| qos | Scheduler class/priority and flexibility eligibility input | No job-specific SLA end mapping found |
| state_at_issue | RUNNING/PENDING at the frozen issue cutoff; can differ from state at D00 | No |
| deadline/latest_finish/completion_deadline/reservation_window_end/SLA end/due time/eligible completion window | No usable job-level authority found in final job payloads or raw job request inputs | NOT_AVAILABLE |

Issue origin is D-1 18:00 fixed AEST, six hours before D00; it is a per-day relative issue coordinate, not Unix absolute time. Day-origin slot = issue-origin slot - 24. Thus 120 issue slots and 96 day slots denote the same evaluation end. See {link('dayahead/v41/data.py',39,49)} and archived AIDC_FIELD_AUTHORITY.slot_origin. All 62 B1/B3 boundary audits independently confirm H=96, issue_begin=24, issue_end_exclusive=120.

## RW: eight required questions

1. **Full name/definition:** RW is the **requested-walltime reference/reservation mode**. The recovered scheduler contract defines it as `running requested-remaining; pending requested-walltime; tier/FIFO first-fit`. There is no source basis for expanding RW as an independently authorized “reservation window” or an SLA deadline. {link('dayahead/v37/aidc_materializer.py',831,844)}
2. **Generation:** raw scheduler `wallclock_req` supplies duration; RUNNING uses max(requested minus elapsed, 900 seconds), PENDING uses requested duration. First-fit/tier/FIFO scheduling creates start/end slots, then the scheduled end is renamed `RW_scheduled_completion`. {link('dayahead/v37/aidc_materializer.py',390,412)}, {link('dayahead/v37/aidc_materializer.py',436,456)}, {link('dayahead/v37/aidc_materializer.py',560,573)}
3. **Measured/raw field?** No. The request duration is a raw scheduler input; RW completion is a generated schedule output. The archived JOB_REQUEST_INPUTS schemas contain wallclock_req and scheduler state/resource fields, but no RW or deadline field.
4. **Engineering-derived window?** Yes as a reference schedule completion, and as a derived noninferiority upper bound for eligible standalone time shifting. It is not a universal migration completion permission.
5. **Generated from current B0 Q90 reservation?** No. `common.build` separately rematerializes current Q90 B0 scheduling and `RSP_start_slot`, while assigning `RW_completion_slot=int(row.RW_scheduled_completion)` from the preserved V37 ledger. {link('dayahead/v41/common.py',39,80)} Current duration authority differs from the historical materializer's duration policy; no old Q90 values were imported as audit results.
6. **Absolute issue-slot coordinate?** It is an end coordinate in the common issue-origin slot axis, not a duration. “Absolute” here means a position on that axis, not a global timestamp.
7. **D-day coordinate?** No. Subtract 24 to express it relative to D00.
8. **Hard contract requiring every checkpoint migration to complete <= RW?** None established. In `terminal.start_bounds`, RW minus duration is an upper bound for eligible standalone shifted starts. The active migration branch preserves RW metadata equality but never compares migrated completion to RW. {link('dayahead/v41r1/terminal.py',59,74)}, {link('dayahead/v41r1/migration.py',87,111)}, {link('dayahead/v41/temporal_restore.py',20,35)}

## Candidate generation and acceptance

**Checkpoint migration candidate generation directly checked a job-specific completion deadline: NO.**

`domain.options` calls `migration_options(..., allow_cross_midnight=True)` for the active migration contract. Candidate completion is `reference_end + transfer_end + 1 - checkpoint`. With cross-midnight enabled, the timing gate requires `transfer_end + 1 < H`, not `finish <= H` and not `finish <= RW_completion_slot`. Site/rack GPU eligibility and WAN capacity/path constraints still apply. {link('dayahead/v40g/domain.py',39,57)}, {link('dayahead/v40g/domain.py',73,88)}

Materialization preserves compute service in two segments and encodes one-slot restart. `migration.check` requires fixed reference start and admission, deterministic first checkpoint, one migration, checkpoint < restart < 120, preserved immutable fields, and useful destination service before D24. RW is checked only for equality with the original metadata. `domain.audit` preserves total safe-duration slots, validates WAN transfers, and treats the reference tail as a service ledger rather than a cap. {link('dayahead/v40g/domain.py',102,133)}, {link('dayahead/v40g/domain.py',140,172)}, {link('dayahead/v41r1/migration.py',87,111)}

Standalone time shifting is a separate branch: a changed start cannot be combined with migration, and only that branch invokes terminal.check. Having an RW bound there does not establish a bound for the 677 migrated decisions. {link('dayahead/v41/temporal_restore.py',20,60)}

All 677 selected migrations were also matched to the archived per-job MIGRATION_CANDIDATES tables; all are marked migration_eligible and first-checkpoint-only, and those tables contain no deadline column. All 62 model boundary audits record terminal_residual_constraint_active=false and service_neutrality_constraint_active=false. No model was executed to perform these checks.

The frozen contract permits cross-midnight completion and explicitly deactivates per-job terminal residual and spill constraints. It requires useful in-day destination service. {link('dayahead/artifacts/v41r1_pending_running_migration/USER_FINAL_ONE_SHOT_MIGRATION_CONTRACT.txt',363,408)}, {link('dayahead/artifacts/v41r1_pending_running_migration/USER_FINAL_ONE_SHOT_MIGRATION_CONTRACT.txt',820,833)}

## Diagnostic names that must not be mistaken for authority

Archived `AIDC_FIELD_AUTHORITY.json` says `completion_lateness_role: evaluation versus existing RW completion; not a new objective variable`. `actual_dispatch.py` uses a local variable named deadline and emits contention_caused_RW_deadline_miss, but the accompanying `SLA_debt_authority` explicitly labels this diagnostic lateness versus frozen RW. The local variable's name does not establish a scheduler-provided deadline. {link('dayahead/v41/actual_dispatch.py',118,131)}, {link('dayahead/v41/actual_dispatch.py',150,156)}, {link('dayahead/v41/scientific_archive.py',140,168)}

`deadline_overrun_noninterruptible_work_seconds` is a separate optimizer search-loop budget diagnostic, computed as max(0, elapsed search time minus the fixed search budget). It is not a job completion deadline. See {link('v41r4_loop_budget.py',46,60)} and archived SEARCH_LOOP_WALL_CLOCK_AUDIT.json, whose budget_basis is CONTINUOUS_SEARCH_LOOP_WALL_CLOCK.

## Archive search scope and findings

All 49,444 JSON members and all 10,640 Parquet members were included in the field search (identical content deduplicated by archive SHA256), along with archived source/text/CSV files. Total covered members: {scan['member_files_covered']}; unique contents: {scan['unique_content_files_scanned']}; content bytes read: {scan['bytes_scanned']}. Search covered deadline/latest finish/latest completion/reservation window end/SLA end/due time/eligible completion window aliases. Every canonical final job was separately recursively inspected, so the primary population check is not dependent on a text search alone.

All 124 JOB_REQUEST_INPUTS files, including metadata, were inspected. All {sum(r['selected_jobs'] for r in units):,} selected job-policy-day records have no explicit job-level deadline field. This is absence of archived authority, not proof that the physical scheduler never had any other contract. Compressed FULL_CANDIDATES first-record schemas were inspected for all 46 unique compressed contents; complete compressed candidate/model internals were not used to infer a job deadline. Binary physical arrays were not interpreted as scheduler authority.

JSON search findings:

{fields_text}

Parquet deadline-like columns:

{parquet_text}

Every discovered deadline-like key is classified in the manifest's scan_review. No requested walltime, reference completion, optimized completion, horizon boundary, or diagnostic RW metric was substituted for an authoritative deadline.

## Source hash evidence

'''+table([dict(path=s['path'],sha=s['sha256'],binding='31 archived domain authorities' if any(b['source']==s['path'] for b in bindings) else 'PR42 lineage/supporting semantics') for s in sources],[('path','PR source'),('sha','SHA256'),('binding','binding')])+'\n'
    (out/'DEADLINE_AUTHORITY_EVIDENCE.md').write_text(evidence,encoding='utf-8')
    report=f'''FINAL_DEADLINE_AUDIT_CLASSIFICATION: C

**DEADLINE_AUTHORITY_NOT_ESTABLISHED**

619 total job-policy-day records(고유 job UID {len(uid_days)}개)를 독립적으로 재계산했다. 실제 허용된 job별 completion deadline/window를 archive와 frozen method authority에서 확정하지 못했다. 따라서 **within deadline 수, deadline violation 수, 최소 slack, 최대 violation은 모두 NOT_AVAILABLE**이다. 미확정은 619/619이며, “위반 0건” 또는 “619건 모두 deadline 이내”라는 의미가 아니다.

RW_completion_slot은 requested-walltime 기준으로 생성한 reference schedule의 완료 좌표다. eligible standalone time shifting에서는 이를 상한 계산에 쓰지만 checkpoint migration의 job-level deadline이라는 authority는 없다. `DEADLINE_AUTHORITY_EVIDENCE.md`에 생성 경로, 활성 계약의 SHA 일치, 검사 분기, 코드 줄 링크를 기록했다.

## Population과 판정

'''+table(summary,[('policy','policy'),('flagged_records','flagged records'),('unique_jobs','unique flagged UID'),('total_migrations','all migrations'),('deadline_authority_available','flagged authority available'),('within_deadline','within'),('deadline_violations','violations'),('unavailable_deadline_records','unavailable')])+f'''

B0/B2는 checkpoint migration이 0건이다. B1 전체 migration 333건, B3 전체 migration 344건, 합계 677건 모두 deadline compliance를 판정할 authority가 없다. 124개 최종 policy-day의 canonical job record 총 {sum(r['total_jobs'] for r in units):,}개를 읽었고, selected {sum(r['selected_jobs'] for r in units):,}개(각 policy {sum(r['selected_jobs'] for r in units if r['policy']=='B1'):,}개)의 deadline field coverage를 확인했다. 명시적 deadline 필드 보유 selected record는 0개다.

619는 unique job 수가 아니다. B1은 284개 UID/306 records, B3은 290개 UID/313 records이며, 합집합은 297개 UID다. 서로 다른 independent D-day에 재등장한 flagged UID는 17개, unique UID-day는 320개다. 동일 UID의 B1/B3 비교와 여러 D-day 출현을 별개의 job-policy-day로 유지했다. 월간 연속 job 실행으로 합치지 않았다.

## 경계와 계산

좌표는 D-1 issue 기준 15분 슬롯, 구간은 [start,end)이다. D00=24, D24=120이고 day-origin에서는 0과 96이다. `final_completion_slot = optimized_completion_slot = max(final frozen compute_segments.end)`로 계산했다. reference completion은 같은 날 B0의 max end다. `post_day_extension_slots=max(0,final_completion-120)`은 평가 경계 이후의 wall-clock 연장량이며, migration으로 추가된 연장량은 별도 completion_delay_slots 및 additional_post_horizon_GPUh다.

677건 전부 segment service 합이 B0 및 safe_duration_slots와 같고, final completion-reference completion = restart-checkpoint임을 확인했다. Transfer end는 event의 exclusive end를 사용했다; `WAN_transfer_complete_slot`의 마지막 occupied slot과 혼동하지 않았다. 이 completion은 사용자가 지정한 **frozen planned compute completion**이며 관측된 Actual runtime completion으로 바꾸지 않았다.

Authoritative deadline이 없으므로 deadline_slack_slots/hours와 within_deadline은 677행 전부 NOT_AVAILABLE로 보존했다. N_at_deadline, min/median/mean/P10/P90/max deadline slack도 계산 불가다. Post-horizon이라는 이유만으로 feasible/infeasible을 새로 판정하지 않았다.

## RW reference와의 진단 비교 — deadline 판정 아님

'''+table(summary,[('policy','policy'),('diagnostic_flagged_completion_le_RW','flagged final <= RW'),('diagnostic_flagged_completion_eq_RW','flagged final = RW'),('diagnostic_flagged_completion_gt_RW','flagged final > RW'),('diagnostic_all_migrations_completion_gt_RW','all migrations final > RW'),('diagnostic_min_RW_minus_completion_h','min(RW-final), h')])+f'''

619건 중 388건(B1 192, B3 196)은 RW reference보다 늦고, 231건은 RW 이내다. 전체 migration에서는 412건이 RW보다 늦다. 가장 큰 RW reference 초과는 23.5시간이다. 이 수치는 **authoritative deadline violation count 또는 maximum violation이 아니다**. “모두 RW 안이다”라는 주장도 raw 결과와 맞지 않는다.

## 요청한 두 사례

'''+table(case,[('day','day'),('policy','policy'),('job_uid','job_uid'),('requested_GPU','GPU'),('state_at_issue','issue state'),('RW_completion_slot','RW'),('reference_completion_slot','B0 end'),('optimized_completion_slot','final end'),('authoritative_deadline_slot','deadline'),('deadline_slack_hours','deadline slack h')])+f'''

**May15 job 8952973, B1/B3:** reference [0,168), final [0,24)+[105,249). Checkpoint=24, transfer=[99,104), restart complete=105. Service 24+144=168 slots 보존. Pause-to-restart interruption은 81 slots=20.25h(wait 75 slots=18.75h, transfer 5 slots=1.25h, restart 1 slot=0.25h)다. 사용자 예시의 23.5h는 이 사례의 값이 아니다. RW=192, final=249로 RW보다 57 slots=14.25h 늦다. Authoritative deadline과 slack은 NOT_AVAILABLE이다. issue 시점에는 PENDING/high지만 reference start=0이므로 D00에서는 이미 RUNNING이고 첫 checkpoint migration 대상이다. Restart=105<120이라 목적지 연산 15 slots가 D-day 안에 존재한다. 이 조건과 서비스 보존 때문에 frozen candidate formulation이 허용한 것이며, deadline 내 완료가 증명된 것은 아니다. Post-horizon service=1,935 GPUh, B0 대비 추가=1,215 GPUh이다.

**May01 B1 job 8571256:** reference [0,188), final [0,26)+[28,190). Checkpoint/transfer start=26, transfer end=27, restart=28; interruption=2 slots=0.5h. RW=188, final=190으로 RW보다 0.5h 늦다. Requested walltime=604800 seconds는 요청 duration이며 deadline으로 변환하지 않았다. Authoritative deadline과 slack은 NOT_AVAILABLE이다. B3에도 동일 timing이 존재한다.

## Worst 20 diagnostic records

실제 deadline slack 순위는 만들 수 없다. 아래는 **RW minus final 값이 작은 순**으로 정렬한 진단 사례 20건이다. 첫 10행이 요청한 worst 10 examples다. 동일 job의 B1/B3를 별도 record로 표시한다. 모든 행의 actual authoritative deadline/slack/violation은 NOT_AVAILABLE이다.

'''+table(worst,worstcols)+f'''

## Candidate가 왜 허용되었는가

**Checkpoint migration candidate generation이 job-specific completion deadline을 직접 검사했는가? NO.**

활성 경로는 allow_cross_midnight=True이다. Candidate final end는 reference end + (restart-checkpoint)로 연장된다. 첫 checkpoint 고정, 기존 시작/입장 결정 보존, GPU/rack/WAN 조건, 1회 migration, 재시작과 유효한 목적지 연산이 D24 전에 존재하는지, 전체 compute service 보존을 검사한다. RW 필드는 원본과 동일한지만 확인하며 final end <= RW 조건은 없다. standalone time-shifting의 RW 상한 검사는 migration 분기와 별개다.

따라서 job-level latest-completion gate가 migration formulation에 없는 것은 확인된다. 다만 이 gate를 요구하는 job-specific scientific contract를 확정하지 못했으므로, 확립된 deadline hard constraint를 implementation bug로 우회했다거나 final archive가 실제 deadline을 위반했다고 단정할 수 없다. 사용자 계약은 cross-midnight migration을 허용하고 terminal residual 제약을 비활성화한다. 이 감사는 새로운 SLA를 도입하거나 결과를 재최적화하지 않았다.

## 논문에서 사용할 수 있는 표현

“Checkpoint migration can defer planned compute service beyond the D-day evaluation boundary while preserving total planned compute service. Job-level completion-deadline compliance could not be established from the archived authority.”

한계는 별도로 유지한다: “Independent daily experiments do not propagate post-horizon service as next-day backlog.”

현재 근거로 “within the job deadline”, “within the authorized job-completion window”, 또는 “admissible post-horizon compute deferral”이라고 deadline 준수를 보증하는 표현은 사용하지 않는다. 관측된 현상은 planned post-horizon compute deferral이며, 이것만으로 workload dumping 또는 deadline violation을 확정하지 않는다. 향후 deadline authority가 확보되어도 deadline compliance PASS가 inter-day backlog accounting 해결을 뜻하지 않는다.

## 산출물과 보존

- 01_FLAGGED_619_DEADLINE_AUDIT.csv: 619행, 모든 요청 timing/authority 필드 및 raw source SHA.
- 02_ALL_MIGRATIONS_DEADLINE_AUDIT.csv: 전체 migration 677행, 같은 스키마.
- 03_DEADLINE_SUMMARY.csv: B1/B3/ALL, deadline 미확정과 RW 진단 통계를 분리.
- DEADLINE_AUTHORITY_EVIDENCE.md: 정의와 static source evidence.
- DEADLINE_AUDIT_MANIFEST.json: 원본 검증, source hash, field coverage, 반복 UID, candidate 검사, 감사 코드 SHA와 CSV readback 검증.

최종 accepted 124/124를 변경하지 않았다. Gurobi, DA/Actual, OpenDSS, ML, SUMO, route search 실행은 모두 0회. External workspace result read count = 0. PR은 method semantics만 읽었고 수정/업로드하지 않았다.
'''
    (out/'DEADLINE_AUDIT_REPORT.md').write_text(report,encoding='utf-8')
    checks=[]
    for filename,expected in [('01_FLAGGED_619_DEADLINE_AUDIT.csv',619),('02_ALL_MIGRATIONS_DEADLINE_AUDIT.csv',677),('03_DEADLINE_SUMMARY.csv',3)]:
        data=(out/filename).read_bytes(); rows=list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
        assert len(rows)==expected and all(None not in r and all(v is not None and v!='' for v in r.values()) for r in rows)
        if filename[:2] in ('01','02'):
            assert len({(r['day'],r['policy'],r['job_uid']) for r in rows})==expected
            for r in rows:
                parts=json.loads(r['optimized_compute_segments']); assert max(s['end'] for s in parts)==int(r['optimized_completion_slot'])
                assert r['within_deadline']==r['deadline_slack_hours']==NA
        checks.append(dict(filename=filename,rows=expected,sha256=digest(data),bytes=len(data),UTF8=True,readback='PASS'))
    av=load('archive_verification.json'); st=Path(av['archive']).stat()
    assert st.st_size==av['size_bytes'] and st.st_mtime_ns==av['mtime_ns']
    for path,meta in preserved.items():
        p=Path(path);assert p.stat().st_size==meta['size'] and p.stat().st_mtime_ns==meta['mtime_ns'] and digest(p.read_bytes())==meta['sha256']
    used={}
    for name in ('archive_sources_used.json','scan_sources_used.json','method_archive_sources_used.json','request_identity_sources_used.json','budget_sources_used.json'):
        used.update(load(name))
    files=[dict(filename=p.name,bytes=p.stat().st_size,sha256=digest(p.read_bytes())) for p in out.iterdir()]
    manifest=dict(schema='V41R4_INDEPENDENT_DEADLINE_AUDIT_V1',created_at=datetime.datetime.now().astimezone().isoformat(),
        classification='C',classification_name='DEADLINE_AUTHORITY_NOT_ESTABLISHED',output_directory=str(out),
        archive_verification=av,raw_archive_unchanged=True,prior_corrected_files_unchanged=preserved,
        external_workspace_result_read_count=0,forbidden_computation_counts={k:0 for k in ['Gurobi','DayAhead','Actual','OpenDSS','ML_training','SUMO','route_search']},
        final_accepted_policy_days=124,final_results_modified=False,PR=dict(number=42,url='https://github.com/BeaverVillage/MobileESS/pull/42',head_commit=COMMIT,usage='static method semantics only'),
        coordinate=dict(issue_origin='D-1 18:00 fixed AEST',issue_begin=24,issue_end_exclusive=120,day_begin=0,day_end_exclusive=96,slot_seconds=900),
        flagged_job_policy_day_count=619,unique_flagged_job_uid_count=len(uid_days),flagged_unique_uid_day_count=sum(map(len,uid_days.values())),
        flagged_repeated_uid_across_independent_days=repeated,population_summary=summary,all_policy_day_population=units,
        all_job_field_coverage=coverage,raw_request_input_checks=requests,request_identity_checks=load('request_identity_checks.json'),scan_review=reviewed,field_search=scan,
        method_sources=sources,method_source_hash_bindings=bindings,candidate_artifact_checks=candidates,
        boundary_audits=load('verified_boundaries.json'),worst_20_RW_diagnostic_records=worst,
        raw_member_reads_verified_by_sha256=used,raw_member_read_count=len(used),
        csv_readback=checks,output_files=files,
        audit_code=[dict(path=str(p),sha256=digest(p.read_bytes())) for p in HERE.glob('*.py')],
        notes=['Deadline counts/statistics NOT_AVAILABLE do not mean zero violations.','No actual job deadline assigned from RW or requested walltime.','FULL_CANDIDATES compressed schemas sampled at first record; model MPS and physical arrays are not scheduler deadline authority.'])
    (out/'DEADLINE_AUDIT_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    save('delivery.json',dict(output=str(out),classification='C',summary=summary,csv_checks=checks,files=[p.name for p in out.iterdir()]))
    print(json.dumps(dict(output=str(out),classification='C',summary=summary),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
