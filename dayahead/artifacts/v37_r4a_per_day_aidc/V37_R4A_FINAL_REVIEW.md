# V37-R4A per-day AIDC final review

- Defect: May가 Apr-01 scheduler/power template을 재사용하던 구현 결함을 제거했다.
- Science: CENTER, 547.7239090195797 W/GPU, 624 GPU, runtime authority, C1, 위치/가중치는 변경하지 않았다.
- Apr-01 exact regression: PASS.
- May causal AIDC preflight: 31/31 PASS.
- May eligible cohort range: 101–6309 jobs.
- May temporal cohort range: 0–5905 jobs.
- May temporal requested GPU-h range: 0.0–460340.00000000006.
- Future runtime/grid/PV/optimization-result reads: 0.
- Old Apr-template May results: APR01_TEMPLATE_MAY_RESULT_SUPERSEDED (preserved, not final-reusable).
- Kestrel D-1 causal snapshot: 31/31 PASS; May-01 includes April-origin RUNNING and PENDING jobs.
- Actual traffic authority (288×509×3, 24 services, Safe ETA, candidate SHA): 31/31 PASS.
- D1 electrical authority / restoration loader / true production loader: each 31/31 PASS.
- Final implementation fingerprint: `3bdd2ce8b9e5f37799528cfb6872fe2cc3d78c86acdb4fd4aa9895d2ea5bdf34`.
- Focused and namespace regression tests: 78 PASS, 0 FAIL.
- MAY_CAMPAIGN_LAUNCH_READY=YES; MAY_STARTED=NO.
