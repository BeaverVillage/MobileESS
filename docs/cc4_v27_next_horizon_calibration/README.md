# CC4-v2.7 후속: 계산 백엔드와 리드 그룹 보정

현재 v2.7 완료·검증·최종 검토·해시 동결 후 시작한 별도 namespace다. 원 증거는 읽기 전용으로 유지한다. [최종 검토](NEXT_STAGE_FINAL_REVIEW_KO.md)에 결과와 제한을 정리했다.

대표 배치 벤치마크에서 CPU 4개 프로세스가 2.52배 빨랐고 비트 단위 예측 재현을 유지했다. GPU는 지원됐으나 느리고 예측 차이가 컸다. 모델 후보는 T2F0/T3F2의 M0/M1로 제한했고 DEV에서 M0를 유지했다. 새 보정 두 방법은 CAL에서 기존 슬롯 보정을 이기지 못했다. 선택을 바꾸기 위해 OOS나 May를 사용하지 않았다.

완료된 모델을 다시 학습할 이유가 없으므로 최종 두 후보의 정확한 일별 모델 기록546개를 검증·재사용했다. 평가 refit364개와21,840개 native 슬롯 예측을 보고하며 새 전체 기간 refit은0이다. 벤치마크 자체는 백엔드별40개 booster, 총120개 학습을 수행했고 장치 확인용 GPU1개를 별도로 실행했다. 미래에 필요한 새 학습에는 frozen CPU4/n_jobs1 backend를 사용한다.

재현은 기존 파일을 덮어쓰지 말고 새 sibling 폴더에 `.py`, 이 README, USER_ADDENDUM.txt와 git 설정만 복사해서 수행한다. 상위 폴더에는 원 `cc4_v27_target_feature_sharpness` 및 그 부모 원본 namespace가 있어야 한다. BENCHMARK_ENVIRONMENT.json의 Python/LightGBM 환경을 사용한다. GPU 결과와 시간은 장치·부하에 따라 달라질 수 있어 새 실행에서 새 backend 선택을 기록한다.

```powershell
python -X utf8 benchmark.py
python -X utf8 study.py register
python -X utf8 study.py a
python -X utf8 study.py b
python -X utf8 study.py c
python -X utf8 test_contract.py
python -X utf8 gpu_device_probe.py
python -X utf8 finalize.py review
python -X utf8 finalize.py seal
python -X utf8 finalize.py verify
```

실행 로그를 저장한다면 seal 전에 닫아야 한다. manifest는 자기 자신과 __pycache__를 제외한 파일을 해시한다. 원 v2.7 manifest도 다시 검증한다. 그룹 보정은 상관된 슬롯의 경험적 잔차 보정이며 엄밀한 교환가능성 기반 coverage 보장을 뜻하지 않는다. 원 슬롯 방법과 새 방법의 DEV/CAL 잔차 은행 차이도 보고서에 명시했다.
