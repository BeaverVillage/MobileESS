# 외부 데이터센터 P/Q 감사

판정: **PLAUSIBLE_APPROXIMATION**. University of Córdoba 외부 참고자료이며 우리 AIDC의 직접 authority가 아니다.

원본 SHA-256 `b3c94fe028abff98734c38a828d2227e403c83922a42670672e693a8fecc4591`는 요구값과 일치하며 분석 전후 hash와 수정시각이 동일하다. Sheet1의 2–11089행, 11,088개 측정값을 읽기 전용으로 분석했다.

측정 범위는 2024-03-20 11:21:00.434000+00:00부터 2024-06-05 11:16:03.805000+00:00까지다. 총 PF 크기의 P5/P50/P95는 0.943389 / 0.950123 / 0.958954, 분산은 0.00002449다. 부하별·시간대별 분포와 상별 PF는 JSON에 저장했다.

총 P/Q는 상별 합, 총 S는 측정된 상별 apparent power 합을 사용했다. PF는 |P|/S다. 고조파 데이터에서 sqrt(P²+Q²)를 측정 S로 대체하지 않았다. 총합과 원본 total 열, PF와 원본 tpftotal(%)을 독립 대조했다.

[원자료 설명](https://github.com/joaquinjgz/Dataset_university_data_center)은 A/B/C 전류 센서 극성 반전을 명시한다. P 소비 방향만 분석값에서 정리했다. Q도 복소전력 부호 반전 대상이라는 가정에서는 leading으로 해석되나, 계측기 Q 부호 정의가 완전히 확인되지 않아 leading/lagging을 확정하지 않았다. 원본은 변경하지 않았다.

고정 PF=0.95의 외부 집계 근사 적합성과 상별·시간별 fidelity는 구분한다. 이번 revision은 AIDC PF=0.95와 Q control NO를 유지한다. 시변 외생 PF에는 우리 시설의 독립 P/Q 자료, 제어 Q에는 UPS/STATCOM의 P-Q capability authority가 필요하다.
