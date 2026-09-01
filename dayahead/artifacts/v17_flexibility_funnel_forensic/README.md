# Provenance — V17 AIDC Flexibility Funnel Forensic V1

이 디렉터리는 기존 V4R1 authority/reference/schedule/result를 읽기만 하여 생성한 forensic 산출물이다. 과학 solver, OpenDSS, ML 재학습을 호출하지 않았고 beta/PUE/PF/scale을 변경하거나 선택하지 않았다.

정의: 15분 slot 적분은 kW × 0.25 h, flexible IT는 whole-GPU service GPU-hour × Dataset312 Q50 kW/GPU, PCC는 IT × frozen PUE 1.30이다. shifted energy는 reference 대비 delta의 L1/2이며 positive/negative/absolute/net도 별도 기록한다. `92.0945%`와 facility flexible share는 분모가 다르다. 평가일은 2025-04-02, 03, 12, 13, 15, 22, 23이다.

`V17_AIDC_FLEXIBILITY_FUNNEL_FORENSIC_V1.json`의 `inputs`에 사용·검토한 모든 입력 경로와 SHA256이 기록되어 있다. CSV는 UTF-8 BOM이며 숫자 단위는 열 이름에 표시했다.
