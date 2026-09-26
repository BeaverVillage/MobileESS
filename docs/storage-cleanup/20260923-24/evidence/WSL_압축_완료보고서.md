# WSL 정리·가상 디스크 압축 완료 — 2026-09-23

- 대상: `D:\WSL\Ubuntu-MobileESS-D\ext4.vhdx`
- 추가 정리: 243개 물리 파일 사본, 2.12 GiB. 동일 SHA256 배포 사본 1개와 pip 다운로드 캐시만 제거. 배포 압축본의 기존 경로는 원본에 대한 하드 링크로 유지해 추가 데이터 공간 없이 계속 읽을 수 있게 함.
- VHDX 파일: 550.32 → 548.15 GiB.
- VHDX 감소: 2.17 GiB.
- D 여유 공간: 이번 압축 전 107.68 → 압축·재시작 후 109.85 GiB.
- 전체 정리 시작 기준: 81.66 → 109.85 GiB, 실제 여유 공간 증가 약 28.18 GiB.

WSL 내부 삭제량은 VHDX 감소량에 이미 포함되므로 다시 더하지 않는다. 디스크 여유 공간 수치는 동시에 실행되는 다른 작업에 따라 소폭 변할 수 있다.

## 수행 및 검증

1. WSL 내부 연구 계산이 실행 중이지 않은 상태 확인.
2. 중복 배포 압축본 전체 SHA256 비교 후 물리 사본 하나를 제거하고, 검증 후 기존 경로를 원본에 대한 하드 링크로 유지. 원본 압축본·실행용 입력·소스·설치된 환경 보존. 두 경로는 같은 완성 압축본이므로 한 경로를 통해 파일 내용을 덮어쓰면 다른 경로에도 반영됨.
3. `sync`와 `fstrim /` 수행. trim 출력 바이트는 가상 디스크의 빈 영역이며 실제 확보 용량으로 계산하지 않음.
4. WSL 종료 후 관리자 DiskPart의 `compact vdisk` 실행. 대상 파일의 절대 경로·재분석 지점·배타적 열기 확인.
5. WSL 재시작 후 보존 파일 14개 SHA256 비교 PASS. 대형 연구 입력 8개 경로·크기 확인 PASS.
6. 연구용 Python 환경 기본 모듈 검사는 `wsl_research_environment_check.txt` 참조. 전체 연구 시뮬레이션은 재실행하지 않음.

최종 IEEE8500 May01 및 IEEE123 B3 raw 백업은 C 결과 데이터 폴더에 그대로 보존. 이전 D 정리에서 보호한 코드·모델·입력은 이번 압축의 삭제 대상이 아님.

## 기록

- `wsl_cleanup_deletion_log.jsonl`: 추가 삭제 파일별 기록.
- `wsl_diskpart_output.txt`: DiskPart 실제 실행 로그.
- `wsl_compaction_admin_result.json`: 시작·종료·종료코드·크기.
- `wsl_after_compaction_verification.json`: 재시작 및 데이터 보존 확인.
- `wsl_compaction_summary.json`: 최종 정량 요약.

절차 참고: [Microsoft compact vdisk 문서](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/compact-vdisk).
