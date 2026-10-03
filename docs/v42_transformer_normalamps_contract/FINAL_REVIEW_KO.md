# Transformer NormalAmps contract 변경

PR130 exact BASE `e0cdb0d8037bfe17b76e1eb95367bf93b3a0d255`. transformer 44개 / phase 120개 모두 source-backed NormalAmps 유효. Planning/Actual compiled 값 및 SHA `0cffff2af474221a7a5693f3c2b7a83026bd1522de2d3f66032c1757b9735d51` 동일.

reg1a current 한계는 693.930612006762 A(5000/(√3×4.16) nameplate 역산)에서 763.323673207438 A(compiled NormAmps)로 변경. CTPrim=700 및 taps는 thermal 분모가 아니다. transformer kVA와 line ratings는 그대로다.

May 31일/2976 slots: transformer current old 12 cells/4 days → new 0 cells/0 days. new max current pu=0.957529931063456. voltage/line/kVA cells=0/0/0. MAY_B0_FULL_AC_SECURITY_PASS=True.

April 30일/2880 slots: transformer current 0 cells/0 days, new max current pu=0.7413957560882314. voltage/line/kVA cells=0/0/0.

기존 raw OpenDSS current/voltage/kVA/PQ/Planning evidence를 보존하고 raw current_A에서 old/new 분류를 독립 계산했다. 새 AC solve나 repair/tuning은 없다. Planning current-response만 정확한 분모 변환을 수행했고 비-current 및 line current 계수는 bit 동일하다.

기존 M1 current authority/certificate는 **SUPERSEDED**. UB=0.5912812634331275, LB=0.5722125039436496 및 gap을 새 모델에 재사용하지 않는다. 새 SHA identity gate에서 거부한다. 후속 M1 재계산 필요; M1 full solve NOT_RUN. B1/B2/B3/A2/M2 NOT_RUN. FINAL_MARGIN_ACCEPTED=false, PROBLEM13_FINAL_VALIDATED=false.

full pytest 1,498 passed(기존 RuntimeWarning 1개). 부모 파일 4,573개 중 명시적으로 허용한 코드 14개만 변경했고 나머지 4,559개는 byte 동일하다. exact BASE evidence 보존 및 git/index 검증은 TEST_RECEIPT.json/VERIFICATION.json/SHA256_MANIFEST.json에 기록한다.
