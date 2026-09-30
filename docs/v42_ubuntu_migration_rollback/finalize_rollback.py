"""Compose measured rollback evidence; refuses to claim completion without health gates."""
import json,hashlib,csv,zipfile,io,subprocess
from pathlib import Path
from datetime import datetime,timezone
O=Path(__file__).absolute().parent;R=O.parents[1]
def read(n):return json.loads((O/n).read_text(encoding='utf-8-sig'))
def dump(n,x):(O/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def git(*a):return subprocess.check_output(['git','-C',str(R),*a],text=True,encoding='utf8').strip()
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def number(n):return f'{n:,} 바이트 ({n/1e9:.3f} GB; {n/2**30:.3f} GiB)'
for n in ['WINDOWS_V42_VALIDATION.json','WINDOWS_PR102_STRUCTURE_COMPARISON.json','IEEE8500_WINDOWS_AUTHORITY_RECEIPT.json','POST_ROLLBACK_WINDOWS_VALIDATION.json','POST_ROLLBACK_UBUNTU_HEALTHCHECK.json','ROOT_LP_WIP_WINDOWS_RESTORE.json','WSL_VHD_COMPACTION_RECEIPT.json']:
    assert read(n)['PASS'],n
assert not git('diff','a88879fd','--','v42_root','tests')
start=read('HOST_INITIAL_SNAPSHOT.json');before=read('HOST_SPACE_before_deletion.json');deleted=read('HOST_SPACE_after_deletion.json');precompact=read('HOST_SPACE_before_compaction.json');compact=read('HOST_SPACE_after_compaction.json');end=read('HOST_SPACE_final.json')
linux=read('WSL_FREE_SPACE_BEFORE_AFTER.json');removal=read('UBUNTU_MIGRATION_DELETION_RECEIPT.json');ieee=read('UBUNTU_IEEE8500_DELETION_RECEIPT.json');bundle=read('WINDOWS_MIGRATION_BUNDLE_DELETION_RECEIPT.json');windows=read('POST_ROLLBACK_WINDOWS_VALIDATION.json');receipt=read('WSL_VHD_COMPACTION_RECEIPT.json')
assert receipt['actual_final_percentage']==100
C=end['C_free_bytes']-start['C'];D=end['D_free_bytes']-start['D'];vhd=before['VHDX_physical_allocated_bytes']-compact['VHDX_physical_allocated_bytes'];host=C+D
assert vhd>0 and D>0,'Do not claim reclaimed host space without positive measured VHD/D recovery'
space=dict(baseline_timestamp=start['date'],final_timestamp=end['timestamp'],C_free_bytes_before=start['C'],C_free_bytes_after=end['C_free_bytes'],C_net_free_bytes_change=C,D_free_bytes_before=start['D'],D_free_bytes_after=end['D_free_bytes'],D_net_free_bytes_change=D,HOST_DISK_BYTES_RECOVERED=host,definition='Signed net C:+D: free-space change; background host activity and rollback evidence also affect the result. VHD allocated-byte reduction is recorded independently.',VHDX_physical_bytes_before=before['VHDX_physical_allocated_bytes'],VHDX_physical_bytes_after_deletion=deleted['VHDX_physical_allocated_bytes'],VHDX_physical_bytes_before_compaction=precompact['VHDX_physical_allocated_bytes'],VHDX_physical_bytes_after_compaction=compact['VHDX_physical_allocated_bytes'],VHDX_physical_bytes_after_restart=end['VHDX_physical_allocated_bytes'],VHDX_BYTES_RECOVERED=vhd,Windows_migration_bundle_bytes_deleted=bundle['logical_bytes_deleted'],phases=[before,deleted,precompact,compact,end],interpretation='Compaction may reclaim previously unused blocks as well as migration deletions; total reclaimed VHD bytes are not attributed solely to this migration.')
dump('HOST_DISK_SPACE_BEFORE_AFTER.json',space)
receipt.update(physical_allocated_bytes_before=before['VHDX_physical_allocated_bytes'],physical_allocated_bytes_after_compaction=compact['VHDX_physical_allocated_bytes'],physical_allocated_bytes_recovered=vhd,physical_measurement='GetCompressedFileSizeW',actual_percentage_visible=True,post_restart_health_PASS=True)
dump('WSL_VHD_COMPACTION_RECEIPT.json',receipt)
flags=dict(MIGRATION_CANCELLED_BY_USER=True,CANONICAL_V42_RUNTIME='WINDOWS',MIGRATION_BACKGROUND_JOBS_STOPPED=True,SCIENTIFIC_WIP_PUSHED=True,UNPUSHED_SCIENTIFIC_WORK=0,WINDOWS_IEEE8500_ORIGINAL_PRESERVED=True,WINDOWS_IEEE8500_FILES_DELETED=0,UBUNTU_MIGRATION_IEEE8500_COPY_REMOVED=True,UBUNTU_MIGRATION_V42_COPY_REMOVED=True,UBUNTU_MIGRATION_DATA_COPY_REMOVED=True,PREEXISTING_UBUNTU_PRESERVED=True,UBUNTU_DISTRO_UNREGISTERED=False,D_WSL_DELETED=False,WINDOWS_V42_RUNTIME_PASS=True,WINDOWS_PR102_STRUCTURE_MATCH=True,GPU_BENCHMARK_PRESERVED=True,GPU_SELECTED_FOR_PRODUCTION=False,LOGICAL_MIGRATION_BYTES_DELETED=removal['logical_regular_file_bytes_deleted'],WINDOWS_MIGRATION_TRANSPORT_BYTES_DELETED=bundle['logical_bytes_deleted'],VHDX_BYTES_BEFORE=before['VHDX_physical_allocated_bytes'],VHDX_BYTES_AFTER=compact['VHDX_physical_allocated_bytes'],VHDX_BYTES_RECOVERED=vhd,C_FREE_BYTES_BEFORE=start['C'],C_FREE_BYTES_AFTER=end['C_free_bytes'],D_FREE_BYTES_BEFORE=start['D'],D_FREE_BYTES_AFTER=end['D_free_bytes'],HOST_DISK_BYTES_RECOVERED=host,ROOT_LP_COMPRESSION_WIP_RESTORED_ON_WINDOWS=True,VHD_COMPACTION_ACTUAL_FINAL_PERCENT=100,PRODUCTION_A1_RUN=False,SCIENTIFIC_SOURCE_CHANGED=False,MIGRATION_SPECIFIC_LINUX_PATH_DEPENDENCIES=0,PREEXISTING_LINUX_UNC_AUTHORITIES_RETAINED=5)
dump('FINAL_FLAGS.json',flags)
free_before=linux['before_statvfs'];free_after=linux['after_statvfs'];used_before=(free_before['total_blocks']-free_before['free_blocks'])*free_before['block_size'];used_after=(free_after['total_blocks']-free_after['free_blocks'])*free_after['block_size']
linux.update(before_used_bytes=used_before,after_used_bytes=used_after,available_bytes_before=free_before['available_blocks']*free_before['block_size'],available_bytes_after=free_after['available_blocks']*free_after['block_size'],used_bytes_reduction=used_before-used_after,trim_receipt='FSTRIM_RECEIPT.json',trim_reported_bytes_are_not_host_recovered_bytes=True)
dump('WSL_FREE_SPACE_BEFORE_AFTER.json',linux)
z=zipfile.ZipFile(O/'ABORTED_MIGRATION_EVIDENCE.zip');originals=list(csv.DictReader(io.TextIOWrapper(z.open('Ubuntu_evidence/IEEE8500_FILE_MANIFEST.csv'),encoding='utf8')))
from collections import Counter
locations=Counter('\\'.join(r['original'].split('\\')[:4]) for r in originals if not r['original'].startswith('/'))
dump('WINDOWS_IEEE8500_AUTHORITY_LOCATIONS.json',dict(Windows_original_file_count=96847,locations=[dict(path=p,manifest_files=n) for p,n in locations.most_common()],note='Actual original manifest paths remain; C: compatibility aliases point to D: physical storage. Eleven Linux clone source references are Git-backed and verified by Windows Git blob hashes.'))
paths='\n'.join('- `'+r['path']+'`: '+number(r['logical_regular_file_bytes_deleted']) for r in removal['deleted'])
events=', '.join(str(e['percentage'])+'%' for e in receipt['percentage_events'])
report=f'''# Ubuntu migration 취소 및 Windows 복원 최종 검토

작성 시각: {datetime.now(timezone.utc).isoformat()}. Canonical V42 runtime은 **WINDOWS**이며 rollback 검증을 완료했다. 새 production solve는 실행하지 않았다.

Ubuntu migration 복사본 논리 크기 {number(removal['logical_regular_file_bytes_deleted'])}를 제거했다. VHD 실제 할당 크기는 {number(before['VHDX_physical_allocated_bytes'])}에서 {number(compact['VHDX_physical_allocated_bytes'])}로 줄었다. 직접 측정한 VHD 감소량은 **{number(vhd)}**다. C:+D: 최종 순 여유 공간 증가량은 **{number(host)}**다.

DiskPart가 실제 출력한 진행률을 별도 Windows 창에 표시했다. 관측한 변경값: {events}. 마지막 실제 값은 100%, 프로세스 종료 코드 0이다. 추정 시간으로 퍼센트를 만들지 않았다. 상세 로그와 진행률 이벤트는 `DISKPART_COMPACTION.log`, `WSL_VHD_COMPACTION_RECEIPT.json`에 있다.

1. **Ubuntu migration을 왜 중단했는가?** 사용자가 취소하고 Windows를 canonical runtime으로 지정했다. GPU full-May LP는 기존 CPU root 기록보다 느렸고 수치 경고가 있었다.
2. **GPU benchmark 결과는 무엇이었는가?** 전체 wall 1938.768148653초, OPTIMAL, objective 0.6716151913951279였다. GPU 모델/PDHG 시작 로그가 있지만 PDHG iteration은 0, CPU simplex 621856회였다. 기존 CPU root 1557.90초와 통제된 동일 조건 비교는 아니므로 GPU 속도 향상을 주장하지 않는다. MaxVio 3.0517578125e-05와 수치 경고도 보존했다.
3. **GPU가 production A1에 채택됐는가?** 아니오. GPU_SELECTED_FOR_PRODUCTION=false. 새 A1/M1/A2/M2/Fresh AC 실행 없음.
4. **현재 canonical V42 runtime은 어디인가?** Windows `{R}`. Python `{windows['python']}`, Windows Gurobi 13.0.2.
5. **Windows WIP는 어떤 commit/branch로 복원됐는가?** 과학 checkpoint `a88879fdb4e6c51dae35656feee90f68ed19ad8f`와 migration evidence `bbbf0acb7e92f523550c498197d2c7af917112bf`를 보존해 `codex/v42-root-lp-compression-a1`에서 복원했다. 삭제 전에 rollback 보존 commit `c3bdf54c`까지 push했다. 최종 receipts도 같은 브랜치에 push한다. 건강검사 당시 HEAD는 `{windows['HEAD_at_healthcheck']}`이며 과학 source/tests diff는 없다.
6. **unpushed scientific work가 남아 있는가?** 현재 root-LP WIP에 0. Linux Git 상태/로그/remote를 삭제 전에 기록했고 과학 변경 없음과 원격 checkpoint를 확인했다. 다른 기존 연구 브랜치를 일괄 push했다는 뜻은 아니다.
7. **IEEE8500 Windows 원본을 삭제했는가?** 아니오. 삭제 파일 0. 전후 Windows 원본 96,847개 존재/크기를 검증했다. 11개 Linux clone 문서/source reference는 기존 Windows Git blob SHA256로도 확인했다.
8. **IEEE8500 Windows 원본은 현재 어디에 있는가?** `D:\\ChatGPT\\Mobile ESS 2`의 기존 IEEE8500 연구 디렉터리들, `D:\\ChatGPT\\IEEE8500_exports`, 기존 `D:\\MobileESS_cleanup_plan_20260910` 자료 등 원래 경로 그대로다. 예: `IEEE8500_PAPER_SCALE_ONLY_20260920`, `IEEE8500_B3_production_20260912`, `IEEE8500_v41r4_production_20260911_r2`. 전체 위치/개수는 `WINDOWS_IEEE8500_AUTHORITY_LOCATIONS.json`, 파일별 원래 경로/hash는 보존 ZIP의 IEEE8500_FILE_MANIFEST.csv에 있다.
9. **Ubuntu에 복사되던 IEEE8500은 몇 파일까지 진행됐었는가?** 취소 후 최초 process inspection 전에 마지막 worker가 이미 완료했다. 원 연구 scan 96,729개(생성 scanner 3개 제외)와 추가 Windows reference 118개, Git-backed Linux reference 11개를 포함해 manifest 96,858개였다. 추가 복사는 실행하지 않았다. 전체 migration 상태는 ABORTED_BY_USER_ROLLBACK이다.
10. **그 partial Ubuntu copy를 삭제했는가?** 예. 실제 완료된 copy/object/symlink store까지 migration 전용 IEEE8500 root 전체를 삭제했다. 취소 시 worker가 이미 종료돼 강제 종료 PID 목록은 비어 있다. unrelated job 종료 없음.
11. **Ubuntu IEEE8500 copy의 logical 삭제 bytes는?** {number(ieee['logical_regular_file_bytes_deleted'])}. 정규 파일 크기 합이며 symlink 대상의 중복 크기를 더하지 않았다.
12. **Ubuntu V42 migration copy도 삭제했는가?** 예. 신규 clone/worktrees/data/frozen-copy/evidence 및 별도 migration env와 launcher를 제거했다. 모든 알려진 target 부재를 재확인했다.
13. **어떤 Ubuntu V42 worktree를 삭제했는가?** `/home/jaewon/mobileess_worktrees/pr102`, `root_lp_compression`, `V42_ROOT_LP_LOCAL`, `PR102_GPU_ROOT_LOCAL` 및 신규 clone `/home/jaewon/codex_mobileess_workspace/MobileESS`. 기존 Windows worktree는 보존했다.
14. **어떤 Ubuntu data directory를 삭제했는가?** `/home/jaewon/mobileess_data`, `/home/jaewon/mobileess_research/IEEE8500`, `/home/jaewon/mobileess_research/V42_PR102_evidence`. 아래 전체 삭제 manifest에 정확한 크기가 있다.
15. **pre-existing Ubuntu 자료를 잘못 삭제한 것은 없는가?** 알려진 migration-created 경로만 허용했다. 기존 keep roots와 Python/Gurobi core/license/기존 입력 대표 SHA256가 전후 동일하다. 수백 GB 기존 연구 전체를 재해시했다는 주장은 하지 않는다. UNKNOWN은 삭제하지 않았다.
16. **Ubuntu-MobileESS-D 배포판은 그대로 존재하는가?** 예. unregister 없음, 압축 후 정상 재시작/healthcheck PASS.
17. **D:\\WSL은 그대로 존재하는가?** 예. D:\\WSL, 배포판, ext4.vhdx 모두 보존했다.
18. **기존 Linux Gurobi는 보존됐는가?** 예. 기존 `~/miniconda3/envs/power_v61` CPU 13.0.2, `power_v61_gpu` 13.0.2+cu129, 기존 license를 보존했다.
19. **Windows V42 import는 정상인가?** 예. Native 1,499 jobs, Runtime 1,152 시점, native grid 96 시점, FrozenQ50 전후 PASS.
20. **Windows Gurobi는 정상인가?** 예. 실제 라이선스로 작은 binary MIP optimal objective=1 검증 PASS. 새 연구 production solve는 없음.
21. **PR102 tests는 Windows에서 통과했는가?** 예. PR102 범위 341 passed, 기존 calibration RuntimeWarning 1개.
22. **WIP tests는 Windows에서 통과했는가?** 예. 393 passed, 동일 경고 1개. 압축 후 전체 suite도 재검증했다.
23. **PR102 full-May model 구조는 동일한가?** 예. 원 F2 full model을 새로 빌드해 실제 matrix counts가 모두 일치했다. optimizer는 호출하지 않았다. frozen source 445개와 원 입력 65개도 검증했다.
24. **binary count는?** 2,796,366.
25. **continuous count는?** 5,124,335.
26. **rows는?** 9,358,534.
27. **nonzeros는?** 100,455,768.
28. **Ubuntu path dependency가 Windows production에 남았는가?** migration 전용 `/home/.../mobileess_data`, `mobileess_research`, `mobileess_worktrees` 의존은 0. 원래 Windows 설정의 **기존 Linux UNC authority 5개는 유지**했다. 이를 migration dependency 0과 혼동하지 않는다. 기존 `mobile_ess_work`의 bus_ids/load_cluster/pv_capacity와 Jemena 두 lookup이다.
29. **migration-only path 설정을 되돌렸는가?** 예. Windows MOBILEESS_PATH_MAP unset, migration sitecustomize inactive. 과학 source/입력 내용 변경 0. 기존 C→D 호환 alias는 원래대로 유지했다. 신규 Linux wrappers/env는 삭제했고 migration docs는 취소 상태의 역사 자료로 표시했다.
30. **Linux 안에서 삭제 전 사용량은?** {number(used_before)}. df/statvfs 둘 다 기록했다.
31. **Linux 안에서 삭제 후 사용량은?** {number(used_after)}. 사용량 감소 {number(used_before-used_after)}. filesystem block/metadata 감소는 논리 파일 크기와 다를 수 있다.
32. **ext4.vhdx 물리 크기는 삭제 전 얼마였는가?** {number(before['VHDX_physical_allocated_bytes'])}. GetCompressedFileSizeW 실제 할당 바이트와 파일 길이를 별도로 기록했고 이 측정에서 같았다. df의 1TB 가상 용량과 구분했다.
33. **삭제 직후 얼마였는가?** {number(deleted['VHDX_physical_allocated_bytes'])}. sync/trim 후, 압축 실행 직전에는 {number(precompact['VHDX_physical_allocated_bytes'])}. 각 timestamp를 기록했다.
34. **VHD compaction을 수행했는가?** 예. 실제 100%/exit 0/PASS. 별도 진행 창의 숫자는 DiskPart stdout에서 읽었으며 시간 기반 가짜 퍼센트는 없다.
35. **어떤 안전한 방법을 사용했는가?** Optimize-VHD가 없어 지원되는 관리자 DiskPart `select vdisk`→`detail vdisk`→`compact vdisk`를 사용했다. HKCU WSL registry와 exact path 일치, wsl --shutdown, running list 비어 있음, 파일 exclusive open을 검증한 detached VHD만 처리했다. [Microsoft 공식 compact vdisk 조건](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/compact-vdisk)에 따른 방법이다. unregister/export-import/resize/format/clean 없음.
36. **compaction 후 VHDX 크기는?** {number(compact['VHDX_physical_allocated_bytes'])}. 재시작 후 최종 할당 크기는 {number(end['VHDX_physical_allocated_bytes'])}이다. 재시작 쓰기로 조금 바뀔 수 있다.
37. **실제 C: 회수 용량은?** C: 순 여유 공간 변화 {number(C)}. 이전 {start['C']:,} → 이후 {end['C_free_bytes']:,}. 부호 포함 실제 관측치이며 C: 연구 cleanup을 수행하지 않았다.
38. **실제 D: 회수 용량은?** D: 순 여유 공간 증가 {number(D)}. 이전 {start['D']:,} → 이후 {end['D_free_bytes']:,}.
39. **총 host disk 회수량은?** C:+D: 순 여유 공간 증가 {number(host)}. 별도로 VHD 할당 감소 {number(vhd)}, 신규 Windows transport bundle 삭제 {number(bundle['logical_bytes_deleted'])}를 기록했다.
40. **예상한 수십 GB가 실제로 회수됐는가?** 예. 위 실제 VHD 할당 감소와 D: free bytes 증가를 확인했다. migration 정규 파일 삭제는 {number(removal['logical_regular_file_bytes_deleted'])}이다.
41. **회수되지 않았다면 이유는?** 전체 목표 공간 회수는 완료했다. 논리 삭제량, trim 보고량, VHD 감소량, host free 증가량은 같지 않다. 압축은 migration 이전의 unused block도 회수하며 기존 데이터/metadata는 남는다. host 변화에는 rollback Git/evidence와 백그라운드 쓰기도 포함된다. fstrim 보고 578,684,366,848바이트를 host 회수량이라고 주장하지 않는다.
42. **Ubuntu는 compaction 후 정상 부팅되는가?** 예. shell/home/git 및 CPU solver healthcheck PASS.
43. **기존 Ubuntu 파일은 정상인가?** 기존 keep root 존재와 대표 hash 모두 동일. 연구 전체의 모든 파일을 전후 재해시한 것은 아니다.
44. **기존 Linux Gurobi는 정상인가?** CPU 13.0.2 실제 license tiny MIP optimal PASS, GPU import 13.0.2+cu129 PASS.
45. **GPU 환경은 보존했는가/삭제했는가?** 기존 power_v61_gpu 보존. migration 신규 `~/mobileess_envs/v42_gpu`, `v42_cpu` 및 신규 CPU CLI만 삭제. nvidia-smi 결과 보존. 추가 GPU 최적화 없음.
46. **migration evidence는 어디에 남겼는가?** 이 `docs/v42_ubuntu_migration_rollback/`와 기존 취소 표시 `docs/v42_ubuntu_gpu_migration/`, 원격 동일 브랜치. 10,740,027바이트 ZIP은 모든 작은 원 migration metadata/manifest/tool/log를 SHA256과 함께 보존한다. GPU raw log/result도 별도 파일이다.
47. **대용량 migration blob은 모두 제거됐는가?** 알려진 Ubuntu 대상 13개와 Windows transport bundle을 제거했고 absence를 확인했다. 보존 자료는 작은 logs/manifests/receipts이다. 원 Windows 연구와 기존 Linux 자료는 duplicate migration blob으로 분류하지 않았다.
48. **Windows old research는 이번 rollback에서 건드렸는가?** 삭제/변경하지 않았다. 기존 IEEE8500/V35/V40/V41/venvs/worktrees 보존. Windows에서 제거한 큰 파일은 이번 migration을 위해 신규 생성한 transport bundle 하나뿐이며 {bundle['bundle_heads_verified_in_original_Windows_Git']}개 bundle refs의 commit이 기존 Git에 남음을 확인했다.
49. **root-LP compression WIP를 Windows에서 복원했는가?** 예. 117 equivalence classes(단일 20, 비단일 97, 포함 jobs 1,479, 최대 75), bounded F2/A/B/C 35 cases PASS. Runtime 1,152 rows/34,923,402 nonzeros, tie 273,614 rows/14,503,274 nonzeros를 재측정했다. 1,499-job physical MIP-start 사전 검증은 PASS지만 **global Runtime/CC4/grid를 포함한 완전 MIP-start는 아직 완료되지 않았다**.
50. **다음 scientific 작업은 무엇인가?** Windows CPU에서 exact root-LP reformulation 압축과 global MIP-start 완성을 검토하는 단계다. rollback 보고까지 완료하고 정지했으며 이번 작업에서 새 scientific optimization을 시작하지 않았다.

## 정확한 삭제 경로 및 논리 크기

{paths}

## 측정 해석과 보존 범위

원본 보존 authority는 Windows 원 경로와 원 Git이다. `UBUNTU_MIGRATION_CREATED_INVENTORY.csv`와 `UBUNTU_MIGRATION_DELETE_MANIFEST.csv`는 migration-created만 승인한다. logical bytes는 regular-file 크기 합계이고 deduplicated symlink store의 원 참조 81.61GB와 구분된다. VHD 직접 감소와 host 순 여유 공간 증가를 혼용하지 않는다.

모든 최종 flags는 `FINAL_FLAGS.json`, 실제 측정 phase는 `HOST_DISK_SPACE_BEFORE_AFTER.json`, Linux free space는 `WSL_FREE_SPACE_BEFORE_AFTER.json`, 검증은 두 POST_ROLLBACK 파일에 있다. 과학 source/tests는 a88879fd와 동일하다. Source manifest는 자체 파일을 제외해 생성하고 최종 Git commit hash는 Git branch/remote에서 확인한다.
'''
(O/'FINAL_REVIEW_KO.md').write_text(report,encoding='utf8')
(O/'README.md').write_text(f'''# Cancelled Ubuntu migration rollback

Canonical V42 runtime: **WINDOWS** (`{R}`). Root-LP scientific checkpoint a88879fd is preserved; no scientific source change or production solve occurred.

Rollback completed with original Windows IEEE8500 and pre-existing Ubuntu CPU/GPU Gurobi retained. Migration-created Linux copies removed: {removal['logical_regular_file_bytes_deleted']:,} logical regular-file bytes. Actual VHD allocation reduction: {vhd:,} bytes. Measured D: net free-space increase: {D:,} bytes; C:+D: net increase: {host:,} bytes. These are distinct measurements; VHD compaction can reclaim earlier unused blocks too.

Compaction used the exact registry-verified detached VHD and real DiskPart percentages in a visible Windows window. Observed progress changes: {events}; final 100%, exit 0. The script remains `Compact-WSL-WithProgress.ps1`; it requires an already shut-down WSL and administrator rights.

See [Korean 50-question review](FINAL_REVIEW_KO.md), [final flags](FINAL_FLAGS.json), [compaction receipt](WSL_VHD_COMPACTION_RECEIPT.json), [host measurements](HOST_DISK_SPACE_BEFORE_AFTER.json), and both POST_ROLLBACK health receipts. Windows PR102 tests 341 passed; WIP/post-restart tests 393 passed; full F2 structural counts and 35 bounded cases match. Original Windows configuration still reads five **pre-existing** Linux UNC authorities; migration-specific Linux dependencies are zero.

The archived small manifests/logs remain as evidence; the large migrated research blobs were removed. Stop here; global MIP-start completion and further CPU root-LP compression are subsequent scientific work.
''',encoding='utf8')
pres=read('SCIENTIFIC_WIP_PRESERVATION.json');pres.update(rollback_evidence_pushed_before_deletion='c3bdf54c',scientific_source_unchanged_after_rollback=True,Windows_branch_after_rollback=git('branch','--show-current'),Windows_HEAD_before_final_receipt_commit=git('rev-parse','HEAD'));dump('SCIENTIFIC_WIP_PRESERVATION.json',pres)
required=['README.md','ROLLBACK_PREREGISTRATION.json','MIGRATION_PROCESS_TERMINATION.json','SCIENTIFIC_WIP_PRESERVATION.json','WINDOWS_CANONICAL_RUNTIME_AUDIT.json','WINDOWS_V42_VALIDATION.json','WINDOWS_PR102_STRUCTURE_COMPARISON.json','IEEE8500_WINDOWS_AUTHORITY_RECEIPT.json','UBUNTU_IEEE8500_DELETION_RECEIPT.json','UBUNTU_MIGRATION_CREATED_INVENTORY.csv','UBUNTU_MIGRATION_DELETE_MANIFEST.csv','UBUNTU_MIGRATION_DELETION_RECEIPT.json','MIGRATION_PATH_REVERT_AUDIT.json','GPU_BENCHMARK_PRESERVATION.json','WSL_FREE_SPACE_BEFORE_AFTER.json','WSL_VHD_COMPACTION_RECEIPT.json','HOST_DISK_SPACE_BEFORE_AFTER.json','POST_ROLLBACK_WINDOWS_VALIDATION.json','POST_ROLLBACK_UBUNTU_HEALTHCHECK.json','ROOT_LP_WIP_WINDOWS_RESTORE.json','FINAL_FLAGS.json','FINAL_REVIEW_KO.md','SOURCE_MANIFEST.json']
assert all((O/n).is_file() for n in required if n!='SOURCE_MANIFEST.json')
manifest=dict(required_artifacts=required,source_and_artifact_hashes=[dict(path=str(p.relative_to(R)).replace('\\','/'),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(O.rglob('*')) if p.is_file() and p.name!='SOURCE_MANIFEST.json' and '__pycache__' not in p.parts],scientific_checkpoint='a88879fdb4e6c51dae35656feee90f68ed19ad8f',scientific_source_diff='',frozen_sources_reference='docs/v42_root_lp_compression_a1/LEGACY_PRESERVATION_AUDIT.json',source_manifest_excludes_itself=True)
dump('SOURCE_MANIFEST.json',manifest)
print('ROLLBACK_FINAL_REPORT_COMPLETE',flags,flush=True)
