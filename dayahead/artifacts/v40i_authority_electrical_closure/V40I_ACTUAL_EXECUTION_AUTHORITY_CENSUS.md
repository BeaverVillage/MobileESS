# V40I Actual authority census

총 14,697개 파일, typed UID 후보 1,366개, 읽기 오류 0개를 조사했다.

Raw 29개 Parquet member에서 blocked UID 2,543개를 모두 확인했으며, frozen observation의 시간·GPU와 일치한다.
Raw nodelist는 실제 물리 노드 정보다. observation adapter에서 누락되지만 원본으로 복구 가능하다(Case 1).
반면 현재 합성 AIDC 12개에 대한 counterfactual 실행 배치·구간 권위는 raw schema에 없다(Case 2). nodelist 복원만으로 해결되지 않는다.
동일 day/case/UID의 V40E 과거 ledger에서 pre-day RUNNING 44개에 대한 job/rack 기록 88개를 추가 확인했다. 생산자 Planning freeze까지 연결했으며 모두 경계 전에 완료된다. 이 기록의 site를 현재 Actual 권위로 승격하지 않았다. 대기 작업의 active interval 전체를 증명하는 기록은 없었다.

| 단계 | source | 확인된 lineage |
|---|---|---|
| raw_observations | C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터\NLR HPC Kestrel Jobs Data\esif.hpc.kestrel.job-anon.zip | Raw Kestrel has actual timestamps and physical node lists, no synthetic AIDC identity or counterfactual allocation history. |
| observation_parser | C:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt\dayahead\tools\audit_v40d_actual_replay.py | workload_audit selects id/job_id/start/end/submit/gpus/state/source_member and omits raw nodelist. |
| causal_materializer | C:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt\dayahead\v37\aidc_materializer.py | STATE_COLUMNS selects D1-visible causal fields; no node-to-synthetic-AIDC execution mapping. |
| spatial_projection | C:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt\dayahead\v39a\spatial.py | production_activity clips scheduled intervals to [24,120); pre-day-only pending jobs do not enter spatial assignment. |
| synthetic_initial_state | C:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt\dayahead\v39e\initial_state.py | Synthetic RUNNING snapshot and RW active jobs; a planning assignment is not Actual authority. |
| case_loader | C:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt\dayahead\v40d_actual\inputs.py | frozen_jobs retains full temporal UID universe, looks up planning AIDC_assignments; missing placement becomes UNASSIGNED. B0/B2 share B0, B1 uses B1, B3 uses final A1. |
| actual_runtime | C:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt\dayahead\v40d_actual\job_replay.py | RUNNING continues at issue; PENDING uses frozen ready or capacity delay. Observed end-minus-start supplies duration only. |
| canonical_actual_segments | C:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt\dayahead\v40g_segments\actual.py | Splits fixed migration source/destination, preserves no-compute gaps, uses observed residual service. It cannot invent missing original site. |
| protected_actual_gate | C:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt\dayahead\v40h\actual.py | Rejects UNASSIGNED pre-horizon jobs before physical replay. |
| V40I_timing_site_classifier | C:\codex_mobileess_workspace\MobileESS_v40a_bounded_iterative_coopt\dayahead\v40i\authority.py | Timing, actual AIDC site and active-interval segment evidence checked separately; planning fallback prohibited. |
