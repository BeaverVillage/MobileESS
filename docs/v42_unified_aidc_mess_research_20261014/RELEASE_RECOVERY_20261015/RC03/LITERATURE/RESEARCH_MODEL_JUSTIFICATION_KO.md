# Pre-site 문헌 근거와 연구 모델의 적용 범위

사용자가 지정한 세 IEEE Transactions 논문의 발행 정보와 저자 공개 원문을 확인했다. 문헌은 공간적 Workload 유연성과 조건부 계약을 연구 모델로 구성할 근거다. 개별 Kestrel 작업에 대한 실제 고객 승인이나 데이터 복제의 관측 증거로 사용하지 않는다.

| 앵커 | 정당화하는 연구 모델 | V42에 자동 이전하지 않는 항목 |
|---|---|---|
| [Wang et al., TSG 2016](https://doi.org/10.1109/TSG.2015.2501808) | 여러 데이터센터에 도착 Workload를 배분하고, 서비스·용량과 전송/대기 지연 제약을 함께 두는 모델 | 개별 GPU Gang·11-SVR 안전성, 실제 Kestrel 이동 동의 |
| [Hogade et al., TSUSC 2022](https://doi.org/10.1109/TSUSC.2021.3086087) | 에너지·네트워크 데이터량·대기 지연을 함께 고려하는 공간 배치와 데이터 크기 민감도 | 모든 작업의 무비용 이동, Kestrel의 실제 Payload·WAN·공유 저장소 상태 |
| [Basmadjian et al., TSG 2018](https://doi.org/10.1109/TSG.2016.2632526) | 공급자–DC의 GreenSDA, DC–고객의 GreenSLA로 유연성 범위와 QoS를 명시하는 계약 | 실제 체결된 Kestrel 고객 계약, 임의의 지연·Checkpoint 권한 |

R1을 주 연구 시나리오로 한다. 도착한 PENDING 작업 중 기존 FLEX30 계약에 적격한 작업만, 원래 Source-Compatible 사이트와 연구용 공유 입력 접근 집합의 교집합에서 평가한다. 입력이 사전 준비되어 실행 직전 AIDC 간 전송이 필요하지 않다는 것은 **본 연구의 명시적 환경 가정**이다. 논문이나 Kestrel에서 관측한 사실로 표현하지 않는다. 따라서 R1에 관측되지 않은 WAN 완료 기록을 요구하지 않고, 연구 계약과 적격 사이트·준비 시각을 검사한다. 명시적 Source 금지·비배치·보호 조건은 우선한다.

R2는 별도 시나리오다. [저자 공개 원문 Table 2](https://arxiv.org/pdf/2106.00066)의 입력 크기 예시 100/233/500/600/650 MB를 절대 작업당 Payload 시나리오로 사용한다. 이 값은 해당 논문의 benchmark dataset 크기이며, Kestrel UID를 그 작업유형에 대응시켰다는 뜻이 아니다. MB를 10⁶ bytes로 해석하는 것은 V42의 명시적 단위 규칙이다. Path·Bandwidth는 기존 V42 WAN 모델, 0.25/1 대역폭 비율과 준비 0/900초는 별도 모델 민감도다. 기존 80 GB/GPU 상태 전송 proxy는 이전 비교 시나리오로 보존하며 문헌의 입력 크기로 재명명하지 않는다.

전송이 필요한 R2에서는 Payload/가용 Bandwidth 이상인 전송시간과 준비시간을 포함하여 완료 시각을 900초 제어 격자로 올림한다. 원래 QoS가 그 추가 지연을 허용하지 않으면 대체 사이트를 거절하고 STAY는 계속 평가한다. R1/R2 어느 쪽도 QoS 추가 지연이나 RUNNING Migration 권한을 새로 부여하지 않는다.

Actual 순서는 `Unknown 도착 → 기존 Initial Placement → PENDING Pre-site → 실제 Start`다. Day-ahead에서 미래 Unknown 개별 UID·사이트를 최적화하지 않는다. 기존 기본 배치와 STAY를 보존하고, Compatibility → GPU/Rack → 데이터 계약 → 기존 QoS → 후보 AC → 공개 Q50 전 구간의 최대 선로·상 부하율 순으로 후보 Funnel을 기록한다. 유리하고 합법적인 대안이 있을 때만 변경한다. 실제 안전성의 공식 보고는 원본 11-SVR 정착 15분 × 96슬롯 AC 계약을 사용하며, 슬롯 내부 진단 한계는 별도로 남긴다.

R1의 217개 도착 중 FLEX30 61개는 연구 계약 대상 수다. GPU·Rack·전기적 검사까지 통과한 UID 수나 실제 변경 수가 아니다. Source-strict/R1/R2, C0/C1, 첫 3슬롯/16슬롯/Full96 결과는 각각 별도 범위로 보고한다. 근거의 숫자·위치·DOI와 V42 가정의 구분은 `LITERATURE_FACTS.json`에 저장한다. 논문 PDF 전체는 저장·배포하지 않는다.
