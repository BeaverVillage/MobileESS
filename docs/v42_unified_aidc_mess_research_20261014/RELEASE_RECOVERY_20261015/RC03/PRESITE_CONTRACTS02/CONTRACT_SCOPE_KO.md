# R1/R2 연구 계약 준비

기존 `PUBLIC_UNKNOWN_PRESTART_COMPATIBLE_SITE_STUDY_V1`은 기본 배치 연구 권한입니다. 기존 CurrentEvent 준비 로직은 관측된 Destination·Source SHA·준비 시각·WAN Path·Bandwidth·Payload 근거를 요구합니다. 최초 배치 연구 권한을 관측된 데이터 이동 권한으로 승격하지 않습니다.

새 R1/R2는 사용자의 별도 연구 시나리오 지시에 따른 계약입니다. 기존 Experimental FLEX30의 UID/Episode 가입 규칙과 ASSUMED_NORMAL_BATCH 분류만 재사용합니다. 미확인 Batch 분류는 연구 가정으로 표시하고, 원본의 명시적 보호·비배치·이동/접근 금지는 우선합니다. 기존 QoS 추가 지연·Checkpoint 권한은 재사용하지 않습니다. 원본 strict QoS와 기본 배치는 그대로입니다.

R1은 FLEX30 적격 작업만, Source-Compatible 대상과 명시된 shared_sites 교집합에서 도착 후 첫 제어 시각부터 입력에 접근 가능하다고 가정합니다. R1에는 실제 WAN 전송 인증이 없습니다. C0/C1 모두 같은 접근 환경이며 Pre-site 행동만 다릅니다.

R2는 기존 WAN 모델의 Path·슬롯 용량·최대 동시 전송 1개를 그대로 사용합니다. 기존 80 GB/GPU는 실행 상태 전송 모델의 값이므로 입력 Payload 관측값으로 주장하지 않습니다. 입력 크기의 명시적 ASSUMED proxy로만 0.25/1/4배를 비교하고, 병목 Bandwidth 0.25/1배 및 준비 0/900초를 구분합니다. 실제 QoS 지연 권한이 없으면 전송을 시작하지 않고 STAY를 유지합니다.

준비 표는 이미 RC01에서 도착 관측된 217 UID의 계약 전제 민감도 감사입니다. GPU/Rack·후보 AC·Actual 변경·성능 결과는 이 표로 인증하지 않습니다. 실제 C0/C1 실행은 별도 원장에 기록합니다. 기존 전압 위반 Gate는 FAIL로 유지합니다.
