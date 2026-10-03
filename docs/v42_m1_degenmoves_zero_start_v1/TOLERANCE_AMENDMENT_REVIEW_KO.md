1. Solver-side tolerance: FeasibilityTol/IntFeasTol/OptimalityTol=1e-8 유지.
2. Post-solve numerical tolerance: 전역 1e-6; 공통 v42_postsolve.contract validator.
3. Incumbent max bound residual: 1.42291128213e-08. 두 raw point의 잔차가 원본 감사와 exact 재현됐다.
4. Full-row max residual: 9.97802544427e-09; 원본 961,472행.
5. Integrality max residual: 0; rounding 0.
6. Physical audit: True. 기존 policy/tolerance 유지. Raw minimum/maximum 및 실제 exceedance는 CURRENT_INCUMBENT_PHYSICAL_REAUDIT.json에 각각 기록한다.
7. Incumbent scientific UB 채택: True, UB=0.72203218925. Solver accepted + numerical PASS + physical PASS를 모두 요구한다.
8. Valid LB: 0.56871161035; 동일 완료 solve의 native global bound만 사용한다.
9. Recalculated gap: 21.2345905325%; (UB-LB)/abs(UB).
10. M1_P1_ACCEPTED: False; gap>0.5%, P2 NOT_RUN.
11. Zero-action Start 재분류: True; numerical + physical + primary semantics PASS, 기존 strict FAIL 보존.
12. Current solve에서 Start 실제 사용: False; 재분류가 완료 solve의 이 기록을 바꾸지 않는다.
13. Physical limits changed: False; voltage 0.95–1.05 pu / source-backed NormalAmps / kVA / line / SOC / PCS / route / capacity / Runtime / CC4 유지.
14. New optimize calls: 0; stored points 재검증만 수행. Accepted A1은 가능한 증거 범위에서 일관성 PASS, 새 full A1 matrix audit는 주장하지 않는다.

이번 정정은 physical constraint 완화가 아니라 post-solve floating-point numerical audit contract의 전역 정상화이다.
Solver-side FeasibilityTol/IntFeasTol/OptimalityTol=1e-8은 변경하지 않았다.
현재 1800초 M1 solve를 재실행하지 않았으며, 저장된 incumbent와 bound만 동일한 새 validator로 재검증했다.
