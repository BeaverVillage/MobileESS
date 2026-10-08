"""Audit and package stored evidence. This module never calls a solver."""
from v42_physics_redesign.common import *
from .certificate import tests
from .preflight import BASE185, SOURCE
import argparse
import py_compile
import shutil

NAMESPACE='docs/v42_m1_b2_root_validation_20261008'
DEST=ROOT/NAMESPACE
OLD_ROOT=Path('D:/v42_m1_physics_strengthened_20261008/repo')
REQUIRED=[
    'B2_ROOT_EXECUTION_PREREGISTRATION.md','B2_ROOT_SOURCE_IDENTITY.json',
    'B2_ROOT_NATIVE_RESULT.json','B2_ROOT_RAW.npz','B2_ROOT_LB_CERTIFICATE.json',
    'B2_ROOT_BOUND_COMPARISON.csv','B2_ROOT_FRACTIONAL_SOLUTION_AUDIT.json',
    'B2_ROOT_CUT_EFFECT_AUDIT.json','B2_ROOT_NUMERICAL_AUDIT.json',
    'B2_ROOT_RESOURCE_AUDIT.json','B2_ROOT_RUNTIME_WORK.csv',
    'B2_ROOT_FINAL_DECISION.json','SHA256_MANIFEST.json','FINAL_REVIEW_KO.md']

def git(*args,cwd=ROOT):
    return subprocess.check_output(['git',*args],cwd=cwd,text=True).strip()

def check_inherited():
    m=read(SOURCE/'SHA256_MANIFEST.json')
    for parent in (ROOT,OLD_ROOT):
        source=parent/'docs/v42_m1_physics_strengthened_20261008'
        assert sha(source/'SHA256_MANIFEST.json')==sha(SOURCE/'SHA256_MANIFEST.json')
        assert all(sha(source/n)==v['sha256'] for n,v in m['files'].items())
        assert all(sha(parent/n)==v['sha256'] for n,v in m['source_modules'].items())
    assert git('rev-parse','HEAD',cwd=OLD_ROOT)==BASE185
    assert git('status','--porcelain',cwd=OLD_ROOT)==''
    assert git('merge-base',BASE185,'HEAD')==BASE185
    assert git('branch','--show-current')=='codex/v42-m1-b2-root-validation-20261008'
    remote=json.loads(subprocess.check_output(['gh','pr','view','185','--repo',
        'BeaverVillage/MobileESS','--json','headRefOid,headRefName,url'],cwd=ROOT,text=True))
    assert remote['headRefOid']==BASE185
    identity=read(REPORTS/'B2_ROOT_SOURCE_IDENTITY.json')
    assert identity['PASS'] and identity['base_HEAD']==BASE185
    assert all(sha(hc.PARENT/n)==v for n,v in m['scientific_source_hashes'].items())
    return dict(PASS=True,source_HEAD=BASE185,remote_PR185=remote,
        preserved_manifest_files_each_workspace=len(m['files']),
        preserved_source_modules_each_workspace=len(m['source_modules']),
        old_worktree_clean=True,scientific_files_unchanged=True)

def audit():
    prior.forbid_optimize()
    inherited=check_inherited()
    identity=read(REPORTS/'B2_ROOT_SOURCE_IDENTITY.json')
    native=read(REPORTS/'B2_ROOT_NATIVE_RESULT.json')
    decision=read(REPORTS/'B2_ROOT_FINAL_DECISION.json')
    certificate=read(REPORTS/'B2_ROOT_LB_CERTIFICATE.json')
    settings=read(REPORTS/'B2_ACTUAL_SOLVER_SETTINGS.json')
    resource=read(REPORTS/'B2_ROOT_RESOURCE_AUDIT.json')
    assert len(identity['original_20_witnesses'])==20
    assert all(w['PASS'] for w in identity['original_20_witnesses'])
    assert identity['best_UB_full_physical_replay']['PASS']
    assert native['executed'] and native['Status']==2 and native['native_optimize_calls']==1
    assert native['Runtime']<=900 and native['parameters']==SETTINGS
    assert native['raw_saved_before_certificate'] and not native['callback_errors']
    assert settings['PASS'] and settings['parameters']==SETTINGS
    assert resource['admission_PASS'] and all(s['admission_PASS'] for s in resource['snapshots'][-2:])
    assert certificate['PASS'] and certificate['independent']['PASS']
    assert not certificate['producer']['raw_native_multiplier_certificate']['PASS']
    assert certificate['producer']['raw_native_multiplier_certificate']['count']==20566
    accepted=certificate['producer']['accepted']
    assert sha(accepted['exact_path'])==certificate['independent']['exact_payload_SHA256']
    assert sha(accepted['npz_path'])==certificate['independent']['multiplier_payload_SHA256']
    assert decision['exact_certified_LB']==certificate['independent']['certified_LB']
    assert decision['old_global_LB']==decision['new_valid_global_LB']==LB
    assert decision['old_UB']==decision['new_UB']==UB
    assert decision['Delta_LB']==decision['valid_global_LB_improvement']==0
    assert decision['Delta_LB_B2_minus_old']==decision['exact_certified_LB']-LB
    assert decision['classification']=='B2_ROOT_NONMATERIAL'
    assert not decision['Material_Gate_PASS'] and not decision['M1_ACCEPTED']
    assert decision['all_651_Cut_rows_strict_PASS'] and not decision['original_strict_primal_PASS']
    assert decision['canary_calls']==decision['production_calls']==0
    assert not decision['additional_cut_generation'] and not decision['downstream_executed']
    assert decision['next_action_count']==1 and not decision['next_action_executed']
    assert read(WORK/'checkpoints/B2_FINAL_NATIVE_CALL_COUNT.json')['native_calls']==1
    ledger=read(WORK/'checkpoints/B2_NATIVE_CALL_LEDGER.json')
    assert ledger['native_calls']==1 and ledger['completed'] and ledger['Status']==2
    with np.load(WORK/'artifacts/B2_ROOT_RAW.npz') as f:
        assert set(f.files)=={'x','pi','rc','slack'}
        assert f['x'].shape==f['rc'].shape==(306040,)
        assert f['pi'].shape==f['slack'].shape==(583459,)
        assert all(np.isfinite(f[k]).all() for k in f.files)
    test=tests();assert test['PASS'] and test['native_calls']==0
    modules=sorted((ROOT/'v42_b2_root_validation').glob('*.py'))
    for p in modules:py_compile.compile(str(p),doraise=True)
    return dict(PASS=True,new_native_calls=0,completed_experiment_native_calls=1,
        inherited=inherited,analytic_exact_checker_test=test,
        compiled_modules=[p.name for p in modules],raw_array_shapes_PASS=True,
        all_scientific_transport_gates_PASS=True,
        independent_exact_payload_and_bound_support_PASS=True,
        original_strict_fractional_replay_PASS=False,all_651_rows_PASS=True,
        classification=decision['classification'],Material_Gate_PASS=False,
        valid_global_LB_improvement=0,required_files=REQUIRED)

def check_package():
    m=read(DEST/'SHA256_MANIFEST.json')
    assert all((DEST/n).is_file() for n in REQUIRED)
    assert all(sha(DEST/n)==v['sha256'] for n,v in m['files'].items())
    assert all(sha(ROOT/n)==v['sha256'] for n,v in m['source_modules'].items())
    actual={p.relative_to(DEST).as_posix() for p in DEST.rglob('*') if p.is_file()}
    assert actual==set(m['files'])|{'SHA256_MANIFEST.json'}
    return dict(PASS=True,manifest_files=len(m['files']),required_files_present=len(REQUIRED),new_native_calls=0)

def package(result):
    write(REPORTS/'B2_FINAL_EVIDENCE_AUDIT.json',result)
    DEST.mkdir(parents=True,exist_ok=True)
    for directory in ('reports','logs','checkpoints','artifacts'):
        for p in sorted((WORK/directory).glob('*')):
            if not p.is_file() or p.name in ('GIT_COMPLETION.json','PACKAGING_CONTROLLER.log','SAVED_REPLAY_CONTROLLER.log'):continue
            target=DEST/p.name if directory=='reports' or p.name=='B2_ROOT_RAW.npz' else DEST/directory/p.name
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    shutil.copyfile(WORK/'tmp/activate.ps1',DEST/'ACTIVATE_D_WORKSPACE.ps1')
    (DEST/'README_KO.md').write_text('''# B2 ROOT 저장 증거의 재현

PR185 exact HEAD `6d1d64beaf012d32ddf39245890785e3d8f01d4b`를 기준으로 만든 결과다. 실행은 원본 `v42_physics_redesign.root`를 byte-identical로 재사용한 `v42_b2_root_validation.run`이다. 실행 token과 ledger가 이미 소비됐으므로 run을 다시 실행하거나 token을 삭제하지 않는다. 추가 optimize는 승인된 작업 범위에 없다.

`B2_ROOT_RAW.npz`에 X/Pi/RC/Slack 원시값을 보존했다. 부호 오류가 있는 raw Pi는 거부했고 별도 sign-cone multiplier와 exact dyadic payload를 `artifacts/`에 저장했다. 인증 producer는 CSC 열을 계산했고 독립 checker는 CSR 행으로 모든 finite bound 항을 대조했다. `B2_ROOT_LB_CERTIFICATE.json`이 정확한 alpha와 payload SHA를 연결한다.

이 작업공간의 D: 활성화 스크립트를 로드한 후 `python -m v42_b2_root_validation.package`를 실행하면 solve 없이 기존 source·71개 PR185 증거·15개 원본 모듈·native call ledger·독립 인증·분석 및 이 manifest를 검증한다. `python -m v42_b2_root_validation.certificate`는 analytic .25 하한과 잘못된 alpha/intercept/bound/sign 네 가지를 optimize=0으로 검사한다. 새 native solve는 어느 명령에도 포함되지 않는다.

`python -m v42_b2_root_validation.verify_saved`는 Git namespace에 저장된 raw Pi와 별도 multiplier를 대조하고 exact proof를 다시 계산한다. 이 명령은 실행 작업공간의 기존 reports·logs·이전 PR185 checkout 없이도 동작하며, 현재 repository에서 동일 SHA의 원본 C3A 자료가 사용 가능해야 한다. 새 optimize 호출은 0이며 결과 receipt만 D: WORK/reports에 쓴다.

다른 위치에서 전체 작업공간 감사까지 재현할 때는 PR185가 참조하는 원본 C3A·archived LP·20개 witness를 동일 SHA로 D:에 준비하고, 이 namespace의 보고서는 WORK/reports, artifacts는 WORK/artifacts, raw 파일은 WORK/artifacts/B2_ROOT_RAW.npz에 복원한다. 원본 경로와 SHA는 SOURCE_IDENTITY에 있다. `ACTIVATE_D_WORKSPACE.ps1`은 이번 실제 작업공간용이다. 재현 source는 Git에, 기존 source는 이전 namespace에 모두 보존했다. Manifest 경로는 namespace 또는 repository 기준이며 SHA256_MANIFEST 자체는 self-reference를 피하기 위해 제외했다.

사전등록의 Delta_LB는 최종 global LB 개선량이다. 요청의 B2 certificate−LB_old는 별도 Delta_LB_B2_minus_old에 보존했다. Native 목적값·독립 인증값·기존 하한을 보존한 최종 global LB를 구분한다. Strict 원본 행 replay FAIL과 raw dual sign FAIL을 숨기지 않는다. 새 fractional point는 정수 UB가 아니다. 후속 실험은 실행하지 않았다.

실행 직전 inherited resource gate는 통과했다. 실행 중 외부 May12 pytest의 단일 관측을 동봉했으므로 전체 실행의 지속적 host isolation 또는 인과적 speedup을 주장하지 않는다. 다른 프로세스·priority·작업 증거는 변경하지 않았다. 최종 Git HEAD·PR URL·remote equality·clean tree 영수증은 commit self-reference를 피하여 작업공간 외부 reports/GIT_COMPLETION.json에 저장한다.
''',encoding='utf-8')
    previous=read(SOURCE/'SHA256_MANIFEST.json')
    files={p.relative_to(DEST).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size)
        for p in sorted(DEST.rglob('*')) if p.is_file() and p.name!='SHA256_MANIFEST.json'}
    modules={p.relative_to(ROOT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size)
        for p in sorted((ROOT/'v42_b2_root_validation').glob('*.py'))}
    write(DEST/'SHA256_MANIFEST.json',dict(files=files,source_modules=modules,
        inherited_source_manifest=str(SOURCE/'SHA256_MANIFEST.json'),
        inherited_source_manifest_SHA256=sha(SOURCE/'SHA256_MANIFEST.json'),
        inherited_source_modules={n.replace('\\','/'):v for n,v in previous['source_modules'].items()},
        scientific_source_hashes=previous['scientific_source_hashes'],
        manifest_self_excluded=True,new_native_calls_in_packaging=0,
        completed_experiment_native_calls=1,source_HEAD=BASE185))
    return check_package()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--package',action='store_true')
    args=parser.parse_args();result=audit()
    published=package(result) if args.package else check_package()
    print('B2_STORED_EVIDENCE_AUDIT_PASS',json.dumps(published),flush=True)

if __name__=='__main__':main()
