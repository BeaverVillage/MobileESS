May current-V42의 GPU authority를 raw request에서 native input까지 복원하고, 날짜 독립 builder로 April 30일 Planning/Actual input inventory를 다시 생성합니다. May GPU는 raw `gpus_requested`를 상속하며 누락 GPU를 복구하는 추가 관계는 없습니다. 역사적 missing/invalid row 제외는 현재 no-drop contract와 충돌하므로 port하지 않습니다.

Known 29,350 및 post-issue Actual 82,323 observations를 모두 유지하고 current frozen V10 Q50/service와 GPU/UID를 PR121 evidence에 대조했습니다. 추가 GPU 복구 0, 미해결 25,632 observations / 16,574 jobs, complete input 0/30입니다. Common reference/B0/AC/calibration은 input gate에서 NOT_RUN이며 energy, voltage, margin/coverage는 미측정입니다. AIDC/workload/ML Runtime flags는 true, flex/MESS는 off, FINAL_MARGIN_ACCEPTED=false입니다.

May code/schema/provenance만 April construction에 사용합니다. 기존 regression의 sealed native matrix/solution fixture 조회는 holdout guard에 별도로 공개했으며 April 값/보정 donor가 아닙니다. May scientific rerun 및 B1/B2/B3/M1/A2/M2 production은 없습니다.

Validation: 기존 983 + 새 121 = 1,104 tests PASS; exact PR121 `c0783fadbbca282f2ce580c45fe82feaed71584c`의 2,730 files byte-preserved; staged/unstaged diff check 및 새 evidence SHA 검증. 변경은 새 package/test/docs namespaces에만 있습니다.
