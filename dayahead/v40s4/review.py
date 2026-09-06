"""Render the Korean closeout from frozen saved results; never fit or predict."""
import re
import xml.etree.ElementTree as ET
from .common import *
from .diagnostics import guard_selection


def required_artifacts():
    request=(OUT/'USER_REQUEST.txt').read_text(encoding='utf-8')
    section=request.split('# 43. REQUIRED ARTIFACTS')[1].split('# 44. RUNTIME ADAPTER')[0]
    return list(dict.fromkeys(re.findall(r'V40S4_[A-Z0-9_]+\.(?:json|csv|md)',section)))


def working_scope():
    paths={p.decode('utf-8') for p in git('diff','--name-only','-z',BASE,binary=True).split(b'\0') if p}
    for entry in git('status','--porcelain=v1','-z','--untracked-files=all',binary=True).split(b'\0'):
        if not entry: continue
        assert b'R' not in entry[:2] and b'C' not in entry[:2], 'Unexpected rename/copy'
        paths.add(entry[3:].decode('utf-8'))
    assert all(allowed(p) for p in paths), sorted(p for p in paths if not allowed(p))
    return sorted(paths)


def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
                     ['| '+' | '.join(str(v) for v in row)+' |' for row in rows])


def num(v,d=3):return 'N/A' if v is None else f'{v:,.{d}f}'
def pct(v):return 'N/A' if v is None else f'{100*v:.3f}%'


def main():
    guard_prereg();guard_selection()
    decision=get('FINAL_DECISION');selection=get('METHOD_SELECTION')
    assert decision['classification']=='V40S4_PROXY_BODY_RUNTIME_INSUFFICIENT'
    assert selection['selected'] is None and decision['valid_primary_eta_count']==0
    suites=ET.parse(OUT/'V40S4_TEST_JUNIT.xml').getroot().findall('testsuite')
    counts={k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ['tests','failures','errors','skipped']}
    assert counts['tests']>=73 and not any(counts[k] for k in ['failures','errors','skipped'])
    request=(OUT/'USER_REQUEST.txt').read_text(encoding='utf-8')
    checklist=re.findall(r'^\d+\. .+$',request.split('# 45. MINIMUM TESTS')[1].split('# 46. FINAL RESPONSE')[0],re.M)
    assert len(checklist)==73
    write('TEST_REPORT',dict(status='PASS',timestamp=now(),pytest=counts,passed=counts['tests'],
        elapsed_seconds=sum(float(s.attrib.get('time',0)) for s in suites),
        command='python -B -m pytest tests/dayahead/test_v40s4_contracts.py -q -p no:cacheprovider --junitxml=dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_TEST_JUNIT.xml',
        tests_SHA256=sha((ROOT/'tests/dayahead/test_v40s4_contracts.py').read_bytes()),
        junit_SHA256=sha((OUT/'V40S4_TEST_JUNIT.xml').read_bytes()),
        required_minimum_checklist=checklist,
        coverage='105 collected cases: source/lineage, membership, proxy/preprocessing leakage, independent eta feasibility, exact metrics, frozen models, protected bytes and firewalls. No fitting in tests.',
        final_postconditions='Checklist72 complete artifact presence and73 final clean Git are checked after the scientific commit in FINAL_COMMIT_RECEIPT and checked again after committing that receipt; not claimed from a dirty precommit pytest run.',
        required_artifacts=required_artifacts(),
        reporting_only_finalization=True,new_fits=0,new_predictions=0,threshold_changes=0))
    dev=get('DEV_CAL_RESULTS');ev=get('EXPOSED_RESULTS');lineage=get('GIT_LINEAGE_AUDIT')
    ledger=get('COMPUTE_LEDGER');rows=[]
    begin=[('FINAL CLASSIFICATION',decision['classification']),('SELECTED TRACK','NONE'),('SELECTED u','NONE'),
      ('SELECTED BODY MODEL','NONE'),('SELECTED TAIL CLASSIFIER','NONE'),('SELECTED eta','NONE'),
      ('SELECTED ROBUST POLICY','NONE'),('PROXY ASSUMPTION',ASSUMPTION),
      ('HISTORICAL D-1 SNAPSHOT VERIFIED','NO / UNVERIFIED'),('BODY SAFETY','FAIL'),
      ('TAIL DETECTION','FAIL / NO CAL-ELIGIBLE ETA'),('HYBRID SAFETY','N/A / NOT ELIGIBLE'),
      ('OPTIMIZER INTEGRATION','NO'),('PRODUCTION READY','NO')]
    rows.append('\n\n'.join(f'{k}: {v}' for k,v in begin))
    def add(i,title,text):rows.append(f'**{i}. {title}**\n\n{text}')
    def link(name):return f'[{name}](<{(OUT/name).as_posix()}>)'
    def body_table(track,scope):
        source=ev if scope=='EXPOSED_EVALUATION' else dev
        rr=[r for r in source['body'] if r['track']==track and r['role']==scope and r['group']=='OVERALL']
        return table(['u(h)','모델','BODY N','Q90 coverage','GPU coverage','Q50 MAE(s)','Q90 MAE(s)','Q90 WAPE','GPU miss(s)'],
          [[r['u_hours'],r['body'],r['N'],pct(r['coverage']),pct(r['GPU_coverage']),num(r['Q50_MAE_sec']),num(r['MAE_sec']),num(r['WAPE']),num(r['GPU_underprediction_sec'])] for r in rr])
    def tail_table(track,scope):
        source=ev if scope=='EXPOSED_EVALUATION' else dev
        rr=[r for r in source['tail'] if r['track']==track and r['role']==scope and r['body']=='B1']
        return table(['u(h)','분류기','N / tail N','ROC-AUC','PR-AUC(AP)','Brier','ECE','eta'],
          [[r['u_hours'],r['classifier'],f"{r['N']} / {r['tail_N']}",num(r['ROC_AUC'],6),num(r['PR_AUC'],6),num(r['Brier'],6),num(r['ECE'],6),'NONE'] for r in rr])
    add(1,'정확한 Git lineage',f"S3 시작 PR27: `{lineage['S3_starting_PR27_head']}` → S3 scientific: `{S3SCIENCE}` → S3 receipt / S4 base: `{BASE}`.\n\n"
        f"조회 시 live PR27: `{lineage['live_PR27_metadata_only']['headRefOid']}`; metadata만 조회했고 merge하지 않았다. Branch: `{git('branch','--show-current')}`. Worktree: `{ROOT}`.\n\n"
        f"S4 사전등록 commit: `{get('PREREGISTRATION_COMMIT_RECEIPT')['commit']}`; model/NONE 선택 freeze: `{get('METHOD_SELECTION_COMMIT_RECEIPT')['commit']}`. 새 fit은 사전등록 뒤, exposed scoring은 선택 freeze 뒤에 수행했다.")
    add(2,'S3 보존','S3 판정 `V40S3_CAUSAL_TAIL_RISK_INFORMATION_INSUFFICIENT`, 선택값 전부 NONE, integration NO를 유지했다. S3 source/artifact 109개는 원본 worktree와 S4 복제본에서 byte identity PASS. S3 strict-provenance 결론을 proxy track으로 다시 이름 붙이지 않았다.')
    add(3,'Assumption contract',f'`{ASSUMPTION}`; `REQUEST_STATE_ROLE=ASSUMPTION_BASED_SCHEDULER_VISIBLE_PROXY`. historical D1 snapshot과 original submission provenance는 모두 UNVERIFIED. operational availability만 FROZEN. 요청 변경 이력 UNOBSERVED, 변경 모델 OUT_OF_SCOPE. 변경 빈도=0이라고 주장하지 않는다. 논문 표현은 `ASSUMPTION-BASED TRACE-DRIVEN RUNTIME MODEL`. '+link('V40S4_ASSUMPTION_BOUNDARY.md'))
    add(4,'Source population',f'원본 73,504행 = positive 72,292 + zero 1,212; negative 0, timestamp missing 0, duplicate 0. Runtime은 정확히 end−start. Source SHA256 `{SOURCE_SHA}`. Zero는 identity audit에 보존하고 모든 모델에서 동일하게 제외했다. 성공/실패 terminal status는 없으므로 COMPLETED-only가 아니다. 기존 exposed terminal-service complete-case population이며 full cluster backlog, censoring 해소, raw rowgroup exclusion bias 해소를 주장하지 않는다.')
    add(5,'PENDING population','10,883 job-issue / 7,603 unique jobs. `submit<=issue AND (start missing OR start>issue) AND end>issue`를 독립 재구성해 S3 ID·순서·label·split·feature와 일치함을 확인했다. start/end는 membership·target·label availability에만 사용했고 predictor에는 없다. RUNNING redesign=0.')
    add(6,'Split',table(['역할','issue UTC 시작(포함)','issue UTC 끝(제외)','N','unique jobs','최대 label end UTC'],
        [[role,*BOUNDS[role],get('POPULATION_AUDIT')['blocks'][role]['N'],get('POPULATION_AUDIT')['blocks'][role]['unique_jobs'],get('POPULATION_AUDIT')['blocks'][role]['max_label_end']] for role in BOUNDS])+
        '\n\nD-1 18:00 fixed AEST=08:00 UTC. end_time은 각 단계 cutoff보다 엄격히 이전이다. TRAIN completion은 모든 이후 prediction issue보다 이전이다. 무작위 분할 없이 S3를 그대로 유지했다. 반복 job-issue는 같은 block 내에서 유지하고 block 간 동일 job 누출은 없다.')
    add(7,'Proxy feature inventory','P: `'+', '.join(FEATURES)+'`. P-W는 `requested_seconds`만 제거한 8개 필드. encoded columns는 P19/P-W17. GPU request는 두 track 모두 predictor이면서 모든 track의 사전 고정 평가 weight다. 실제 allocation으로 해석하지 않는다. Memory는 MiB로 확인했다. 별도 hardware request field는 없고 파생 hardware만 있어 제외했다. Partition은 요청 queue 의미로 유지했다.')
    m=get('PROXY_FEATURE_MISSINGNESS_AUDIT')['rows']
    assert all(r['nonmissing_fraction']==1 and r['invalid_N']==0 for r in m)
    add(8,'Missingness','원본·PENDING·TRAIN/DEV/CAL/EVAL 모두 9개 feature의 nonmissing=100%, invalid=0. TRAIN median을 사전등록했고 log1p+missing indicator를 사용했다. Categorical TRAIN vocabulary 외 값은 UNKNOWN으로 처리했다.\n\n'+
        table(['scope','feature','N','unique','unseen N','unseen values'],[[r['scope'],r['feature'],r['N'],r['unique_values'],r['unseen_N'],', '.join(r['unseen_values'])] for r in m if r.get('unseen_N',0)])+
        '\n\nZero·impossible·unique 수는 feature별 JSON에 모두 보존했다. Categorical impossible은 수치 불가능값을 정의할 수 없어 null이며 unseen과 구분했다. '+link('V40S4_PROXY_FEATURE_MISSINGNESS_AUDIT.json'))
    add(9,'제외 feature','user/account/username/job name/application identity·job ID·actual start/end/runtime·K0·reference safe seconds·support counts는 새 predictor에서 제외했다. Derived hardware도 제외했다. TRAIN-only vocabulary/median이며 target encoding은 없다. Clock은 고정 raw hour/weekday를 사용했으며 post-outcome scaling/subset search는 하지 않았다.')
    ratio=[r for r in get('REQUEST_RUNTIME_RELATIONSHIP')['rows'] if r['group']=='OVERALL']
    add(10,'Actual/requested walltime forensic',table(['scope','N','median','P90','P95','P99','actual>request N','fraction'],
        [[r['scope'],r['N'],num(r['median'],6),num(r['P90'],6),num(r['P95'],6),num(r['P99'],6),r['actual_gt_request_N'],pct(r['actual_gt_request_fraction'])] for r in ratio])+
        '\n\nRequested-walltime bins, GPU count, partition/QoS(N>=100)별 분포도 '+link('V40S4_REQUEST_RUNTIME_RELATIONSHIP.json')+'에 기록했다.')
    add(11,'Actual > request','Positive 원본 2,925/72,292=4.046%; PENDING 309/10,883=2.839%; exposed 189/2,713=6.966%. 해당 행을 그대로 유지했다. Walltime은 predictive metadata이며 hard upper bound가 아니다. 새 Q50/Q90를 walltime으로 cap하지 않았다.')
    c=get('TRACK_C_REFERENCE')
    add(12,'Track C reference','S3의 submit_hour/submit_dow 두 feature 결과를 read-only로 비교했다. Retrain=NO, S3 eta 규칙과 판정은 그대로다. 동일 u/model/split에 대한 P/P-W minus C body delta를 '+link('V40S4_TRACK_C_REFERENCE.json')+'에 보존했다. S3 R1(RW)은 S4 R2에 대응하며 S4 R1은 새 threshold floor다. B0는 S3 current-recipe seconds를 재사용한 comparator이며 exact production Apr01 final-state equivalence를 주장하지 않는다.\n\n'+
        table(['track','u','body','DEV coverage Δ(pp)','CAL coverage Δ(pp)','EVAL coverage Δ(pp)'],[[track,h,b,*[num(100*next(r['coverage_minus_C'] for r in c['matched_body_deltas'] if (r['track'],r['u_hours'],r['body'],r['role'])==(track,h,b,role))) for role in ['DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION']]] for track in ['P','PW'] for h in U for b in ['B1','B2','B3']]))
    add(13,'Track P body table','B0는 reference only; B1=LGB quantile, B2=XGB quantile, B3=TRAIN-body empirical quantile. 모든 표는 oracle BODY `T<=u`의 조건부 평가이며 total hybrid 성능이 아니다.\n\n'+
        '\n\n'.join(f'**{scope}**\n\n'+body_table('P',scope) for scope in ['DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION']))
    add(14,'Track P-W body table','Walltime만 제거한 사전 고정 sensitivity track.\n\n'+'\n\n'.join(f'**{scope}**\n\n'+body_table('PW',scope) for scope in ['DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION']))
    bad=[r for r in dev['body'] if r['track']=='P' and r['u_hours']==12 and r['body']=='B1' and (r['coverage_gate']=='FAIL' or r['GPU_gate']=='FAIL')]
    add(15,'Body Q90/GPU safety','DEV+CAL 모두에서 overall Q90 90–95%, GPU>=90%, major issue-day N>=100에서 coverage/GPU>=88%를 통과한 새 body/u 쌍은 0개다. >95%도 FAIL이며 >97.5%는 추가 warning이다. 예: P 12h B1의 실패 subgroup은 다음과 같다.\n\n'+table(['split','group','N','coverage','GPU coverage','coverage gate','GPU gate'],[[r['role'],r['group'],r['N'],pct(r['coverage']),pct(r['GPU_coverage']),r['coverage_gate'],r['GPU_gate']] for r in bad])+
        '\n\n높은 pooled coverage만으로 일자별 실패를 무시하지 않았다. 이는 등록된 cohort/model family의 안전성 실패이지 모든 runtime 예측의 불가능성 증명은 아니다.')
    add(16,'Body MAE/WAPE/miss','13–14 표에서 Q50 MAE와 Q90 duration MAE/WAPE를 분리했다. 전체 CSV에는 Q50 pinball/WAPE, log-MAE, positive residual seconds, GPU-weighted miss, completion-slot MAE와 temporal/GPU subgroup도 있다. Native Q90 coverage를 평가하며 scheduler metrics는 `ceil(seconds/900)`을 한 번 적용한다. '+link('V40S4_TRACK_P_BODY_RESULTS.csv')+' / '+link('V40S4_TRACK_PW_BODY_RESULTS.csv'))
    add(17,'Track P classifier table','C0=TRAIN base rate, C1=logistic, C2=LGB, C3=XGB. ROC/PR/Brier/ECE는 body model과 무관하므로 B1 행으로 중복을 제거했다. Eta feasibility는 모든 body별로 따로 계산했다.\n\n'+'\n\n'.join(f'**{scope}**\n\n'+tail_table('P',scope) for scope in ['DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION']))
    add(18,'Track P-W classifier table','\n\n'.join(f'**{scope}**\n\n'+tail_table('PW',scope) for scope in ['DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION']))
    add(19,'ROC/PR/ECE 해석','PR-AUC는 average precision(AP), ECE는 동일 폭 10-bin N-weighted absolute calibration gap이다. S4에서는 ECE를 diagnostic으로 고정했다. Exposed P 8h C3의 ROC 0.841505 / AP 0.661571이 좋아도 CAL-eligible eta가 없으므로 승격하지 않는다. Exposed tail N은 u4/6/8/12/24에서 1,229/590/309/62/19이므로 12h/24h tail support<100을 명시한다.')
    add(20,'Recall / GPU recall','선택된 eta가 없으므로 primary recall, precision, specificity, FNR/FPR, GPU recall/FNR는 null(N/A)이다. 0으로 대체하지 않았다. CAL saved predictions의 전체 eta feasibility를 별도 독립 brute-force test로 재검증했다. Selectivity를 제거한 사후 tradeoff 수치는 selected policy 성능이 아니다.')
    add(21,'Danger-mass capture','정의: `sum(g*max(T−Q90_body,0)*flag) / sum(g*max(T−Q90_body,0))`. Body별로 CAL eta feasibility에 80% gate를 적용했다. 실제 primary capture는 eta NONE으로 N/A. 등록된 weighting은 requested GPU이며 measured GPU occupancy가 아니다.')
    trade=[r for r in get('SELECTIVITY_AUDIT')['records'] if r['body']=='B1' and r['classifier']=='C2']
    add(22,'Flagged fraction / selectivity','기본 cap=60%; true tail prevalence>60%이면 min(80%, prevalence+20pp). 아래는 CAL에서 세 safety target을 만족시키기 위해 필요한 최소 flag fraction을 사후 분해한 값이다. Eta를 바꾸거나 exposed에 적용하지 않았다.\n\n'+
        table(['track','u','CAL tail N','support','cap','필요 flag','recall','GPU recall','capture'],[[r['track'],r['u_hours'],r['tail_N'],r['support_sufficient'],pct(r['selectivity_cap']),*[pct((r['minimum_flagging_needed_for_three_safety_targets'] or {}).get(k)) for k in ['flagged_fraction','recall','GPU_recall','mass_capture']]] for r in trade])+
        '\n\n예: u8 B1+C2는 89.332%를 flag해야 해서 60% cap을 초과한다. 24h는 CAL tail N=43이라 support gate도 실패한다.')
    add(23,'Eta','P/P-W × 5u × 3개 새 body × 4 classifiers의 CAL-eligible eta 수=0. Largest feasible eta 규칙을 유지했고 NONE을 .5/all-tail/all-body로 대체하지 않았다. DEV/EVAL에서 threshold를 다시 선택하지 않았다. '+link('V40S4_ETA_SELECTION.json'))
    add(24,'R0','Flagged job에 current-recipe `reference_safe_sec`를 적용하는 등록 comparator. 유효 eta가 없으므로 data hybrid replay는 `NOT_EXECUTED_NO_CAL_ELIGIBLE_ETA`. Formula synthetic test PASS. '+link('V40S4_R0_REPORT.json'))
    add(25,'R1','Flagged job에 `max(reference_safe_sec,u_seconds)` 적용. S3의 RW policy와 구분되는 S4 threshold floor. Data hybrid replay N/A, formula test PASS. '+link('V40S4_R1_REPORT.json'))
    add(26,'R2','Flagged job에 recorded requested walltime을 적용하는 comparator. Guaranteed runtime bound가 아니다. Data hybrid replay N/A, formula test PASS. '+link('V40S4_R2_REPORT.json'))
    refs=get('GPU_WEIGHTED_UNDERPREDICTION')['reference']
    add(27,'Hybrid overall coverage','모든 candidate hybrid metric은 eta NONE에 따라 null이다. BODY+TAIL requested denominator(DEV 4,346/CAL 2,634/EVAL 2,713)를 보존했다. Below table은 전체 denominator의 별도 baseline comparator이며 S4 hybrid가 아니다.\n\n'+
        table(['split','reference','coverage','GPU coverage','GPU miss(s)','overreserve GPU-h'],[[role,ref,pct(m['coverage']),pct(m['GPU_coverage']),num(m['GPU_underprediction_sec']),num(m['overreservation_GPU_hours'])] for role,v in refs.items() for ref,m in v.items()]))
    add(28,'Hybrid GPU coverage','N/A / NOT ELIGIBLE. Mandatory >=90% gate를 충족했다고 주장하지 않는다. '+link('V40S4_HYBRID_RESULTS.csv'))
    add(29,'Underprediction reduction','Selected reduction=N/A. 등록된 조건은 current reference보다 GPU-positive miss가 엄격히 작아야 한다. Eta 없이 대체 duration을 만들어 감소율을 계산하지 않았다. '+link('V40S4_GPU_WEIGHTED_UNDERPREDICTION.json'))
    add(30,'Overreservation ratio','Selected ratio=N/A. 3.0× cap은 유지했고 완화하지 않았다. Reference가 0인 경우 smoothing 없이 candidate도 0을 요구한다. R2 coverage가 좋다는 이유로 cap을 무시한 승격은 없다. '+link('V40S4_OVERRESERVATION_REPORT.json'))
    add(31,'Selected policy','Track/u/body/classifier/eta/robust policy 전부 NONE. Primary failure는 selection hierarchy의 body safety 단계다. Tail eta도 독립적으로 모두 부적격이다. Adapter proposal 12개 field만 명시했고 recommended_rows=[]; export/integration하지 않았다.')
    add(32,'Walltime dependence','P와 P-W 모두 실패: `REQUEST_STATE_PROXY_INFORMATION_STILL_INSUFFICIENT`. 동일 u/model/split의 body coverage/GPU/MAE/WAPE/miss 및 classifier ROC/AP/Brier/ECE deltas를 보존했다. Recall/capture/hybrid deltas는 eta가 없어 null이다. B1과 tree classifiers는 P/P-W 결과가 동일하고 B2 12h/24h 및 logistic에서 차이가 있다. Walltime을 추가하면 항상 좋아진다고 주장하지 않는다. '+link('V40S4_WALLTIME_DEPENDENCE_ANALYSIS.json'))
    wall=get('FEATURE_IMPORTANCE_DIAGNOSTIC')['wallclock_records']
    add(33,'Feature importance','DEVELOPMENT only, original-field grouped gain, 고정 seed로 3회 permutation. LGB total gain, XGB total_gain. 동률은 dense rank. Exposed importance/SHAP feature selection=NO.\n\n'+
        table(['u','tree model','alpha','wall gain rank','relative gain','permutation loss Δ'],[[r['u_hours'],r['model'],r.get('alpha'),r['gain_rank'],num(r['relative_gain'],6),num(r['permutation_delta_mean'],6)] for r in wall])+
        '\n\nWalltime gain은 모든 LGB model과 XGB classifier에서 0. XGB body 12h/24h의 상대 gain만 약0.16–1.70%였다. 이 제한된 TRAIN/모델의 결과이며 walltime이 일반적으로 쓸모없다는 결론은 아니다.')
    sensitivity=get('PROXY_PERTURBATION_SENSITIVITY')
    add(34,'±10% proxy sensitivity','Winner NONE에 대한 사전등록 고정 diagnostic anchor=P/P-W u4 B1 C2 R1을 사용했다. S0=1.0/S1=.9/S2=1.1, refit0/reselectionNO.\n\n'+
        table(['track','scenario','max Q50 Δ(s)','max Q90 Δ(s)','max p Δ','flag Δ','hybrid'],[[r['anchor']['track'],r['scenario'],num(r['max_Q50_change_sec']),num(r['max_Q90_change_sec']),num(r['max_probability_change']),'N/A','N/A'] for r in sensitivity['records']])+
        '\n\nAnchor의 출력 변화0을 runtime decision robustness 인증으로 해석하지 않는다. Eta가 없어 discrete flag/hybrid decision 자체가 없으며 ±10%는 관측된 변경 이력이 아니다.')
    add(35,'Exposed evaluation','Model/NONE freeze commit 뒤에만 실행했다. Selection result를 바꾸지 않았다. 예: P/P-W 12h B1 Q90 coverage=77.744%, GPU=78.526%. B3의 일부 exposed pooled gate가 좋아도 DEV+CAL 실패를 지우거나 winner를 재선정하지 않았다. 추가 fit/prediction/retuning 없이 최종 보고한다.')
    add(36,'Bootstrap','`NOT_EXECUTED_SAFETY_FAIL`; runs0, confidence interval=null. 실패 후 유리한 CI를 계산하지 않았다.')
    add(37,'Confirmation','`TRUE_CONFIRMATORY_AVAILABLE=NO`. 이 평가도 이미 exposed된 자료이며 untouched confirmation이 아니다. Apr-24–30 shadow는 계속 SEALED, row reads0.')
    add(38,'May firewall','Canonical fixed AEST(+10): `2025-05-01T00:00:00+10:00` = UTC `2025-04-30T14:00:00Z`. 사용 source의 더 엄격한 timestamp boundary는 `2025-04-24T00:00:00Z`. May runtime/status/outcome/fit/calibration/threshold/eta/selection/sensitivity scientific reads는 모두0. Git path/index metadata discovery는 NONZERO로 별도 공개했고 May total read=0이라고 주장하지 않았다. '+link('V40S4_MAY_FIREWALL.json'))
    add(39,'Optimizer/Gurobi/OpenDSS calls','모두0. Fresh0. Runtime 연구용 CPU model fit/prediction만 수행했다.')
    add(40,'Migration/WAN/terminal','A0/A1/M1/MF, migration, RUNNING, WAN, Rack, terminal, event-trigger/local-repair/rolling-MPC 변경0. Future consumers `dayahead/v37/aidc_materializer.py`, `dayahead/v40a/initial.py`도 unchanged. Production q=5576.44921875s, PF=.95, Q control NO, electrical HOLD, B0–B3 electrical NO, FULL_MAY NO를 유지했다.')
    add(41,'Tests',f"Pytest {counts['tests']} PASS, failure/error/skip0. Independent eta feasibility, exact row/metric/slot checks, forbidden predictor invariance, TRAIN-only preprocessing, source/selection locks와 보호 범위를 검증했다. 최종 artifact presence와 clean Git는 scientific commit 뒤 별도 receipt 검증에 포함한다. "+link('V40S4_TEST_REPORT.json'))
    inference=sum(r['seconds'] for r in ledger['inference_times']);exposed_time=sum(r['seconds'] for r in ledger['exposed_inference_times'])
    add(42,'Reproducibility',f"Python3.11.7, numpy2.2.6, pandas2.2.3, sklearn1.6.1, LGB4.6.0, XGB3.2.0. CPU threads1/seed4003. Primary fits70 + independent repeats70; empirical body10/base-rate10. 70개 model pair의 TRAIN+DEV+CAL prediction이 byte-identical, max/mean difference=0.0. Repeat 중 더 좋은 결과를 고르지 않았다.\n\nMeasured model fit 합계 {ledger['total_fit_seconds']:.6f}s; DEV/CAL inference 합계 {inference:.6f}s; exposed inference 합계 {exposed_time:.6f}s. 데이터 준비/diagnostics/Git 작업을 포함한 전체 wall time이 아니다. 모델별 시간은 compute ledger에 기록했다. Benign LGB sklearn feature-name warnings는 stderr log에 보존했다.")
    add(43,'Protected scope','S3 receipt에서 상속한 tracked Git entries 5,352개를 모두 유지했다. S3 tracked109개는 원본과 복제본 byte identity 검증. 변경은 S4 source/artifact/test 경로로만 한정한다. Final receipt에서 staged/untracked 포함 경로 검증과 Git blob↔working bytes를 다시 확인한다. '+link('V40S4_PROTECTED_SCOPE_DIFF.json'))
    add(44,'Scientific commit','최종 scientific commit의 full SHA 및 owned-file SHA256 manifest는 '+link('V40S4_FINAL_COMMIT_RECEIPT.json')+'의 `scientific_commit`과 `owned_files_SHA256`에 기록한다. Self-reference를 만들지 않기 위해 이 보고서를 담는 commit SHA는 후속 receipt가 증명한다.')
    add(45,'Receipt commit','Receipt commit은 `V40S4_FINAL_COMMIT_RECEIPT.json`을 최초 추가하는 후속 commit이다. Full SHA는 최종 응답과 `git log -1 --format=%H -- dayahead/artifacts/v40s4_request_state_proxy_runtime_risk/V40S4_FINAL_COMMIT_RECEIPT.json`으로 확인한다. Receipt를 commit한 다음 clean Git와 receipt Git blob identity를 다시 확인한다.\n\n현재 입증된 strict provenance와 명시적 request-state proxy assumption을 구분한다. 등록된 feature/model family 안에서는 proxy 정보를 추가해도 안전하고 선택적인 runtime handling에 충분하지 않았다. 새 model family나 optimizer 변경으로 이 결과를 덮지 않는다.')
    (OUT/'V40S4_FINAL_REVIEW.md').write_text('\n\n'.join(rows)+'\n',encoding='utf-8')
    missing=[n for n in required_artifacts() if not (OUT/n).is_file()]
    assert missing==['V40S4_FINAL_COMMIT_RECEIPT.json'],missing
    scope=get('PROTECTED_SCOPE_DIFF');scope['allowed_changed_paths']=working_scope()
    scope['scope_includes']='Tracked diff against S3 receipt plus every untracked file before scientific commit; receipt rechecks final tree.'
    write('PROTECTED_SCOPE_DIFF',scope)
    print('REVIEW_WRITTEN',len(required_artifacts()),'required;',counts,'; only receipt deferred')


if __name__=='__main__':main()
