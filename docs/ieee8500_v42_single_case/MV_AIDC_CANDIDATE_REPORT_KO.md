# 새 공동 재선정을 위한 MV AIDC 전기적 후보

사용자가 종전 v3 AIDC 12곳의 고정을 해제했으므로, AIDC 12곳과 STA 12곳의 새 공동 재선정에 사용할 전기적 host 후보를 원 계통에서 다시 검증했다. **원 638개 전기적 후보와 원 root-distance guard 통과 606개를 동일하게 재구성했다.** 실제 서비스 포트 승인 또는 최종 배치가 완료된 것은 아니다.

새 모듈 `ieee8500_v42/mv_candidates.py`는 과거 launcher, selector, Native 모델, OpenDSS를 import하지 않는다. 저장된 실제 원 OpenDSS inventory와 원 topology audit만 읽으며, 새 AC solve와 Native 호출은 0회이다. 원 소스·기존 campaign·종전 배치 결과를 수정하지 않았다.

## 유지한 hard gate

원 v3의 전기적 host 조건을 유지했다. 원 nominal line-to-line 12.47 kV와 원 ±0.01247 kV 허용값, 정확히 node 1/2/3인 ABC, feeder head에서 연속 ABC 경로, 원 source/substation/regulator terminal 제외, source 연결성, 원 좌표 존재, 원 638개에서 root impedance 하위 5% 제외가 모두 필요하다. `r>=q05`인 equality는 통과한다.

각 버스에 ABC node가 있다는 이유만으로 경로를 인증하지 않는다. `ORIGINAL_FEEDER_INVENTORY.json`의 실제 conductor node_order로 동일한 버스쌍 사이의 `1→1`, `2→2`, `3→3`을 확인한다. 별도 1상 line과 원 regulator bank는 같은 버스쌍에서만 합친다. 서로 바뀐 phase, 끊긴 phase, 원 audit에서 open인 line은 ABC 경로를 만들지 못한다. 전압경계를 건너는 일반 배전변압기를 ABC 동일경로로 취급하지 않는다.

원 source Reactor를 포함한 전체 연결성도 확인한다. 원 placement 거리의 시작점은 계속 `_hvmv_sub_lsb`이고, `sourcebus`의 reactor·변전소 변압기·feeder regulator는 실제 source 연결성의 앞 경로이다. 이 구분으로 원 static placement distance의 의미를 보존한다.

## 원 거리와 guard의 재계산

원 matrix 기반 corridor weight는 각 원 line의 `hypot(R_ii,X_ii)*native_DSS_length`를 ABC에 대해 평균한다. 원 regulator bank는 이 placement metric에서 0 Ω identity connector이다. 원래 이 정의는 정적 위치 선정 지표이며 실제 AC 등가 임피던스·고장전류·연결용량 인증이 아니다.

646개 ABC corridor와 647개 tree bus를 원 자료와 대조하고, 638개 host의 root 거리 차이가 모두 정확히 0.0 Ω임을 확인했다. 순서가 동결된 원 638개 거리의 linear q05는 1.3819547376654384 Ω이다. 원 guard와 같은 32개가 제외되고 같은 606개가 남았다. 임계값을 새 성능 결과에 맞춰 변경하지 않았다.

`MV_AIDC_CANDIDATES.csv`는 606개를 기록하고 `MV_AIDC_EXCLUDED_SOURCE_PROXIMITY.csv`는 제외된 32개를 기록한다. 버스·candidate ID·원 XY·phase·nominal kV·root 거리·guard ratio·경로 hop·원 lateral group을 제공한다. 단위가 알려진 line 구간 길이는 km로 환산해 합산하고, 원 `Line.hvmv_sub_connector`의 DSS Units=0은 unknown으로 보존한다. 따라서 경로의 전체 물리 km 길이를 인증했다고 표시하지 않는다.

## 최신 공동 재선정 범위와 과거 dispersion 조건

새 공동 재선정은 하나의 동결된 proper similarity와 24개 고유 PCC 버스·서비스 ID 및 전체 276쌍 방향 조건을 hard gate로 평가한다. 종전 고정 roster의 정확한 불가능성 증명은 `GEOMETRY_INDEPENDENT_REVIEW_KO.md`에 보존하고 새 후보 집합의 불가능성으로 확대하지 않는다.

원 AIDC electrical pair거리 0.9129072401559803 Ω 및 원 XY pair거리 2221.532547954318은 과거 dispersion design 기준이다. 최신 요청의 물리적 host 자격·source proximity·3상 조건과 구분하여 **새 공동 선택에서 감사와 점수에 보존**한다. 원 XY 단위가 unknown이므로 이를 물리적 접속 안전거리로 인증하지 않는다. API는 두 원 기준의 pass/fail도 반환하여 조용히 삭제하거나 물리적 한계를 완화했다고 주장하지 않는다. 과거 shape `E_coord≤0.20`, `E_pair≤0.20`, 이웃 보존≥0.50도 감사 metadata로 보존한다. 이 범위 결정은 공동 선택 전 새 preregistration에 기록한다.

## 실제 포트·derating에 대한 미완료 조건

606개의 `electrical_host_eligible=True`는 기존 버스에 새 AIDC를 연결할 전기적 후보 자격이다. 원 24곳 registry에 있는 service label은 과거 시나리오 mapping이며 실재 장비·PCC·접속 허가·보호·접근·시간의 증거가 아니다.

모든 row에서 `physical_port_qualified=False`, `port_derating_certified=False`이고 import/export kW 및 PCS kVA 허용값은 unset이다. 원 버스·line·transformer 정격이나 구간 거리를 임의의 접속용량으로 변환하지 않았다. 어떤 transformer나 port도 추가하지 않았다. 실제 AIDC 설비·충방전 포트·보호·연결방식·동시운전·접근 및 연결 소요시간 증거가 제공돼야 해당 위치의 물리적 승인과 derating을 정할 수 있다.

## API, provenance와 검증

`build_candidates()`는 `MVCandidateSet`을 반환한다. `.candidates`는 606개 row, `.excluded`는 32개 row이고 `.pair_metrics(bus_a,bus_b)`는 원 electrical tree거리, shared upstream path ratio, 원 XY 거리 및 과거 pair dispersion pass/fail을 반환한다. `.parent`, `.depth`, `.coordinates`는 원 tree·위치 정보를 제공한다. 최종 geometry 선택과 AC sensitivity는 별도 모듈에서 수행한다.

원 자료 사본은 새 `ieee8500_v42/data/mv_candidates/`에만 저장했다. 사본 생성 전에 원 FREEZE_MANIFEST와 GUARDED_SELECTION_FREEZE_MANIFEST에 기록된 hash를 검증했다. `SOURCE_MANIFEST.json`은 원 경로·SHA·freeze hash와 읽기만 한 원 compile/feature/selector source SHA를 기록한다. 후보 생성 때 매 사본 hash와 현재 원 feeder 32개 파일 hash를 다시 검증하고, 원/current 모든 line roster·bus terminal·phase·length·units·enabled를 대조한다. 차이가 나면 후보 생성 전에 중단한다.

6개 작은 검증은 실제 606/32 guard와 미승인 port, source input hash 변조 중단, conductor ABC 누락·교차·open 차단, unknown length unit 보존 및 pair metric 대칭을 확인한다. 테스트의 작은 connectivity fixture는 알고리즘 검사이며 실제 후보의 물리적 자격 증거로 사용하지 않는다. 실제 후보 자격은 원 source hash와 실제 원 inventory 대조에 근거한다.

재현: `python -B -m ieee8500_v42.mv_candidates`. 검증: `python -B -m unittest discover -s tests -p test_ieee8500_v42_mv_candidates.py -v`. 후보 감사 receipt는 `MV_AIDC_CANDIDATE_AUDIT.json`이다. 원본 초기 사본 생성만 `--capture-original` 인수로 별도 수행한다.
