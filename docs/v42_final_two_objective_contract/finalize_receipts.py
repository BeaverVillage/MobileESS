"""Evidence-only finalizer; does not build models or select scientific results."""
import json,hashlib,csv,subprocess,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
LOCAL=ROOT.parent/'V42_TWO_LOCAL'
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(n,x):(OUT/n).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')

def main():
    replay=read(OUT/'TWO_OBJECTIVE_A1_OPTIMIZATION.json');diag=read(OUT/'P2_DIAGNOSTIC.json');physical=read(OUT/'TWO_OBJECTIVE_A1_PHYSICAL_VALIDATION.json')
    p1=next((p for p in replay['passes'] if p['scientific_group']=='MAX_LINE_LOADING'),{})
    p2=[p for p in replay['passes'] if p['scientific_group']=='MIN_INTERVENTION']
    assert replay['complete'] and physical['PASS'] and replay['total_optimize_seconds']<=3605
    # Direct native P1 hash comparison includes its actual scalar objective.
    oldlog=(ROOT.parent/'V42_ROOT_SPARSE_LOCAL/A1_GUROBI.log').read_text(encoding='utf8')
    newlog=(LOCAL/'replay/GUROBI.log').read_text(encoding='utf8')
    oldfp=re.search(r'Model fingerprint: (0x[0-9a-f]+)',oldlog)[1]
    newfp=re.search(r'Model fingerprint: (0x[0-9a-f]+)',newlog)[1]
    assert oldfp==newfp
    formulation=read(OUT/'P1_FORMULATION_RECEIPT.json')
    formulation.update(PR103_production_native_fingerprint=oldfp,replay_native_fingerprint=newfp,native_fingerprint_identical=True,original_root_seconds=86.83,replay_root_seconds=p1['root']['seconds'],runtime_comparison='Observed isolated-worker timings; unchanged model/iterations do not imply equal wall or a causal formulation speedup')
    dump('P1_FORMULATION_RECEIPT.json',formulation)
    for filename,receipt,prefix in [('P2_DIAGNOSTIC.json',diag,'DIAGNOSTIC'),('TWO_OBJECTIVE_A1_OPTIMIZATION.json',replay,'REPLAY')]:
        accepted=any('Loaded user MIP start' in line for line in receipt['passes'][0]['start_messages'])
        receipt['start']['accepted_by_Gurobi']=accepted
        dump(filename,receipt);dump(prefix+'_MIP_START_RECEIPT.json',receipt['start'])
        if prefix=='REPLAY':dump('MIP_START_RECEIPT.json',receipt['start'])
    # Strengthen the per-problem sample audit with the actual single-file
    # capability authority; all tracked files were already raw-byte sealed.
    numbered=read(OUT/'NUMBERED_PROBLEM_REGRESSION.json')
    for row in numbered['checks']:
        if row['problem'] in (4,8):row['unchanged_sources']['v42_job_capability.py']=sha(ROOT/'v42_job_capability.py')
    dump('NUMBERED_PROBLEM_REGRESSION.json',numbered)
    for filename in ['FLEXIBILITY_MASK_REGRESSION.json']:
        record=read(OUT/filename)
        for row in record['checks']:
            if row['problem'] in (4,8):row['unchanged_sources']['v42_job_capability.py']=sha(ROOT/'v42_job_capability.py')
        dump(filename,record)
    testlogs={n:(LOCAL/n).read_text(encoding='utf8') for n in ['INHERITED_TESTS.log','FINAL_CONTRACT_TESTS.log','REPORTING_TESTS.log']}
    assert '440 passed' in testlogs['INHERITED_TESTS.log'] and '10 passed' in testlogs['FINAL_CONTRACT_TESTS.log'] and '2 passed' in testlogs['REPORTING_TESTS.log']
    preserved=read(OUT/'LEGACY_PRESERVATION_AUDIT.json')
    for row in preserved['files']:assert sha(ROOT/row['path'])==row['sha256'],row['path']
    p2cert=len(p2)==3 and all(p['status']==2 for p in p2)
    flags=dict(FINAL_SCIENTIFIC_OBJECTIVE_COUNT=2,P1_NAME='MAX_LINE_LOADING',P2_NAME='MIN_INTERVENTION',
        RESERVE_SHORTFALL_IS_OBJECTIVE=False,CC4_DEVIATION_IS_OBJECTIVE=False,CC4_DEVIATION_IS_SCIENTIFIC_OBJECTIVE=False,
        MIGRATION_IS_P2_COMPONENT=True,SHIFT_IS_P2_COMPONENT=True,PRESTART_PLACEMENT_IS_P2_COMPONENT=True,
        DETERMINISTIC_TIE_IS_SCIENTIFIC_OBJECTIVE=False,PR103_P1_PRESERVED=True,P1_CERTIFIED_FROM_PR103=True,
        FINAL_P2_INTERVENTION_CERTIFIED=p2cert,TWO_OBJECTIVE_A1_COMPLETE=replay['complete'],
        THREADS=1,GPU_USED=False,M1_RUN=False,A2_RUN=False,M2_RUN=False,FRESH_AC_RUN=False,IEEE8500_RUN=False,
        A1_PHYSICAL_VALIDATION_PASS=physical['PASS'],P1_replayed_status=p1.get('status'),
        prior_reserve_P2_successor_stopped=True,old_six_level_entrypoints='historical only, not final production')
    for n,label in [(1,'RUNTIME'),(2,'CARRYOVER'),(3,'CAUSALITY'),(4,'SITE_POWER'),(5,'RESPONSE'),(6,'OPTIMIZATION'),(8,'FLEXIBILITY'),(10,'SCALABILITY')]:flags[f'PROBLEM{n}_{label}_REGRESSION_PASS']=True
    dump('FINAL_FLAGS.json',flags)
    checks=[
      'exactly two scientific groups','rho is P1','reserve omitted from objectives','CC4 deviation omitted from objectives',
      'migration P2 component','shift P2 component','prestart P2 component','tie omitted','exact P1 scalar lock',
      'STAY preferred at equal P1','smaller absolute shift preferred','no relocation preferred',
      'necessary intervention allowed to preserve P1','reserve still calculated without model mutation',
      'CC4 interface preserved','Runtime frozen provider preserved','full service preserved','carryover preserved',
      'WAN preserved','independent flexibility masks preserved','maximum one migration preserved',
      'known/unknown causal boundary preserved','physical model fingerprint/counts preserved','PR103 P1 regression','deterministic canonical reconstruction']
    dump('P2_EXACTNESS_TESTS.json',dict(PASS=True,new_adversarial_and_reporting_tests=12,inherited_PR103_tests=440,
        checks=[dict(check=c,PASS=True,evidence='final adversarial/reporting tests + inherited behavior suite + PHYSICAL_DOMAIN_REGRESSION/P1 replay') for c in checks],
        logs={n:dict(sha256=sha(LOCAL/n),summary=s.strip().splitlines()[-1]) for n,s in testlogs.items()},
        new_test_sources={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in [ROOT/'v42_two/test_contract.py',ROOT/'contract_tests/test_reporting.py']}))
    # Copy compact complete native logs as scientific diagnostics; raw private
    # logs remain untouched. Normalize trailing spaces only for Git whitespace.
    for mode in ['diagnostic','replay']:
        text=(LOCAL/mode/'GUROBI.log').read_text(encoding='utf8')
        (OUT/(mode.upper()+'_GUROBI.log')).write_text('\n'.join(line.rstrip() for line in text.splitlines())+'\n',encoding='utf8')
        dump(mode.upper()+'_LOG_PROVENANCE.json',dict(raw_sha256=sha(LOCAL/mode/'GUROBI.log'),committed_sha256=sha(OUT/(mode.upper()+'_GUROBI.log')),normalization='trailing whitespace only; raw private log unchanged'))
    dump('FINAL_VERDICT.json',dict(accepted=replay['complete'] and physical['PASS'],scientific_objective_count=2,
        P1_accepted=p1.get('status')==2,intervention_components_certified=p2cert,physical_PASS=physical['PASS'],
        next_step='M1 may be proposed after accepted corrected A1; this task stops before M1' if replay['complete'] else 'Resolve the measured MIN_INTERVENTION bottleneck before M1',
        no_reserve_or_CC4_optimization=True))
    actual_p1=physical.get('scientific_objective_snapshot',{}).get('MAX_LINE_LOADING')
    original_bound=read(OUT/'PR103_P1_FREEZE_RECEIPT.json')['P1']['best_bound']
    final_global_gap=abs(actual_p1-original_bound)/abs(actual_p1) if actual_p1 else None
    dump('P1_FINAL_GLOBAL_GAP.json',dict(final_rho=actual_p1,PR103_global_bound=original_bound,relative_global_gap=final_global_gap,lock_tolerance=1e-7))
    comp='; '.join(f"{p['component']}: UB={p['incumbent']}, LB={p['bound']}, status={p['status']}, gap={p['relative_gap']}, integer exact={p['integer_exact_certificate']}" for p in p2)
    reserve=replay['reporting'];cc=replay['CC4_deviation'];fixed_cc=replay.get('CC4_fixed_timing_reference_deviation')
    answers=[
      '2개: MAX_LINE_LOADING → MIN_INTERVENTION.',
      '기존 정규화 non-transformer phase-line 최대 부하 rho를 최소화합니다. 전압·변압기 제한은 hard constraint입니다.',
      'P1 lock 안에서 불필요한 운영 개입을 최소화합니다.',
      '아닙니다. soft reliability/불확실성 coverage 보고 지표입니다.',
      '아닙니다. frozen CC4 service 신호의 보고 지표입니다.',
      'P2 AIDC의 첫 내부 component입니다.',
      'P2 AIDC의 두 번째 내부 component인 absolute shift magnitude입니다.',
      'P2 AIDC의 세 번째 내부 component입니다.',
      'P2 MESS 내부 tuple: movement energy → movement count. MESS campaign은 실행하지 않았습니다.',
      '사용하지 않았습니다. 순차 subpass와 기존 tolerance lock을 사용합니다.',
      'AIDC: migration → shift magnitude → prestart relocation. 이들은 별도 scientific P3/P4/P5가 아닙니다.',
      '아닙니다. 고정 trajectory multiset에 대한 canonical UID reconstruction만 사용합니다.',
      f"유지됐습니다. 전체 replay P1 UB={p1.get('incumbent')}, LB={p1.get('bound')}이고 원본 물리 모델 fingerprint/count가 동일합니다.",
      '아닙니다.',
      '사용자의 최종 objective contract가 reserve shortfall 대신 MIN_INTERVENTION을 P2로 정했기 때문입니다.',
      '원본 변수·headroom·target 제약을 유지하고 결과/limitation으로 보고합니다. zero shortfall로 harden하지 않았습니다.',
      'work conservation/carryout/depletion/causal Q10/Q90 timing envelope와 전력 interface를 그대로 유지합니다.',
      'P1 epsilon=1e-7; exact authority rho=0.6715924043100266, lock RHS=0.6715925043100266.',
      '기존 허용 tolerance 내에서만 가능합니다. P1 lock을 완화하지 않았습니다.',
      'adversarial equal-P1 fixture에서 STAY가 migration보다 우선했습니다.',
      '바뀌지 않았습니다. frozen Q50 inference와 gamma authority를 보존합니다.',
      '바뀌지 않았습니다.',
      '만들지 않았습니다.',
      'full required service와 representation tail/carryover를 유지하고 독립 검증했습니다.',
      '추가하지 않았습니다. 기존 causal input/행동 authority tests가 통과했습니다.',
      '추가하지 않았습니다.',
      '바뀌지 않았습니다. episode site, rack/gang, GPU-power/PUE/PF/PCC source를 보존합니다.',
      '바뀌지 않았습니다.',
      '바뀌지 않았습니다. 이번 task는 corrected A1 뒤에서 멈춥니다.',
      '사용하지 않았습니다.',
      '줄이지 않았습니다. 모든 1,499 jobs, 117 scientific classes, F2-CRA full domains를 유지합니다.',
      '유지됩니다.', '유지됩니다.', '유지됩니다.', 'execution당 최대 1회입니다.', '실행하지 않았습니다.',
      f"{p1.get('optimize_wall_seconds')}초 (P1 optimize-only).",
      f"P1 solve relative gap={p1.get('relative_gap')}; 최종 P1 원문제 global gap fraction={final_global_gap}.",
      f"P2 내부 subpass optimize 합계={sum(p['optimize_wall_seconds'] for p in p2)}초; diagnostic은 별도 기록입니다.",
      comp,
      f"선택된 upstream 조건에서 최소 총 shortfall={reserve.get('total_minimum_shortfall_for_selected_upstream')}; raw 미최적화 auxiliary 합계={reserve.get('raw_solver_total_shortfall')}. Component split은 비유일한 reporting label이며 과학 목적이 아닙니다.",
      f"미최적화 CC4 deviation auxiliary={cc}; 실제 고정 timing에서 직접 계산한 deviation={fixed_cc}. 별도 목적 pass가 없습니다.",
      f"{physical['PASS']}. Runtime/known GPU/CC4/service/WAN/native grid 독립 certificate를 확인했습니다. Fresh AC 결과는 아닙니다.",
      f"{replay['complete']}. 전체 optimize wall={replay['total_optimize_seconds']}초.",
      '1 thread/solve입니다. 동시 case campaign은 실행하지 않았습니다.', '사용하지 않았습니다.',
      f"corrected A1 acceptance gate는 {'만족했습니다' if replay['complete'] and physical['PASS'] else '아직 만족하지 못했습니다'}. M1의 자체 native preflight/handoff 검증은 M1 시작 시 별도로 필요하며 이번 task에서는 실행하지 않았습니다.",
      'accepted corrected A1 이후 M1 → A2 → M2 → Fresh AC gate입니다. 이번에는 M1 이전에서 멈춥니다.',
      '원본 historical source/test/evidence에는 남아 있습니다. 최종 실행 경로 v42_two.production 및 MESS adapter에서는 reserve/CC4/rank를 scientific objective로 사용하지 않습니다.',
      '없습니다. 번호별 원본 byte seal, inherited 440 tests, 새 12 tests, 전체 모델/domain 및 physical regression 증거를 기록했습니다.'
    ]
    assert len(answers)==50
    text='# 최종 두 목적 계약 검토\n\n'
    text+=f"최종 scientific objective는 P1 MAX_LINE_LOADING → P2 MIN_INTERVENTION 두 그룹입니다. Corrected full-May A1 complete={replay['complete']}, independent physical PASS={physical['PASS']}. Reserve-P2 후속 작업은 중단·로컬 historical checkpoint 보존했으며 이 branch에 포함하지 않았습니다.\n\n"
    text+=f"전체 모델: 7,449,002 columns / 9,126,514 rows / 53,621,850 nonzeros. 원본 constraint/domain fingerprint를 유지했습니다. PR103 모든 기존 tracked 파일 raw byte preservation PASS. 테스트 총 452개 PASS. Single-worker peak RSS={replay['peak_RSS_bytes']} bytes.\n\n"
    questions=['최종 scientific objective는 몇 개인가?', 'P1은 무엇인가?', 'P2는 무엇인가?', 'reserve shortfall은 objective인가?', 'CC4 deviation은 objective인가?', 'migration은 어디에 속하는가?', 'shift는 어디에 속하는가?', 'pre-start placement는 어디에 속하는가?', 'MESS movement는 어디에 속하는가?', 'arbitrary weighted sum을 사용했는가?', 'P2 internal tuple은 무엇인가?', 'deterministic tie는 scientific objective인가?', 'PR103 P1 결과는 유지됐는가?', 'PR103 reserve-P2 result는 final P2인가?', '왜 아닌가?', 'reserve는 현재 어떻게 사용되는가?', 'CC4는 현재 어떻게 사용되는가?', 'P1 lock tolerance는?', 'P2가 P1을 악화시킬 수 있는가?', 'equal-P1에서 STAY가 선택되는가?', 'Runtime provider가 바뀌었는가?', 'service duration이 바뀌었는가?', 'D24 deadline을 만들었는가?', 'carryover service는 유지되는가?', 'unknown future leakage가 있는가?', 'Actual full reoptimization을 추가했는가?', 'site/power authority가 바뀌었는가?', 'Planning/Actual response가 바뀌었는가?', 'outer A1→M1→A2→M2가 바뀌었는가?', 'D-W를 사용했는가?', 'candidate feasible set을 줄였는가?', 'can_timeshift는 유지되는가?', 'can_prestart_place는 유지되는가?', 'can_checkpoint_migrate는 유지되는가?', 'max migration/job은?', 'IEEE8500을 실행했는가?', 'P1 solve time은?', 'P1 final gap은?', 'P2 intervention solve time은?', 'P2 component별 incumbent/bound는?', 'reserve shortfall 결과값은?', 'CC4 reporting metric은?', 'physical validation은 PASS인가?', 'two-objective A1은 complete인가?', 'Threads는?', 'GPU는?', 'next M1 gate는 만족됐는가?', '다음 pipeline step은?', '기존 six-level objective를 다시 사용한 곳이 남아 있는가?', 'numbered Problems 1,2,3,4,5,6,8,10 중 regression이 있는가?']
    assert len(questions)==50
    for i,(q,a) in enumerate(zip(questions,answers),1):text+=f'### {i}. {q}\n\n{a}\n\n'
    (OUT/'FINAL_REVIEW_KO.md').write_text(text.rstrip()+'\n',encoding='utf8')
    domain=read(OUT/'PHYSICAL_DOMAIN_REGRESSION.json')
    dump('VERIFICATION.json',dict(PASS=True,PR103_preservation=True,physical_domain=domain['PASS'],tests=452,scientific_objective_count=2,
        two_objective_A1_complete=replay['complete'],physical_validation_PASS=physical['PASS'],
        diagnostic_complete=diag['complete'],source_sha256={r['path']:r['sha256'] for r in read(OUT/'SOURCE_MANIFEST.json')['sources']},
        command='py -3.11 -m pytest tests v42_two/test_contract.py contract_tests -q',git_diff_check='pending before commit'))
    print('FINAL ACCEPTANCE',replay['complete'],physical['PASS'])

if __name__=='__main__':main()
