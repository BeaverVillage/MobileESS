# Causal completed-history neighbors

{
  "pool": "TRAIN only, including TRAIN queries with strict end_i<submit_j; no VALID outcome may enter features",
  "retrieval": "Union of latest16 completed matches per each10 metadata fields and latest64 global completed TRAIN jobs; deduplicate",
  "ranking": "8 identity equality scores + 2 software token Jaccards + exp(-mean absolute TRAIN-IQR-normalized log-resource distance), divided by11; deterministic pool-row tie break",
  "search_claim": "Bounded approximate global retrieval; exact ranking within candidate union; no claim of exhaustive global nearest neighbors",
  "k": [
    16,
    64
  ],
  "statistics": [
    "Q50",
    "Q75",
    "Q90",
    "mean_log_runtime",
    "long4h_fraction",
    "long12h_fraction",
    "support_count",
    "nearest_similarity",
    "mean_similarity"
  ],
  "empty_pool": "support0; other values missing, not fake zero outcomes"
}

All target statistics use TRAIN-only candidates satisfying strict completion before submission. Category vocabularies and resource scaling are fitted on TRAIN without labels. Unknown categories cannot retrieve same-ID candidates. Exact outcome keys are rejected by the predictor boundary. Row-level selected neighbor IDs and completion-margin audits remain local and SHA-bound.

Implementation boundary: stack Jaccard is tabulated over TRAIN-observed bundle
categories. An unseen bundle receives zero stack similarity even when some of
its individual tokens were observed. The D2 predictor still retains those known
individual tokens through its multi-hot features. This limits the neighbor
retrieval/ranking representation and does not establish that exhaustive global
token-set neighbors or a separately registered rolling-history model lack value.
