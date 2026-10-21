# V2_add

독립 IEEE8500 Balanced / AIDC12 / STA12 / MESS8 확장실험 준비.

- [현재 한국어 검토](FINAL_V2_ADD_REVIEW_KO.md)
- [실험 식별](V2_ADD_EXPERIMENT_IDENTITY.json)
- [공식 계통 감사](IEEE8500_BALANCED_SOURCE_AUDIT.md)
- [Scale 사전등록](BACKGROUND_SCALE_PREREGISTRATION.json)
- [실행 Gate](FINAL_GO_NO_GO.json)

재현: 별도 Python 환경에서 `python -B -m v2_add_preflight.audit`.
필요 라이브러리: numpy, psutil, opendssdirect.py, matplotlib(figures).
외부 권위 저장소 경로와 runtime은 CLI 인수로 지정할 수 있다.
입력 authority 파일이 없거나 SHA가 다르면 PASS를 선언하지 않는다.
이 진입점은 inventory와 입력 산술까지만 실행하며 B0/Native를 호출하지 않는다.
