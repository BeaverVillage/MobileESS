# Runtime-vNext16 rich RADDiT information-value study

Base: PR #89, commit `c84588e02727eb5311ba25f6a3ed43ff229cfe07`.

Native information value, future submission reproducibility and Runtime safety are separate conclusions. Read FINAL_REVIEW_KO.md for all 50 requested questions and exact scope.

| Arm | Pooled Q90 | Min-fold | >4h | >12h | >24h | Pinball (s) | Nodeh 예약/실제 |
|---|---:|---:|---:|---:|---:|---:|---:|
| D0 | 84.74% | 82.02% | 63.69% | 34.75% | 16.19% | 3723.84 | 2.550 |
| D1 | 82.28% | 78.81% | 57.95% | 26.59% | 16.33% | 3461.57 | 2.038 |
| D2 | 83.71% | 80.23% | 60.53% | 25.32% | 15.88% | 3368.10 | 2.086 |
| D3 | 85.29% | 81.83% | 62.35% | 26.88% | 13.56% | 3417.55 | 2.143 |
| D4 | 86.04% | 80.57% | 59.95% | 25.43% | 12.31% | 3525.65 | 2.160 |
| IDENTITY_ONLY | 83.71% | 78.69% | 57.33% | 24.35% | 14.09% | 3453.64 | 2.063 |
| SOFTWARE_STACK | 85.87% | 82.68% | 70.77% | 43.50% | 18.59% | 3432.02 | 2.572 |
| NEG_SHUFFLE | 84.36% | 80.12% | 59.69% | 27.79% | 13.30% | 3482.96 | 2.330 |

Study order: source audits → corrected exact research-proxy crosswalk → preregistration SHA freeze → three native expanding folds D0–D4 and fixed information/control contrasts → matched-cohort public embedding diagnostic → triggered ablation → information freeze → gated Runtime/CC4 decision → verification.

Runtime: COMPLETED. The exact V13 R0 baseline remains unchanged. CC4 baseline remains T0/B0; selected=C0.

Reproduction requires the supplied original archive, public RADDiT files and existing SHA-bound V6–V15 local evidence in the exact recorded environment. Large matrices, selected-neighbor IDs, models, row predictions and logs are under ignored .local and bound by LOCAL_EVIDENCE_MANIFEST.json. A fresh BASE checkout is required by prepare16.py; it must not be rerun to overwrite a completed study. register16.py refuses registration after metrics. train_native16.py and embedding16.py check the frozen implementation hashes. Use collect_native16.py only after all folds finish, then authorized ablation/bridge stages. No validation-driven parameter tuning is performed.

Limitations: anonymized identity is not language semantics; unresolved exporter/timezone lineage; original initial mutable-request versions unproven; bounded candidate neighbor retrieval; uniquely mapped native rows do not overlap the existing GPU VALID folds (unmapped rows are not certified CPU-only); embedding TRAIN cap100000 with all4096 stored coordinates and no future-generation contract.
