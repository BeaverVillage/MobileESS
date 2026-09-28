# 요청 버전·수집 방식 감사

공식 NLR 데이터 카드와 [dataset302](https://data.nlr.gov/submissions/302)는 주기적 sacct 수집→PostgreSQL load_slurm→DB trigger/batch 갱신 경로를 설명한다. 내부 SQL 함수는 공개되지 않았고 원 Slurm JSONB 및 job_step은 배포에서 빠졌다. 공개 아카이브의 버전 번호는 작업 요청의 버전 이력이 아니다. 로컬 scheduler authority 디렉터리의 slurmctld 자료는 parser 코드와 합성 테스트이며, Kestrel 제출 원본 로그가 아니다. 조사 범위 안에서 원본 authority는 발견되지 않았다는 결론이며, 비공개 로그의 부재를 주장하지 않는다.

| 정규화 피처 | 제출 시 의미 존재 | 이후 수정 가능성 | 아카이브 최초/최종 | 원본 이력 | 새 모델 사용 |
|---|---|---|---|---|---|
| requested_seconds | walltime 요청 | 문서상 가능 | 미확인 | 없음 | 제외 |
| num_gpus_req | GPU 요청 | GRES 변경 경로 존재 | 미확인 | 없음 | 제외 |
| num_nodes_req | node 요청 | 문서상 가능 | 미확인 | 없음 | 제외 |
| num_cores_req | CPU 요청 | 문서상 가능 | 미확인 | 없음 | 제외 |
| requested_memory_mib | memory 요청 | 이 조사에서 불변성 증명 못함 | 미확인 | 없음 | 제외 |
| qos | QoS | 문서상 가능 | 미확인 | 없음 | 제외 |
| partition | partition | 문서상 가능 | 미확인 | 없음 | 제외 |
| account | allocation account | 문서상 가능 | 미확인 | 없음 | 제외 |
| user | submitting user hash | 수정 관측 없음; 해시 변환·원본 매핑 권한 미확인 | 미확인 | 없음 | 제외 |

[SchedMD scontrol](https://slurm.schedmd.com/scontrol.html)의 수정 명령은 scheduler 기능의 근거이며 이 7개 필드가 실제 Kestrel 각 행에서 변경됐다는 증거는 아니다. [sacct](https://slurm.schedmd.com/sacct.html)는 재큐잉 시 Submit이 재설정될 수 있다고 명시한다. 따라서 hour/weekday도 초기 제출 시각이라는 증거 없이 쓰지 않는다. 종료시각은 인과적 피처가 아니라 사용자 지정 end<cutoff 라벨 성숙 조건에만 쓴다. 수집 지연은 확인되지 않았다.

최종 피처는 자체 생성 constant_bias=1 하나, 작업별 피처는 0개다. 해당 값의 가용성만 TRUE다. GPU 기반 표본 선택·가중치·strata와 W0/B0/대기열은 과거 archive descriptor를 쓰는 연구 평가이며 최초 요청값으로 인증하지 않는다. 이 조건에서 총 실행시간의 무조건부 분포를 학습할 수는 있으나 개별 작업을 구별할 근거가 없다.
