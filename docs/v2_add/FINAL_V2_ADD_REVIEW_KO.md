# V2_add — 현재 Preflight 검토

판정: **NO_GO_PENDING_PREFLIGHT / INPUT_MAPPING_NOT_VERIFIED**. 버전명은 **V2_add**다. 실험·브랜치·runtime·원장은 V44 및 V1_add와 분리했다. 이번 보고서는 준비/감사 결과이며 확장성 실험 완료 보고서가 아니다.

공식 Balanced를 실제 OpenDSS에서 다시 compile해 8,531 노드, 3,703 선로, 1,177 Triplex, 1,190 변압기를 확인했다. 날짜별 원본 권위 검사 190행 중 190행이 현재 SHA와 일치했다(고유 path/SHA 쌍 135개; May01 보강 검사와 중복 포함). 정확한 범위는 MAY01_07_AUTHORITY_SHA_RECHECK.csv에 있다. 전체 재귀 Source Lineage나 D-1 입수 시점의 인증은 아니다. PR235의 May01 최종 전력 배열을 Git 바이트 및 .npy SHA로 다시 확인했다. Planning96과 Actual24+96을 구분하고 alpha_BG=1.15를 재적용하지 않았다.

PR199 C2 공동 PCC24 후보를 결과 탐색 전에 고정해 복원했다. 24개 기존 route service ID 대응을 확인했지만 P300/Q250/PCS400·동시8대 물리 적합성 인증은 아니다. 후보 beta=[1.00,1.05,1.10,1.15,1.20,1.25,1.30,1.40,1.50]와 판정/동률 규칙을 먼저 등록했다. B1/B2/B3 결과를 읽거나 Scale 선택에 사용하지 않았다.

## 요청한 12개 질문의 현재 답

1. V44 입력 연결: May01 원본 최종 BG/PV/AIDC P/Q 배열은 그대로 확보했다. 공식 고객 P/Q 가중치로 BG를 배분한 후보의 총량만 검증했다. PV의 2.4kV Model1→공식 hot-leg 전압/상/인버터 및 PCC24 물리 계약은 미검증이다. 후보 산술을 실제 AC 적용 완료로 표시하지 않는다.
2. beta=1.00 B0 최대 부하율: **NOT_VERIFIED**. PR197의 57.0975%는 다른 입력/조건의 과거 결과이며 이번 값으로 사용하지 않는다.
3. 최종 beta: **선정하지 않았다**. SELECTED_SCENARIO_FREEZE.json은 NOT_FROZEN이다.
4. 75~85% 달성 여부: **NOT_VERIFIED**. 후보 실패와 미실행을 구분한다.
5. MV/LV 차이: **NOT_VERIFIED**. 일별/슬롯별 전역 AC가 필요하다.
6. 병목 하류 제어 PCC: **NOT_VERIFIED**. 원본 topology와 C2 후보는 복원했지만 병목이 측정되지 않았다.
7. AIDC 실제 유연량: 설치 GPU780을 보존했다. 원본 로더가 최종 적용하는 WINDOWS.json 기준 시간 이동 허용 Job은 1024개다. 구형 Native raw can_timeshift 플래그 0개를 최종 유연 Job 0개로 해석하지 않는다. 아래 원본 capability 및 Window 집계는 실현 가능한 피크 kW/GPUh 이동량으로 합산하지 않는다.

```json
{
  "raw_native_masks": {
    "can_timeshift": {
      "job_count": 0,
      "GPU_gang_sum": 0,
      "warning": "Sum across jobs, not simultaneous GPU or feasible flexible kW; masks alone are not a QoS/WAN/96-slot witness"
    },
    "can_prestart_place": {
      "job_count": 1395,
      "GPU_gang_sum": 1395,
      "warning": "Sum across jobs, not simultaneous GPU or feasible flexible kW; masks alone are not a QoS/WAN/96-slot witness"
    },
    "can_checkpoint_migrate": {
      "job_count": 1603,
      "GPU_gang_sum": 1796,
      "warning": "Sum across jobs, not simultaneous GPU or feasible flexible kW; masks alone are not a QoS/WAN/96-slot witness"
    }
  },
  "effective_windows": {
    "source": "WINDOWS.json, applied by original v42_may_campaign_native90/bindings.py:check_a_cells",
    "source_sha256": "5aec44479490ea00c0532f87229850507623b3d365fcdfbd6b105208dc8317a8",
    "rows": 1605,
    "eligible_known_jobs": 1605,
    "effective_can_timeshift_count": 1024,
    "positive_service_can_timeshift_count": 1024,
    "warning": "Effective source window capability, not independently certified feasible flexible power"
  }
}
```

8. MESS8 제어량: 대당 P±300kW/Q±250kvar/PCS400kVA, 초기/종단760kWh, SOC440~1080kWh, 충방전효율0.95를 원본에서 유지한다. 순간 합계2.4MW와 실제 96슬롯 이동/SOC/Rebound 제약을 만족한 공급량은 다르다. 후자는 NOT_VERIFIED다.
9. 96슬롯 pilot의 전역 감소량: **NOT_VERIFIED**. 진단 결과를 B1/B2/B3 성과로 표시하지 않는다.
10. B0/B1/B2/B3 차이: **NOT_VERIFIED**, 단일 시나리오 동결 및 알고리즘 통합 전 미실행.
11. B3 공동제어 추가효과: **NOT_VERIFIED**. 우열을 가정하거나 보정하지 않는다.
12. IEEE123 대비 계산량/시간/Gap: **NOT_VERIFIED**. 실제 모델/Native 실행이 없다.

## 차단 원인과 재개 조건

- PV voltage/phase/inverter and bus-wise power balance adapter not certified
- PR199 C2 dedicated hardware not yet AC-certified for V44 P300/Q250/PCS400 and 8 simultaneous vehicles
- IEEE8500 original controls/P5 versus V44 Planning7/Actual43 physical contract unresolved
- No verified 96-slot Job/route/SOC/rebound pilot; no scale B0 measured
- 8-vehicle FULL/Compact/K48/A1/M1/A2/M2 integration and independent validator not certified
- Existing V44 processes/heavy-worker leases active: no conflicting long Native run

PV/PCC/제어 하드웨어 Adapter를 독립 검증한 뒤 beta1.00부터 Fresh AC 전수 screening을 실행해야 한다. 해당 결과와 실제 feasible pilot만으로 Primary Scenario를 동결한다. 전체 후보 screening을 수행하지 않았으므로 NO_QUALIFIED_HIGH_CONTROLLABILITY_SCENARIO로 단정하지 않는다. 장시간 Native는 기존 캠페인 lease/실행 보호 Gate를 통과한 뒤에만 진행한다.

요청한 숫자 산출물은 빈 수치와 NOT_VERIFIED/사유를 저장했다. topology 그림은 실제 원본 정적 구조와 C2 후보만 보여준다. MV/LV 히트맵·Scale 곡선·민감도·B0~B3 그림은 실제 측정자료가 없어 생성하지 않았다. 요청한 그림들의 완료 상태는 FIGURE_READINESS.json에 기록한다.
