# Implementation corrections before method selection

The candidate families, split dates, metric priority, target coverage and support thresholds in pre-registration commit 570c653 are unchanged.

1. A regression found that pandas iteration over an empty column list did not create pooled keys. The implementation now explicitly emits one empty tuple per row. This repair precedes any calibration comparison result.
2. Review found that an early evaluator used the robust grid envelope duration for the calibration coverage gate. This could let R3 Q95 reserve conceal a Q90 calibration failure. Before any aggregate comparison or winner freeze was produced, the evaluator was stopped while waiting for C0 F2. The coverage gate now uses the native conditional Q90 bound. R0–R3 grid safety and conservatism remain separate. Previously computed F1 calibrators retain identical formulas and are deterministically regenerated. No candidate was added or removed.
3. Zero-duration jobs now contribute zero realized grid slots even at an off-grid timestamp.
4. Read audit events are additionally appended to a stage JSONL stream so interruption cannot lose completed read events. The earlier stopped evaluator was limited to V40J development files and had not opened any external data or shadow member. Its partial log is retained as EVALUATION_PRE_GATE_REPAIR.log.
5. Before aggregate results or selection were emitted, replay was corrected to preserve each historical job's actual-start phase within the 300-second grid. This retrospective anchor is used only for paired evaluation; the causal feature frame remains unchanged. Duration-only coverage and training are unchanged. The interrupted evaluation read log is retained and the same frozen models/calibrators are evaluated again. The final point support-stratum summary explicitly records its support threshold.
6. Amendment review confirmed Arrow stored timestamps at microsecond resolution. The epoch conversion now explicitly converts to nanoseconds before division by 1e9. Storage-unit invariance is regression-tested before the amendment commit and before selection.

These are implementation repairs to enforce the registered protocol, not parameter amendments. No shadow or May outcome was used.
