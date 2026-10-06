현재 PR160의 4-MESS/96-slot scientific authority를 보존한 exact node-activity/continuous-flow M1을 재구성하고 정적 고정점 압축을 적용했습니다. 최종 C2는 654,348행 / 306,040열 / binary 9,322개 / nnz 5,584,200개입니다. 원본 대비 binary 95.5254%, C0 대비 nnz 35.5539% 감소했습니다.

C0와 C1은 같은 300초 arm wall budget에서 root를 완료하지 못했고 C2만 root LP를 207.78초에 완료해 SUPER_COMPACT_EXACT_SELECTED로 동결했습니다. valid gap은 약 15.0436%이며 0.5% 도달이나 root 이후 B&B 진척은 주장하지 않습니다.

검증: PR160 삭제 인증 190,280개 compact LP replay; C1 전체 704,775행 및 19,741개 역복원 검증; 1,536개 물리 fixture 할당; 경로 전수/분수/adversarial 검사; 물리값 보정 없는 start residual 1.3828e-9. 모든 arm은 300초 이하, 207개 native parameter가 LogFile을 제외하고 동일합니다.

실행 source: 4c491cbb4427776d0ac095ef563c3908422522f8. Evidence commit: 2b2fcef1. 34항목 한국어 최종 보고서와 SHA256 manifest, 선택된 C2 freeze를 포함합니다. Tournament는 설계만 작성했으며 추가 heavy solve는 실행하지 않았습니다.
