## 문제와 결과

PR #89가 평가한 user/submit_line 정보만으로 full RADDiT의 정보가치를 판단할 수 없었다. 실제 20개 필드·2,557,884행을 감사하고, native D0–D4와 identity/software-stack 대비, 완료 이웃, 대조군, 동일 매핑 표본의 공개 4,096차원 좌표를 평가했다. 기준은 PR #89 commit `c84588e02727eb5311ba25f6a3ed43ff229cfe07`이다.

Native 판정: **LIMITED_OR_MIXED_INFORMATION_VALUE**. Primary 최저 pinball D2: min-fold 80.23%, >4h 60.53%, pinball 3368.10s. Software-stack 대비는 >4h 63.69%→70.77%의 부분적 신호를 보였으나 엄격한 min-fold 동시 개선 조건은 통과하지 못했다.

R16-A/B/C의 exact 5-fold 평가를 완료했고 TOTAL 통과 모델은 없다. H1은 R16-A로 평가했다. H2는 modules/conda 권한 부재로 미실행이다. Stage C/provider, remaining, April은 TOTAL 실패로 미실행이며 May는 unopened다. CC4 rich 단계는 조건 미충족으로 미실행이며 C0를 유지했다. C0는 frozen T0/B0이며 T2_F0/T3_F2는 연구 후보로 유지했다.

| Runtime arm | 상태 | Min-fold | >4h | Pinball (s) |
|---|---|---:|---:|---:|
| R0 | FROZEN_REFERENCE_RECOMPUTED | 70.70% | 69.72% | 4752.76 |
| R15 | FROZEN_REFERENCE_RECOMPUTED | 66.75% | 66.87% | 4720.18 |
| R16-A | COMPLETED | 66.21% | 64.79% | 5083.33 |
| R16-B | COMPLETED | 65.49% | 50.53% | 4972.60 |
| R16-C | COMPLETED | 61.77% | 64.85% | 5006.08 |

## 과학적 해석과 공개된 정정

정보가치, 미래 제출 재현성, Runtime 안전성을 별도로 판정한다. Native 유일 매핑 작업은 기존 GPU VALID 5개 fold와 교집합이 없다. Modules/conda는 원본 Kestrel 제출 데이터에 없어 운영 입력으로 승격하지 않았다. user/submit_line도 기존 receipt·namespace 계약을 조건으로 하는 연구 입력이다.

원 사전등록에 추가됐던 회색 구간 자동 중단은 사용자 원문의 명시한 STOP에서만 중단하라는 지시와 달라, 일부 native 결과 이후 실행 경로를 정정했다. 전체 native 판정·bridge 학습 전에 기록했으며 원 사전등록 bytes, 모델·fold·성공/STOP·안전 threshold를 보존했다. 모든 실행이 무수정 사전등록이었다고 주장하지 않는다.

전체 native D1–D4 범위: 사전등록 material-win 조건을 충족한 arm이 없어 그룹 제거 학습은 NOT_RUN_NO_MATERIAL_WIN으로 기록했다. IDENTITY_ONLY와 SOFTWARE_STACK은 사전등록된 기본 정보 대비 실험이다. 별도로 같은 매핑·TRAIN cap 표본의 EMB_D2가 >4h +5.29pp, pinball 약16.06% 개선으로 사용자 그룹 제거 조건을 만족해 A–E를 제거하는 후속 진단을 완료했다(F는 채널 없음). 원 사전등록의 primary ablation 범위를 넘는 조건부 진단 확장이며, paired 결과 확인 후 실행 동결을 공개했다. Primary 판정·Runtime 선택에 소급 적용하지 않는다. 또한 사전등록 SOFTWARE_STACK 대비가 >4h +7.08pp와 pinball -7.84%로 사용자 조건을 만족해 별도 full-population 그룹 제거 진단을 완료했다. A는 실제 학습, E는 동일 설계행렬을 확인한 D0 재사용이며 B/C/D/F는 해당 채널이 없다. 이 역시 primary D1–D4 판정을 바꾸지 않는 공개된 조건부 진단 확장이다.

유일 연구용 연결은 historic 2,069,804행, embedding 1,504,846행이고 비교 가능한 holdout 충돌은 0건이다. 서로 다른 partition namespace를 직접 비교했던 최초 오류 결과도 보존했다. 3월 파일에서 읽힌 UTC 4월 경계 10,760행은 feature/selection 전에 제외했으며, 이를 April 바이트를 전혀 읽지 않았다고 표현하지 않는다. May 2025 payload는 열지 않았다.

## 검증 및 보존

집중 테스트, 모든 선택 이웃의 strict 완료 시간 검사, 새 프로세스 모델·이웃 재생, 저장 예측의 지표/gate 재계산, exact R0/PR89 재집계, V6–V15 기존 hash와 원본 fingerprint 검증을 수행했다. 정확한 건수와 최종 PASS는 VERIFICATION.json에 있다. 대용량 모델·행 예측·로그는 `.local`에 보존하고 SHA256 manifest로 연결했다.

변경은 새 연구 디렉터리로 제한했다. 기존 V42/optimizer/MESS/flexibility를 수정하지 않았고 OpenDSS를 실행하지 않았다. FINAL_REVIEW_KO.md에 요청한 50개 질문을 모두 답했다.
