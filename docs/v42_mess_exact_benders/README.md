# Exact joint MESS Benders validation

Read FINAL_VERDICT.json and FINAL_REVIEW_KO.md first. Canonicalization and both cut derivations were committed before cut code. All original finite bounds and both equality directions remain explicit. Exact rational bound-compensated certificates are weaker, globally valid cuts on the stored linear model; no uncertified numerical ray is accepted.

`python -m v42_benders.fixtures` reproduces the bounded census and comparison. `python -m v42_benders.audit` performs real-model structural/matrix/warm-start audits without optimization. `python -m v42_benders.runner` is a once-only, preregistered B3 diagnostic guarded by a local execution marker. Do not rerun it or downstream production without new authorization/preregistration. `v42_benders.stage.solve_mess_stage_exact_benders` uses explicit anchor/state/authority and the same engine for M1 and M2. `v42_benders.production` enforces sequential registered gates and never runs A2/M2.

Cut payloads support independent fixture replay. Raw B3 logs, execution source checkpoint, partition axes and original inherited model receipt preserve provenance. Status/timeouts and non-run gated artifacts are explicit. All inherited files remain unchanged.
