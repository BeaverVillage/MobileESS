# V35R1 Apr-01--20 Forensic Review

Primary classification: `V35R1_MULTIPLE_DEFECTS_REPAIRED`

Authority scope: 2025-04-01 through 2025-04-20 (Apr-21 excluded by user override).
Canonical matched case-days: 80
Maximum algebraic closure residual: 0
B3 lineage valid days: 20/20
Storage reloadable case-days: 80/80
Correction leakage count: 0
Scientific optimization reruns: 0

The apparent comparison mismatch was a decimal-place transcription error in B1-B0, not a raw authority or join failure.
A separate report-only defect divided 760 kWh by 1000 kWh for Actual MESS SoC; it was repaired to the frozen 1200 kWh capacity without changing Planning, Fresh, AIDC, or MESS scientific arrays.
AIDC coupling is live but its exact B1-B0 effect is small because line.sw2 phase A remains the common upstream binding bottleneck.
MESS uses stationary nonzero P/Q on every day and no movement; Planning incumbent effects are large, while Fresh effects are reported separately and global optimality is not claimed.
