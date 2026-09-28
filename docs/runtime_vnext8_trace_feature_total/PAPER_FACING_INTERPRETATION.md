# 논문용 문구 초안 — 본문은 수정하지 않음

“Runtime prediction was trained using anonymized job request descriptors contained in the Kestrel workload trace.”

“The public trace does not provide sufficient request-version provenance to verify that every archived descriptor exactly corresponds to the immutable initial submission value.”

The frozen Runtime-vNext8 trace-descriptor challenger reduced rounded reservations but failed calibration, long-job coverage, and queue utility criteria in the locked April evaluation. It was therefore not adopted as the V42 research runtime provider. These results describe a retrospective trace experiment and do not certify original scheduler inputs or production readiness.

baseline·challenger의 전체 결과와 부정적 gate를 함께 보고한다. 장기 undercoverage를 예약 절감이라는 장점만으로 대체하지 않는다. checkpoint subtraction 실패는 total-runtime 성능이 불충분한 상태의 관측이므로 별도 survival model의 필요성을 확정하지 않는다.
