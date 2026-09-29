# Frozen grouped-ablation interpretation

The groups are feature blocks in CURRENT_STATE_FEATURE_CONTRACT.json, not
interventions on the real scheduler or causal effects of workload pressure.

* A removes the S1 arrival block and its dependent S4 interaction columns.
* B removes the S2 pending resource/age/matching-count block and its dependent
  S4 interaction columns.
* C removes the S3 running resource/age/matching-count block.
* D removes the S4 pending/running composition block (shares, entropy, HHI).
* E removes the four declared S4 job-by-state interaction columns.

Composition is a separate block. B/C therefore leave composition columns in
place when the anchor contains S4; they do not remove every possible source of
pending/running information. E leaves the original S1 same-QoS arrival counter,
which duplicates one of the declared S4 matching-count columns. These are the
preregistered block definitions; they are not changed after seeing results.

An absent block is NOT_APPLICABLE_GROUP_ABSENT, without fabricated metrics.
When a removal produces exactly a previously evaluated primary arm, the saved
booster is reused only after verifying identical columns, preprocessing and
TRAIN size; predictions are independently regenerated and checked for exact
equality. All ablations are diagnostic only and cannot promote a failed primary
candidate into a provider. Tree gain importance is descriptive association only.
