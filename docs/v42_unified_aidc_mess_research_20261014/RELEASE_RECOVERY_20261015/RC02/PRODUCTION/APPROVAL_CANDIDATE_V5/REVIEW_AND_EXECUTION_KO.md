이 후보는 현재 성공 A1·독립 May01 D0 manifest·측정된 현재 M1 캐시 receipt·실제 executor Source bytes·안정된 RC03 정책 hash에 직접 묶여 있다. approved=false이며 Native 권한은 없다. 기본 검토 CLI는 Source/Case/정책을 검사하고 실행하지 않는다.

```powershell
python -B -X utf8 "D:\v42_trajectory_tracking_may01_20261014\tools\run_v42_production_campaign.py" --planning-only --plan "D:\v42_trajectory_tracking_may01_20261014\docs\v42_unified_aidc_mess_research_20261014\RELEASE_RECOVERY_20261015\RC02\PRODUCTION\APPROVAL_CANDIDATE_V5\UNAPPROVED_MAY01_PLAN.json" --approval "D:\v42_trajectory_tracking_may01_20261014\docs\v42_unified_aidc_mess_research_20261014\RELEASE_RECOVERY_20261015\RC02\PRODUCTION\APPROVAL_CANDIDATE_V5\UNAPPROVED_PLANNING_570_APPROVAL.json"
```

별도 명시 승인을 받은 뒤에만 같은 검토 파일의 승인 상태와 실제 human approval reference를 채워야 한다. 승인 파일은 하나의 새 원장 경로/authorization_id에 결합된다. 실행에는 --execute --output <새체크포인트폴더> --budget-ledger <승인에결합된원장경로>가 추가로 필요하다. 이번 준비에서 이 명령을 실행하지 않았다.

첫 요청 상한은 Planning 570초(cap480+반환30+overshoot60)이며 A1을 반복하지 않고 M1→A2→M2까지만 수행한다. 각 단계 Original FULL이 없으면 다음 단계로 갈 수 없다. 이후 K48 현재 Case packet 포함성 인증 뒤 별도270초를 검토한다. 현재 K48 packet/executor가 미인증이므로 후속270초 제안도 승인 요청 전 단계다. 기존750초 문서는 역사 안으로 보존하고 현재 두 원장 흐름에 쓰지 않는다.

2.13GB 캐시는 여기서 다시 읽거나 hash하지 않았다. 기존 Native0 측정 receipt를 재사용했으며 실제 복원 시 RAM admission, packet bytes 재hash, 원본 Source/Case/Domain proof 검증이 필수다. R1 31일 정책 mapping은 준비 자료이며 Actual96/Fresh96 또는 31일 실행 인증이 아니다.
