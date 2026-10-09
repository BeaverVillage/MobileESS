# 선정 저압 포트 유한 AC 끝점 독립 검토

저장된 12개 STA×96개 시점×8개 P/Q 명령 **9,216개 fixed 끝점**, 원384개 automatic 요약, 별도 focused automatic384개 실제 국부 읽기를 검토했다. 원 수치·좌표·정격·선정 결과를 바꾸거나 추가 AC/Native를 실행하지 않았다. fixed9,216개와 automatic384개의 **표본 국부 계통/하드웨어 전부 PASS**가 재현되며, 두 검사 모두 전체 계통 PASS는 **0개**다.

| 검사 | 최대 오차/결과 |
|---|---:|
| actual S/VLL 대 두 hot 전류 | 2.27e-08 A |
| 실제 P/Q 읽기 | 6.84e-09 |
| 두 hot 복소 전류 KCL | 0 A |
| 원 Triplex I/NormalAmps | 1.39e-16 |
| 실제−기준 hot 크기 변화 | 1.44e-14 A |
| 포트 요약 수치 재집계 | 0 |

원 Triplex의 모든 경로·양 단자·두 hot 축과 원 정격을 확인했다. 중성선은 원 Kron 축약의 추정값이고 독립 정격이 비어 있다. hot 크기와 추정 neutral 값의 삼각 부등식 및 원 기준/교란 대응을 검산했으나, 크기만으로 복소 neutral phasor나 독립 ampacity 통과를 증명하지 않는다.

원 transformer는 passive sign이다. **PRIMARY P<0가 전체 서비스 upstream 역송전**이고, 보통 부하로 전달되는 SECONDARY P<0를 역송전으로 잘못 세지 않았다. SECONDARY leg P>0는 그 개별 leg에서의 반대 방향 전력이다. 전체 primary 역송전을 보는 포트는 6개, 개별 secondary leg 역송전은 10개다. 원 보호 허용은 UNVERIFIED다.

5kW 방전 때 일부 hot 크기는 줄지만 STA03/04/06의 다른 hot는 증가할 수 있다. 이는 불균형 원 부하와 단일 240V balanced 주입의 크기 반응이며, hot 크기 증가만으로 실제 분기 phasor/전력 방향을 단정할 수 없다. 충전5kW hot 증가와 최대 original rho를 포트 요약에서 그대로 재집계했다.

점수에서 선택한 48개 bounded P/Q 행동도 원 command와 일치하고 실제 국부/하드웨어 PASS다. 초기6대 동시 진단은 routing/SoC/QoS dispatch가 아닌 known-only/순간 전기 반응이다. 단일 포트8명령 검사, 제한된 자동 제어 검사, 48행의 국부 성공을 continuous P/Q×자동탭 전체 영역이나 전체 A/M 정책의 증명으로 확장하지 않는다.

별도 automatic384개는 실제 P/Q 합산 오차 7.43e-09, 실제 S/VLL–hot 전류 오차 1.42e-14A, hot KCL 0A다. 원 CT current/권선 nameplate, 원 Triplex 양단 hot 최대 및 PCC 전압을 저장 열에서 독립 재판정했다. 모든 실제 국부 전압은 0.995773491–1.046206702pu, 최대 hot 24.279982A다.

automatic의384개 persisted settled state를 표준 JSON 규칙으로 별도 SHA256 재계산해 각 command 행과 대조했다. 원12개 regulator transformer의 모든 권선, 원10개 capacitor의 step 축, tap 범위/격자와 capacitor0/1 상태를 확인했다. 별도 재검사와 원384개 global archive의 모든 공통 수치·제어 탭은 그대로 일치한다. 원 initial reset은 코드와 행 선언으로 확인하지만, 초기 solve 전 상태 자체는 별도로 저장되지 않았다.

고정 끝점의 taps-caps 동일 필드는 producer가 True로 선언했다. 코드가 매 probe에서 원 settled state를 복원하고 controlmode off로 푸는 것은 확인했지만, archived fixed 끝점별 상태 checksum이 없어 그 선언을 별도 기록으로 재검산할 수는 없다. 원384 automatic global-only 파일은 그대로 보존했고, 별도 focused384개가 local PCC/hardware 및 final settled-state 증거를 보완한다. 이것도 전체 자동탭/P/Q 영역 인증으로 확대하지 않는다.

수치·입력 SHA와 모든 한계는 `INDEPENDENT_PORT_REVIEW.json`에 있다. 재현: `python -B -m ieee8500_v42.review_selected_port_ac`. 새 AC/Native 호출은 0회다.
