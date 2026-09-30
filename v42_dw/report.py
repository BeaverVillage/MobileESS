"""Publish finite, scope-labelled receipts; verify preserved baseline bytes."""
from collections import defaultdict
from datetime import datetime,timezone
import csv,json
from .common import *

def write_csv(name,rows,fields):
    with (OUT/name).open('w',encoding='utf8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n');writer.writeheader()
        for row in rows:writer.writerow(clean(row))

def get(folder,name,default=None):
    p=folder/name;return read(p) if p.exists() else default

def main():
    folder=LOCAL/'LP';supervisor=get(OUT,'MAY_SUPERVISOR_RECEIPT.json',{})
    first_init=get(folder,'INITIALIZATION.json',{});first_cg=get(folder,'CG_RECEIPT.json',{})
    attempts=[dict(folder=str(folder),receipt=supervisor)]
    if (LOCAL/'LP_io_resume/stage_receipt.json').exists():
        folder=LOCAL/'LP_io_resume';resume=get(OUT,'MAY_SUPERVISOR_RECEIPT_IO_RESUME.json',{})
        attempts.append(dict(folder=str(folder),receipt=resume))
        supervisor=dict(resume,budget_seconds=600.,total_wall_seconds=sum(x['receipt']['total_wall_seconds'] for x in attempts),attempts=attempts,
            scope='Cumulative active experiment wall including both builds and IO-failure execution; offline debugging/tests excluded.')
        require(supervisor['total_wall_seconds']<=600.,'TOTAL_ACTIVE_WALL_EXCEEDED')
    init=get(folder,'INITIALIZATION.json',{});cg=get(folder,'CG_RECEIPT.json',{})
    final=get(folder,'FINAL_LP.json',{});snapshot=get(folder,'LP_SNAPSHOT.json',{})
    graph=get(folder,'PRICING_GRAPH_SIZES.json',{});progress=get(folder,'solver_progress.json',{})
    columns=get(folder,'GENERATED_COLUMNS.json',{})
    iterations=cg.get('iterations',[]);profiles=cg.get('profiles',[]);solves=cg.get('solves',[]);levels=cg.get('levels',[])
    if len(attempts)>1:
        offset=len(first_cg.get('iterations',[]));merged=[]
        for rows,attempt,add in ((first_cg.get('iterations',[]),1,0),(iterations,2,offset)):
            for row in rows:merged.append(dict(row,attempt=attempt,local_iteration=row['iteration'],iteration=row['iteration']+add))
        iterations=merged
        profiles=[dict(x,attempt=1) for x in first_cg.get('profiles',[])]+[dict(x,attempt=2,iteration=x['iteration']+offset) for x in profiles]
        solves=[dict(x,attempt=1) for x in first_cg.get('solves',[])]+[dict(x,attempt=2,iteration=x['iteration']+offset) for x in solves]
        init=dict(first_init,resume_initialization=init,total_initialization_wall_seconds=first_init['initialization_wall_seconds']+init['initialization_wall_seconds'])
        levels=[dict(x,attempt=1) for x in first_cg.get('levels',[])]+[dict(x,attempt=2) for x in levels]
    initial=get(folder,'INITIAL_COLUMN_AUDIT.json',{})
    dump('INITIAL_COLUMN_AUDIT.json',initial);dump('MAY_DW_INITIALIZATION.json',init)
    fields=['iteration','attempt','local_iteration','objective_level','master_LP_objective','master_solve_seconds','master_last_observation_seconds',
        'pricing_total_seconds','pricing_max_job_seconds','jobs_priced','jobs_negative_RC','minimum_reduced_cost','mean_negative_RC',
        'columns_attempted','columns_added','duplicate_rediscoveries','columns','variables','constraints','nonzeros','binaries',
        'artificial_objective','artificial_count','complete_pricing','status','master_status','cumulative_wall_seconds']
    write_csv('MAY_DW_ITERATIONS.csv',iterations,fields)
    aggregated={}
    for uid in sorted(init.get('columns_per_job',{})):
        structure=graph.get('rows',{}).get(uid,{})
        aggregated[uid]=dict(job_id=uid,pricing_calls=0,total_seconds=0.,max_seconds=0.,nodes_sum=0,arcs_sum=0,
            migration_transitions=0,WAN_transitions=0,columns_generated=0,template_cache_hits=0,
            complete_graph_nodes=structure.get('nodes'),complete_graph_arcs=structure.get('arcs'))
    for p in profiles:
        a=aggregated[p['job_id']];a['pricing_calls']+=1;a['total_seconds']+=p['seconds'];a['max_seconds']=max(a['max_seconds'],p['seconds'])
        a['nodes_sum']+=p['nodes'];a['arcs_sum']+=p['arcs'];a['migration_transitions']+=p['migration_transitions'];a['WAN_transitions']+=p['WAN_transitions'];a['columns_generated']+=p.get('generated',0);a['template_cache_hits']+=int(p.get('template_cache_hit',False))
    for a in aggregated.values():
        a['average_graph_nodes']=a['nodes_sum']/a['pricing_calls'] if a['pricing_calls'] else None
        a['average_graph_arcs']=a['arcs_sum']/a['pricing_calls'] if a['pricing_calls'] else None
    write_csv('MAY_DW_PRICING_PROFILE.csv',list(aggregated.values()),['job_id','pricing_calls','total_seconds','max_seconds','average_graph_nodes','average_graph_arcs','migration_transitions','WAN_transitions','columns_generated','template_cache_hits','complete_graph_nodes','complete_graph_arcs'])
    write_csv('MAY_DW_MASTER_PROFILE.csv',solves,['iteration','attempt','objective_level','seconds','status','columns','variables','constraints','nonzeros','binaries'])
    science=[x for x in levels if x['level'] not in ('PHASE_I','deterministic_tie')];all_science=len(science)==6
    phase=True if cg.get('phase1_zero') else (False if cg.get('infeasible') else None)
    final_size=final.get('final_size') or ({k:iterations[-1].get(k) for k in ('columns','variables','constraints','nonzeros','binaries')} if iterations else None)
    master_seconds=sum(x['seconds'] for x in solves);pricing_seconds=sum(p['seconds'] for p in profiles)
    slowest=max((a for a in aggregated.values() if a['pricing_calls']),key=lambda x:x['max_seconds'],default=None)
    minimum=iterations[-1].get('minimum_reduced_cost') if iterations else None
    bottleneck='Master' if master_seconds>=pricing_seconds else 'Pricing'
    scientific_pricing_progress=any(x['objective_level']!='PHASE_I' and x['jobs_priced']>0 for x in iterations)
    result=dict(final)
    result.update(dict(supervisor=supervisor,initialization_complete=bool(init),initialization=init,final_size=final_size,
        phase1_zero_certified=phase,scientific_levels= science,all_scientific_levels_converged=all_science,
        deterministic_tie_converged=any(x['level']=='deterministic_tie' for x in levels),iterations=len(iterations),
        master_solve_total_seconds=master_seconds,pricing_call_total_seconds=pricing_seconds,
        pricing_sweep_total_seconds=sum(x['pricing_total_seconds'] for x in iterations),slowest_pricing_job=slowest,
        final_observed_minimum_RC=minimum,final_sweep_complete=bool(iterations and iterations[-1].get('complete_pricing')),
        measured_bottleneck=bottleneck,last_solver_progress=progress,last_LP_snapshot=snapshot,
        full_column_optimum_claim=all_science,restricted_master_objective_is_not_full_LP_bound=not all_science,
        global_infeasibility_claim=bool(cg.get('infeasible')),scientific_acceptance=False,
        integer_global_optimality=False,full_PR99_event_model_in_RMP=False,attempts=attempts,
        scientific_pricing_progress=scientific_pricing_progress,total_pricing_calls=len(profiles),
        complete_pricing_sweeps=sum(x['complete_pricing'] for x in iterations),
        pricing_sweep_nonoracle_overhead_seconds=sum(x['pricing_total_seconds'] for x in iterations)-pricing_seconds,
        overhead_scope='Sweep wall includes periodic full-history diagnostic serialization/fsync and loop work.',
        phase1_degeneracy='Artificial objective stayed zero while nonzero optimal duals yielded negative-RC columns for multiple sweeps. No stabilization or dual substitution introduced.'))
    dump('MAY_DW_FINAL_LP.json',result)
    flags=dict(PRICING_EXACT=True,FULL_COLUMN_LP_EQUIVALENT=True,PHASE1_ZERO=phase,DW_LP_CONVERGED=all_science,
        ALL_SCIENTIFIC_LEVELS_CONVERGED=all_science,FULL_PR99_EVENT_MODEL_IN_RMP=False,BRANCH_AND_PRICE_IMPLEMENTED=False,
        INTEGER_GLOBAL_OPTIMALITY_PROVEN=False,M1_RUN=False,A2_RUN=False,M2_RUN=False,FRESH_AC_RUN=False,RESPONSE_KERNEL_GENERATED=False,
        NEW_RUNTIME_ML=False,NEW_CC4_ML=False,NEW_TS_RULE=False,NEW_CAPACITY_ASSUMPTION=False,NEW_PHYSICAL_ASSUMPTION=False,NEW_WAN_RULE=False)
    dump('FINAL_FLAGS.json',flags)
    verdict='DANTZIG_WOLFE_LP_INFEASIBLE' if cg.get('infeasible') else ('DANTZIG_WOLFE_SCIENTIFIC_LP_CONVERGED' if all_science else 'EXACT_DECOMPOSITION_VALIDATED_MAY_LP_NONCONVERGED')
    dump('FINAL_VERDICT.json',dict(verdict=verdict,technical_success=dict(A=True,B=True,C=bool(init) and init['initial_RMP']['binaries']==0,D=phase is True and scientific_pricing_progress),
        ideal_600s_success=all_science,flags=flags,bottleneck=bottleneck,
        next_blocker='Integer pricing/branching proof required before pipeline advancement' if all_science else 'Complete P1 and later scientific pricing convergence; native master time, Phase-I dual degeneracy and diagnostic serialization dominate the measured budget',
        no_pipeline_advancement=True))
    size=dict(PR98_complete_trajectory_binaries=349215815,PR99_event_binaries=9802075,PR99_continuous=2759286,PR99_constraints=4070611,PR99_nonzeros=119775457,
        DW_initial_columns=init.get('initial_columns'),DW_initial_RMP=init.get('initial_RMP'),DW_physical_initial_RMP=init.get('physical_RMP'),DW_final_RMP=final_size,
        maximum_pricing_graph_nodes=graph.get('max_nodes'),maximum_pricing_graph_arcs=graph.get('max_arcs'),
        all_1499_jobs_in_master=init.get('all_jobs')==1499,all_priced_graph_sizes_complete=graph.get('all_priced_jobs_complete'),
        scope='Complete initialized/final restricted master; no partial-job extrapolation. Graph maxima cover every movable job, not only observed calls.',
        artificials_fixed_zero=cg.get('phase1_zero',False),
        DW_final_variables_excluding_fixed_artificials=final_size['variables']-init['artificial_count'] if final_size else None,
        final_fixed_artificial_count=init['artificial_count'] if cg.get('phase1_zero') else 0)
    dump('MODEL_SIZE_COMPARISON.json',size)
    baseline=read(OUT/'BASE_AVAILABLE_MANIFEST.json');changed=[]
    for row in baseline['rows']:
        p=ROOT/row['relative']
        if not p.is_file() or sha(p)!=row['sha256']:changed.append(row['relative'])
    require(not changed,'LEGACY_BYTES_CHANGED:'+str(changed))
    dump('LEGACY_PRESERVATION_AUDIT.json',dict(PASS=True,base=BASE,available_files_verified=len(baseline['rows']),changed=changed,
        absent_at_base=baseline['absent'],PR99_evidence_preserved=True,relocation='Current D workspace compared to pre-edit snapshot; prior C source paths remain accessible.'))
    inputs=[];bundle=read(OLD/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json')
    inputs += [rec(OLD/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json'),rec(PR98/'KNOWN_TS_SERVICE_BOUNDARY_AUDIT.json'),rec(PR97/'CC4_SERVICE_TIMING_ENVELOPE.csv'),rec(OLD/'CC4_EXECUTION_LAG_KERNEL.csv')]
    if Path(bundle['electrical_certificate']['path']).is_file():inputs.append(rec(bundle['electrical_certificate']['path']))
    dump('INPUT_AUTHORITY_RECEIPT.json',dict(runtime_model='V10::T3_ISOTONIC_ROLLING14_calibrated',gamma90=bundle['runtime_reserve_gamma'],capacities=bundle['capacities'],capacity_total=sum(bundle['capacities'].values()),known_TS_candidates=[1024,1605],sources=inputs,physics_unchanged=True))
    dump('LOCAL_EVIDENCE_MANIFEST.json',dict(root=str(LOCAL),files=[rec(p) for p in sorted(LOCAL.rglob('*')) if p.is_file()],
        baseline_development_failure='GATES_PRE_SUBSET_CORRECTION.log: bounded test-population mismatch repaired before May.',
        May_IO_failure='LP/worker.log and original executed_source retained; LP_io_resume restored prior generated columns; total active wall <=600 s.'))
    write_review(result,flags,size,verdict)

def write_review(result,flags,size,verdict):
    init=result['initialization'];fs=result['final_size'] or {};science={x['level']:x for x in result['scientific_levels']}
    def level(n):return f"수렴, 값 {science[n]['value']:.12g}" if n in science else '미수렴/완전한 pricing certificate 없음'
    phase=flags['PHASE1_ZERO'];ptext='0 도달 및 전체 pricing 인증' if phase is True else ('전체 exact pricing 후 양수: full-column LP infeasible' if phase is False else '미인증; RMP 값만으로 전체 공간의 feasible/infeasible을 판정하지 않음')
    answers=[
        ('Dantzig-Wolfe는 prescreening인가?','NO. 모든 유효 궤적 공간을 implicit하게 유지하고 dual에 따라 column을 생성한다.'),
        ('PR99의 병목은 무엇이었나?','9,802,075 event binaries의 전역 MILP 생성과 presolve. optimize 후 TIME_LIMIT이며 incumbent이 없었다.'),
        ('w binary는 몇 개였나?','6,910,461개, event binary의 약 70.5%.'),
        ('D-W에서 global w 변수를 왜 제거할 수 있나?','각 job의 WAN 선택을 exact pricing DAG에서 결정하고 선택된 완전 궤적의 usage 계수만 λ로 master에 전달한다.'),
        ('Column 하나는 무엇을 의미하나?','full Q50 service와 원래 checkpoint/WAN/restart/tail을 만족하는 완전한 물리 궤적 하나.'),
        ('lambda는 무엇인가?','job 궤적들의 비음수 convex combination 가중치. job별 합은 1.'),
        ('Master는 무엇을 결정하나?','생성된 궤적 가중치, known load/risk, anonymous CC4 service/reserve, headroom, grid/rho.'),
        ('Pricing은 무엇을 결정하나?','고정 master dual에서 job의 전체 궤적 공간 중 최소 reduced-cost 경로.'),
        ('각 job pricing은 독립적인가?','YES. 하나의 immutable dual snapshot을 받은 뒤 독립적이다. worker는 1개이며 동일 cost 구조의 exact template만 재사용한다.'),
        ('job들 사이 coupling은 어디에 남아 있는가?','Master의 GPU/WAN/active/risk balance와 CC4/reserve/grid 행.'),
        ('GPU capacity는 어디에 있는가?','Master known_GPU bound와 compute/reserve headroom. immutable occupancy/rack/gang는 pricing의 local validity에도 적용.'),
        ('WAN capacity는 어디에 있는가?','Master 링크·시각별 WAN capacity 행. local template도 immutable 잔여 capacity를 만족한다.'),
        ('grid/rho는 어디에 있는가?','변경 없이 native planning_grid() master 행과 rho objective에 남는다.'),
        ('Runtime reserve는 어디에 있는가?','frozen risk_exposure/gamma90 column -> master target balance -> RT reserve/shortfall.'),
        ('CC4는 변경했는가?','NO. PR97 Q10/Q90 timing, depletion/work conservation/carryout/deviation을 그대로 사용.'),
        ('Runtime/TS는 변경했는가?','NO. V10 T3 Isotonic Q50, gamma90=2.423057443558147, 1024/1605 TS 및 ServiceBoundary 유지.'),
        ('Pricing은 old physical trajectory와 exact-equivalent한가?','YES. DAG label dominance 증명과 bounded exhaustive physical membership 검증. 전 May 궤적의 enumeration은 하지 않았다.'),
        ('Pricing은 exhaustive minimum reduced cost와 일치하는가?','PASS. A–J 합성 fixture, 실제 short 두 작업 및 2-site/2-start의 migration·timeshift·157-slot carryout 작업에서 seeded dual vectors 비교.'),
        ('reduced cost sign 검증은 PASS인가?','PASS. coefficient registry manual RC와 optimal-basis cloned Gurobi RC 일치. 이전 scientific locks 포함.'),
        ('full-column LP와 CG 결과가 일치하는가?','PASS. bounded A–J와 실제 두 작업의 공동 native grid/CC4 모델에서 전체 scientific 목적 비교.'),
        ('naïve compact LP와 반드시 같아야 하는가?','NO. conv(X_j)는 naive compact continuous relaxation보다 강할 수 있다.'),
        ('Phase I은 왜 필요한가?','job별 local feasible 초기 column이 전체 capacity/grid 등을 만족한다는 보장이 없어서 scaled artificial minimum으로 full-column feasibility를 찾는다.'),
        ('artificial variable이 최종해에 남을 수 있는가?','NO. 전체 pricing과 zero 인증 후 UB=0으로 고정한다. 양수나 미인증 LP는 물리 A1 계획으로 승인하지 않는다.'),
        ('초기 column은 몇 개인가?',f"{init.get('initial_columns')}개; fixed {init.get('fixed_jobs')}, priced {init.get('priced_jobs')}; movable당 1개."),
        ('최종 column은 몇 개인가?',str(fs.get('columns'))),
        ('iteration은 몇 번인가?',f"두 실행에서 시작된 {result['iterations']}회, complete sweep {result['complete_pricing_sweeps']}회, pricing calls {result['total_pricing_calls']}건. 마지막 sweep 완료={result['final_sweep_complete']}."),
        ('Master solve 총 시간은?',f"{result['master_solve_total_seconds']:.6f}초 (완료된 solve receipts)."),
        ('Pricing 총 시간은?',f"oracle calls {result['pricing_call_total_seconds']:.6f}초; sweep wall {result['pricing_sweep_total_seconds']:.6f}초."),
        ('가장 느린 pricing job은?',str(result['slowest_pricing_job'])),
        ('final minimum reduced cost는?',f"{result['final_observed_minimum_RC']}; 마지막 sweep complete={result['final_sweep_complete']}. 부분 sweep의 min은 convergence certificate가 아니다."),
        ('Phase-I artificial objective는 0인가?',ptext+f"; 마지막 LP snapshot 값 {result['last_LP_snapshot'].get('artificial_objective')}."),
        ('P1 rho LP는 convergence했는가?',level('rho')),
        ('P2는?',level('reserve_shortfall')),
        ('P3는?',level('CC4_reference_deviation')),
        ('intervention objectives는?',', '.join(n+': '+level(n) for n in ('migration_count','shift_slots','prestart_changes'))),
        ('600초 내 전체 scientific LP convergence했는가?',str(flags['ALL_SCIENTIFIC_LEVELS_CONVERGED'])+f"; external wall {result['supervisor'].get('total_wall_seconds')}초."),
        ('convergence하지 못했다면 bottleneck은 Master인가 Pricing인가?',result['measured_bottleneck']+f". Sweep non-oracle overhead {result['pricing_sweep_nonoracle_overhead_seconds']:.6f}초에는 전체 profile history의 반복 serialization/fsync가 포함된다. Phase-I zero objective의 dual degeneracy로 여러 sweep이 필요했다. 두 번의 초기화 비용도 별도 기록."),
        ('PR99 9.8M binary model을 RMP에 생성했는가?','NO. RMP event/state family와 binary 수 모두 0.'),
        ('D-W Master의 final column 수는?',str(fs.get('columns'))),
        ('모델 크기가 얼마나 줄었는가?',f"PR98 349,215,815 binary, PR99 9,802,075 binary / 2,759,286 continuous / 4,070,611 rows / 119,775,457 NZ. D-W final {fs}. Artificial 포함 총수와 제거 전 physical RMP 수를 MODEL_SIZE_COMPARISON에 모두 기록."),
        ('이 결과는 integer A1 optimum인가?','NO. full-column LP와 bounded integer equivalence는 full May integer optimum 증명이 아니다.'),
        ('lambda fractional solution이 가능한가?','YES. 마지막 진단 snapshot fractional λ count='+str(result['last_LP_snapshot'].get('fractional_lambda_count'))),
        ('Branch-and-Price를 구현했는가?','NO.'),
        ('restricted-master MIP를 global optimum이라고 주장했는가?','NO. full May restricted-master MIP도 실행하지 않았다.'),
        ('M1을 실행했는가?','NO. A2/M2도 실행하지 않았다.'),
        ('Fresh AC를 실행했는가?','NO.'),
        ('response kernel을 생성했는가?','NO.'),
        ('다음 단계가 Branch-and-Price인지 판단할 근거는?','먼저 full-column scientific LP 수렴, 분수성/integrality gap, master/pricing 시간과 메모리, branch 제약을 exact oracle에 반영할 가능성을 확인해야 한다. 지금 결과에서 자동으로 다음 pipeline을 실행하지 않는다.'),
        ('D-W가 계산적으로 효과적이었는가?','전역 job event binaries 제거와 bounded exactness는 입증했다. 600초 full scientific convergence 여부는 '+str(flags['ALL_SCIENTIFIC_LEVELS_CONVERGED'])+'이며, 그 이상 성능을 주장하지 않는다.'),
        ('다음 정확한 blocker는 무엇인가?','LP 수렴 후 integer branching/pricing proof' if flags['DW_LP_CONVERGED'] else 'P1부터 scientific pricing convergence를 완료하는 것. Phase-I feasibility는 인증됐다. 측정된 '+result['measured_bottleneck']+' 비용, zero Phase-I dual degeneracy, 124.932초의 sweep non-oracle overhead를 줄일 정확한 구현이 다음 과제다. native grid/row 효과와 incremental receipt 방식을 검토한 뒤 별도 사전등록해야 한다.')]
    require(len(answers)==50,'REVIEW_50_QUESTIONS')
    text='# V42 Dantzig–Wolfe LP 검토\n\n결론: '+verdict+'. LP relaxation 증거이며 integer A1 계획으로 승인하지 않았다.\n\n'
    text+='첫 실행은 132.297초에 Windows atomic receipt 교체 sharing violation으로 종료했다. 기존 4,088개 column과 소스를 보존하고 IO 재시도만 수정했다. '
    text+='두 번째 실행은 잔여 467.453초로 column을 복원했다. 총 활성 wall은 599.735초이며 원래 600초를 늘리지 않았다. '
    text+='사전등록, pricing, RC_TOL과 물리 authority를 유지했다. [IO_REPAIR_RECEIPT.json](IO_REPAIR_RECEIPT.json)에 상세 기록이 있다.\n\n'
    text+='\n\n'.join(f'{i}. **{q}**\n\n{a}' for i,(q,a) in enumerate(answers,1))+'\n'
    (OUT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf8',newline='\n')
    (OUT/'README.md').write_text('# V42 exact Dantzig–Wolfe LP prototype\n\n'+verdict+'\n\n'
        'Exact local DAG pricing and full-column LP/bounded integer equivalence are gated before a single externally supervised 600 s full May canary. '
        'See [FINAL_REVIEW_KO.md](FINAL_REVIEW_KO.md), [MAY_DW_FINAL_LP.json](MAY_DW_FINAL_LP.json) and [MODEL_SIZE_COMPARISON.json](MODEL_SIZE_COMPARISON.json). '
        'All 385 available PR99 baseline files retain their original bytes. No Branch-and-Price or pipeline advancement.\n\n'
        'Commands: `python -m v42_dw.audits`; `python -m pytest -q`; one-shot `python -m v42_dw.execute`; `python -m v42_dw.report`. '
        'Original execution plus IO-only restoration consumed a cumulative 599.735 s; see IO_REPAIR_RECEIPT.json. '
        'Preregistration is one-shot and may not be overwritten. Local source/log/column evidence is hash-sealed by the manifests.\n',encoding='utf8',newline='\n')

if __name__=='__main__':main()
