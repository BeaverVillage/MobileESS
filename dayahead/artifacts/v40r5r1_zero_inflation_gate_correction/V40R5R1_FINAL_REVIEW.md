# V40R5R1 최종 검토

V40R5R1_ZERO_INFLATION_AWARE_EVALUATION_COMPLETE

R5의 실패 판정과 전체 파이프라인 미선택을 유지한다. 저장된 예측의 양수 BODY 크기 평가 계약만 교정하였다.
양수 Q90 coverage 90–95%를 평가하고, 전체/0값 coverage는 진단으로 분리했다. 모델·보정 재학습은 0회다.

```text
              role       candidate  BODY_N  positive_BODY_N  zero_N  positive_Q90_coverage  positive_Q90_pinball_GPUh  positive_Q90_MAE_GPUh  positive_Q90_WAPE  positive_underprediction_GPUh  positive_overprediction_GPUh  all_BODY_underprediction_GPUh  all_BODY_overprediction_GPUh  overall_coverage_DIAGNOSTIC  zero_only_coverage_DIAGNOSTIC  coverage_identity_abs_error  positive_contract_compatible
       CALIBRATION PB1_TRIAL_0_BC0    2345             1150    1195               0.727826                  17.156805              40.909376           1.413949                   18782.184317                  28263.598504                   18782.184317                  51946.216093                     0.866525                            1.0                 0.000000e+00                         False
       CALIBRATION PB1_TRIAL_1_BC0    2345             1150    1195               0.706957                  17.980542              39.043924           1.349473                   20234.465301                  24666.047872                   20234.465301                  45463.525463                     0.856290                            1.0                 1.110223e-16                         False
       CALIBRATION PB1_TRIAL_0_BC1    2345             1150    1195               0.900870                  15.591471             121.034331           4.183303                    5014.054829                 134175.426339                    5014.054829                 229082.596289                     0.951386                            1.0                 0.000000e+00                          True
EXPOSED_EVALUATION PB1_TRIAL_0_BC0    8030             4174    3856               0.746047                  16.070564              43.355490           1.363604                   61227.443172                 119738.370773                   61227.443172                 213142.708677                     0.867995                            1.0                 0.000000e+00                         False
EXPOSED_EVALUATION PB1_TRIAL_1_BC0    8030             4174    3856               0.731672                  16.307839              43.532977           1.369186                   62372.817148                 119333.826809                   62372.817148                 214262.197604                     0.860523                            1.0                 1.110223e-16                         False
EXPOSED_EVALUATION PB1_TRIAL_0_BC1    8030             4174    3856               0.941303                  16.305292             140.375161           4.415037                   11832.123124                 574093.800473                   11832.123124                 946228.651092                     0.969489                            1.0                 1.110223e-16                          True
```

BC1의 양수 BODY 신호는 관찰되지만 optimizer integration=NO, production ready=NO다.
CAL의 기존 전체 coverage 상한은 0값 비율 때문에 구조적으로 모순되었다. 기존 burst·hybrid 실패는 그대로다.
검증 결과는 V40R5R1_TEST_REPORT.json, 커밋 연결은 V40R5R1_FINAL_COMMIT_RECEIPT.json에 기록한다.
