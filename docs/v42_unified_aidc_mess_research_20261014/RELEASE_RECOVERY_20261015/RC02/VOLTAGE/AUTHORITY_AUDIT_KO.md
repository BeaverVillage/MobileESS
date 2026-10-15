# RC02 최초 배치·Pre-site·Migration 권한 감사

현재 16슬롯 Unknown 217개는 원본 입력에 고객 사이트 지정이나 Pre-site 필드가 없다. 원본 Actual 어댑터가 `can_prestart_place=False`를 부여한다. 이는 확인되지 않은 행동 권한을 보수적으로 닫은 것이며, 고객이 명시적으로 금지했다고 해석하지 않는다.

최초 배치는 이미 승인된 연구용 기본 사이트 계약이다. 같은 Reference site를 사용하며 계통 민감도로 다시 선택하지 않고, Pre-site 권한을 요구하지 않는다. RC01의 217개 기본 사이트 지정과 25개 실제 STAY 시작은 이 계약 범위이다. SourceStrict 고객 동의 인증은 아니다.

PENDING 대체 사이트 이동에는 별도의 행동 권한과 데이터 위치·목적지·관측 시각, 이미 준비된 데이터 또는 실제 payload/WAN 경로·대역폭·준비시간이 필요하다. 현재 미래 Unknown 696개에는 해당 근거가 없다. `compatible_sites`는 GPU/사이트 호환성으로, 데이터가 모든 사이트에 준비되어 있다는 뜻이 아니다. 기존 최초 배치 연구 계약에서 이를 잘못 차단한 연결부 오류는 확인되지 않았다. Pre-site 변경 0건을 유지하며 기본 사이트 실행은 계속한다.

RUNNING Migration은 체크포인트·전송·재개 근거가 없어 HOLD이다. 추가 연구용 Pre-site 가정이 필요하면 별도 Science/Policy로 승인받아야 하며 현재 활성화하지 않았다. 원본 QoS와 hard window를 연장하지 않는다.

세부 수치, 원본 파일 SHA, 함수별 근거 줄과 최소 추가 계약 항목은 `AUTHORITY_AUDIT.json`에 있다. 이 감사는 신규 실행 또는 생산 권한을 발급하지 않는다.
