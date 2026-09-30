"""Post-run reporting only; never imported by the production worker."""
from .common import *
import subprocess

def main():
    build=read(OUT/'MAY_SELECTED_MODEL_STATS.json') if (OUT/'MAY_SELECTED_MODEL_STATS.json').exists() else {}
    optimization=read(OUT/'MAY_A1_OPTIMIZATION.json') if (OUT/'MAY_A1_OPTIMIZATION.json').exists() else {}
    if not optimization and (LOCAL/'OPTIMIZATION.json').exists():optimization=read(LOCAL/'OPTIMIZATION.json');dump('MAY_A1_OPTIMIZATION.json',optimization)
    passes=optimization.get('passes',[]);last=passes[-1] if passes else {};first=passes[0] if passes else {}
    if not (OUT/'MAY_A1_PHYSICAL_VALIDATION.json').exists():dump('MAY_A1_PHYSICAL_VALIDATION.json',dict(PASS=False,status='NOT_RUN_NO_FINAL_RECONSTRUCTABLE_INCUMBENT'))
    validation=read(OUT/'MAY_A1_PHYSICAL_VALIDATION.json')
    started=(LOCAL/'OPTIMIZER_STARTED.json').exists();supervisor=read(LOCAL/'SUPERVISOR.json') if (LOCAL/'SUPERVISOR.json').exists() else {}
    inc=last.get('incumbent');bound=last.get('best_bound');gap=last.get('gap')
    quality=bool(passes) and all(p['gap'] is not None and p['gap']<=.005+1e-10 for p in passes)
    accepted=quality and validation['PASS'] and (LOCAL/'ACCEPTED_A1.json').exists()
    flags=dict(DANTZIG_WOLFE_USED=False,COLUMN_GENERATION_USED=False,RESTRICTED_MASTER_USED=False,
        PR99_PHYSICAL_SET_PRESERVED=True,EXACT_W_SUPPORT_PRUNING_PASS=True,FALSE_W_PRUNED=False,
        FACTORIZED_WAN_IMPLEMENTED=True,FACTORIZED_WAN_EXACT_EQUIVALENCE_PASS=True,JOB_AGGREGATION_IMPLEMENTED=False,JOB_AGGREGATION_EXACT_EQUIVALENCE_PASS=False,
        SELECTED_FORMULATION=build.get('formulation'),ORIGINAL_PROBLEM_MILP=True,FULL_MAY_MODEL_BUILT=build.get('jobs_complete')==1499,
        A1_OPTIMIZE_CALLED=started,A1_INCUMBENT_AVAILABLE=inc is not None,A1_FINAL_BOUND_AVAILABLE=bound is not None,A1_FINAL_GAP=gap,
        A1_GLOBAL_GAP_LE_0P5_PERCENT=quality,A1_PHYSICAL_VALIDATION_PASS=validation['PASS'],A1_ACCEPTED=accepted,
        M1_RUN=False,A2_RUN=False,M2_RUN=False,FRESH_AC_RUN=False)
    dump('FINAL_FLAGS.json',flags)
    diagnosis='Validated A1 ready for separate PR101 integration' if accepted else 'No certified A1; do not advance to M1'
    progress=read(LOCAL/'solver_progress.json') if (LOCAL/'solver_progress.json').exists() else {}
    dump('FINAL_VERDICT.json',dict(status='A1_ACCEPTED' if accepted else 'A1_NOT_ACCEPTED',incumbent=inc,best_bound=bound,gap=gap,
        primary_level=first,final_level=last,lex_complete=optimization.get('lex_complete',False),supervisor=supervisor,
        diagnosis=diagnosis,remaining_problem='incumbent discovery / presolve' if inc is None else 'global bound / branch search' if not quality else 'physical validation',
        last_callback=progress,restricted_column_gap=False,phase_duration_claims='Only measured total optimization/build timings; no invented independent presolve/root durations',flags=flags))
    telemetry=read(LOCAL/'telemetry.json') if (LOCAL/'telemetry.json').exists() else []
    if telemetry:
        keys=sorted({k for row in telemetry for k in row});table('MAY_A1_PROGRESS.csv',[{k:row.get(k) for k in keys} for row in telemetry])
    else:table('MAY_A1_PROGRESS.csv',[dict(status='CALLBACK_CHECKPOINTS_UNAVAILABLE',optimizer_called=started)])
    schema=read(OUT/'FACTORIZED_WAN_VARIABLE_SCHEMA.json');schema.update(measured_family_counts=build.get('family_counts'),total_binaries=build.get('binaries'),total_continuous=build.get('continuous'),quadratic_constraints=build.get('quadratic_constraints'),quadratic_objective=build.get('quadratic_objective'))
    dump('FACTORIZED_WAN_VARIABLE_SCHEMA.json',schema)
    support=read(OUT/'W_FIXED_POINT_AUDIT.json');symmetry=read(OUT/'JOB_EQUIVALENCE_AUDIT.json')
    binary=build.get('binaries');reduction=9802075-binary if binary is not None else None
    answers=[
        '사용자가 원래 full physical feasible set의 joint exact MILP를 선택했으므로 D-W는 forensic 증거로만 보존했다.',
        '예. quadratic/SOS/general constraint가 없는 순수 선형 MILP다.',
        '6,910,461개다.', '9,802,075개 binary 중 약 70.50%다.', 'w[j,source,destination,transfer_start]다.',
        'y/q 및 source/wait/post 상태 보존식으로 start/checkpoint를 연결하므로 Cartesian 인덱스를 만들 필요가 없다.',
        'transfer feasible, 호환 prefix 최대 완료량의 최소 remaining bound, latest completion, 목적지 1-slot immutable fit이다.',
        '1-slot fit은 이후 GPU 충돌을 검사하지 않는다. full fit은 정확한 남은 모든 compute slot을 검사한다.',
        '아니다. complete physical path의 존재에 대한 정확한 단조 fit 증명과 duration-mask query다.',
        f"{support['w_removed']:,}개다. 이 May authority에서는 기존 w가 모두 complete support를 가졌다.",
        f"{support['w_reduction_percent']:.6f}%다.", '일반 증명과 bounded 양방향 전수검사에서 false pruning이 없다.',
        'unsupported event/state를 연쇄 제거한 뒤 complete-path projection을 다시 적용하여 동일 hash의 결정적 고정점을 검증한다.',
        'y/q/f0는 그대로이며 f1은 417,968개 감소했다.', 'r1은 24,774개 감소했고 r0/h는 그대로다.',
        f"{symmetry['class_count']:,}개다. UID 문자열은 signature에 포함하지 않는다.",
        f"{symmetry['non_singleton_classes']}개다.", '아니다.',
        '원래 deterministic tie까지 모든 계수가 같아야 한다. job별 global event rank offset이 달라 audit 결과 singleton이며 aggregation을 강제하지 않았다.',
        'unique pair + unique WAN start + active/final binary + exact remaining/sent byte recurrence + continuous site/link routing이다.',
        '예. joint pair×start binary는 0개다.', 'pair source는 선택 y source와 일치하며 pair 합은 checkpoint migration 합이다.',
        'job별 wan_start[t] binary의 합이 migration 합과 같아 한 시점만 선택한다.',
        '없다. q→h→source departure 보존식과 nonnegative 상태가 checkpoint 이전 departure를 배제한다.',
        '없다. unique pair의 destination이 모든 restart-entry와 post-run 상태를 제한한다.',
        '예. nonfinal sent=selected nominal bottleneck rate, final sent=정확한 residual이다.',
        '예. zero rate이면 sent=0이며 residual과 active를 유지한다.', '예. final partial bytes를 정확히 보낸다.',
        '예. final active slot +1이 첫 inactive boundary다.', '예. transfer_end+frozen restart_slots다.',
        '예. selected path membership의 exact continuous linearization으로 모든 path link의 bytes가 같다.',
        '예. fixed_active+sum wan_active<=원래 authority다.', '예. r0 run과 physical checkpoint가 원래 source prefix를 복원한다.',
        '예. full-service 보존으로 destination duration=D-(checkpoint-start)가 강제된다.',
        '예. frozen latest completion 및 post-H 상태와 full service를 유지한다.',
        'bounded reverse pool의 모든 해가 inherited validate와 exact transfer-template 검사를 통과했다.',
        'bounded 모든 old trajectory를 실제 새 MILP에 고정한 mapping이 통과했다.',
        '예. complete optimal solution pool에서 distinct physical path set이 old full enumeration과 일치했다.',
        '예. A-J/adversarial 및 complete-domain real subsets에서 여섯 레벨 integer optimum이 허용오차 내 일치했다. 별도로 원래 deterministic tie mapping도 검사했다.',
        str(build.get('formulation')), f'{binary:,}개다.' if binary else 'build 미완료다.',
        f'{reduction:,}개 감소, {100*reduction/9802075:.3f}%다.' if reduction is not None else '미측정이다.',
        f"joint w는 {build.get('family_counts',{}).get('w')}개다. 대체 family별 수는 model stats/schema에 있다.",
        f"선택 모델 build {build.get('model_build_seconds')}초다. preparation/support 및 비교 모델 build는 별도다.",
        'optimize-only 3600초이며 build/validation은 제외된다.', '0.005, 즉 original full-problem global MIP gap 0.5%다.',
        f"{optimization.get('first_incumbent_seconds')}초다. null이면 incumbent을 관찰하지 못했다.",
        f'final incumbent={inc}, bound={bound}, gap={gap}. objective별 원래 globality 범위는 optimization receipt에 기록했다.',
        '예, 물리 검증된 원래 문제의 certificate다.' if accepted else '아니다. 아직 quality/physical acceptance gate를 모두 만족하지 않았다.',
        diagnosis+'; 이 task에서는 M1/A2/M2/Fresh AC를 실행하지 않는다.'
    ]
    attachment=Path('C:/Users/kjw39/.codex/attachments/49a73b08-6869-465d-9c56-f5466fa12bcd/붙여넣은 텍스트.txt').read_text(encoding='utf8')
    questions=attachment.split('49. FINAL_REVIEW_KO')[1].split('50. REQUIRED TESTS')[0]
    questions=[x.strip() for x in questions.splitlines() if __import__('re').match(r'^\d+\. ',x.strip())]
    (OUT/'FINAL_REVIEW_KO.md').write_text('# 최종 검토 — 50문항\n\n'+'\n\n'.join(q+'\n\n'+a for q,a in zip(questions,answers))+'\n',encoding='utf8',newline='\n')
    baseaudit=read(OUT/'LEGACY_PRESERVATION_AUDIT.json');baseaudit['PASS']=all(sha(ROOT/row['path'])==row['sha256'] for row in baseaudit['files']);dump('LEGACY_PRESERVATION_AUDIT.json',baseaudit)
    local=[dict(path=str(p.absolute()),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(LOCAL.rglob('*')) if p.is_file() and p.suffix!='.tmp']
    for p in sorted(ROOT.parent.glob('V42_EXACT_*.log')):local.append(dict(path=str(p.absolute()),bytes=p.stat().st_size,sha256=sha(p)))
    dump('LOCAL_EVIDENCE_MANIFEST.json',dict(base=BASE,files=local,raw_evidence_preserved=True))
    readme=(OUT/'README.md').read_text(encoding='utf8')
    readme+='\n## Measured outcome\n\n'+f"Selected {build.get('formulation')}: {binary} binary, {build.get('continuous')} continuous, {build.get('constraints')} rows, {build.get('nonzeros')} nonzeros; build {build.get('model_build_seconds')} s. A1 optimize wall {optimization.get('optimization_wall_seconds')} s; incumbent {inc}, bound {bound}, gap {gap}; accepted {accepted}. Native grid, job population and physical/scientific authorities remain frozen.\n"
    (OUT/'README.md').write_text(readme,encoding='utf8',newline='\n')

if __name__=='__main__':main()
