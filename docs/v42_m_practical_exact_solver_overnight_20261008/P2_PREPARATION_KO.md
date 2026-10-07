P2는 실행하지 않았다. 현재 gap이 수용 기준 0.5%에 도달하지 않았다.

PR162 원본 M1 objective contract의 movement energy와 movement count를 독립적인 정확 유리수 좌표 inverse로 C3A 축에 투영했다. 두 목적함수의 모든 계수와 ObjCon이 binary64로 정확히 표현 가능하다. 별도의 PhysicalReplay inverse로 복원한 원본 벡터의 목적값과 현재 incumbent에서 차이가 모두 0이었다. 이 준비의 optimize 호출은 0회이며 P1의 minimize rho를 변경하지 않았다.

P1이 수용된 경우에만 v42_integrated.certificate.make의 원본 provenance·물리·matrix·전역 gap gate를 통과한 뒤 movement energy → movement count 순서로 실행한다. P1 lock은 v42_two.contract.P1_EPS=1e-7, 후속 component lock은 COMPONENT_EPS=1e-8을 그대로 사용한다. P2의 bound는 P1의 전역 rho LB로 수용하지 않는다.
