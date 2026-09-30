# V42 exact Dantzig–Wolfe LP prototype

EXACT_DECOMPOSITION_VALIDATED_MAY_LP_NONCONVERGED

Exact local DAG pricing and full-column LP/bounded integer equivalence are gated before a single externally supervised 600 s full May canary. See [FINAL_REVIEW_KO.md](FINAL_REVIEW_KO.md), [MAY_DW_FINAL_LP.json](MAY_DW_FINAL_LP.json) and [MODEL_SIZE_COMPARISON.json](MODEL_SIZE_COMPARISON.json). All 385 available PR99 baseline files retain their original bytes. No Branch-and-Price or pipeline advancement.

Commands: `python -m v42_dw.audits`; `python -m pytest -q`; one-shot `python -m v42_dw.execute`; `python -m v42_dw.report`. Original execution plus IO-only restoration consumed a cumulative 599.735 s; see IO_REPAIR_RECEIPT.json. Preregistration is one-shot and may not be overwritten. Local source/log/column evidence is hash-sealed by the manifests.
