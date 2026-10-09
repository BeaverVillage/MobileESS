# 원 소스 Reactor 경로 메타데이터 수정과 선정 pin 보존

원 `Reactor.HVMV_Sub_HSB`는 SourceBus와 HV 변압기 입력을 잇지만 기존 inventory의 line/transformer 목록에는 없었다. 과거 함수가 inventory의 reactor 목록만 가정하면 SourceBus 이외의 경로가 비어 선로–PCC 교차가 모두 False가 되었다. 실제 AC 회로·전류·전압 계산에는 원 Reactor가 이미 포함돼 있어 이 문제는 경로 교차 메타데이터에 한정된다.

원 Master의 활성 Redirect를 정적으로 읽고 원 line/transformer inventory 및 활성 source Reactor를 포함해 전 4,876개 원 bus 경로를 재구성했다. 주석 처리된 Generators 파일의 reactor를 활성 회로에 추가하지 않았다. root SENSITIVITY_RESULTS, v2 sensitivity 4슬롯과 witness_response, v3 MV aggregate/4슬롯의 총 11개 CSV에서 해당 경로 True/False만 수정했다. 모든 다른 CSV 셀의 **원 문자열 SHA**, 관련 AC NPZ·요약·검증 파일 SHA가 같다. AC·Native·전체 모형 실행은 0회다. `PATH_METADATA_CORRECTION.json`에 변경 전후 SHA·행/셀 수와 소스 정적 검증을 기록했다.

선정 당시 `SCORE_INPUT_SHA256.json`에 동결한 root receipt SHA **95b97778897e7c40bae779f64d7c8420a830d42f00d03c0223c9f773eecdc085**는 그대로 유지한다. 선정 mapping·점수 CSV·방법·사전 등록·결과를 재작성하거나 재선정하지 않았다. 수정 전 11개 CSV는 손실 없는 gzip으로, 수정 전 4개 JSON 영수증은 원 바이트로 `path_metadata_history/pre_correction_20261009/`에 보존했다. 모든 역사 파일을 복원해 수정 전에 기록한 **SHA와 byte count가 정확히 같은지** 확인했다. 현재 root receipt에는 원 경로 수정 이력과 갱신된 leaf SHA만 붙인다.

`PATH_METADATA_FROZEN_PIN_CHAIN.json`이 원 선정 pin→원 바이트 archive→제한된 현재 topology amendment를 연결한다. 기존 `score_selection_audit.py`는 현재 receipt가 원 pin과 다르면 이 체인을 확인하도록 강화했다. archive 원 SHA, 모든 경로 값의 원 static graph 일치, 모든 비메타데이터 셀 불변, 현재 receipt의 허용된 두 amendment 필드와 CSV leaf SHA 이외의 변경 금지, 원 mapping/score/method/prereg SHA를 검증한다. 임의의 receipt 변경을 허용하거나 현재값으로 선정 pin을 다시 동결하지 않는다.

실행 결과 `PASS_EXACT_ORIGINAL_SELECTION_PIN_AND_CURRENT_TOPOLOGY_AMENDMENT`, 선택된 STA 48개 행동의 root score 재계산 PASS를 확인했다. 독립 전수 score 검토도 현재 MV SHA로 다시 수행해 PASS였다. 원 그래프 회귀 테스트 2개는 전체 4,876개 bus의 정상 경로와 source Reactor를 빼면 SourceBus만 남는 오류를 확인한다. l3234149 경로는 37개 edge, sx2748781a 경로는 127개 edge다.

재검증: `python -B -m ieee8500_v42.score_selection_audit --root .`, `python -B -m ieee8500_v42.review_joint_scores`, `python -B -m unittest tests.test_ieee8500_v42_path_metadata -v`. 어떤 명령도 AC/Native를 새로 실행하지 않는다. 역사 before-SHA를 덮어쓰지 않도록 실제 수정 프로그램은 이미 correction 기록이 있으면 재수정을 거부한다.
