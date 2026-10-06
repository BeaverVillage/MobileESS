"""Freeze tested authority. This module performs no native solve."""
import gzip,shutil
from .common import *

def run():
    names=['PR134_ACCEPTED_WITNESS_REPLAY.json','START_VALIDATION.json','A_STAGE_FIXTURE_RESULTS.json',
           'A_STAGE_ADVERSARIAL_RESULTS.json','A2SC_INDEPENDENT_VERIFICATION.json','SCIENTIFIC_INTERFACE_CAPTURE_AUDIT.json']
    receipts={n:read_artifact(n) for n in names}
    assert receipts[names[0]]['BASELINE_FEASIBLE_WITNESS_PASS']
    assert all(r['PASS'] for n,r in receipts.items() if n!=names[0])
    comparison=read_artifact('ROOT_COMPARISON.json'); assert comparison['practical_benefit']
    assert not comparison['full_comparison_authorized']
    aliases={
      'ROW_FAMILY_AUDIT.csv':'A_STAGE_ROW_FAMILY_CENSUS.csv','VARIABLE_FAMILY_AUDIT.csv':'A_STAGE_VARIABLE_FAMILY_CENSUS.csv',
      'EXACT_REDUCTION_LEDGER.csv':'A_STAGE_EXHAUSTIVE_REDUCTION_LEDGER.csv','JOB_DOMAIN_AUDIT.csv':'JOB_TIME_RESOURCE_DOMAIN_AUDIT.csv',
      'WAN_REDUCTION_AUDIT.json':'WAN_STATE_AUDIT.json','MIGRATION_TIMESHIFT_PRESTART_AUDIT.csv':'MIGRATION_DOMAIN_AUDIT.csv',
      'RUNTIME_SERVICE_AUDIT.json':'RUNTIME_COMPLETION_AUDIT.json','CC4_AUDIT.json':'CC4_REDUNDANCY_AUDIT.json',
      'GPU_RACK_GANG_AUDIT.csv':'GPU_RACK_IMPOSSIBILITY_AUDIT.csv','GRID_REDUNDANCY_AUDIT.json':'A_STAGE_GRID_REDUNDANCY_AUDIT.json',
      'SUBSTITUTION_LEDGER.csv':'SPARSE_SUBSTITUTION_LEDGER.csv','A1R_CENSUS.json':'A1R_MODEL_CENSUS.json','A2SC_CENSUS.json':'A2SC_MODEL_CENSUS.json',
      'ORIGINAL_TO_SC_MAPPING.json':'A_STAGE_MAPPING_ORIGINAL_TO_SC.json','SC_TO_ORIGINAL_MAPPING.json':'A_STAGE_MAPPING_SC_TO_ORIGINAL.json',
      'FIXTURE_RESULTS.json':'A_STAGE_FIXTURE_RESULTS.json','ADVERSARIAL_RESULTS.json':'A_STAGE_ADVERSARIAL_RESULTS.json',
      'INDEPENDENT_VERIFICATION.json':'A_STAGE_INDEPENDENT_VERIFICATION.json'}
    for dest,src in aliases.items():shutil.copyfile(OUT/src,OUT/dest)
    # Combined temporal audit has every original job in each of its domains.
    import csv
    temporal=[]
    for source in ['MIGRATION_DOMAIN_AUDIT.csv','TIMESHIFT_PRESTART_DOMAIN_AUDIT.csv']:
        with (OUT/source).open(encoding='utf8') as f:
            temporal.extend(dict(source=source,original_record=json.dumps(r)) for r in csv.DictReader(f))
    table('MIGRATION_TIMESHIFT_PRESTART_AUDIT.csv',temporal)
    samples=[]
    for arm in ['A0','A2SC']:
        with (OUT/('SHORT_'+arm+'_RESOURCE_LEDGER.csv')).open(encoding='utf8') as f:
            samples.extend(dict(r,arm=arm) for r in csv.DictReader(f))
    table('RESOURCE_LEDGER.csv',samples)
    for p in sorted(OUT.glob('*.json')):
        if p.stat().st_size<10_000_000:continue
        payload=p.read_bytes();compressed=gzip.compress(payload,compresslevel=6,mtime=0)
        archived=p.with_suffix('.json.gz');archived.write_bytes(compressed)
        write(p.name,dict(lossless_gzip=archived.name,sha256=sha(archived),original_sha256=hashlib.sha256(payload).hexdigest(),original_bytes=len(payload)))
        assert clean(read_artifact(p.name))==clean(json.loads(payload))
    sources=[record(p) for p in sorted((ROOT/'v42_pr134_sc').glob('*.py'))]
    authority=dict(name='V42_A_STAGE_SUPERCOMPACT_AUTHORITY',PASS=True,scientific_base=BASE,selected='A2SC',
        selection='A_STAGE_SUPERCOMPACT_SELECTED',original=read_artifact('A0_CENSUS.json'),compressed=read_artifact('A2SC_CENSUS.json'),
        scientific_problem_changed=False,FULL_LP_equivalence=True,integer_domain_and_four_objectives_preserved=True,
        baseline_identity=record(OUT/'PR134_BASE_IDENTITY.json'),input_sha=read_artifact('PR134_BASE_IDENTITY.json')['bundle']['sha256'],
        mappings=[record(OUT/n) for n in ('ORIGINAL_TO_SC_MAPPING.json','SC_TO_ORIGINAL_MAPPING.json','A2SC_DELETION_PROOFS.npz')],
        tests=[record(OUT/n) for n in names],source_files=sources,
        solver=dict(Threads=1,Method=1,Seed=20260929,MIPGap=.005,Presolve=-1,Cuts=-1,Heuristics=.05,NumericFocus=0,
                    FeasibilityTol=1e-6,OptimalityTol=1e-6,IntFeasTol=1e-5,cumulative_native_seconds=3600),
        selection_scope='One accepted-start May01 P1 diagnostic per arm, cap 300s. Same validated UB and accepted gap target reached 36.1034% faster.',
        root_LP_completed=False,full_four_pass_benchmark_executed=False,one_hour_solvability_claim=False,
        memory_guards=False,artificial_slowdown=False,parameter_sweep=False)
    write('V42_A_STAGE_SUPERCOMPACT_AUTHORITY.json',authority)
    write('SELECTION.json',dict(PASS=True,state=authority['selection'],selected='A2SC',comparison=record(OUT/'ROOT_COMPARISON.json'),
        full_benchmark_authorized=False,practical_metric='same_P1_objective_gap_target_runtime',
        full_fresh_A1_speedup_measured=False,presolved_nnz_reduction=False))
    write('VERIFICATION.json',dict(PASS=True,compression=authority['selection'],baseline_feasible=True,independent_exactness=True,
        original_row_replay=True,full_LP_equivalence=True,raw_accepted_start_unchanged=True,model_source_changed=False,
        root_interruption_interpretation_corrected=True,optimization_calls=2,total_heavy_native_seconds=206.63100004196167,
        native_root_completion=False,benchmark_repeat_calls=0,May_campaign_complete=False))
    (OUT/'FINAL_REVIEW_KO.md').write_text('''# PR134 정확 압축 전수 검증

PR134 `52ef855a59144a7c561df44b81dc2ad265babdbd`의 accepted A1 원시 해를 재구성했다. 1,499개 작업, 96슬롯의 실제 accepted freeze이며 PR150/151 또는 V39/V41 historical operating point를 current witness로 사용하지 않았다.

원본 9,133,426행 / 7,449,002열 / binary 2,223,230 / continuous 5,184,087 / nnz 53,767,578.
A2SC 7,828,869행 / 6,852,953열 / binary 2,220,986 / continuous 4,590,282 / nnz 42,419,133.
행 14.2833%, 열 8.0017%, binary 0.1009%, continuous 11.4544%, nnz 21.1065% 감소.

모든 행·열 family를 감사했고 채택된 모든 삭제 index는 독립 verifier에서 exact rational/byte/equality 증명으로 확인했다. full LP feasible set, integer domain, rho·migration·absolute shift·prestart 네 목적, 서비스/WAN/Runtime/CC4/GPU/rack/grid를 보존한다. 원본 해 왕복 차이는 0이며 모든 원본 행 최대 잔차는 5.97575355e-7로 원래 numerical authority 이내이다. 삭제 tolerance는 사용하지 않았다.

일반 affine·global equality rank·별도 semantic pruning은 증명되지 않은 경우 UNKNOWN으로 보존했다. structural rank 자체를 삭제 증명으로 사용하지 않는다. 이 감사는 모든 row/column을 검사했다는 뜻이며 가능한 모든 새 정리까지 찾아냈다는 주장은 아니다.

각 arm 300초 한도의 동일 accepted-start P1 비교를 1회씩 수행했다. 원본 126.074초, A2SC 80.557초: 같은 valid UB 및 기존 gap 목표에 36.1034% 빨리 도달했다. sampled peak RSS는 18,364,227,584 → 16,940,888,064 bytes(7.7506% 감소). 두 root LP는 interrupted였으며 완료 LP 시간/Work 개선은 측정하지 않았다. presolved nnz는 거의 동일하고 A2SC가 0.0468% 더 크다. native four-pass 비교는 gate 미충족으로 실행하지 않았다. fresh 전체 A1 속도 개선·one-hour solvability는 주장하지 않는다.

분류: **A_STAGE_SUPERCOMPACT_SELECTED**. 선택 근거는 작은 matrix 자체가 아니라 동일 accepted P1 objective/gap 목표의 실제 runtime 개선이다. Phase II는 별도의 입력 호환성 감사와 detached 실행 증거를 기록한다.

PR134 accepted feasible witness reconstructed: TRUE.
PR134 scientific authority unchanged: TRUE.
No historical operating-point pruning: TRUE.
Performance-based exact formulation selected: TRUE (scope: accepted-start P1 diagnostic).
''',encoding='utf8')
    write('SHA256_MANIFEST.json',dict(files=[record(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='SHA256_MANIFEST.json'],source_files=sources))
    print('PHASE_I_AUTHORITY_FROZEN',flush=True)

if __name__=='__main__':run()
