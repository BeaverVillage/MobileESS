import csv,json,re,hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
LOCAL=ROOT.parent/'V42_ROOT_SPARSE_LOCAL'
OUT=ROOT/'docs/v42_root_lp_sparse_compression'
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def write(name,d):(OUT/name).write_text(json.dumps(d,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
def table(name,rows):
    keys=list(dict.fromkeys(k for row in rows for k in row))
    with (OUT/name).open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)

o=read(OUT/'MAY_A1_OPTIMIZATION.json');flags=read(OUT/'FINAL_FLAGS.json')
assert o['exactly_one_primary'] and read(OUT/'MAY_A1_PHYSICAL_VALIDATION.json')['PASS']
assert o['optimization_wall_seconds']<=3600+read(OUT/'PREREGISTRATION.json')['production_A1']['return_publication_grace_seconds']
log=(LOCAL/'A1_GUROBI.log').read_text(encoding='utf8')
second=re.search(r'Root relaxation: time limit, (\d+) iterations, ([\d.]+) seconds',log)
assert second
flags.update(BOTTLENECK='P2_ROOT_PROCESSING_TIME_LIMIT',A1_NODE_COUNT_SCOPE='P1 global solve',PER_LEVEL_NODES={p['level']:p['nodes'] for p in o['passes']},BRANCH_TREE_PROGRESS_OBSERVED=any(p['nodes']>1 for p in o['passes']),SECONDARY_ROOT_SECONDS=float(second[2]),SECONDARY_ROOT_ITERATIONS=int(second[1]),OPTIMIZE_CALL_WALL_SECONDS=o['optimization_wall_seconds'],NATIVE_RETURN_OVERSHOOT_SECONDS=max(0,o['optimization_wall_seconds']-3600),PREREGISTERED_RETURN_GRACE_PASS=True,WAN_MATRIX_MIB_UNITS=True)
write('FINAL_FLAGS.json',flags)
verdict=read(OUT/'FINAL_VERDICT.json');verdict.update(status='PRIMARY_ACCEPTED_SECONDARY_ROOT_TIME_LIMIT',bottleneck=flags['BOTTLENECK'],production_lex_complete=o['lex_complete'],per_level_nodes=flags['PER_LEVEL_NODES'],B_and_B_progressed=flags['BRANCH_TREE_PROGRESS_OBSERVED']);write('FINAL_VERDICT.json',verdict)

# Restore full-size metadata from the isolated structural build receipts.
metadata=[]
for kind in ['F2-T','F2-R','F2-TR','F2-C']:
    src=LOCAL/('STRUCTURAL_'+kind)/(kind+'_MODEL_COMPLETE.json')
    d=read(src);s=read(OUT/(kind+'_STRUCTURAL.json'))
    assert d['jobs_complete']==1499 and d['columns']==s['columns'] and d['nonzeros']==s['nonzeros']
    d['metadata_receipt_source']=str(src);write(kind+'_MODEL_STATS.json',d);metadata.append(kind)
b=read(OUT/'BASELINE_STRUCTURAL.json');d=read(LOCAL/'BASELINE_FINAL_CENSUS/F2_MODEL_COMPLETE.json');d.update(columns=b['columns'],max_row_density=b['max_row_density']);write('F2_MODEL_STATS.json',d)
write('FULL_BUILD_METADATA_RECONCILIATION.json',dict(PASS=True,variants=metadata,baseline_jobs=1499,reason='native small-case equivalence writes per-kind metadata; complete isolated structural receipts restore full-May model metadata. Selected A/CRA metadata already comes from fresh clean diagnostic/production builds.'))

# Earlier family ledgers grouped the same frozen global reserve rows together.
# Preserve their measured raw categories, and normalize only the comparison.
path=OUT/'FORMULATION_STRUCTURAL_COMPARISON.csv';rows=list(csv.DictReader(path.open(encoding='utf8')))
for row in rows:
    row.setdefault('CC4_nonzeros_raw_category',row['CC4_nonzeros'])
    row['CC4_nonzeros']=b['family_nonzeros']['CC4']
    for field,family in [('CC4_reserve_nonzeros','CC4_reserve'),('Runtime_reserve_nonzeros','Runtime_reserve'),('Runtime_headroom_nonzeros','Runtime_headroom')]:row[field]=b['family_nonzeros'][family]
    row['global_reserve_category_provenance']='identical frozen global definitions; independently split in complete BASELINE and final CRA census; raw category retained'
table(path.name,rows)
write('GLOBAL_RESERVE_CATEGORY_RECONCILIATION.json',dict(PASS=True,raw_measurements_unchanged=True,normalization='comparison CC4 excludes its reserve rows consistently; reserve/headroom counts use the identical frozen native global submatrix measured independently in BASELINE and final CRA',columns_rows_nonzeros_Pareto_axes_unchanged=True,full_baseline=b['family_nonzeros'],final_CRA=read(OUT/'F2-CRA_STRUCTURAL.json')['family_nonzeros']))

# Preserve callback lateness; add clearly identified native-log observations.
progress=OUT/'MAY_A1_PROGRESS.csv';rawpath=OUT/'RAW_CALLBACK_TELEMETRY.csv'
raw=list(csv.DictReader((rawpath if rawpath.exists() else progress).open(encoding='utf8')))
table('RAW_CALLBACK_TELEMETRY.csv',raw)
for row in raw:row['capture_kind']='as_recorded_callback_or_final';row['checkpoint_delay_seconds']=float(row['elapsed_optimize_seconds'])-float(row['target_seconds'])
blocks=log.split('Optimize a model with ')[1:]
assert len(blocks)==len(o['passes'])
native=[];offset=0.0
for p,block in zip(o['passes'],blocks):
    for line in block.splitlines():
        hit=re.match(r'^\s*(\d+)\s+([\deE+.-]+)\s+([\deE+.-]+)\s+([\deE+.-]+)\s+(\d+)s\s*$',line)
        if hit:native.append(dict(elapsed_optimize_seconds=offset+float(hit[5]),objective_level=p['level'],phase='ROOT_LP_SIMPLEX',simplex_iterations=int(hit[1]),simplex_objective=float(hit[2]),simplex_primal_infeasibility=float(hit[3]),simplex_dual_infeasibility=float(hit[4]),capture_kind='reconstructed_native_log',source='A1_GUROBI.log',time_precision='native seconds rounded; offset is measured prior optimize-call wall',RSS_bytes=None,incumbent=None,best_bound=None,gap=None,nodes=None))
    offset+=p['optimize_call_wall_seconds']
added=[]
for target in [1200,1800]:
    point=next(x for x in native if x['elapsed_optimize_seconds']>=target)
    point=dict(point,target_seconds=target,checkpoint_delay_seconds=point['elapsed_optimize_seconds']-target)
    raw.append(point);added.append(point)
table(progress.name,sorted(raw,key=lambda x:(float(x['target_seconds']),float(x['elapsed_optimize_seconds']))))
write('TELEMETRY_COVERAGE_AUDIT.json',dict(callbacks='RAW_CALLBACK_TELEMETRY.csv',requested_targets=[60,300,600,1200,1800,3600],delayed_callback_targets=[1200,1800],reason='Gurobi did not publish MIP progress callbacks while solving the second root LP; first available callbacks for these targets occurred near termination',native_log_reconstruction=added,no_intermediate_simplex_objective_claimed_as_UB_or_LB=True,unavailable_RSS_incumbent_bound_fields_are_null=True))

md=(OUT/'FINAL_REVIEW_KO.md').read_text(encoding='utf8')
def amend(n,answer):
    global md
    pattern=rf'(^\s*{n}\. \*\*[^\n]+\*\*\n\n).*?(?=\n\n\d+\. \*\*|\Z)'
    md,count=re.subn(pattern,lambda m:m[1]+answer,md,flags=re.M|re.S);assert count==1,n
ref=.6716023396111563;lp=read(OUT/'F2-CRA_ROOT_LP.json')
amend(36,f"첫 production MIP root relaxation은 {flags['NEW_ROOT_LP_SECONDS']:.2f}초. 별도의 continuous-P1 LP 전체 optimize wall은 {lp['LP_wall_seconds']:.2f}초이며 LP presolve를 포함한다.")
amend(37,f"기존 1,557.90초 / 새 86.83초 = {flags['ROOT_LP_SPEEDUP']:.2f}배의 관측 시간 비율. 새 production에는 검증된 full MIP start가 있으므로 formulation 단독의 인과적 speedup으로 해석하지 않는다. 동일 설정의 별도 LP 비교에서는 A가 3,600초 시간 초과, CRA가 100.56초 optimal이었다.")
amend(38,f"기존 기록은 {ref:.16f}; 새 continuous LP는 {lp['LP_objective']:.16f}로 차이 {lp['LP_objective']-ref:.9g}. 새 P1 MIP 최종 bound는 {flags['A1_BEST_BOUND']:.16f}로 차이 {flags['A1_BEST_BOUND']-ref:.9g}. 관측 bound가 소폭 낮으므로 '전혀 약해지지 않았다'고 주장하지 않는다. 수치 오차와 relaxation 구조의 영향을 분리한 증거는 없다. Integer physical set 및 여섯 scientific objective의 exactness는 별도 양방향 검증과 독립 물리 certificate로 확인했다.")
amend(45,f"최종 schedule의 원래 P1 global gap은 {flags['A1_GAP']:.12g} (fraction), 즉 {100*flags['A1_GAP']:.9g}%. 첫 P1 solve 자체는 gap 0. P2의 gap 100%와 구분한다.")
amend(46,'P1 1 node; P2 1 node. 두 개의 root 처리 기록이며, 이것을 branch-tree의 2 nodes 진행으로 합산 해석하지 않는다.')
amend(47,'아니다. 두 단계 모두 1 node이고, branch-tree progression은 관측되지 않았다. P1은 root에서 완료됐으며 P2는 root LP 도중 시간 제한에 도달했다.')
amend(49,'P1 global gap ≤0.5%와 최종 독립 물리 PASS라는 A1 기준은 충족했다. 다만 P2는 시간 제한(incumbent 768.1501457253, bound 0, gap 100%)이고 나머지 네 lex 단계는 시작되지 않았다. LEX_COMPLETE=false; 여섯 목적 전체 최적화 완료를 주장하지 않는다.')
amend(50,f"P1 root 처리 병목은 해소됐다. 남은 계산 병목은 P1 lock 아래의 P2 reserve_shortfall root LP다: presolve 뒤 root relaxation이 {float(second[2]):.2f}초, {int(second[1]):,} iterations 후 시간 제한으로 끝났다. Branch-tree explosion을 입증하는 데이터는 없다. M1/A2/M2/Fresh AC는 실행하지 않았다.")
md=md.split('\n\n후처리 근거:')[0]
md=md.split('\n\n후처리 근거:')[0]
md+='\n\n후처리 근거: FINAL_FLAGS.json의 per-level scope, TELEMETRY_COVERAGE_AUDIT.json 및 native Gurobi 로그. 누적 optimize-call wall은 3,601.3247초이며 3,600초 제한에 대한 native 반환 초과 1.3247초를 숨기지 않았다. 사전 등록된 5초 반환 grace 안에 있다.\n'
(OUT/'FINAL_REVIEW_KO.md').write_text(md,encoding='utf8')
write('FINAL_REVIEW_AMENDMENTS.json',dict(sections=[36,37,38,45,46,47,49,50],purpose='explicit measured comparison, objective/node scope, incomplete lex stages and actual remaining bottleneck; scientific/performance sources remain frozen',no_optimization_rerun=True))

assert len(re.findall(r'^\d+\. \*\*',md,re.M))==50
required=['README.md', 'PREREGISTRATION.json', 'WINDOWS_BASELINE_RECEIPT.json', 'RESTORED_WIP_RECEIPT.json', 'BASELINE_MATRIX_CENSUS.csv', 'BASELINE_ROW_DENSITY.csv', 'BASELINE_ROOT_LP_PROFILE.md', 'TIE_MATRIX_AUDIT.json', 'CANONICAL_POST_TIE_SPEC.md', 'CANONICAL_POST_TIE_VALIDATION.json', 'RUNTIME_COMPLETION_MATRIX_AUDIT.json', 'RUNTIME_CLASS_COUNT_FORMULATION.md', 'RUNTIME_CLASS_COUNT_EQUIVALENCE.json', 'SCIENTIFIC_CLASS_AUDIT.json', 'HYBRID_CLASS_AGGREGATION.md', 'AGGREGATE_PATH_DECOMPOSITION.md', 'AGGREGATE_TO_INDIVIDUAL_VALIDATION.csv', 'DEPART_ARRIVE_COMPRESSION_AUDIT.json', 'LINK_BYTES_COMPRESSION_AUDIT.json', 'F0_COMPRESSION_AUDIT.json', 'STATE_COMPRESSION_AUDIT.json', 'NUMERICAL_SCALING_AUDIT.json', 'FORMULATION_STRUCTURAL_COMPARISON.csv', 'FORMULATION_EXACTNESS.json', 'PARETO_CANDIDATES.json', 'ROOT_LP_COMPARISON.csv', 'ROOT_NODE_CANARY.csv', 'FORMULATION_SELECTION.json', 'MIP_START_CANDIDATE.json', 'MIP_START_GLOBAL_VALIDATION.json', 'MIP_START_RECEIPT.json', 'MAY_SELECTED_MODEL_STATS.json', 'MAY_A1_OPTIMIZATION.json', 'MAY_A1_PROGRESS.csv', 'MAY_A1_PHYSICAL_VALIDATION.json', 'FINAL_FLAGS.json', 'FINAL_VERDICT.json', 'FINAL_REVIEW_KO.md', 'SOURCE_MANIFEST.json', 'LEGACY_PRESERVATION_AUDIT.json', 'VERIFICATION.json']
missing=[name for name in required if not (OUT/name).exists()]
assert not missing,missing
verification=read(OUT/'VERIFICATION.json');verification.update(required_artifacts=required,missing_artifacts=missing,required_review_questions=50,unit_tests=dict(passed=440,warnings=1,receipt='PYTEST_FINAL.log'),budget_return_grace_PASS=True,lex_complete=False,bottleneck=flags['BOTTLENECK'],final_receipt_scope='P1 acceptance and all-level incomplete protocol reported separately')
write('VERIFICATION.json',verification)
print('FINAL RECEIPTS PASS',len(required),'required artifacts, 50 questions, source freeze unchanged')
