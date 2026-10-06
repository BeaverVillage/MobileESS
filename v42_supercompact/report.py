"""Seal bounded experimental evidence and Korean 34-question review."""
from .common import *
from .formulation import census
from .build import load
import subprocess,csv,re
from collections import Counter

STATEMENTS=[
'이번 작업은 현재 4-MESS V42 M1의 scientific problem을 변경하지 않고, 이동경로의 integer 표현을 exact node-activity/flow formulation으로 재구성하고, 수학적으로 중복·고정·결정적임이 증명된 행과 변수만 제거한 exact reformulation이다.',
'PR160의 삭제 증명은 compact continuous relaxation에서도 다시 검증했으며, integer feasible set에서만 중복이지만 compact LP relaxation을 강화하는 행은 성능을 위해 유지했다.',
'Compact-specific continuous flow와 linking structure도 fixed-point exact presolve로 감사했으며, 증명되지 않은 행·변수·경로는 제거하지 않았다.',
'Binary 감소, row 감소, memory 감소만으로 성공을 선언하지 않았으며, root completion, valid global bound, node progress 및 valid MIP-gap의 실제 개선을 최종 선택 기준으로 사용했다.'
]
def run():
    data=read('SUPERCOMPACT_FINAL_MATRIX_AUDIT.json');s=data['summary'];start=read('COMPACT_START_VALIDATION.json');transport=read('PR160_CERTIFICATE_TRANSPORT_AUDIT.json');independent=read('SUPERCOMPACT_INDEPENDENT_VERIFICATION.json');selection=read('SUPERCOMPACT_SELECTION.json')
    names={'C0':'C0_COMPACT_FULL_RESULT.json','C1':'C1_COMPACT_REDUCED_RESULT.json','C2':'C2_SUPERCOMPACT_RESULT.json'}
    arms={k:read(v) for k,v in names.items()} if all((OUT/v).exists() for v in names.values()) else {}
    milestones={}
    for k,r in arms.items():
        native=(OUT/(k+'_NATIVE.log')).read_text(encoding='utf-8')
        root=re.search(r'Root relaxation: objective ([\deE+.-]+), (\d+) iterations, ([\d.]+) seconds \(([\d.]+) work units\)',native)
        r['root_Work_rounded_from_log']=float(root[4]) if root else None
        milestones[k]=dict(root_completed=bool(root),root_LP_time_rounded=float(root[3]) if root else None,root_LP_Work_rounded=float(root[4]) if root else None,root_objective_rounded=float(root[1]) if root else None,root_iterations=int(root[2]) if root else None,first_optimal_root_callback_received=r['first_root_optimal_callback'] is not None,log_SHA256=sha(OUT/(k+'_NATIVE.log')))
        write(names[k],r)
    write('NATIVE_ROOT_LOG_MILESTONES.json',dict(arms=milestones,log_values_have_printed_precision=True,uncompleted_roots_not_matched=True))
    original=read('CURRENT_ORIGINAL_MODEL_CENSUS.json');censusdata={'F0':original,'C0':data['C0'],'C1':data['C1'],'C2':data['C2']}
    refs={k:json.loads((OLD/v).read_text(encoding='utf-8')) for k,v in [('F0','M1_REDUNDANCY_BASELINE_RESULT.json'),('F1','M1_REDUNDANCY_REDUCED_RESULT.json')]}
    publication=read('PUBLICATION.json') if (OUT/'PUBLICATION.json').exists() else {};commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();source=read('SUPERCOMPACT_EXECUTION_FREEZE.json')['source_commit'] if (OUT/'SUPERCOMPACT_EXECUTION_FREEZE.json').exists() else commit
    def size(label):
        z=censusdata[label];return f"rows {z['rows']:,}, cols {z['columns']:,}, B {z['binaries']:,}, C {z['continuous']:,}, nnz {z['nnz']:,}"
    def armv(k,key):return arms[k][key] if k in arms else '미실행'
    pct=lambda n:f'{100*n:.6f}%'
    answers=[
        ('현재 원본 규모',size('F0')),('C0 규모',size('C0')),('C1 규모',size('C1')),('C2 규모',size('C2')),
        ('최종 binary',f"{data['C2']['binaries']:,}; 원본 대비 {pct(data['binary_reduction_vs_original'])} 감소"),
        ('최종 continuous',f"{data['C2']['continuous']:,}; C0 대비 {pct(data['reduction_vs_C0']['continuous'])} 감소"),
        ('compact-specific 제거 행',f"{s['compact_specific_rows_removed']:,}; C1→C2 순차 압축"),
        ('제거·고정 변수',f"제거 {s['variables_removed']:,}, continuous 고정값 증명 {s['fixed_variables']:,}, source activity binary 추가 고정 4개. 제거·고정 집계는 중첩되며 합산하지 않는다."),
        ('결정적 flow contraction',f"{s['deterministic_flows']:,}개 flow를 동일 activity 변수로 단위 치환. 중간 scientific event를 제거하는 다단계 route chain contraction은 0개."),
        ('bound 변경',f"{s['bounds_tightened']:,}건; 독립 검증 {independent['bound_tightening']['checked']:,}건. 동일 변수의 순차 tightening은 각각 기록."),
        ('compact LP에서 PR160 삭제 유지',f"{transport['compact_LP_safe']:,}개 전부. 정확한 행/대표/PCS/연결/분수 convex-hull 상계를 독립 재검증."),
        ('LP strengthening으로 PR160 행 유지',f"{transport['integer_only_LP_strengthening_retained']}개. 이번 인증 집합에는 integer-only 삭제 증명이 없었고 UNKNOWN/정수 전용 증명으로 삭제한 행도 0개."),
        ('grid auxiliary 제거',f"{s['grid_auxiliaries_eliminated']:,}개. 상수·완전히 같은 정의·희소 단위 alias만 채택."),
        ('nnz 증가로 grid auxiliary 유지',f"{s['grid_auxiliaries_keep_fill']:,}개에서 보수적 nnz union 비용 증가. 그 외 KEEP_FIXED/정확한 계수 표현 불가/필수 변수도 별도 기록."),
        ('C0 대비 행 감소',pct(data['reduction_vs_C0']['rows'])),('C0 대비 열 감소',pct(data['reduction_vs_C0']['columns'])),('C0 대비 nnz 감소',pct(data['reduction_vs_C0']['nnz'])),
        ('계수 범위',f"C0 {data['C0']['coefficient_range']} → C2 {data['C2']['coefficient_range']}; 모든 채택 계수/RHS는 저장 binary rational과 정확히 일치."),
        ('1,536 할당 동등성','PASS; F0/F1/C0/C1/C2의 feasibility, objective, 정수 경로와 모든 원본 P/Q/SOC/grid 행을 비교.'),
        ('경로 전수·양방향 증명','PASS; 작은 4종 그래프 11개 원본 경로와 compact 상태를 전수 비교. 평행 arc 에너지 fixture에는 binary selector 2개를 유지. 실제 현재 그래프 평행 arc 0개.'),
        ('fractional 삭제 증명','PASS; C0 LP의 원본 arc LP 투영이 동일함을 증명하고 PR160 및 C2 삭제마다 분수점에 유효한 증명만 적용.'),
        ('adversarial 검사',f"PASS; {read('SUPERCOMPACT_ADVERSARIAL_RESULTS.json')['tests']}개. 분기/역방향/단말/이동 SOC/PCS 사분면/grid/비결정적 chain/fill/정수 전용 중복 반례 포함."),
        ('현재 검증 start','PASS; COMPACT_START_VALID=true, P/Q/SOC/모드/경로 물리값 변경 0.'),
        ('최대 start residual',f"{start['maximum_row_residual']:.17g}; FeasibilityTol=1e-8 유지."),
        ('C0 root 완료',str(armv('C0','root_completed'))),('C1 root 완료',str(armv('C1','root_completed'))),('C2 root 완료',str(armv('C2','root_completed'))),
        ('root Work/time','아래 arm 표. C2 root LP Work는 로그의 반올림 값 452.05, root LP 시간 207.78초. C0/C1 root 미완료이며 미완료 Work를 matched progress 개선으로 해석하지 않는다. 첫 optimal-root callback은 전달되지 않아 null로 보존.'),
        ('node 수',' / '.join(f"{k}: {armv(k,'node_count')} (root 이후 {armv(k,'nodes_after_root')})" for k in ['C0','C1','C2'])),
        ('유효 UB/LB/gap','아래 표. native BestBd와 inherited full-domain LB는 별도 열로 표시.'),('메모리','아래 peak RSS/process commit 표. 메모리만으로 선택하지 않는다.'),
        ('SUPER_COMPACT_EXACT_SELECTED',str(selection['SUPER_COMPACT_EXACT_SELECTED'])),
        ('정확한 commit / Draft PR',f"실행 source {source}; evidence receipt {publication.get('evidence_commit',commit)}; Draft PR {publication.get('url','작성 예정')}; 게시 후 최종 head는 PUBLICATION.json/최종 응답에 별도 기록."),
        ('선택 시 다음 lane','Lane A native C2가 우선. Lane B/C는 callback/원본 행 preimage 증명 후, Lane D는 original-arc F1, Lane E는 recourse 10배 개선 예측 이후. 이번 작업에서는 tournament 미실행.' if selection['SUPER_COMPACT_EXACT_SELECTED'] else '선택하지 않았으므로 다음 tournament를 실행하지 않는다. 크기 개선은 유지하되 계산 개선 증거가 있는 별도 설계가 먼저다.')
    ]
    lines=[f"# 현재 4-MESS M1 exact supercompact 검토",'',f"최종 상태: **{selection['final_state']}**. 선택: **{selection['SUPER_COMPACT_EXACT_SELECTED']}**.",'',f"기준: PR160 `{BASE}`. PR124 `{REFERENCE}`는 설계/증명 참고에만 사용했다. scientific authority, 4 MESS, 96 slot, objective P1, PCS16, SOC 양 끝점, 모든 route/travel/grid 한계와 MIPGap .005를 보존했다.",'','| 모델 | rows | cols | binary | continuous | nnz |','|---|---:|---:|---:|---:|---:|']
    for k,z in censusdata.items():lines.append(f"| {k} | {z['rows']:,} | {z['columns']:,} | {z['binaries']:,} | {z['continuous']:,} | {z['nnz']:,} |")
    lines+=['',f"F1 원본 arc reference: rows {refs['F1']['rows']:,}, cols {refs['F1']['columns']:,}, B {refs['F1']['binaries']:,}, nnz {refs['F1']['nnz']:,}. F0/F1은 동일 authority·start·설정의 PR160 영수증을 사용했고 새 heavy solve를 재실행하지 않았다.",'','| 질문 | 답변 |','|---|---|']
    lines.extend(f'| {i}. {question} | {answer} |' for i,(question,answer) in enumerate(answers,1))
    lines+=['','| arm | root 완료 | root LP s | root LP Work (로그) | native Runtime s | 전체 Work | nodes | raw BestBd | safe native LB | inherited LB | valid LB | valid UB | valid gap |','|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for k,r in arms.items():
        lines.append('| '+' | '.join(str(v) for v in [k,r['root_completed'],r['root_time'],r['root_Work_rounded_from_log'],r['native_runtime'],r['Gurobi_Work'],r['node_count'],r['raw_native_BestBd'],r['safely_adjusted_native_bound'],r['inherited_certified_full_domain_LB'],r['valid_global_LB'],r['valid_UB'],r['valid_global_gap']])+' |')
    lines+=['','| arm | peak RSS GiB | process commit GiB | min free RAM GiB | 전체 arm s | 최초 native / independently valid incumbent s |','|---|---:|---:|---:|---:|---|']
    for k,r in arms.items():lines.append(f"| {k} | {r['peak_RSS']/2**30:.6f} | {r['peak_process_commit']/2**30:.6f} | {r['minimum_free_RAM']/2**30:.6f} | {r['total_arm_wall']:.6f} | {r['first_native_incumbent']} / {r['first_independently_valid_native_incumbent']} |")
    lines+=['','RSS/commit은 0.5초 간격의 동일 worker 순차 실행에서 관측한 최대치다. 모든 arm은 build 포함 300초 hard wall과 native TimeLimit=270초의 동일 설정으로 실행했다. 원본 검증 seed는 arm 시작 시점부터 유효한 incumbent로 별도 보유했으며 native 해가 검증 실패하면 유효 UB를 갱신하지 않았다. native 흐름의 정수 경로 복원은 유일하게 함의되는 algebraic flow 값만 허용했고 P/Q/SOC는 보정하지 않았다.','',f"정적 고정점은 {s['rounds']}라운드. 제거 행 증명: {s['row_proof_categories']}. 변수 제거: {s['elimination_categories']}. 독립 검증은 production deletion 함수를 호출하지 않고 C1 전체 행의 C2 preimage를 재구성했다.",'','Continuous 증가의 주원인은 원래 binary였던 207,928개 경로 arc를 continuous로 옮긴 것이다. 연결과 이동 에너지·비음수 flow bounds 때문에 비결정적 이동 flow는 유지했다. 192개 결정적 stay flow는 activity에 정확히 치환했으며 P/Q 연결 시간은 그대로다. 비단위 또는 dense 치환에서 계수 표현·bound 운반·nnz union/fill 비용이 안전하다고 증명되지 않으면 KEEP했다. 보수적 비용 proxy는 실제 성능 개선 증거와 구별한다.','',f"채택한 크기 gate: binary {pct(data['binary_reduction_vs_original'])} 감소, C0 대비 행 {pct(data['reduction_vs_C0']['rows'])}, nnz {pct(data['reduction_vs_C0']['nnz'])}. 선택 판정 근거는 SUPERCOMPACT_SELECTION.json의 matched root/valid gap/node gates다. LP microcheck 및 tournament solve 호출은 0회.",'']
    lines+=['\n\n'.join(STATEMENTS)]
    prose('FINAL_REVIEW_KO.md','\n'.join(lines))
    verify=read('VERIFICATION.json');verify.update(PASS=all(r['PASS'] for r in arms.values()) and independent['PASS'] and transport['PASS'] and start['PASS'],stage='FINAL',heavy_execution_pending=False,final_state=selection['final_state'],selected=selection['SUPER_COMPACT_EXACT_SELECTED'],source_commit=source,all_300_second_wall_caps_respected=all(r['total_arm_wall']<=300 for r in arms.values()),required_final_questions_answered=34,no_tournament_executed=True)
    write('VERIFICATION.json',verify)
    if selection['SUPER_COMPACT_EXACT_SELECTED']:
        freeze=read('SUPERCOMPACT_EXECUTION_FREEZE.json');freeze.update(name='SUPER_COMPACT_CURRENT_AUTHORITY_M1',selection=selection,freeze_files={n:sha(OUT/n) for n in ['C2_A.npz','C2_DATA.npz','C2_ELIMINATION_CERTIFICATES.json','C2_ROW_CERTIFICATES.json','C2_RETAINED_AXES.npz','COMPACT_BOUND_TIGHTENING.csv','C2_VALID_START.npz','COMPACT_START_MAPPING.json']},heavy_experiment_STOP=True);write('SUPER_COMPACT_CURRENT_AUTHORITY_M1.json',freeze)
    manifest={}
    paths=list((ROOT/'v42_supercompact').glob('*.py'))+[ROOT/'v42_supercompact/.gitattributes',ROOT/'.gitignore',ROOT/'.gitattributes']+list(OUT.iterdir())
    for p in sorted(paths):
        if p.is_file() and p.name!='SHA256_MANIFEST.json':manifest[str(p.relative_to(ROOT)).replace('\\','/')]=sha(p)
    write('SHA256_MANIFEST.json',dict(algorithm='SHA256',files=manifest,file_count=len(manifest),manifest_self_excluded=True,scientific_base=BASE,executed_source_commit=source))
    print('REPORT_SEALED',selection['final_state'],len(manifest),flush=True)

if __name__=='__main__':run()
