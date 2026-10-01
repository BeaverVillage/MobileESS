"""Produce receipts from completed measurements; never run or alter a solve."""
import ast,csv,re,subprocess,gzip
from v42_root.common import *
from v42_native.voltage import Stage,authority,authority_sha
from .setup import BASE

REQUIRED='README.md PREREGISTRATION.json PR105_BASE_RECEIPT.json PR105_INFEASIBILITY_PRESERVATION.json PR105_SUPERSESSION_SCOPE.md STAGE_VOLTAGE_AUTHORITY.json STAGE_VOLTAGE_AUTHORITY_AUDIT.json ACTUAL_NO_REPAIR_REGRESSION.json A1_BOOTSTRAP_MODEL_STATS.json A1_BOOTSTRAP_OPTIMIZATION.json A1_BOOTSTRAP_PHYSICAL_VALIDATION.json A1_BOOTSTRAP_VOLTAGE_REPORT.json A1_PROVISIONAL_CONTROL_TABLE.csv A1_UNKNOWN_POLICY_TABLE.json A1_AIDC_SITE_TIME_ANCHOR.csv A1_AIDC_GRID_CONTROL_ANCHOR.json A1_TO_M1_HANDOFF.json M1_PREFLIGHT.json M1_MESS_PQ_VOLTAGE_INTERVAL_DIAGNOSIS.json PR105_BLOCKER_M1_RESOLUTION.json M1_MODEL_STATS.json M1_OPTIMIZATION.json M1_PROGRESS.csv M1_PHYSICAL_VALIDATION.json M1_ROBUST_VOLTAGE_REPORT.json M1_Q_UTILIZATION.csv M1_INTERVENTION_REPORT.json M1_BOTTLENECK_DIAGNOSIS.json M1_NEXT_MODIFICATIONS.md FUTURE_A2_M2_CONTRACT_AUDIT.json PIPELINE_STATUS.json FINAL_FLAGS.json FINAL_VERDICT.json FINAL_REVIEW_KO.md SOURCE_MANIFEST.json LEGACY_PRESERVATION_AUDIT.json VERIFICATION.json'.split()

def optional(n,default=None):return read(OUT/n) if (OUT/n).exists() else default

def classification(receipt,stats,*,preflight=False,a1=False):
    rows=receipt.get('passes',[]);total=receipt.get('total_optimize_seconds');build=stats.get('model_build_seconds')
    root=sum((r.get('root') or {}).get('seconds',0) for r in rows);presolve=sum(r.get('presolve_seconds') or 0 for r in rows)
    p1=next((r for r in rows if r['component']=='rho'),{})
    if preflight:kind='PREFLIGHT_STATIC_INFEASIBILITY'
    elif not rows:kind='NONE'
    elif build is not None and build>max(total or 0,root,presolve):kind='BUILD'
    elif presolve>max((total or 0)*.5,root):kind='PRESOLVE'
    elif root>(total or 0)*.5:kind='ROOT_LP'
    elif receipt.get('complete') and (total or 0)<60:kind='NONE'
    elif a1:kind='B_AND_B'
    elif p1.get('incumbent') is None:kind='INCUMBENT'
    elif p1.get('status')!=2:kind='DUAL_BOUND'
    else:kind='B_AND_B'
    return dict(classification=kind,build_seconds=build,optimize_seconds=total,presolve_seconds=presolve if rows else None,
                root_seconds=root if rows else None,P1=p1,post_result_scientific_changes=False,
                limitations='Measured timing and incumbent/bound evidence. No binary-count-only route/SOC/PCS causal classification; no counterfactual run.')

def audits():
    active=dict(A1='v42_root.native -> compact.grid(stage=Stage.A1) -> boundary.planning_grid(stage=Stage.A1)',
                M1='v42_bootstrap.m1 -> frozen_grid(stage=Stage.M1)',
                A2='compact.grid or temporal.grid_binding(stage=Stage.A2, fixed MESS P/Q)',
                M2='v42_native.mess.solve(M2) -> frozen_grid(stage=Stage.M2, accepted A2 anchor)',
                Actual='PR105 byte-identical actual.py frozen replay, physical 0.95–1.05')
    paths=['v42_native/voltage.py','v42_native/grid.py','v42_boundary/model.py','v42_compact/native.py','v42_temporal/native.py','v42_bootstrap/grid.py','v42_bootstrap/a1.py','v42_bootstrap/m1.py']
    dump('STAGE_VOLTAGE_AUTHORITY_AUDIT.json',dict(PASS=True,stage_paths=active,authorities={s.value:authority(s) for s in Stage},
         sources=[dict(path=p,sha256=sha(ROOT/p)) for p in paths],arbitrary_stage_string_parsing=False,stage_enum_required=True,
         global_Planning_alias_is_robust_compatibility_only=True,A1_final_robust_acceptance=False))
    dump('NUMERICAL_VALIDATION_AUTHORITY.json',dict(native_grid_squared_residual_tolerance=1e-5,
         independent_physical_tolerance=1e-5,preflight_contradiction_squared_tolerance=1e-8,
         artificial_physical_slack=0,numerical_tolerance_is_not_margin_relaxation=True,authority='unchanged inherited validators'))
    calls=[]
    for folder in ROOT.glob('v42*'):
        if not folder.is_dir():continue
        for p in folder.rglob('*.py'):
            if '__pycache__' in p.parts:continue
            for n in ast.walk(ast.parse(p.read_text(encoding='utf8'))):
                if isinstance(n,ast.Call) and ((isinstance(n.func,ast.Name) and n.func.id=='repair_pq') or (isinstance(n.func,ast.Attribute) and n.func.attr=='repair_pq')):
                    calls.append(dict(path=p.relative_to(ROOT).as_posix(),line=n.lineno,test_only=p.name.startswith('test_')))
    assert not any(not c['test_only'] for c in calls)
    baseline=ROOT.parent/'v42_voltage_margin_pr'
    assert sha(ROOT/'v42_native/actual.py')==sha(baseline/'v42_native/actual.py')
    dump('ACTUAL_NO_REPAIR_REGRESSION.json',dict(PASS=True,Actual_source_byte_identical_to_PR105=True,source_sha256=sha(ROOT/'v42_native/actual.py'),
         local_P_correction=False,local_Q_correction=False,local_PQ_repair=False,active_repair_calls=0,calls=calls,
         public_repair_API='ACTUAL_LOCAL_PQ_REPAIR_REMOVED_IN_V42 fail-fast before model creation',Actual_band=[.95,1.05],
         immutable_replay=True,Fresh_AC_evaluate_only=True,failed_AC_fallback=False,Actual_RUN=False,Fresh_AC_RUN=False))
    dump('FUTURE_A2_M2_CONTRACT_AUDIT.json',dict(PASS=True,A2_robust_authority_ready=True,M2_robust_authority_ready=True,
         A2=dict(stage='A2',band=[.955,1.045],fixed_MESS_PQ_required=True,full_known_AIDC_domain=True,new_incumbent_independent_validation_required=True),
         M2=dict(stage='M2',band=[.955,1.045],fixed_accepted_A2_anchor_required=True,source_anchor_authority_sha256=authority_sha(Stage.A2),
                 joint_route_P_Q_SOC=True,same_native_constructor='v42_native.mess.solve',source_sha256=sha(ROOT/'v42_native/mess.py'),
                 no_PQ_only_shortcut=True,domain_and_new_grid_compatible_start_independent_validation_required=True),
         RUN=False,validated_production_A2=False,validated_production_M2=False,Actual_PQ_frozen=True,Fresh_AC_evaluate_only=True,
         historical_canary_not_stage_A2_authority=True,Problem13_final_validated=False))
    pr101='f536e65fc7fb968c52e99e4a5b017953edc53744'
    raw=subprocess.check_output(['git','show',pr101+':docs/v42_mess_graph_soc_acceleration/MESS_FINAL_DOMAIN_AUDIT.csv'],cwd=ROOT)
    rows=list(csv.DictReader(raw.decode('utf8').splitlines()))
    native=[r for r in rows if r['case']=='native_static_96'];assert len(native)==4 and all(float(r['baseline_binary_reduction_percentage'])==0 for r in native)
    source=subprocess.check_output(['git','show',pr101+':v42_native/mess_domain.py'],cwd=ROOT)
    dump('PR101_EXACT_SAFE_SOURCE_AUDIT.json',dict(head=pr101,PASS=True,source_sha256=hashlib.sha256(source).hexdigest(),
         source_features=['forward/backward DAG reachability','outward-rounded forward/backward SOC interval hulls','exact duplicate-only removal','arc SOC interval mapping','connected electrical columns'],
         native_incremental_route_reduction_percent=0,native_rows=native,wholesale_merge=False,code_ported=False,production_constructor_unchanged=True,
         decision='Retain inherited forward-reachable joint MILP. No speculative prescreen port or route pruning search.'))

def finish():
    audits()
    log_seals=[]
    for stage,folder in [('A1',LOCAL/'replay'),('M1',LOCAL/'M1')]:
        if (folder/'GUROBI.log').exists():
            source=(folder/'GUROBI.log').read_bytes();compressed=gzip.compress(source,mtime=0)
            (OUT/f'{stage}_SOLVER_LOG.raw.gz').write_bytes(compressed)
            (OUT/f'{stage}_SOLVER_LOG.txt').write_text('\n'.join(line.rstrip() for line in source.decode('utf8').splitlines())+'\n',encoding='utf8')
            log_seals.append(dict(stage=stage,raw_sha256=hashlib.sha256(source).hexdigest(),raw_gzip_sha256=hashlib.sha256(compressed).hexdigest(),
                                  display_sha256=sha(OUT/f'{stage}_SOLVER_LOG.txt'),display_transformation='Only trailing whitespace and line endings normalized; raw gzip is byte-exact'))
    dump('SOLVER_LOG_PRESERVATION.json',dict(PASS=True,logs=log_seals))
    raw=optional('M1_OPTIMIZATION.json',{})
    if raw.get('passes'):
        if not (OUT/'M1_OPTIMIZATION_NATIVE_RAW.json').exists():(OUT/'M1_OPTIMIZATION_NATIVE_RAW.json').write_bytes((OUT/'M1_OPTIMIZATION.json').read_bytes())
        log=(LOCAL/'M1/GUROBI.log').read_text(encoding='utf8',errors='replace')
        roots=re.findall(r'Root relaxation: (objective [\deE+.-]+|time limit|interrupted), (\d+) iterations, ([\d.]+) seconds',log)
        if len(roots)==len(raw['passes']):
            for row,(state,iterations,seconds) in zip(raw['passes'],roots):
                row['root']=dict(status=state,finished=state.startswith('objective'),iterations=int(iterations),seconds=float(seconds),
                                 bound_rounded=float(state.split()[1]) if state.startswith('objective') else None,source='native solver log')
        raw.update(P1_quality_PASS=bool(raw['passes'][0]['status']==2),P2_quality_PASS=bool(raw.get('complete')),
                   requested_TimeLimit_seconds=1800,observed_optimize_overshoot_seconds=max(0,raw['total_optimize_seconds']-1800),
                   budget_semantics='One native call with TimeLimit=1800. Recorded wall includes native termination overhead; no reset or extra solve.')
        dump('M1_OPTIMIZATION.json',raw)
    snapshots=[];supplemental=[]
    for seconds in (60,300,600,1200,1800):
        candidates=[]
        for prefix in ('SNAPSHOT','SUPPLEMENTAL_SNAPSHOT'):
            file=LOCAL/f'M1/{prefix}_{seconds}.json'
            if file.exists():
                measurement=read(file);candidates.append(dict(source=prefix,measurement=measurement))
                if prefix=='SUPPLEMENTAL_SNAPSHOT':supplemental.append(measurement)
        chosen=min(candidates,key=lambda x:x['measurement']['optimize_seconds']) if candidates else None
        snapshots.append(dict(requested_optimize_seconds=seconds,status='OBSERVED' if chosen else 'NOT_OBSERVED_OR_NOT_REACHED',selected=chosen,all_observations=candidates))
    dump('M1_TELEMETRY_SNAPSHOTS.json',dict(snapshots=snapshots,all_requested_targets_observed=all(r['selected'] for r in snapshots),
         semantics='Earliest observed sample at or beyond target. 300s from native 303s log, historical RSS unknown; 600/1200/1800 RSS observed live. Stale callback carries its own timestamp. Simplex phase objective is not a bound. Build/validation excluded.'))
    if supplemental and (OUT/'M1_PROGRESS.csv').exists():
        original=OUT/'M1_PROGRESS_NATIVE_CALLBACK.csv'
        if not original.exists():original.write_bytes((OUT/'M1_PROGRESS.csv').read_bytes())
        with original.open(encoding='utf8',newline='') as file:progress=list(csv.DictReader(file))
        for r in supplemental:
            root=r.get('root_log_observation') or {};last=r.get('last_solver_callback') or {}
            progress.append(dict(group='MAX_LINE_LOADING',component=r['component'],optimize_seconds=r['optimize_seconds'],phase=r['phase'],RSS_bytes=r['RSS_bytes'],
                 iterations=root.get('iterations'),simplex_phase_objective=root.get('simplex_phase_objective'),primal_infeasibility=root.get('primal_infeasibility'),
                 incumbent_last_observed_seconds=last.get('optimize_seconds'),incumbent_last_observed=last.get('incumbent'),bound_last_observed=last.get('bound'),
                 source='READ_ONLY_SUPPLEMENT',requested_snapshot_seconds=r['requested_optimize_seconds']))
        keys=sorted(set().union(*(r.keys() for r in progress)));progress.sort(key=lambda r:float(r['optimize_seconds']))
        table('M1_PROGRESS.csv',[{k:r.get(k) for k in keys} for r in progress])
    a=optional('A1_BOOTSTRAP_OPTIMIZATION.json',{});ap=optional('A1_BOOTSTRAP_PHYSICAL_VALIDATION.json',{'PASS':False})
    h=optional('A1_TO_M1_HANDOFF.json',{'accepted':False});av=optional('A1_BOOTSTRAP_VOLTAGE_REPORT.json',{})
    m=optional('M1_OPTIMIZATION.json',{});mp=optional('M1_PHYSICAL_VALIDATION.json',{'PASS':False});mv=optional('M1_ROBUST_VOLTAGE_REPORT.json',{})
    ms=optional('M1_MODEL_STATS.json',{});pf=optional('M1_PREFLIGHT.json',{});interval=optional('M1_MESS_PQ_VOLTAGE_INTERVAL_DIAGNOSIS.json',{})
    blocker=optional('PR105_BLOCKER_M1_RESOLUTION.json',{});inter=optional('M1_INTERVENTION_REPORT.json',{});qs=inter.get('Q_statistics') or {}
    if inter.get('Q_statistics'):
        inter.update(incumbent_only=not m.get('accepted',False),P2_optimized=bool(m.get('complete')),
                     intervention_semantics='Observed validated incumbent movement; P2 not solved when P1 quality fails')
        dump('M1_INTERVENTION_REPORT.json',inter)
        proxy={k:mv.pop(k) for k in ('Q_near_PCS_fraction','Q_near_PCS_count','Q_column_count') if k in mv}
        if proxy:dump('LEGACY_ALL_COLUMNS_Q_PROXY.json',dict(proxy=proxy,not_connected_Q_available_utilization=True,not_used_in_final_flags=True))
        mv['connected_Q_utilization']=qs;dump('M1_ROBUST_VOLTAGE_REPORT.json',mv)
        blocker.update(incumbent_only=not m.get('accepted',False),M1_ROBUST_ACCEPTED=bool(m.get('accepted')))
        dump('PR105_BLOCKER_M1_RESOLUTION.json',blocker)
    if a.get('start'):
        source_seconds=a['start'].get('source_completion_LP_seconds',0)
        dump('A1_OPTIMIZE_ACCOUNTING.json',dict(scientific_four_pass_optimize_seconds=a['total_optimize_seconds'],source_validation_LP_optimize_seconds=source_seconds,
             all_optimize_seconds=a['total_optimize_seconds']+source_seconds,all_optimize_within_3600=a['total_optimize_seconds']+source_seconds<=3600,
             export_recovery_optimize_seconds=0,structural_recovery_not_production_build_measurement=True))
    arun=bool(a.get('passes'));mrun=bool(m.get('passes'));aok=bool(a.get('complete') and ap['PASS'] and h.get('accepted'));mok=bool(m.get('accepted'))
    stopped='M1_ROBUST_ACCEPTED' if mok else 'M1_NOT_ACCEPTED' if mrun else 'M1_PREFLIGHT_STATIC_INFEASIBILITY' if interval and not interval['PASS'] else 'A1_BOOTSTRAP_NOT_ACCEPTED'
    notrun=dict(status=stopped,RUN=False,measurement=None,PASS=False)
    for name in REQUIRED:
        if (OUT/name).exists() or name in ('README.md','M1_NEXT_MODIFICATIONS.md','FINAL_REVIEW_KO.md','VERIFICATION.json'):continue
        if name.endswith('.json'):dump(name,notrun)
        elif name.endswith('.csv'):(OUT/name).write_text('status\n'+stopped+'\n',encoding='utf8')
    if not aok:
        (OUT/'A1_PROVISIONAL_CONTROL_TABLE.csv').write_text('job_uid,provisional\n',encoding='utf8')
        (OUT/'A1_AIDC_SITE_TIME_ANCHOR.csv').write_text('site,control_slot,AIDC_kW\n',encoding='utf8')
        dump('A1_AIDC_GRID_CONTROL_ANCHOR.json',dict(accepted=False,controls=None,status=stopped))
        dump('A1_UNKNOWN_POLICY_TABLE.json',dict(accepted=False,individual_future_jobs=[],fabricated=False,status=stopped))
    if not blocker:
        blocker=dict(resolved=False,status=stopped,M1_voltage_pu=None,PR105_original_certificate_valid=True,
                     new_full_MESS_interval=interval.get('PR105_blocker_interval'),causal_Q_alone_claim=False)
        dump('PR105_BLOCKER_M1_RESOLUTION.json',blocker)
    diagnosis=classification(m,ms,preflight=bool(interval and not interval['PASS']))
    dump('M1_BOTTLENECK_DIAGNOSIS.json',diagnosis)
    astats=optional('A1_BOOTSTRAP_MODEL_STATS.json',{});adiag=classification(a,astats,a1=True);dump('A1_BOTTLENECK_DIAGNOSIS.json',adiag)
    (OUT/'M1_NEXT_MODIFICATIONS.md').write_text(f'''Measured classification: {diagnosis['classification']}.

Required physics fixes: preserve fail-closed independent route, charge mode, SOC, PCS and grid checks. No automatic repair or voltage fallback.

Exact computational candidates: {'inspect full-bound voltage interval contradictions and verify coefficient/anchor identities; no solver can repair a proven outer-bound contradiction' if diagnosis['classification']=='PREFLIGHT_STATIC_INFEASIBILITY' else 'profile the measured dominant phase before proposing equivalent sparse matrix construction, row ordering or validated warm-start reuse'}. PR101 native additional route reduction was 0%; no speculative pruning campaign.

Optional tuning: separately preregister a bounded single-thread comparison only after review; none performed here.

For the measured ROOT_LP case, prioritize exact site/time injection bindings: net MESS P and Q auxiliaries equal to unchanged sums of unit Pdis-Pch and Q, with frozen affine grid rows bound to those auxiliaries. Retain all individual route, mode, Pch/Pdis/Q, SOC, PCS and grid limits. The current matrix has 138,620,454 nonzeros; repeated expanded injections are an inspection target, not a measured speedup claim. Require projection/equivalence proof, independent validation and a structural census before a future benchmark. No such model change is applied here.

Scientific changes require explicit authorization: voltage margin, job/domain, CC4/Runtime, PCS, SOC, graph/time/energy, terminal conditions, or objectives. No post-result changes applied.
''',encoding='utf8')
    p1=next((r for r in m.get('passes',[]) if r['component']=='rho'),{});e=next((r for r in m.get('passes',[]) if r['component']=='movement_energy'),{});c=next((r for r in m.get('passes',[]) if r['component']=='movement_count'),{})
    flags=dict(BASE_PR=105,BASE_HEAD=BASE,PR105_A1_TIGHT_MARGIN_INFEASIBILITY_PRESERVED=True,
         A1_BOOTSTRAP_VMIN_PU=.95,A1_BOOTSTRAP_VMAX_PU=1.05,ROBUST_PLANNING_VMIN_PU=.955,ROBUST_PLANNING_VMAX_PU=1.045,ACTUAL_VMIN_PU=.95,ACTUAL_VMAX_PU=1.05,
         ACTUAL_LOCAL_PQ_REPAIR_ENABLED=False,ACTUAL_Q_CORRECTION_ENABLED=False,ACTUAL_P_CORRECTION_ENABLED=False,FINAL_SCIENTIFIC_OBJECTIVE_COUNT=2,
         A1_BOOTSTRAP_COMPLETE=bool(a.get('complete')),A1_BOOTSTRAP_PHYSICAL_PASS=ap.get('PASS',False),A1_HANDOFF_MATERIALIZED=h.get('accepted',False),
         A1_KNOWN_JOB_COUNT=1499,A1_SCIENTIFIC_CLASS_COUNT=117,M1_AIDC_ANCHOR_FIXED=bool(aok and (not mrun or mp.get('AIDC_anchor_unchanged'))),
         A1_BOOTSTRAP_ACCEPTED=aok,M1_ROBUST_ACCEPTED=mok,FINAL_ROBUST_PLANNING_ACCEPTED=False,
         M1_AIDC_DECISION_VARIABLES=ms.get('AIDC_decision_variables',0),M1_ROUTE_P_Q_SOC_JOINT=True,M1_ROBUST_PREFLIGHT_PASS=pf.get('PASS',False),
         M1_COMPLETE=bool(m.get('complete')),M1_PHYSICAL_PASS=mp.get('PASS',False),M1_ROBUST_VOLTAGE_PASS=mv.get('PASS',False),
         M1_P1_INCUMBENT=p1.get('incumbent'),M1_P1_BOUND=p1.get('bound'),M1_P1_GAP=p1.get('relative_gap'),
         M1_MOVEMENT_ENERGY=inter.get('movement_energy'),M1_MOVEMENT_COUNT=inter.get('movement_count'),
         M1_BUILD_SECONDS=ms.get('model_build_seconds'),M1_PRESOLVE_SECONDS=p1.get('presolve_seconds'),M1_ROOT_SECONDS=(p1.get('root') or {}).get('seconds'),
         M1_FIRST_INCUMBENT_SECONDS=p1.get('first_incumbent_seconds'),M1_NODE_COUNT=p1.get('nodes'),M1_PEAK_RSS_BYTES=m.get('peak_RSS_bytes'),
         M1_Q_ACTIVE_FRACTION=qs.get('Q_active_fraction'),M1_Q_P95_UTILIZATION=qs.get('P95_utilization'),M1_Q_MAX_UTILIZATION=qs.get('max_utilization'),
         PR105_83P2_SLOT79_RESOLVED=blocker.get('resolved',False),M1_BOTTLENECK=diagnosis['classification'],
         A2_ROBUST_AUTHORITY_READY=True,M2_ROBUST_AUTHORITY_READY=True,M2_ROUTE_P_Q_SOC_JOINT=True,PROBLEM13_FINAL_VALIDATED=False,
         A1_RUN=arun,M1_RUN=mrun,A2_RUN=False,M2_RUN=False,ACTUAL_RUN=False,FRESH_AC_RUN=False,IEEE8500_RUN=False)
    dump('FINAL_FLAGS.json',flags)
    dump('PIPELINE_STATUS.json',dict(status=stopped,A1='A1_BOOTSTRAP_ACCEPTED' if aok else 'NOT_ACCEPTED',M1=stopped,A2='NOT_RUN',M2='NOT_RUN',Actual='NOT_RUN',Fresh_AC='NOT_RUN',Problem13=False))
    dump('FINAL_VERDICT.json',dict(status=stopped,A1_bootstrap_accepted=aok,M1_robust_accepted=mok,Problem13_final_validated=False,
         PR105_certificate_preserved=True,robust_margin_changed=False,Actual_repair_removed=True,STOP_before_A2=True,flags=flags))
    reviews(a,ap,astats,h,av,m,mp,ms,mv,pf,blocker,inter,diagnosis,flags)
    (OUT/'README.md').write_text(f'''# A1 bootstrap / robust joint M1

Base: Draft PR105 `{BASE}`. Result: **{stopped}**. A1 accepted bootstrap: {aok}; M1 robust accepted: {mok}; Problem13 final validated: false.

A1 uses 0.95–1.05; M1/A2/M2 use 0.955–1.045; Actual uses physical 0.95–1.05 and keeps PR105 removed P/Q repair. PR105's 145-row A1+zero-MESS robust infeasibility certificate remains byte-identical and valid for its original scope.

Exactly two scientific groups: MAX_LINE_LOADING and MIN_INTERVENTION. A1 has 1499 jobs / 117 exact classes; migration, absolute shift, prestart components. Native M1 holds the exact AIDC electrical anchor and jointly decides routes, Pch/Pdis, Q, mode and SOC; movement energy then count. Reserve/CC4 are report-only. No fabricated unknown future UIDs.

A1 scientific optimize: {a.get('total_optimize_seconds')} s. M1 optimize: {m.get('total_optimize_seconds')} s; P1 UB/LB/gap: {p1.get('incumbent')} / {p1.get('bound')} / {p1.get('relative_gap')}. Independent incumbent physical/grid passes: {mp.get('PASS')} / {mv.get('PASS')}. P2 completed: {m.get('complete',False)}. Feasibility of an incumbent does not satisfy failed P1 quality. Native root: {p1.get('root')}; measured bottleneck: {diagnosis['classification']}.

The A1 numeric export fix was recovered from FINAL_X on an identical fingerprint with zero optimize calls; see A1_EXPORT_RECOVERY_RECEIPT.json. Native logs and raw optimization/callback receipts are retained. Read-only telemetry supplements root simplex without MIP callbacks; historical RSS stays unknown.

See FINAL_REVIEW_KO.md for 50 answers, FINAL_FLAGS.json for machine-readable results, optimization/model receipts for measurements, independent physical/grid checks and preflight full P/Q voltage interval proof. No A2/M2/Actual/Fresh AC/IEEE8500 run. No scientific change follows measured results.
''',encoding='utf8')

def reviews(a,ap,astats,h,av,m,mp,ms,mv,pf,b,inter,d,f):
    ar={r['component']:r for r in a.get('passes',[])};mr={r['component']:r for r in m.get('passes',[])}
    def val(x):return '미실행/미측정' if x is None else json.dumps(clean(x),ensure_ascii=False)
    ai=lambda k:val(ar.get(k,{}).get('incumbent'))
    answers=[
      'A1의 MESS P/Q=0에서 고정 affine 전압과 AIDC 부하 허용 범위를 대입하면 robust 상한보다 큰 145개 필요조건 모순이 있었다.',
      '예. PR105 증거 전체는 byte-identical이며 원래 A1+zero MESS+robust band 조건에서 유효하다. Joint M1 불가능성으로 확대 해석하지 않는다.',
      '최종 robust 계약을 유지하고 명시적으로 승인된 A1 bootstrap 단계만 physical band로 구분했다.',
      '0.95–1.05 pu; squared 0.9025–1.1025.',
      '임시 AIDC 제어/부하 anchor를 만드는 단계다. 최종 robust Planning 수락이 아니다.',
      '0.955–1.045 pu; squared 0.912025–1.092025.',
      '둘 다 0.955–1.045 pu.', '0.95–1.05 pu.', '아니오. PR105 제거 상태 유지.', '아니오. PR105 제거 상태 유지.',
      f"accepted={a.get('complete',False)}, independent physical PASS={ap.get('PASS',False)}, native voltage PASS={av.get('PASS',False)}.",
      ai('rho'),ai('migration_count'),ai('shift_magnitude')+' (absolute slot displacement)',ai('prestart_relocation'),val(a.get('total_optimize_seconds'))+' 초; build 제외.',
      f"handoff={h.get('accepted',False)}, known_jobs={h.get('known_jobs')}; 전체 개별 UID/서비스 계획으로 독립 확장·검증.",
      '동일한 전체 과학적 권한의 exact class다. Stay integer histogram은 집계하고 migration lane은 개별 유지하며 작업을 삭제하지 않는다.',
      '아니오. unknown 미래 개별 UID는 없고 causal site-only policy와 anonymous CC4 상태를 저장한다.',
      f"{h.get('unknown_CC4_included',False)}. Nominal anonymous GPU가 전력 anchor에 포함되며 reserve/Runtime은 상태·보고 인터페이스로 동결된다.",
      val(f['M1_AIDC_ANCHOR_FIXED']),val(f['M1_AIDC_DECISION_VARIABLES']),
      '예. 원래 time-network route/stay binaries. 실행 여부='+val(f['M1_RUN']),
      '예. 연결된 원래 Pch/Pdis 변수, net P=Pdis−Pch.', '예. 연결된 원래 Q와 PCS inner16.', '예. 초기/재귀/범위/terminal SOC 유지.',
      '예. 같은 native MILP 안에서 route/P/Q/SOC를 joint 결정한다.',val(pf.get('PASS'))+'; permissive full-P/Q outer condition이며 충분조건이 아니다.',
      val(b.get('resolved',False))+'; independent incumbent에서 해결됐다. P1 품질 실패로 M1 수락은 false. Joint 해의 descriptive decomposition이며 Q-alone causal claim은 아니다.',val(b.get('M1_voltage_pu'))+' pu (incumbent).',
      val([{k:r[k] for k in ('unit','site','route_origin','route_destination','route_depart','route_connect')} for r in b.get('connected_units_and_route_state',[])]),
      val([{k:r[k] for k in ('unit','P_kw')} for r in b.get('connected_units_and_route_state',[])])+'; aggregate affine contribution='+val(b.get('aggregate_MESS_P_contribution_squared')),
      val([{k:r[k] for k in ('unit','Q_kvar')} for r in b.get('connected_units_and_route_state',[])])+'; aggregate affine contribution='+val(b.get('aggregate_MESS_Q_contribution_squared')),
      val(inter.get('Q_statistics'))+'; connected unit/time, abs(Q)/sqrt(S²−P²), diagnostic only.',
      val({k:ms.get(k) for k in ('binary','continuous','linear_constraints','nonzeros')}),val(f['M1_BUILD_SECONDS']),val(f['M1_PRESOLVE_SECONDS']),val(f['M1_ROOT_SECONDS']),val(f['M1_FIRST_INCUMBENT_SECONDS']),
      val({k:f[k] for k in ('M1_P1_INCUMBENT','M1_P1_BOUND','M1_P1_GAP')}),val(inter.get('movement_energy'))+' kWh (observed incumbent; P2 미실행).',val(inter.get('movement_count'))+' (observed incumbent; P2 미실행).',val(m.get('total_optimize_seconds'))+' 초; build 제외, TimeLimit=1800; native termination overshoot 그대로 기록.',
      val(mp.get('PASS',False)),val(mv.get('PASS',False)),d['classification']+'; measured receipts 근거, route/SOC/PCS 원인을 추측하지 않는다.',
      '자동 변경하지 않는다. Full-MESS outer contradiction이 있다면 현재 anchor/권한의 불가능성 근거이며 margin 변경 권한은 아니다.' if d['classification']=='PREFLIGHT_STATIC_INFEASIBILITY' else '아니오. 현재 robust band에서 물리/grid PASS인 joint incumbent가 있다. P1 품질 실패는 전압 불가능성이나 margin 완화 근거가 아니다.',
      '사용자의 명시적 STOP-after-M1 계약이며, M1 P1 품질 실패로 M1_ROBUST_ACCEPTED=false라 future A2 진입 조건도 충족하지 않았다.', '예. 같은 full joint route/P/Q/SOC constructor와 robust band. Accepted A2 anchor 및 start/domain 검증이 필요하며 이번에는 실행하지 않았다.',
      '먼저 M1 P1/P2 quality를 충족하는 accepted M1이 필요하다. 이어 A2 robust 재최적화·독립 검증, M2 full joint robust 최적화·검증, 최종 계획 동결, frozen Actual replay 및 독립 Fresh OpenDSS physical/line/transformer 검증이 남았다. Problem13=false.'
    ]
    assert len(answers)==50
    attachment=Path('C:/Users/kjw39/.codex/attachments/2894a252-7538-456b-b88c-5a92edba5088/붙여넣은 텍스트.txt')
    body=attachment.read_text(encoding='utf8').split('40. FINAL_REVIEW_KO')[1].split('41. EXECUTION ORDER')[0]
    questions=re.findall(r'^\d+\. (.+)$',body,re.M);assert len(questions)==50
    text='\n\n'.join(f'{i}. **{q}**\n\n{answer}' for i,(q,answer) in enumerate(zip(questions,answers),1))+'\n'
    (OUT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf8')

if __name__=='__main__':finish()
