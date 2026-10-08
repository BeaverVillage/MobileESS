# 계산 구조

H1은 원래 node_activity·charge_mode·continuous route_flow·SOC·Pch·Pdis·Q·injection P/Q·rho 축을 공유한다. 실제 CSR audit에서 shared 248,765열, physics-only 213,868행·2,780,220 nnz, residual network 57,275열, coupling 368,940행을 확인했다. 변수 복사는 없다. Native +1 pivot definition 48,551개를 확인했지만 network 변수 13,224개는 이 family 기준에서 직접 정의가 증명되지 않았다. 이를 자유 변수나 유일 affine auxiliary라고 단정하지 않고 원래 bounds와 모든 행을 유지한다.

잔여 grid를 복구하면 H1은 원래 C3A와 동일한 B1이다. 별도 거대 recourse LP와 반복 row-generation 대신 모든 물리·grid 행과 원래 network auxiliary를 보유한 compact monolithic branch-and-cut 후보를 선택했다. 이 구조 변경 자체는 LP 강화가 아니며 B1 ROOT를 중복 실행하지 않는다.

B2는 모든 4대 MESS와 전체 96-slot 이동 arc에서 유도한 정수 유효 route–SOC 제약을 원래 변수에 추가한다. 795,944개 후보를 exact arithmetic으로 검토하고 archived fractional point에서 위반한 651개를 모두 포함했다. 총 306,040열·583,459행·5,352,914 nnz이며 새 열·새 binary는 0개다. 모든 원래 행·grid 행·bounds·types를 유지한다. Critical-grid top-K 축소는 없다. 각 추가 행에는 원래 arc/SOC 인덱스·계수·RHS·outward transport certificate가 있다.

H2는 별도 계산 구조다. SOC 380열을 제거하고 원래 energy 384행의 누적식, SOC bound 760행과 terminal equality 4행으로 같은 projection을 표현한다. cumulative.py의 matrix-free forward/inverse와 bound 검사에서 실제 원본 계수를 사용한다. 전체 prefix CSR는 만들지 않았다. 예상 nnz가 약 2,594만이고 LP 완화가 같으므로 material ROOT 후보에서 제외했다. SOC를 이산화하거나 전체 상태를 열거하지 않았다.

ROOT → certified gain≥0.001와 tractability → canary≤900초 → 실용 canary → production의 gate를 유지한다. ROOT가 미측정인 현재는 canary·production·downstream을 실행하지 않는다. Production-ready=false다.
