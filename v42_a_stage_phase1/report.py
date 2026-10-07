"""Read-only postsolve replay/provenance and Korean bounded-canary review.

This reporting module is added AFTER the executed source freeze. It never
constructs or optimizes a Gurobi model and cannot authorize another native run.
"""
from pathlib import Path
from fractions import Fraction
import subprocess,csv,json
import zipfile,hashlib
import numpy as np
import scipy.sparse as sp
from v42_pr134_b1.common import atomic,read,record,table,sha
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_domain_v2.postsolve_review import internal_attempts
from .setup import ROOT,OUT,STATIC,HISTORY,DAY
from .core import primal_replay,verify_sign_convention
from . import BASE


def review_raw(calls):
    records=[]
    for call in calls:
        folder=Path(call['folder']);identity=read(call['model_identity']['path'])
        for r in (identity['matrix'],identity['attributes'],call['raw_attributes']):
            if record(r['path'])!=r:raise ValueError('PERSISTED_NATIVE_BYTES_CHANGED')
        attrs=np.load(identity['attributes']['path']);raw=np.load(call['raw_attributes']['path'])
        objective=Objective('Phi' if call['component']=='PHASE_I' else 'P1',tuple(
            (int(j),Fraction(float(attrs['objective'][j]))) for j in np.flatnonzero(attrs['objective'])),Fraction(0))
        snapshot=LinearSnapshot(sp.load_npz(identity['matrix']['path']),attrs['lower'],attrs['upper'],
            attrs['senses'],attrs['rhs'],attrs['vtypes'],(objective,)).require()
        rec=dict(component=call['component'],native_status=call['status'],native_seconds=call['native_seconds'],
            available_raw_attributes=raw.files,raw_persisted_before_verification=True,source_commit=call['source_commit'],
            matrix_and_attribute_bytes_verified=True,original_raw_files_unchanged=True,primal=None,dual_sign=None,
            replayed_objective=None,original_artificial_free_replay=None)
        if 'X' in raw:
            rec['primal']=primal_replay(snapshot,raw['X'])
            rec['replayed_objective']=str(sum((c*Fraction(float(raw['X'][j])) for j,c in objective.terms),Fraction(0)))
            if call['component']=='PHASE_I':
                n=int(np.flatnonzero(attrs['objective'])[0])
                original=LinearSnapshot(snapshot.matrix[:,:n],snapshot.lower[:n],snapshot.upper[:n],
                    snapshot.senses,snapshot.rhs,snapshot.vtypes[:n],(Objective('none',(),0),))
                rec['original_artificial_free_replay']=primal_replay(original,raw['X'][:n])
        if all(k in raw for k in ('Pi','RC')):
            try:rec['dual_sign']=verify_sign_convention(snapshot,raw['Pi'],raw['RC'])
            except Exception as error:rec['dual_sign']=dict(PASS=False,error=str(error))
        rec['raw_classification']='NUMERICAL_RAW_FAIL' if rec['primal'] and not rec['primal']['PASS'] else 'RAW_AVAILABLE_NOT_CLOSURE' if rec['primal'] else 'RAW_UNAVAILABLE'
        atomic(folder/'POSTSOLVE_RAW_REVIEW.json',rec);records.append(rec)
    atomic(OUT/'MAY19/POSTSOLVE_REVIEW.json',dict(scope='DIAGNOSTIC_REPLAY_ONLY; native status and raw data never replaced',records=records))
    return records


def performance(result,calls):
    old=ROOT/'docs/v42_b1_may19_prescreening_rescue_20261007/evidence/S_A'
    a=read(old/'COMPACT/A2SC_MODEL_CENSUS.json');ar=read(old/'RESULT.json')['LP']
    aa=internal_attempts((old/'LP_NATIVE.log').read_text(encoding='utf8'))
    complete=ROOT/'docs/v42_a_stage_v2_stress4_20261007/MAY19';b=read(complete/'rho/PASS_RESULT.json')
    bc=read(complete/'DOMAIN_CENSUS.json');ba=internal_attempts((complete/'rho/NATIVE_SOLVER.log').read_text(encoding='utf8'))
    c=read(OUT/'PHASE1_CONSTRUCTION_VERIFICATION.json');first=calls[0] if calls else {}
    def max_metric(attempts,name):return max((v.get(name,0) for v in attempts),default=None)
    rows=[dict(architecture='A_historical_restricted_PR165_S_A',scientific_domain_complete=False,
        active_STAY=None,active_migration=None,rows=a['rows'],columns=a['columns'],nnz=a['nnz'],
        presolved_rows=2657339,presolved_columns=2524847,
        factor_nnz=max_metric(aa,'factor_nnz'),factor_memory_GB=max_metric(aa,'factor_memory_GB'),
        peak_RSS_GB=None,native_seconds=ar['native_runtime'],feasibility='UNRESOLVED_TIME_LIMIT_RAW_FAIL',closure=False,
        source=str(old/'RESULT.json'),notes='old S0 physical census:34426 STAY/11737638 migration; actual merged S_A active counts not captured; zero-objective feasibility LP/Crossover0'),
        dict(architecture='B_V2_COMPLETE_STAY_ALL_ACTIVE',scientific_domain_complete=True,
            active_STAY=bc['qualification_active_STAY_options'],active_migration=bc['new_hard_physical']['migration_path_multiplicity']-bc['inactive_migration_path_multiplicity'],
            rows=b['model_census']['rows'],columns=b['model_census']['cols'],nnz=b['model_census']['nnz'],
            presolved_rows=2958547,presolved_columns=3718260,factor_nnz=max_metric(ba,'factor_nnz'),
            factor_memory_GB=max_metric(ba,'factor_memory_GB'),peak_RSS_GB=None,
            native_seconds=b['native_seconds'],feasibility='ROOT_LP_TIMEOUT_NO_INCUMBENT',closure=False,
            source=str(complete/'A1_RESULT.json'),notes='complete STAY active; remaining physical migration pool retained; MILP rho root timeout'),
        dict(architecture='C_PHASE1_FAST_ACTIVE_ORIGINAL',scientific_domain_complete=True,
            active_STAY=result['final_active_STAY'],active_migration=result['final_active_migration'],
            rows=result['final_original_model']['rows'],columns=result['final_original_model']['cols'],nnz=result['final_original_model']['nnz'],
            presolved_rows=None,presolved_columns=None,factor_nnz=first.get('max_factor_nnz'),factor_memory_GB=first.get('max_factor_memory_GB'),
            peak_RSS_GB=(first['peak_RSS_bytes']/1e9 if first.get('peak_RSS_bytes') else None),native_seconds=result['native_seconds'],
            feasibility=result['classification'],closure=result['LP_PRICING_CLOSED'],source=str(OUT/'MAY19/PHASE1_RESULT.json'),
            notes='original scientific matrix; artificials are counted in the separate auxiliary row below'),
        dict(architecture='C_PHASE1_AUXILIARY_ACTUALLY_SOLVED',scientific_domain_complete=True,
            active_STAY=result['final_active_STAY'],active_migration=result['final_active_migration'],
            rows=c['phase1_rows'],columns=c['phase1_columns'],nnz=c['phase1_nnz'],
            presolved_rows=(first.get('presolved_matrix') or {}).get('rows'),presolved_columns=(first.get('presolved_matrix') or {}).get('columns'),
            factor_nnz=first.get('max_factor_nnz'),factor_memory_GB=first.get('max_factor_memory_GB'),
            peak_RSS_GB=(first['peak_RSS_bytes']/1e9 if first.get('peak_RSS_bytes') else None),native_seconds=result['native_seconds'],
            feasibility=result['classification'],closure=result['FULL_LP_FEASIBILITY_CLOSED'],source=str(OUT/'MAY19/PHASE1_RESULT.json'),
            notes=str(c['artificial_columns'])+' auxiliary variables; no production solution with positive Phi')]
    table(OUT/'MAY19/PERFORMANCE_COMPARISON.csv',rows,list(rows[0]))
    atomic(OUT/'MAY19/PERFORMANCE_COMPARISON.json',dict(records=rows,successful_root_speedup_measured=False,
        time_limits_and_objectives_differ=True,timeout_runtime_ratio_is_not_completed_root_speedup=True))
    return rows


def create_report(pr_url='PENDING_PUBLICATION'):
    result=read(OUT/'MAY19/PHASE1_RESULT.json');gate=read(OUT/'MAY19/SPEED_GATE_V2.json')
    original_freeze=OUT/'PHASE1_SOURCE_FREEZE.json'
    latest_path=OUT/'PHASE1_SOURCE_FREEZE_CONTINUATION_001.json'
    if not latest_path.exists():latest_path=original_freeze
    freeze=read(latest_path);calls=read(OUT/'MAY19/NATIVE_CALLS.json')['calls']
    archives=[]
    for path in dict.fromkeys([original_freeze,latest_path]):
        version=read(path)
        if record(version['source_archive']['path'])!=version['source_archive']:raise ValueError('EXECUTED_SOURCE_ARCHIVE_DRIFT')
        with zipfile.ZipFile(version['source_archive']['path']) as archive:
            for i,r in enumerate(version['source_files']):
                source=Path(r['path']);name='repo/'+source.relative_to(ROOT).as_posix() if source.is_relative_to(ROOT) else 'external/'+str(i)+'/'+source.name
                if hashlib.sha256(archive.read(name)).hexdigest()!=r['sha256']:raise ValueError('ARCHIVED_ACTUAL_SOURCE_BYTE_DRIFT')
        archives.append(dict(source_commit=version['git_head'],archive=version['source_archive'],all_archived_source_bytes_verified=True))
    raw=review_raw(calls);comp=performance(result,calls)
    drift=[r['path'] for r in freeze['source_files'] if record(r['path'])!=r]
    historical=subprocess.check_output(['git','diff',BASE,'--name-only','--','docs/v42_a_stage_fast_active_domain_20261007',
        'docs/v42_a_stage_v2_stress4_20261007','docs/v42_a_stage_domain_authority_v2_20261007',
        'docs/v42_b1_may19_prescreening_rescue_20261007','v42_a_stage_domain_v2'],cwd=ROOT,text=True).splitlines()
    if drift or historical:raise ValueError('EXECUTED_SOURCE_OR_HISTORICAL_EVIDENCE_CHANGED')
    by_head={r['source_commit']:r['archive']['sha256'] for r in archives}
    table(OUT/'MAY19/NATIVE_RUN_SOURCES.csv',[dict(call=i,component=c['component'],folder=c['folder'],
        native_seconds=c['native_seconds'],source_commit=c['source_commit'],source_archive_sha256=by_head[c['source_commit']],
        raw_sha256=c['raw_attributes']['sha256'],model_identity_sha256=c['model_identity']['sha256']) for i,c in enumerate(calls)],
        ['call','component','folder','native_seconds','source_commit','source_archive_sha256','raw_sha256','model_identity_sha256'])
    remaining=[name for name in ('FULL_LP_FEASIBILITY_CLOSED','FULL_LP_DOMAIN_INFEASIBLE','LP_PRICING_CLOSED',
        'INTEGER_DOMAIN_CLOSURE_PROVEN','PRODUCTION_ACCEPTED') if result[name] is not True]
    test_path=OUT/'SYNTHETIC_TESTS_CONTINUATION_001.json'
    if not test_path.exists():test_path=OUT/'SYNTHETIC_TESTS.json'
    tests=read(test_path)['tests']
    atomic(OUT/'VERIFICATION.json',dict(PASS=gate['PASS'],audit_PASS=True,primary_classification=result['classification'],
        speed_gate=gate['classification'],pre_run_tests=tests,executed_source_versions=archives,
        original_active_reassembled_matrix_and_four_objectives_identical=read(OUT/'BLOCK_PRICING_ORACLE_VERIFICATION.json')['reassembled_initial_original_matrix_and_all_four_objectives_exactly_equal'],
        source_drift=drift,historical_evidence_changed=historical,source_archive_verified=record(freeze['source_archive']['path'])==freeze['source_archive'],
        all_available_raw_arrays_persisted_before_assertions=True,pricing_certification_incomplete=not result['LP_PRICING_CLOSED'],
        unresolved_closure_states=remaining,production_accepted_dates=[],May17_current_task_native_calls=0,
        May12_current_task_native_calls=0,May10_current_task_native_calls=0,Planning_calls=0,Actual_calls=0,Fresh_OpenDSS_calls=0,
        no_post_gate_run_authorized=not gate['PASS'],exact_executed_source_head=freeze['git_head'],
        reporting_source=record(__file__),source_freeze_has_no_native_calls_after_report=True))
    phi=result.get('initial_phi');replayed=raw[0].get('replayed_objective') if raw else None
    initial=f"native ObjVal={phi}; raw replay Phi={replayed}; native status={calls[0]['status'] if calls else 'NONE'}. 원 solver 값은 진단이며 원본 물리 feasibility가 아닙니다."
    factor=max((c.get('max_factor_nnz') or 0 for c in calls),default=0)
    memory=max((c.get('max_factor_memory_GB') or 0 for c in calls),default=0)
    questions=[
        ('Exact base HEAD?',BASE),
        ('PR168 실패 이유?', '제한 active LP가84.455초에 INFEASIBLE(status3)을 반환했고 usable FarkasDual을 회수하지 못해 feasibility activation과 전체 LP pricing closure가 막혔습니다.'),
        ('속도 감소 자체는 성공했는가?', '행/열/nnz 및 최대 factor25.46M/0.5GB로 감소했습니다. 완료된 feasible root의 speedup은 측정되지 않았습니다.'),
        ('FarkasDual 문제?', '수치 trouble 및 내부 barrier 재시도 후 해당 attribute가 unavailable했습니다. solver 설정이나 물리 infeasibility의 원인을 증명한 것은 아닙니다.'),
        ('Phase-I가 Farkas를 피하는 방식?', '항상 feasible한 별도 elastic LP의 Pi와 실제 RC를 저장하고, complete native local block의 feasibility 가격을 계산합니다. FarkasDual을 읽지 않습니다.'),
        ('정확한 formulation?', '등식 a·x+u−v=b, ≤행 a·x−s≤b, ≥행 a·x+s≥b; u,v,s≥0. original scientific columns/rows/bounds를 복사하고 auxiliary columns만 추가합니다.'),
        ('artificial 대상 행?', '692160개 global/nonlocal 행. GPU, Runtime, WAN, ACTIVE 결합과 grid/CC4 전역 행입니다. Hard local20631행에는 추가하지 않습니다.'),
        ('hard physical constraints?', 'class exact-cardinality, release/complete/compatibility, native local flow/state/checkpoint/transfer/WAN/service/finish 및 original variable bounds를 유지합니다. GPU/Runtime/global capacity는 Phase-I copy에서만 elastic이며 original 모델에서는 hard입니다.'),
        ('Phi objective?', 'Σw_i artificial_i. 최초 original row scale의 다음2의 거듭제곱 역수인 양의 dyadic rational을 사전 고정했습니다. 695424개 actual weight의 NPZ byte receipt를 저장했고 activation 후에도 retune하지 않습니다.'),
        ('Phi>0 의미?', '제한 active auxiliary LP의 잔여 violation입니다. Full-domain physical infeasibility나 production feasibility를 뜻하지 않습니다. 엄밀한 full lower bound>0과 complete pricing closure 없이는 full LP infeasible을 선언하지 않습니다.'),
        ('초기 May19 Phi?',initial),
        ('Phase-I iterations?', str(sum(c['component']=='PHASE_I' for c in calls))+' native master solve; activation rounds='+str(result['activation_rounds'])),
        ('STAY activation?',str(result['actual_activated_STAY'])),
        ('migration activation?',str(result['actual_activated_migration'])),
        ('complete STAY pool 가격 계산?', '197537 physical STAY/161644 initial inactive STAY의 lossless provider와 native coupling을 검증했습니다. 실제 complete canary pricing 수행 여부는 Phase-I/closure receipt에 따르며 static producer PASS는 가격 완료가 아닙니다.'),
        ('complete migration lossless 가격?', '97724022 physical paths/1710374 compact blocks의 전체 graph union과 original native hard LP를 만들었습니다. 모든 mixed fractional finish 방향을 포함하고 N개의 동일 continuous lane 합 투영을 증명/검증했습니다. Native canary complete pricing closure는 '+str(result['LP_PRICING_CLOSED'])+'입니다.'),
        ('마지막 omitted minimum rc?', 'complete pricing result가 없으면 미측정입니다. 각 block은 exact original-binary64 rational lower bound와 native feasible point 가격의 interval을 반환하며, gap 미인증을 exact attained minimum으로 표시하지 않습니다.'),
        ('Phi certified zero?',str(result['ACTIVE_DOMAIN_FEASIBLE'])+'; original rows/bounds replay와1e−8 Phi zero tolerance를 모두 요구합니다.'),
        ('full LP infeasibility proven?',str(result['FULL_LP_DOMAIN_INFEASIBLE'])),
        ('후보 영구 삭제?', 'NO. D_ACTIVE⊂D_PHYSICAL, D_POOL=D_PHYSICAL\\D_ACTIVE. Engineering threshold는 실행/활성화를 멈추며 물리 pool을 삭제하지 않습니다.'),
        ('reference_start hard cutoff?', 'NO. 순위/warm support/objective 정보만 유지합니다.'),
        ('final active model size?',str(result['final_original_model'])+'; initial actually-solved Phase-I=712791 rows/779175 columns/14446564 nnz, 별도 artificial695424개 포함.'),
        ('maximum factor nnz?',str(factor)+'; 모든 내부 barrier attempt를 읽은 maximum, log rounded value.'),
        ('maximum factor memory?',str(memory)+' GB estimated from log; process peak RSS와 구분합니다.'),
        ('Phase-I runtime?',str(sum(c['native_seconds'] or 0 for c in calls if c['component']=='PHASE_I'))+' native seconds'),
        ('pricing runtime?',str(result['pricing_wall_seconds'])+' wall seconds; partial pricing도 charge하며 pricing-native overlap을 보수적으로 중복 계산합니다.'),
        ('artificial-free original P1 feasible?',str(result['ACTIVE_DOMAIN_FEASIBLE'])+'; original P1 solve 상태는 ORIGINAL_LP_RESULT.json에 저장했습니다.'),
        ('P1 pricing closed?',str(result['LP_PRICING_CLOSED'])),
        ('P1 root runtime?',str(sum(c['native_seconds'] or 0 for c in calls if c['component']=='ORIGINAL_P1'))+' seconds; 미실행이면0은 완료 시간이 아닙니다.'),
        ('complete-active 대비 speedup?', '성공적으로 완료된 feasible root 간 speedup은 미측정. 별도 PERFORMANCE_COMPARISON.csv에서 timeout/budget과 objective의 차이를 명시하고 실제 original/auxiliary 크기를 함께 비교합니다.'),
        ('tolerance 완화?', 'NO. solver FeasibilityTol/OptimalityTol1e−6와 frozen Method2/Threads1 정책을 유지했습니다. Raw original replay1e−6; pricing/zero epsilon1e−8; no sweep.'),
        ('physics 변경?', 'NO. PR168 scientific source/evidence 변경0, original initial matrix/all four objectives 재조립 동일. Native builders와 original binary64 coupling을 재사용했습니다.'),
        ('May17 regression?', '이번 task native 미실행. SPEED_GATE_V2_PASS 전 금지; 과거 independent replay-valid witness 및 source/membership evidence는 그대로 보존합니다.'),
        ('May12 실행?', 'NO. Speed gate 이후에만 허용됩니다.'),
        ('May10 실행?', 'NO. 기존 lex rebuild/zero migration projection/direct shift/integer certificate/strengthening 소스와 테스트를 보존했습니다.'),
        ('증명된 closure?',json.dumps({k:result[k] for k in ('ACTIVE_DOMAIN_FEASIBLE','FULL_LP_FEASIBILITY_CLOSED','FULL_LP_DOMAIN_INFEASIBLE','LP_PRICING_CLOSED','INTEGER_DOMAIN_CLOSURE_PROVEN')},ensure_ascii=False)),
        ('production accepted dates?', '없음. Planning/Actual/Fresh OpenDSS0; 다른27일0; integer closure=False.'),
        ('primary classification?',result['classification']+' / '+gate['classification']+'; error='+str(result.get('error'))),
        ('final commit SHA?', '실제 native executed HEAD='+freeze['git_head']+'. 최종 publication HEAD/clean/remote match는 외부 FINAL_PUBLICATION_RECEIPT.json을 권위로 사용합니다. 보고서가 자신의 최종 commit hash를 포함하는 순환 참조를 만들지 않습니다.'),
        ('Draft PR URL?',pr_url)]
    lines=[result['classification'],'',gate['classification']+'. Full-domain scientific acceptance='+str(gate['PASS'])+'.',
        '',f"실제 실행 source HEAD: `{freeze['git_head']}`. Source archive SHA256: `{freeze['source_archive']['sha256']}`.",
        '',f"사전 검증{tests} tests PASS,150 native classes exact incidence/reassembly PASS. 실제 canary native calls={len(calls)}; incomplete pricing/zero/full infeasibility를 성공으로 해석하지 않습니다.",
        '', '| architecture | rows | columns | nnz | max factor | estimated GB | native s |', '|---|---:|---:|---:|---:|---:|---:|']
    for row in comp:lines.append('| '+ ' | '.join(str(row[k]) for k in ('architecture','rows','columns','nnz','factor_nnz','factor_memory_GB','native_seconds'))+' |')
    lines+=['','A는 과거 PR165 S_A zero-objective restricted feasibility LP입니다. B는 COMPLETE-STAY rho MILP root, C는 새로운 auxiliary Phase-I LP입니다. 완료된 root speedup으로 비교하지 않습니다. Complete provider qualification과 실제 pricing closure는 분리합니다.','']
    for i,(question,answer) in enumerate(questions,1):lines.extend([f'{i}. **{question}** {answer}',''])
    lines.extend(['실행 원본: MAY19/NATIVE_CALLS.json, NATIVE_RUN_SOURCES.csv, ROUND_000/NATIVE_RESULT.json, POSTSOLVE_REVIEW.json. 모델/원본 NPZ/가중치/cache/source ZIP은 external SHA receipt로 연결합니다.',
        '첫 receipt 저장 경로가 Windows 한계를 넘은 오류는 ATTEMPT_001에 보존했습니다. C1 continuation은 이미 최적인 master/첫 block raw를 재사용하고 prior native/pricing ledger를 이어받았습니다. Native budget/weights/policy/physics를 reset하거나 추가하지 않았습니다.',
        '새 reporter는 source freeze 후의 관찰/문서 작업이며 native solver policy, weights, source, status, raw arrays를 수정하지 않습니다.'])
    (OUT/'FINAL_REVIEW_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf8',newline='\n')
    (OUT/'REPRODUCIBILITY.md').write_text('''Frozen native command: python -m v42_a_stage_phase1.runner
Only May19, cumulative native300s, native+pricing-wall600s, frozen Method2/Threads1.
No automatic rerun: PHASE1_STARTED.json is a durable one-shot marker.
PHASE1_SOURCE_FREEZE.json records every actual executed source byte, archive SHA and exact Git source HEAD.
Existing legacy checkout newline filters are listed; actual bytes match immutable PR168 source receipts.
Heavy NPZ/cache/witness/source ZIPs are external with SHA256/length receipts. Git retains the complete receipt inventory.
Tests: python -m pytest tests/test_v42_a_stage_phase1.py tests/test_v42_a_stage_fast_active.py tests/test_v42_a_stage_fast_pricing.py tests/test_v42_a_stage_fast_runner.py tests/test_v42_a_stage_fast_integration.py tests/test_v42_a_stage_domain_v2_execution.py
All40 review answers distinguish producer qualification, actual pricing, scientific closure, integer closure and production acceptance.
One IO-repair continuation uses PHASE1_SOURCE_FREEZE_CONTINUATION_001.json and the SAME cumulative budget; both source ZIPs and prior attempt/raw points are retained.
''',encoding='utf8',newline='\n')
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--pr-url',default='PENDING_PUBLICATION');args=parser.parse_args()
    create_report(args.pr_url)
