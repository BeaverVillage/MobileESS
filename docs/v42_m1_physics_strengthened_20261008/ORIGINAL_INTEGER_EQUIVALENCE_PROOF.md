# 원본 정수 영역 동치

B1의 forward/inverse는 원래 306,040축의 identity다. 모든 C3A 582,808행·RHS·senses·objective·ObjCon·bounds·types가 남아 있다. B2의 추가 행이 모든 original integer schedule에서 유효하므로 B2 forward도 identity다. B2에서 original로는 추가 행을 무시하면 된다. 정수 feasible set과 min rho 목적값을 보존한다.

Route flow f는 원래 continuous다. 정수성은 types 변경이 아니라 binary node_activity와 원래 unit-path projection에서 유도한다. 원래 time DAG에는 parallel endpoint arc가 없다. Nonnegative unit flow의 path 분해에서 binary vertex mass는 모든 양의 path에 같은 occupied vertices를 강제한다. 시간 순서와 parallel arc 부재로 경로와 f가 유일하다. Source·terminal·alias(terminal stay 95→node_activity 96)·zero identities를 확인한 PR183 일반 증명의 SHA를 보존하고 새 D: traffic copy에서 DAG를 독립 대조했다.

H2의 forward는 SOC 380좌표만 제거한다. Inverse는 원래 FULL energy 384행의 실제 계수로 initial SOC부터 누적 SOC를 복원한다. 모든 원래 SOC bound를 해당 누적 표현의 bound로 대체하고 terminal condition을 유지한다. Retained bounds·types·objective는 그대로다. 전체 CSR에서 SOC가 non-energy 행에 등장하지 않음을 확인했다. Real arithmetic의 symbolic bijection과 floating reconstruction replay를 구분한다. 작은 fixture만으로 실제 C3A 동치성을 주장하지 않는다.
