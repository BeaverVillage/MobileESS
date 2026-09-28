# 연구 trace 변환 명세

`features8.py::engineer`가 정확한 구현이다. GPU/nodes/cores/memory 및 walltime을 수치화하고 비양수·비정수 count·비유한 값은 NaN과 별도 indicator로 표현한다. 0/누락 분모는 NaN이며 임의 물리값으로 대체하지 않는다. log1p walltime/GPU/nodes/cores/memory, GPU/node, cores/node, cores/GPU, memory/GPU, memory/node, GPU×walltime과 그 log1p를 평가한다. F0에는 walltime이나 그 곱이 없다.

메모리는 공개 문자열의 MiB 수치이며 total/per-node/per-CPU 원래 범위는 확정되지 않았다. memory 비율은 연구 trace 산술이라는 한계를 유지한다. GPU>4×nodes도 값을 자동 수정하지 않고 inconsistency flag를 추가한다. array index는 원본 ID lookup이 아닌 공개 구조 descriptor이며 null을 non-array 확정으로 간주하지 않는다.

범주 mapping은 TRAIN에서만 만든다. 지원하지 않는 값은 코드0 UNKNOWN이다. identity는 최소빈도20, cardinality≤5000, TRAIN 지원행≥80%, DEV/CAL 각 unseen≤25%일 때만 F2에 포함한다. 이름·스크립트 등을 역식별하지 않는다. job_type/python/reframe은 생성시점이 검증되지 않아 제외한다. submit clock과 모든 execution outcome은 입력에서 제외한다.

M3의 변환은 log((T+1)/(walltime+1))이며 역변환은 exp(pred)×(walltime+1)-1이다. 0초 runtime을 보존하는 단조변환이고 walltime을 실제 라벨로 바꾸지 않는다. M3 inference에 양수 walltime이 없으면 fail-closed한다.
