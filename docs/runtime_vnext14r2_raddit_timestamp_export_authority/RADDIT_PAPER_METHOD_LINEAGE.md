# 관련 논문 방법과 접근 한계

관련 논문은 Menear 외, **Energy-Aware HPC Scheduling with LLM-Based Power Prediction**, SC25 Workshops, 2025, pp.1997–2006, [DOI](https://doi.org/10.1145/3731599.3767563)다. [NLR 공식 기록](https://research-hub.nlr.gov/en/publications/energy-aware-hpc-scheduling-with-llm-based-power-prediction/) 및 [학회 abstract](https://sc25.supercomputing.org/proceedings/workshops/workshop_pages/ws_ss107.html)에서 식별했다. Crossref 등록 metadata도 일치한다.

| 방법 항목 | 확보한 근거 | 이번 판단 |
|---|---|---|
| Job trace 출처 | RADDiT 공식 README는 Kestrel trace 기반 simulation을 설명 | 원본 Slurm row까지 연결하는 manifest는 아님 |
| Semantic input | 공식 abstract는 enriched job script embedding을 설명. 실제 8개 필드는 공개 prep source에서 확인 | 공개 문자열 입력의 직접 outcome-free 성격 확인 |
| CPU/GPU 제한 | README의 CPU-exclusive power 결과 설명 | 배포 전체 embedding이 동일 CPU-only filter를 썼다는 근거로 전용하지 않음 |
| Power availability filter | 확보한 abstract/metadata는 exact filter 미기재 | 미입증. historic의 power 결측은 0이나 원본 수집 filter까지 의미하지 않음 |
| Embedding 생성 | source의 Linq 모델·pooling·normalization 확인 | 배포 encrypted/int8 export 단계까지 연결되지 않음 |
| Timestamp 처리 | 확보한 공식 abstract/metadata에 stripping 규칙 없음 | 미입증 |
| Prediction/runtime 평가 기간·모집단 | full methods를 회수하지 못함 | 이번 배포 1,780,972행의 정의로 추정하지 않음 |
| Supplement/export manifest | 확보한 공개 기록에서 회수하지 못함 | 존재하지 않는다는 증명은 아님 |

ACM full text/PDF와 NLR publication-number 기반 PDF 후보 경로의 회수가 실패했고 OSTI API는 timeout이었다. 따라서 full paper의 모든 방법·부록을 검사했다고 주장하지 않는다. 제3자 요약에서 필터·기간·시간 의미를 보충하지 않았다. 별개의 PEARC25 power-classification 논문 모집단을 이 배포 데이터와 동일시하지 않았다. 보고된 모델 성능은 변환, 필터 또는 다음 모델 선택에 사용하지 않았다.
