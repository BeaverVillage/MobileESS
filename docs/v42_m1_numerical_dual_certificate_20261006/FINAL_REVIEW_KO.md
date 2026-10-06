# Numerical dual-certificate audit

EXACT_DUAL_AUTHORITY_PASS=false. Native solve 없는 최초 audit가 FAIL이어서, 명시적으로 허용된 certificate-only dual-simplex polish 1회만 실행했다. Native runtime 0.6309998035430908초, status OPTIMAL, iteration 0이다. 추가 native solve/CG/pricing/B&P/7200초/P2는 0회다.

## Raw numerical metrics

| Metric | Original independent reconstruction | Polished independent reconstruction | Polished native attribute |
|---|---:|---:|---:|
| Max sign violation | 4.7607794600631628e-11 | 4.7607799183594876e-11 | row family census |
| DualVio | 6.6793514989782476e-10 | 6.6793524357289247e-10 | 6.6793524357289247e-10 |
| DualResidual | 8.2572837456496018e-16 | 2.5699928296596397e-14 | 2.5699928296596397e-14 |
| ComplVio | 4.1592911421166405e-18 | 3.7859706868733059e-17 | 0 |
| Primal equality residual | 1.1546319456101628e-12 | 1.503241975342462e-12 | 1.503241975342462e-12 |

Original snapshot에 native DualVio/DualResidual/ComplVio가 저장되어 있지 않았으므로 값은 독립 재계산으로 명시했다. Polish snapshot에는 실제 native attribute를 sign gate 전에 저장했다. Native ComplVio와 재구성 값 차이는 내부 slack과 저장된 CSR의 외부 residual 계산을 구분해서 기록했다. 정의: [Gurobi quality attributes](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/quality.html).

원래 OptimalityTol=1e-8, polish OptimalityTol=1e-9(강화)이다. Acceptance numerical authority는 1e-8로 유지했다. 원래 max sign violation/tolerance=0.004760779460063163, 원래 max unsupported RC/tolerance=0.06679351498978248. 이 값들만으로 PASS를 선언하지 않았다. Raw original-bound dual objective는 잘못된 sign 및 infinity support 때문에 유한하게 정의되지 않으며 raw primal-dual difference도 unavailable로 명시했다.

## Row-family maximum sign violation

| Family | Maximum original violation |
|---|---:|
| DW_convexity | 0 |
| NormalAmps | 0 |
| flow | 0 |
| injection_P_binding | 0 |
| injection_Q_binding | 0 |
| line_thermal_face | 0 |
| response_line_P_binding | 0 |
| response_line_Q_binding | 0 |
| response_line_correction_binding | 0 |
| response_transformer_P_binding | 0 |
| response_transformer_Q_binding | 0 |
| transformer_kVA | 4.7607794600631628e-11 |
| voltage_lower | 0 |
| voltage_upper | 0 |

최초 실패: c454461 / transformer_kVA / <=. Raw Pi +4.760779460063163e-11, RHS 245.1963201008076이다. 부호 boundary로 옮길 때 이 row의 RHS 항 변화만 약 1.167e-8이므로 작은 Pi 자체가 작은 목적값 오차를 보장하지 않는다.

## Seven originally invalid infinity supports

이 7개는 LB=0 / UB=infinity인 lambda이며 genuinely free 변수는 아니다. 원래 free global 좌표 81,216개는 별도로 확인했다.

| Variable | Original native RC | Polished native RC | Canonical rational RC (float display) |
|---|---:|---:|---:|
| `lambda[MESS02,1408]` | -6.6793514989782476e-10 | -6.6793524357289247e-10 | 7.4718608305105909e-09 |
| `lambda[MESS04,1617]` | -3.2959746043559335e-17 | -3.0617869350990645e-15 | 1.9140558503603912e-09 |
| `lambda[MESS02,1625]` | -1.0408340855860843e-17 | 6.9388939039072284e-18 | 1.9140589212578125e-09 |
| `lambda[MESS03,1644]` | -6.591949208711867e-17 | -1.5612511283791264e-17 | 1.118499465140188e-16 |
| `lambda[MESS03,1645]` | -6.2450045135165055e-17 | -1.3877787807814457e-17 | 1.1385393520432138e-16 |
| `lambda[MESS02,1655]` | -2.0816681711721685e-17 | -8.6736173798840355e-18 | 1.9140589142784679e-09 |
| `lambda[MESS03,1675]` | -2.5500435096859064e-16 | -3.1398494915180208e-16 | 5.7518309555148155e-09 |

## Mathematical canonicalization and independent proof

원시 X/Pi/RC는 보존했다. 기존 authority 안에 있는 residual임을 확인한 뒤 positive <= Pi를 정확한 0 boundary로 옮겼다. 원래 triangular equality 81,216개에서 unrestricted equality dual을 유리수로 조정하여 free-coordinate stationarity를 정확히 0으로 만들었다. 각 MESS convexity equality dual을 해당 retained-column의 exact minimum RC만큼 낮춰, 1,841개 RC를 모두 정확히 nonnegative로 만들었다. RC를 직접 clipping하거나 infinity를 pseudo-finite 값으로 바꾸지 않았다. Objective/rows/bounds를 바꾸지 않았다.

전체 83,058 RC와 lower/upper dual 및 bound support 항을 처음부터 재계산했다. 독립 CSC-column Fraction 계산이 CSR-row 계산과 정확히 일치했다. Original bounds만으로 finite support를 구성해 weak-duality rational lower bound를 증명했다. 원래 full local domain의 coordinate interval support로 같은 canonical dual의 full-domain beta lower bounds도 계산했고 corrected formula를 독립 확인했다. 과거 다른 dual의 pricing bounds를 섞지 않았다.

Weak-duality proof와 1,841-column feasibility: PASS. 그러나 complete numerical authority: FAIL.

- Polish primal objective: 0.57293861549439529
- Canonical rational dual objective: 0.5729385980789613
- Primal-dual difference: 1.7415433958910485e-08, 기존 1e-8의 1.741543396배
- Restricted RMP safe LB (fixed1e-8 safety 후): 0.57293858807896125; original M1 global LB로 쓰지 않는다.
- Full-domain analytic corrected LB: -4.9168560342380223, 유효하지만 느슨하다.
- Inherited valid global LB: 0.56871157253362081, 유지했다. Root CG closure나 integer incumbent UB를 주장하지 않았다.

Polish setting changes: Method1, LPWarmStart1, Presolve0, NumericFocus3, Quad1, MarkowitzTol0.5, OptimalityTol1e-9. Same scientific CSR/axes/RHS/senses/objective/bounds의 SHA가 모두 일치한다. Saved native basis를 붙이면 fingerprint가 0xf6cbcc5d에서 0xb49886f2로 바뀌며 reset하면 돌아오는 것을 optimize 없이 관찰했다; scientific payload 변화가 아니다. `FINGERPRINT_BASIS_EFFECT.json`에 증거를 저장했다.

Same-coordinate transformer face row들도 검사했다. 실패 face 외 동일 두 좌표를 가진 15개 face의 Pi는 모두 0이고 slack이 있다. 이 local census에서는 stationarity/RHS를 보존하면서 부호만 교체할 co-active multiplier identity를 확보하지 못했다. 추가 solver 호출이나 acceptance 완화로 대체하지 않았다.

Original PR155 974개 파일과 이전 reproduction의 모든 manifest 대상 파일을 byte-for-byte 보존했다. Native snapshot 전에 native quality와 원시 벡터를 저장했고, rational dual/RC/bound 항/canonicalization trace와 전체 SHA manifest를 별도로 보관했다. 현재 blocker는 canonical objective agreement다. 허용된 polish 호출은 소진했으며 이후 계산은 시작하지 않았다.

회귀검증: exact certificate/기존 sign guard/corrected bound 45개 테스트 모두 PASS, 6개 Python 파일 compile 및 diff whitespace 검사 PASS. 이 검증은 full-scale native solve를 추가하지 않았다. 상세 결과는 `FINAL_TEST_RESULTS.xml`과 `VERIFICATION.json`에 보존했다.
