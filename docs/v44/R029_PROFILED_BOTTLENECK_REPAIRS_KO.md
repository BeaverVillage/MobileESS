# r029: 관측된 병목과 오류 복구 통합

2026-10-18 사용자 요청에 따라 r028의 오류·P1 수정과 ±0.005 pu 조건부 A2 전압 정책을 유지하고, 실제 프로파일에 근거한 추가 성능 보정을 별도 revision에 봉인했다.

## 관측 근거

May07 B1 실행 프로세스 61092를 25초간 nonblocking 방식으로 샘플링했다. 유효한 메인 스레드 샘플 22.9초 중 완료 AC 컨텍스트의 `gc.collect()`를 포함한 정리 지점은 약 3.225초(14.1%)를 차지했다. 이는 짧은 관측 구간의 비율이며 전체 캠페인의 비율로 단정하지 않는다. 원래 원본은 독립 probe마다 전체 generation-2 heap을 스캔했다.

May02 B3 attempt012 조립 기록에는 35회 build에 6,542초, native block 캐시 miss 2,980회와 eviction 2,643회가 기록됐다. 캐시 크기는 기존 512 MiB 상한에 도달했다. 반면 이미 검증된 같은 입력의 블록을 더 보관할 여지가 있었다.

## 추가 수정

1. 조립·투영 캐시의 큰 직렬화 payload를 zlib level 1로 무손실 압축한다. 실제 전체 입력 바이트를 해시하는 기존 key와 512/32 MiB 상한은 유지한다. 압축된 값은 매 사용 시 복원해 독립 객체를 반환한다. Native solve 결과나 Raw point는 캐시하지 않으며 행·bounds·RHS·types·objective 검산은 그대로다.
2. Current AC의 완료 컨텍스트는 매 probe에서 generation 1을 수집하고, 매 8회 또는 미정리 retired context 16개 이상일 때 generation 2를 수집한다. 원본의 engine/utility 소유권·callback manager 검산 본문을 유지한다. 실제 컨텍스트는 원본대로 ClearAll 후 retire하며 CFFI의 기존 disposer만 사용한다. case 종료 시 원본 full cleanup을 수행한다. 독립 Fresh는 원래 수집 경로를 유지한다.
3. B1에서도 B3에서 이미 검증한 class schema를 사용해 불변 property 이름을 재사용한다. 매번 live class와 property count를 확인하고, 모든 실제 property 값은 계속 live로 읽는다. 원본 소스의 내용 해시는 계속 재계산한다.

## 실측 검증

실제 May02 초기 상태에서 native block 3개를 Native optimization 없이 구축해 압축·복원했다. raw 369,906 / 169,799 / 400,802 bytes가 각각 23,279 / 7,119 / 15,387 bytes로 줄었다. 복원한 직렬화 전체 바이트와 snapshot fingerprint가 원본과 일치했다. 이는 샘플 payload 크기 약 94~96% 감소이며 전체 캠페인 가속 배율을 의미하지 않는다.

원래 heap 스캔 비용을 재현하는 일반 Python 그래프를 유지한 채 독립 OpenDSS 컨텍스트 24개씩 정리했다. 기존 방식은 3.366초, 변경 방식은 0.613초였다. 변경 방식은 full GC 3회·young GC 21회였고 마지막 pending은 0이었다. engine, utility, callback manager 등록부는 모두 시험 전 상태와 같았으며 원본 소유권 검사를 생략하지 않았다. 이 약 5.5배 수치는 컨텍스트 정리 시험에 한정된다.

전체 회귀 **309개 PASS**. 실제 May06 693,549행·22,616열 Planning의 Native0 재사용 검산도 다시 통과했다. source 50개 SHA는 `fa216dc432350d000b1e50b652e7dc41bfd6e2c29d6617455c4b64d619642da0`이다.

## 오류 수정과 적용 상태

r028의 원본 Barrier P1/Pricing 정책 복구, 검산한 가능해 전달, 동일 행렬 basis 재사용, 검증된 개선 블록 전체 activation을 승계한다. May03~05 B1의 keyword-only 기본값 유실 복구, May06의 기존 Planning P1/정수 결정/Native12.264초 보존과 연속해 복원 경로도 유지한다. A Native5400초, Phase I LP+Pricing Native1500초, Full Pricing·독립 Gap·원본 물리 검증은 유지한다.

현재 실행 중인 May07 B1 Actual/Fresh는 수정하거나 중단하지 않는다. `MobileESS_V44_Campaign004_Recovery_R029`가 자연 종료 경계를 기다려 새 retry release와 coordinator를 연결한다. 미실행 r028 waiter는 새 허가에 따라 자연 종료시키고 task를 비활성화했다. 과거 소스·PASS·실패·Raw·Native 원장을 보존한다.

**실제 재실행의 전체 속도 개선과 최종 PASS는 아직 측정 전이다.** 개별 기능 시험 통과와 실제 캠페인 성공을 구분한다.
