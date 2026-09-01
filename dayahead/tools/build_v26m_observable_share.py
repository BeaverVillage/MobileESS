"""Build pre-April V26M observable-state share artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from dayahead.ml.c_mass_tpp.data import conflict_ids, load_h100_source, semantic_flexible_targets
from dayahead.ml.safe_flex.contracts import TRAIN_END_INCLUSIVE, TRAIN_START
from dayahead.ml.safe_flex.observable_share import observable_share_by_day, summarize_shares


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v26m_safe_flex"


def main() -> None:
    raw, provenance = load_h100_source(min_month=202407, max_month=202503)
    jobs = semantic_flexible_targets(raw, "2024-07-01", "2025-04-01", conflict_ids())
    by_day = observable_share_by_day(jobs, TRAIN_START, TRAIN_END_INCLUSIVE)
    by_day.to_csv(OUT / "V26M_OBSERVABLE_STATE_SHARE_BY_DAY.csv", index=False)
    summary = summarize_shares(by_day)
    summary.update(
        {
            "artifact_id": "V26M_OBSERVABLE_STATE_SHARE_AUDIT_V1",
            "authority": "POST_HOC_LABEL_AUDIT_NOT_ONLINE_FEATURES",
            "service_boundary": "REALIZED_D_DAY_FLEXIBLE_SERVICE_OVERLAP_GPU_H",
            "K": "submit <= D-1 18:00 AEST",
            "G": "D-1 18:00 < submit < D-day 00:00 AEST",
            "N": "D-day 00:00 <= submit < D-day 24:00 AEST",
            "K_primary_policy": "PENDING=SCHEDULABLE_KNOWN_WORK; RUNNING=LOCKED_RESIDUAL",
            "future_event_values_used_as_online_features": 0,
            "actual_events_used_for_post_hoc_labels_only": True,
            "semantic_flexible_jobs_in_label_pool": int(len(jobs)),
            "source_authority": provenance,
        }
    )
    (OUT / "V26M_OBSERVABLE_STATE_SHARE_AUDIT.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary["shares"], indent=2))


if __name__ == "__main__":
    main()

