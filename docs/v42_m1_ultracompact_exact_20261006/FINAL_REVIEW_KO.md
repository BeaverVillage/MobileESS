# PR161 C2 exact ultra-compact 전수 감사

최종 상태: **ULTRACOMPACT_EXACT_SELECTED**

기준: `4f45f04d685d5d5e689463f953695fe40d52cf98` / Draft PR161. 추가 71,540행을 full-LP 증명으로 제거했다. C3A=C3B=C3C이며 추가 치환·병합은 채택하지 않았다.

선택: C3A, selected=True. 동일한 full MILP 설정의 새 C2/C3 root 비교에서 시간 212.29→180.21초 (15.11% 감소), root Work 452.05→359.99 (20.37% 감소)로 사전 등록한 15% 기준을 충족했다. 두 arm 모두 root 이후 B&B node 0, 새 valid incumbent 없음, valid gap 약 15.0436%이며 LB/gap 개선 기준은 통과하지 않았다.

Micro C2의 root는 제한 시간 내 미완료했다. 표의 None은 미완료에 따른 측정 불가이며 0을 뜻하지 않는다. Micro와 full MILP 사이 또는 과거 PR161 실행과의 시간/Work 비교는 사용하지 않았다. 원래 micro-only 자동 판정은 별도 파일에 보존하고, 새 native 실행 없이 완료된 full MILP 쌍의 root 지표에 같은 사전 기준 A/B를 적용했다.

이번 작업은 PR161의 selected C2 exact formulation을 기준으로 남아 있는 모든 row/column family를 전수 감사하고, C2의 continuous relaxation에서도 수학적으로 중복·고정·함의·결정적임이 증명된 구조만 추가 제거한 exact ultra-compact reformulation 연구다.

행 수를 줄이는 것 자체가 목적이 아니며, integer-only redundancy가 있지만 LP relaxation을 강화하는 제약은 primary C3에 유지했다.

line thermal, PCS16, route-flow, grid-response family까지 family-level 구조를 재검토했으며, 증명되지 않은 삭제 후보는 모두 유지했다.

최종 선택은 모델 크기가 아니라 root completion/time/Work, B&B node progress, valid global bound 및 valid MIP gap 개선으로 판정했다.

## 필수 검토 40문항

| 번호 | 질문 | 답변 |
|---:|---|---|
| 1 | C2 원래 크기 | 654,348행 / 306,040열 / B 9,322 / C 296,718 / nnz 5,584,200 |
| 2 | C2 presolved 크기 | 535,063행 / 280,359열 / B 9,326 / C 271,033 / nnz 4,668,412 |
| 3 | 추가 duplicate rows | 0 |
| 4 | 추가 dominated rows | PCS/연결 Q 다중 제약 함의 71,536; 단일 비례 지배 0 |
| 5 | 추가 line thermal 삭제 | 0 |
| 6 | 추가 PCS16 삭제 | 53,652 |
| 7 | 추가 transformer 삭제 | 0 |
| 8 | 추가 voltage 삭제 | 0 |
| 9 | Flow conservation 종속행 | 종단 위치 4행은 실제 retained flow 등식의 합; flow 자체 삭제 0행 |
| 10 | node activity link 삭제 | 0 |
| 11 | mode/connection rows 삭제 | connected_Qmax/min 17,884; P 연결/충방전 mode 행은 0 |
| 12 | energy balance 삭제 | 0 |
| 13 | route flow 변수 삭제 | 0 |
| 14 | state 병합 | 0 |
| 15 | transit chain 축약 | 0 |
| 16 | grid auxiliaries 삭제 | 0 |
| 17 | response auxiliaries 삭제 | 0 |
| 18 | injection auxiliaries 삭제 | 0 |
| 19 | continuous 삭제 합계 | 0 |
| 20 | 새 binary fix | 0 |
| 21 | 새 bound tightening | 48,551개 열의 함의된 경계 전환; 모두 독립 검증 |
| 22 | Polygon face count 축소 | PCS16 16→10; P 연결 영역을 포함한 최소 H facet은 12; line/transformer 비상수 normalized polygon은 16 |
| 23 | 더 작은 exact extended formulation | 채택 없음. 유리수 barycentric lift는 상태당 3행/12열/40 nnz로 최소 PCS 10행/0 추가열/36 nnz보다 열·nnz 증가; 일부 정점은 binary64 비표현 가능 |
| 24 | C3A 크기 | 582,808행 / 306,040열 / B 9,322 / C 296,718 / nnz 5,351,612 |
| 25 | C3B 크기 | 582,808행 / 306,040열 / B 9,322 / C 296,718 / nnz 5,351,612 |
| 26 | C3C 크기 | 582,808행 / 306,040열 / B 9,322 / C 296,718 / nnz 5,351,612 |
| 27 | Presolved C3 vs C2 | 407,856행 / 287,699열 / B 9,324 / C 278,375 / nnz 4,498,109; C2 535,063행 / 280,359열 / B 9,326 / C 271,033 / nnz 4,668,412; 역증가 flag=True |
| 28 | 1536 assignment equivalence | PASS; 기존 12 fixture를 변경하지 않고 F0/C2/C3 모두 같은 feasible assignment와 목적값 |
| 29 | Fractional LP proof | PASS; 비음수 Farkas 조합·flow 등식 합·단위 DAG 질량 max-union support; integer-only 삭제 0 |
| 30 | Adversarial tests | PASS; 13개 신규 경우 및 독립 인증 변조 거절 |
| 31 | Independent verification | PASS; C2 전체 행/열과 모든 새 bound, 제거행을 재구성; production deletion 함수 미호출 |
| 32 | Start mapping | PASS; 물리 route/P/Q/SOC/mode 변경 0, 최대 잔차 1.3827730072080158e-09 ≤ 1e-8 |
| 33 | Root time C2 vs C3 | micro C2 None / C3 194.03; full MILP root C2 212.29 / C3 180.21 |
| 34 | Root Work C2 vs C3 | micro C2 None / C3 359.99; full MILP root C2 452.05 / C3 359.99; overall Work와 분리 |
| 35 | Nodes C2 vs C3 | C2 1.0 / C3 1.0 |
| 36 | Valid LB | C2 0.5687116004028935 / C3 0.5687116003498334 |
| 37 | Valid UB | C2 0.6694159238756877 / C3 0.6694159238756877 |
| 38 | Valid gap | C2 0.15043610389449788 / C3 0.15043610397376117; MIPGap=.005 유지 |
| 39 | Selected | True; C3A |
| 40 | Exact commit / Draft PR | 0a27fb90dead2b944a72c31145f5a7bdc4dbb9ac / Draft PR 생성 예정; 실행 소스 커밋은 아래 기록 |

## 검증과 계산 범위

계수 범위는 C2 [1.0006451962467139e-13, 400.0]에서 C3 [1.0006451962467139e-13, 392.3141121612922]로 바뀌었다. 계수 400인 Q 링크를 삭제한 결과이며, 남는 계수·목적·변수 type은 정확히 보존했다. 새 경계는 물리 변수의 관측값이 아니라 C2 affine 정의와 단위별 위치/PCS max-union으로 증명했다. PR160 190,280개 인증과 PR161 704,775개 C1행 매핑을 재검증했다.

모든 현재 row/column family는 개별 ID 결정 파일과 family ledger에 포함한다. KEEP는 삭제 불가의 완전한 일반 정리를 뜻하지 않는다. 높은 fanout 후보의 비용은 정확한 sparse support union 상한이며 가능한 모든 수치 상쇄를 전수 증명한 값으로 표시하지 않았다. 전역 coupling rank는 structural rank만 보고하고 exact signed-incidence/삼각 정의 블록 외의 미증명 rank 삭제는 하지 않았다. SOC projection은 유한 상·하한의 두 경계 행까지 정확한 비용을 기록했다. 새 polytope, topology recursion, GUB/SOS/indicator, symmetry 후보는 증명이 없거나 비용이 악화되어 유지했다. 실제 C2에서 integer-only로 증명하여 삭제한 행은 0개이며 그런 삭제는 허용하지 않았다.

Root는 NodeLimit=1의 동일 설정으로 두 모델만 순차 비교한다. root 시간/Work는 native log의 0.01 정밀도 값이며 total Work와 구분한다. MILP도 같은 모든 native parameter(로그 경로 제외), 같은 물리 start, 285초 TimeLimit과 300초 전체 arm 상한을 사용한다. inherited full-domain LB와 안전 조정 native bound를 분리한다. 차이 1e-6 이하의 LB/gap 잡음은 개선으로 선택하지 않는다. time_after_root는 root 직후 native progress의 정수 초와 Runtime을 이용한 근삿값이다. 정확한 root 완료 callback 시각은 수집하지 못했고, Runtime에서 root LP 소요 시간을 단순 차감하면 presolve가 포함되므로 그 값은 별도로 보존했다. 0.5% gap 달성이나 전역 최적 완료를 주장하지 않는다. D-W/B&P/Benders/one-tree B&C/row generation/3600초/parameter sweep은 실행하지 않았다.

## 재현

`python -m v42_ultracompact.forensic C2` → `python -m v42_ultracompact.audit` → `python -m v42_ultracompact.network` → `python -m v42_ultracompact.closure` → `python -m v42_ultracompact.cost_finish` → `python -m v42_ultracompact.verify` → `python -m v42_ultracompact.tests` → `python -m v42_ultracompact.start`.

부모 PR 증명 replay는 원래 verifier의 읽기 전용 입력과 독립 연산을 사용하고 write/table만 새 namespace로 전달했다. 모든 parent artifact는 불변이다. C3B/C3C 동일성은 실제 sparse matrix/data 비교로 확인해 presolve/root/MILP를 중복 실행하지 않았다. `BENCHMARK_ONCE.json`이 있으면 benchmark를 다시 실행하지 않는다.

실제 4개 native arm 실행 소스는 `0a27fb90dead2b944a72c31145f5a7bdc4dbb9ac`다. `python -m v42_ultracompact.selection`은 이미 수집한 로그/JSON만 읽어 판정과 timing 메타데이터를 재구성하며 optimize를 호출하지 않는다. `python -m v42_ultracompact.report`는 최종 보고서·authority·SHA manifest를 생성한다. 새 scientific 실행 없이 C3를 고정하고 STOP했다.
