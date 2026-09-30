"""Generate Korean review and truthful flags from completed evidence only."""
import json,csv,hashlib,subprocess,re
from pathlib import Path
H=Path.home();O=Path(__file__).absolute().parent;R=O.parents[1]
def read(n):return json.loads((O/n).read_text(encoding='utf-8-sig'))
def dump(n,x):(O/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def rows(n):return list(csv.DictReader((O/n).open(encoding='utf8')))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
b=read('PR102_GPU_ROOT_BENCHMARK.json');log=(O/'PR102_GPU_ROOT.log').read_text()
stage=re.search(r'PDHG solved model in ([\d.]+) iterations and ([\d.]+) seconds',log)
b.update(GPU_stage_reported_seconds=float(stage[2]) if stage else None,post_PDHG_CPU_refinement_elapsed_approx_seconds=b['solver_runtime']-float(stage[2]) if stage else None,crossover_separate_seconds=None,crossover_timing_scope='No separate crossover timer in log; post-PDHG elapsed estimate includes refinement and overhead. Zero PDHG iterations, then CPU simplex.',prior_Windows_continuous_LP_objective=.6715992598027204,objective_delta_from_prior_Windows_LP=b['objective']-.6715992598027204,objective_delta_from_prior_native_MIP_root=b['objective']-b['prior_CPU_native_MIP_root_objective'],historical_CPU_wall_divided_by_GPU_wall=1557.9/b['wall_seconds'],strict_numerical_bound_validation=False,GPU_for_next_production_A1=False,decision='Computational execution and VRAM fit verified; no acceleration or strict bound certification. Preserve solver numerical warnings and prioritize exact CPU formulation compression.')
dump('PR102_GPU_ROOT_BENCHMARK.json',b)
ieee=read('IEEE8500_PRESERVATION_MANIFEST.json');post=read('POST_CLEANUP_VALIDATION.json');resume=read('UBUNTU_ROOT_COMPRESSION_RESUMPTION.json');deleted=read('WINDOWS_ACTUAL_DELETE_RECEIPT.json');smoke=read('GUROBI_GPU_SMOKE_TEST.json');hardware=read('GPU_HARDWARE_AUDIT.json');tests=read('UBUNTU_V42_VALIDATION.json');structure=read('UBUNTU_PR102_STRUCTURE_COMPARISON.json')
assert ieee['IEEE8500_PRESERVED'] and post['PASS'] and resume['PASS'] and tests['PASS'] and structure['PASS']
planned=rows('WINDOWS_SAFE_DELETE_MANIFEST.csv');inventory=rows('WINDOWS_MOBILEESS_STORAGE_INVENTORY.csv');unknown=[r['path'] for r in inventory if r['classification']=='UNKNOWN_DO_NOT_DELETE']
actual=int(deleted['total_logical_file_bytes_deleted'] or 0);safe=sum(int(r['bytes']) for r in planned)
flags=dict(CURRENT_WIP_CHECKPOINTED=True,CURRENT_WIP_PUSHED=True,UBUNTU_DISTRO='Ubuntu-MobileESS-D',WSL_VERSION=2,CANONICAL_V42_RUNTIME_IS_UBUNTU=True,IEEE8500_PRESERVED=ieee['IEEE8500_PRESERVED'],IEEE8500_UNRESOLVED_FILES=ieee['IEEE8500_UNRESOLVED_FILES'],ACTIVE_WINDOWS_RUNTIME_DEPENDENCIES=read('V42_EXTERNAL_PATH_DEPENDENCY_AUDIT.json')['ACTIVE_WINDOWS_RUNTIME_DEPENDENCIES'],V42_DATA_MIGRATION_HASH_PASS=all(x['hash_pass']=='True' for x in rows('V42_DATA_MIGRATION_MANIFEST.csv')),UBUNTU_V42_TEST_PASS=tests['PASS'],UBUNTU_PR102_FULL_BUILD_PASS=structure['PASS'],UBUNTU_PR102_STRUCTURE_MATCH=structure['PASS'],GUROBI_LINUX_LICENSE_VALID=True,GUROBI_VERSION='13.0.2',WSL_NVIDIA_GPU_VISIBLE=True,GPU_MODEL='NVIDIA GeForce RTX 4060 Laptop GPU',GPU_VRAM_BYTES=8585740288,GUROBI_GPU_BUILD_INSTALLED=True,GUROBI_GPU_VERIFIED=True,GPU_PDHG_LOG_CONFIRMED=True,FULL_MAY_GPU_ROOT_ATTEMPTED=b['attempted'],FULL_MAY_GPU_ROOT_SUPPORTED=b['supported'],FULL_MAY_GPU_ROOT_SUPPORTED_SCOPE='computational execution and memory fit; strict numerical bound certification false',GPU_ROOT_SECONDS=b['wall_seconds'],CPU_BASELINE_ROOT_SECONDS=1557.90,GPU_ROOT_SPEEDUP=None,GPU_PEAK_VRAM_BYTES=b['peak_total_GPU_used_bytes'],GPU_NUMERICAL_WARNINGS=b['warnings'],GPU_NUMERICAL_BOUND_VALIDATED=False,GPU_FOR_NEXT_PRODUCTION_A1=False,WINDOWS_SAFE_DELETE_BYTES=safe,WINDOWS_ACTUAL_DELETED_BYTES=actual,POST_CLEANUP_V42_PASS=post['V42_PASS'],POST_CLEANUP_GPU_PASS=post['GPU_PASS'],POST_CLEANUP_IEEE8500_PASS=post['IEEE8500_PASS'],ROOT_LP_COMPRESSION_RESUMED=resume['ROOT_LP_COMPRESSION_RESUMED'],NO_PRODUCTION_A1=True,NO_M1_A2_M2_FRESH_AC=True,NO_DW_CG=True,SCIENTIFIC_PHYSICS_UNCHANGED=True)
dump('FINAL_FLAGS.json',flags)
answers=[
('중단 시점 WIP 보존 위치','Windows 원본 worktree, Git checkpoint a88879fdb4e6c51dae35656feee90f68ed19ad8f 및 origin/codex/v42-root-lp-compression-a1, Linux /home/jaewon/mobileess_worktrees/root_lp_compression. ignored DATA.pkl·로그·receipt도 hash 검증하여 Linux V42_ROOT_LP_LOCAL에 보존했습니다.'),
('push되지 않은 작업','현재 V42 scientific WIP와 migration evidence는 push 대상으로 모두 커밋했습니다. 기존 다른 연구의 local-only/uncommitted 자료는 정리 대상에서 제외하고 Git 상태·패치·파일 hash와 실제 바이트를 보존했습니다. IEEE8500 Windows 원본은 삭제하지 않았습니다.'),
('WSL2 여부','Ubuntu-MobileESS-D는 WSL2입니다. 저장소 D:\\WSL\\Ubuntu-MobileESS-D는 정리 대상에서 제외했습니다.'),
('canonical 경로','Git: /home/jaewon/codex_mobileess_workspace/MobileESS. PR102: /home/jaewon/mobileess_worktrees/pr102. WIP: /home/jaewon/mobileess_worktrees/root_lp_compression.'),
('filesystem','canonical Git/runtime/input은 Linux filesystem입니다. /mnt/c·/mnt/d는 최초 이전 및 Windows 증거 읽기 용도였고 V42 scientific runtime의 실제 open에는 나타나지 않았습니다.'),
('PR102 SHA','cd7e40762097b6c20303bd2238edf7ffeba87aa4와 동일합니다. frozen source 445개 byte SHA도 전후 일치하고 PR102 Git 상태는 clean입니다.'),
('WIP Ubuntu 복원','codex/v42-root-lp-compression-a1 branch와 checkpoint source를 복원했습니다. 모든 Windows local heads/tags/history도 bundle에서 windows-preserved refs로 보존했습니다.'),
('Windows old path runtime 참조','ACTIVE_WINDOWS_RUNTIME_DEPENDENCIES=0. frozen JSON의 역사적 Windows 문자열은 유지하고 명시적 Linux path table로 byte-identical 파일을 연결했습니다. 미등록 drive 경로는 fail closed입니다.'),
('실제 old dependency','v41r2/v41r3/v40a 및 recovered authority의 job/reference/runtime/power/grid·NPZ·weather·C1 parameter·OpenDSS·3개 transitive Python 파일, 기존 WSL 배열 경로가 실제 의존성이었습니다. 정확한 목록은 V42_DATA_MIGRATION_MANIFEST.csv입니다.'),
('dependency 이전 방식','실제 필요한 65개 파일만 /home/jaewon/mobileess_data/immutable_inputs에 원본 바이트로 복사했습니다. inference source는 Git-vendored 파일의 원 SHA를 확인한 뒤 Linux 전용 launcher/sitecustomize의 명시적 path map을 사용합니다.'),
('immutable SHA256',f"65개, 71,783,023 bytes 모두 source/destination SHA256·크기 일치. 사후 재시작 검사도 통과했습니다."),
('IEEE8500 보존 위치','/home/jaewon/mobileess_research/IEEE8500/objects의 content-addressed 실제 파일과 windows/ 아래 원래 경로를 재현한 symlink. Windows IEEE8500 원본 및 기존 Linux 연구도 모두 유지했습니다.'),
('IEEE8500 local-only',f"있었습니다. 96,732개 파일 중 Git에 추적되지 않은 local-only 88,842개를 포함하여 보존했습니다. 9개 Git 상태의 HEAD·diff·uncommitted·unpushed 정보도 보존했습니다."),
('IEEE8500 hash 검증',f"{ieee['files']:,}개 logical 파일 / {ieee['unique_sha256_objects']:,}개 unique SHA 객체가 모두 크기·SHA 검증을 통과했습니다. logical bytes {ieee['total_logical_bytes']:,}, unresolved {ieee['IEEE8500_UNRESOLVED_FILES']}. 비-IEEE long-path regression fixture의 inventory 오류는 원본 유지 및 별도 오류 receipt에 기록했습니다."),
('IEEE8500 삭제 여부','없습니다. IEEE8500 관련 파일·worktree·cache·원본 디렉터리는 삭제하지 않았습니다.'),
('Ubuntu Python','native Python 3.12.13, v42_cpu / v42_gpu 환경 정상. Windows 과학 package 버전을 유지했습니다. PR102 341 / WIP 393 tests 통과; 기존 calibration log1p 경고 1개는 변경하지 않았습니다.'),
('Linux license','기존 유효 WLS license로 CPU MIP·CLI LP·GPU LP가 정상 실행됐습니다. license를 재발급하거나 덮어쓰지 않았고 내용은 manifest에 저장하지 않았습니다.'),
('Gurobi version','CPU 13.0.2, GPU gurobipy 13.0.2+cu129. 별도 CPU CLI도 13.0.2 공식 archive입니다.'),
('nvidia-smi','WSL에서 정상 동작했습니다. cleanup 후 실제 GPU solver 재검증도 통과했습니다.'),
('실제 GPU','NVIDIA GeForce RTX 4060 Laptop GPU.'),
('VRAM','8188 MiB = 8,585,740,288 bytes. full-May 실행에서 관측한 최대 total GPU 사용은 3,435,134,976 bytes이며 display/다른 앱도 포함합니다.'),
('기존 Gurobi GPU build','기존 power_v61 CPU 환경은 일반 13.0.2로 GPU 요청 시 CPU fallback했습니다. 별도 power_v61_gpu에는 이미 공식 13.0.2+cu129 build가 있었습니다.'),
('GPU 별도 설치','기존 별도 GPU build를 v42_gpu에 재사용했습니다. 739,479,874-byte 공식 wheel의 SHA와 공식 checksum MD5를 확인했습니다. CPU build는 덮어쓰지 않았습니다.'),
('CPU 환경 보존','기존 power_v61과 CPU license를 유지했습니다. v42_cpu와 v42_gpu를 분리했고 GPU 환경에 CPU CLI library 경로를 전역 주입하지 않았습니다.'),
('GPU model log','tiny 및 full-May GPU 로그에 실제 GPU model이 표시됩니다.'),
('Start PDHG log','tiny 및 full-May 로그에 Start PDHG on GPU가 표시됩니다. full-May PDHG 반복은 0회였고 이후 CPU simplex refinement가 621,856회 수행됐습니다.'),
('tiny CPU/GPU objective','둘 다 OPTIMAL, objective 6.178316765223549, feasibility violation 약 1.78e-15, 동일 fingerprint. cleanup 후 다시 일치했습니다.'),
('PR102 full-May 구조','원본 F2 builder로 Ubuntu에서 전체 모델을 새로 build했고 네 가지 구조 수가 모두 일치했습니다. 모델 physics·tolerance를 바꾸지 않았습니다.'),
('binary','2,796,366 — 일치.'),('continuous','5,124,335 — 일치.'),('rows','9,358,534 — 일치.'),('nonzeros','100,455,768 — 일치.'),
('full-May GPU root 실행','실제 original F2 continuous P1 relaxation을 Method=6, PDHGGPU=1, Threads=1, Seed=20260929, TimeLimit=3600으로 실행했습니다. production A1이나 policy/global MIP bound 결과는 아닙니다.'),
('GPU PDHG 실제 사용','GPU device와 Start PDHG 로그를 확인했습니다. 단, PDHG는 0 iterations/60.71초 단계로 종료되어 전체 wall 대부분은 후속 CPU refinement였습니다. GPU가 전체 계산을 가속했다고 주장하지 않습니다.'),
('OOM/fallback','full-May GPU 실행에 OOM·CPU fallback은 없었습니다. 기존 일반 CPU build의 GPU 요청 fallback 로그는 별도 보존했습니다.'),
('GPU wall',f"{b['wall_seconds']:.9f}초, solver Runtime {b['solver_runtime']:.9f}초."),
('CPU 대비 speedup',f"기존 1557.90초보다 느렸습니다. 역사적 wall 비율 CPU/GPU={1557.9/b['wall_seconds']:.6f}, 즉 약 0.804. OS·LP vs MIP-root·algorithm이 달라 controlled speedup은 null이며 가속 근거로 사용하지 않습니다."),
('crossover 시간',f"Crossover=-1 기본값을 유지했습니다. 별도 crossover timer는 로그에 없어 exact 시간은 알 수 없습니다. PDHG 단계 60.71초 이후 CPU refinement/overhead elapsed는 약 {b['solver_runtime']-60.71:.2f}초입니다."),
('numerical warning','large matrix coefficient range / large rhs / large bounds, unscaled dual violation 6.59379e-06, residual 2.75601e-11. 최종 MaxVio 3.0517578125e-05. 경고를 숨기거나 tolerance를 완화하지 않았습니다.'),
('objective/bound 일치',f"GPU LP objective {b['objective']:.16f}; 이전 Windows continuous LP 0.6715992598027204와 차이 {b['objective']-.6715992598027204:.9g}, native MIP-root 0.6716023396111563과 차이 {b['objective']-.6716023396111563:.9g}. solver OPTIMAL 종료와 실행 가능성은 확인했지만 엄격한 numerical bound 인증은 하지 않았습니다. 초기 PDHG objective 0.639049654는 최종 feasible/scientific bound로 채택하지 않았습니다."),
('다음 A1 GPU 근거','불충분합니다. 다음 production A1에 GPU 사용을 preregister하지 않습니다. 먼저 exact CPU root formulation compression과 conditioning, global MIP-start 검증을 완료해야 합니다.'),
('Windows 삭제 디렉터리','\n'.join('- '+x['path'] for x in deleted['deleted']) if deleted['deleted'] else '검증을 모두 충족한 디렉터리가 없어 삭제하지 않았습니다.'),
('삭제 bytes',f"{actual:,} logical file bytes / {int(deleted['files_deleted'] or 0):,} files. 각 삭제 전 파일 Length 합계와 manifest를 대조한 실제 삭제량입니다. sparse/compressed/파일시스템 overhead를 포함한 physical free-space delta와 혼동하지 않습니다."),
('UNKNOWN 유지',f"{len(unknown)}개 UNKNOWN_DO_NOT_DELETE 경로를 유지했습니다. 전체 목록은 WINDOWS_MOBILEESS_STORAGE_INVENTORY.csv에 있습니다. 7.49/8.00GB old venv도 CC4 재현성과 child-venv lineage 참조가 있어 유지했습니다."),
('구버전 Git 복구','삭제된 worktree의 정확한 pushed HEAD, 모든 local refs/tag/history는 Linux canonical Git 및 검증된 all-history bundle에 있습니다. tracked frozen authority/result 파일도 version_objects/version_worktrees에 별도 hash 검증 보존하여 exact head에서 복구 가능합니다.'),
('cleanup 후 V42','Ubuntu-MobileESS-D를 terminate 후 재시작하고 imports·native job1499·power1152·grid96·FrozenQ50·bounded model tests·PR102 source SHA·65개 inputs를 다시 검증했습니다. 모두 통과했습니다.'),
('cleanup 후 GPU','fresh CPU/GPU tiny LP를 재실행했습니다. GPU model 및 Start PDHG, no fallback, OPTIMAL과 objective 일치를 다시 확인했습니다.'),
('cleanup 후 IEEE8500',f"{post['IEEE8500_files']:,}개 Linux logical path 크기와 {post['IEEE8500_unique_SHA256']:,}개 unique object SHA256을 재검증했습니다. 모두 통과했습니다."),
('Ubuntu root-LP 작업 재개','사후 검증 후 Ubuntu에서 117 classes를 독립 재계산하고 35개 bounded F2/A/B/C physical equivalence·6-level scientific optima를 재검증했습니다. 원본 full-F2 matrix census도 새로 측정했습니다: Runtime 1152 rows / 34,923,402 NZ, tie 273,614 rows / 14,503,274 NZ. source 변경 없음. global CC4/Runtime/grid complete MIP start는 여전히 미완료이며 full F2A/B/C LP 또는 production A1은 실행하지 않았습니다.'),
('다음 blocker','환경과 GPU VRAM은 실행을 막지 않습니다. 주 blocker는 Runtime/tie가 지배하는 root formulation·수치 conditioning 및 complete global MIP start입니다. 다음 단계는 exact CPU formulation compression입니다.')]
assert len(answers)==50
text='# Ubuntu V42 migration 최종 검토\n\n환경 이전과 사후 검증을 완료했습니다. GPU full-May LP는 실행됐지만 가속·엄격한 bound 검증 근거는 부족하여 다음 production A1에 채택하지 않습니다.\n\n'
for i,(q,a) in enumerate(answers,1):text+=f'## {i}. {q}\n\n{a}\n\n'
(O/'FINAL_REVIEW_KO.md').write_text(text)
cleanup=f'# Windows cleanup 결과\n\n실제 삭제: {actual:,} logical file bytes, {int(deleted["files_deleted"] or 0):,} files. manifest의 exact path/HEAD/size를 삭제 직전 재검증했습니다.\n\n'
cleanup+='\n'.join('- '+x['path'] for x in deleted['deleted'])+'\n\nIEEE8500, D:\\WSL, license, current WIP, old dependent environments 및 UNKNOWN 경로는 유지했습니다. Git history와 정확한 frozen evidence를 Linux에 보존했습니다. 재시작 후 V42/CPU/GPU/IEEE8500 검증 통과.\n\nUNKNOWN 목록:\n\n'+'\n'.join('- '+p for p in unknown)+'\n'
(O/'WINDOWS_CLEANUP_REPORT_KO.md').write_text(cleanup)
(O/'README.md').write_text('# Canonical Ubuntu V42 runtime\n\nDistro: Ubuntu-MobileESS-D (WSL2). Linux Git `/home/jaewon/codex_mobileess_workspace/MobileESS`; checkpoint branch `codex/v42-root-lp-compression-a1` in `/home/jaewon/mobileess_worktrees/root_lp_compression`; exact PR102 in sibling `pr102`.\n\nRun from Windows:\n\n```powershell\nwsl.exe -d Ubuntu-MobileESS-D -- /home/jaewon/.local/bin/mobileess-v42 -m pytest -q tests\nwsl.exe -d Ubuntu-MobileESS-D -- /home/jaewon/.local/bin/mobileess-v42 --pr102 -m pytest -q tests\n```\n\nLauncher uses native Linux v42_cpu (or `--gpu` v42_gpu), exact immutable inputs and scoped explicit path mapping. Frozen source/JSON remains byte-identical. Gurobi licenses and IEEE8500 originals are preserved. Do not use Windows worktrees for canonical high-I/O V42 science.\n\nFull-May GPU LP execution completed, but 0 PDHG iterations and CPU refinement dominate. It was slower than the historical CPU-root reference and emitted numerical warnings; no production GPU A1 or strict bound certificate is authorized by this evidence.\n\nSee FINAL_REVIEW_KO.md for all 50 answers, FINAL_FLAGS.json for machine-readable status, manifests for exact source/destination/hash/deletion proof, and UBUNTU_ROOT_COMPRESSION_RESUMPTION.json for resumed bounded/class/full-F2 census audits. No production A1/M1/A2/M2/Fresh AC/D-W/CG was run in migration.\n')
required=['README.md','MIGRATION_PREREGISTRATION.json','CURRENT_WIP_CHECKPOINT.json','INTERRUPTED_PROCESS_RECEIPT.json','WINDOWS_MOBILEESS_STORAGE_INVENTORY.csv','WINDOWS_SAFE_DELETE_MANIFEST.csv','WINDOWS_CLEANUP_REPORT_KO.md','IEEE8500_PRESERVATION_MANIFEST.json','IEEE8500_FILE_MANIFEST.csv','V42_EXTERNAL_PATH_DEPENDENCY_AUDIT.json','V42_DATA_MIGRATION_MANIFEST.csv','UBUNTU_GIT_STATE.json','UBUNTU_ENVIRONMENT_MANIFEST.txt','UBUNTU_V42_VALIDATION.json','UBUNTU_PR102_STRUCTURE_COMPARISON.json','GUROBI_LINUX_VALIDATION.json','GPU_HARDWARE_AUDIT.json','GUROBI_GPU_BUILD_AUDIT.json','GUROBI_GPU_SMOKE_TEST.json','GUROBI_GPU_SMOKE_CPU.log','GUROBI_GPU_SMOKE_GPU.log','PR102_GPU_ROOT_BENCHMARK.json','PR102_GPU_ROOT.log','POST_CLEANUP_VALIDATION.json','FINAL_FLAGS.json','FINAL_REVIEW_KO.md']
assert all((O/n).is_file() for n in required)
dump('SOURCE_MANIFEST.json',dict(required_artifacts_count=27,artifacts=[dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(O.iterdir()) if p.is_file() and p.name!='SOURCE_MANIFEST.json'],PR102_exact_head='cd7e40762097b6c20303bd2238edf7ffeba87aa4',scientific_checkpoint='a88879fdb4e6c51dae35656feee90f68ed19ad8f',source_authority='LEGACY_PRESERVATION_AUDIT.json (445 scientific files); exact data and IEEE manifests; no physics change',self_hash_excluded=True))
print(json.dumps(flags,ensure_ascii=False,indent=2))
