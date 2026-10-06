# P1/P2 interface contract

Frozen authority: `v42_two/contract.py`, `docs/v42_single_worker_single_thread_a1_m1/M1_OBJECTIVE_CONTRACT.json`, and `docs/v42_final_two_objective_contract/P2_MIN_INTERVENTION_SPEC.md`. These files are not changed.

P1 minimizes max_line_loading (`rho`). `P1Acceptance` requires a finite consistent global LB/UB interval, a validated original integer incumbent, complete open-node coverage, explicit scientific scope SHA and gap <=0.005. A root D-W LP upper bound is not an original integer UB; an incomplete restricted-master objective is not the global LB. All-zero UB uses the requested small-positive gap denominator.

Only a passing P1 receipt can call `call_p2`. Ordered names come directly from unchanged `mess_groups`: movement_energy, then movement_count. P1 locks use accepted UB + existing `P1_EPS=1e-7`; movement energy locks use accepted energy + existing `COMPONENT_EPS=1e-8`. There is no weighted combination or reserve/rank/tie objective. Existing reserve rows and report-only semantics remain unchanged.

The injected `solve_layer(component, p1_cap, energy_cap, scope_sha)` returns a receipt containing validated original physical solution, globally accepted layer objective and matching scientific scope SHA. Production implementations must supply their own complete branch tree, exact layer certificates and independent original-row validator; the boolean fields are a callback contract, not a certificate inferred from solver status. The framework rejects unaccepted P1, nonfinite/negative energy, invalid movement count and unvalidated or mismatched layer receipts.

The four-entry exhaustive `BAP_P1_P2_FIXTURE.json` verifies energy-before-count and preservation of P1. It selects energy 0.2, then count 2, despite a worse-P1 alternative with zero movement. This is interface-only arithmetic; production P2 calls are zero.
