"""Preserve measured per-stage Native accounting for successful and failed runs."""
from pathlib import Path
import math
from .admission import read, record
from v42_b3_joint.contracts import require, require_sha
from v42_b3_joint.policy import native_limit

STAGES = ("A1", "M1", "A2", "M2")


def collect_native_accounting(pipeline, identity, previous_attempts=()):
    totals, counts, states, ledger_receipts, identity_receipts, details = {}, {}, {}, {}, {}, {}
    for stage in STAGES:
        try:
            candidates = []
            input_sha = None
            folders = [Path(attempt).resolve() / "PIPELINE" / stage for attempt in previous_attempts]
            folders.append(Path(pipeline).resolve() / stage)
            for folder in dict.fromkeys(folders):
                ledger = folder / "NATIVE_RUNTIME_LEDGER.json"
                seal = folder / "NATIVE_RUNTIME_LEDGER_IDENTITY.json"
                if not ledger.exists() and not seal.exists():
                    raw = next(folder.rglob("NATIVE_RESULT.json"), None) if folder.exists() else None
                    require(raw is None, "NATIVE_RESULT_WITHOUT_LEDGER_QUARANTINE")
                    continue
                require(ledger.is_file() and seal.is_file(), "PARTIAL_NATIVE_LEDGER_IDENTITY_QUARANTINE")
                document, metadata = read(ledger), read(seal)
                require(metadata["stage"] == stage and metadata["day"] == identity["day"] and
                        metadata["run_id"] == identity.get("scientific_run_id", identity["run_id"]) and metadata["native_limit_seconds"] == native_limit(stage) and
                        document["Native_ceiling_seconds"] == native_limit(stage) and
                        document["budget_basis"] == "MEASURED_NATIVE_RUNTIME_ONLY",
                        "STAGE_NATIVE_ACCOUNTING_IDENTITY_DRIFT")
                require_sha(metadata["source_sha"])
                if folder == Path(pipeline).resolve() / stage:
                    require(metadata["source_sha"] == identity["source_SHA"], "CURRENT_STAGE_SOURCE_ACCOUNTING_DRIFT")
                if input_sha is None:
                    input_sha = metadata["input_sha"]
                require(metadata["input_sha"] == input_sha, "PRIOR_STAGE_INPUT_ACCOUNTING_DRIFT")
                require(document.get("inflight") is None and not any(row.get("runtime_unavailable") for row in document["calls"]),
                        "UNKNOWN_NATIVE_RUNTIME_QUARANTINE")
                measured = document["measured_Native_Runtime"]
                require(type(measured) in (float, int) and math.isfinite(measured) and measured >= 0,
                        "MEASURED_NATIVE_RUNTIME_REQUIRED")
                values = [row["Native_Runtime"] for row in document["calls"]]
                require(all(type(value) in (float, int) and math.isfinite(value) and value >= 0 for value in values) and
                        all(row.get("entered_native") is True for row in document["calls"]) and
                        math.isclose(sum(values), measured, rel_tol=0, abs_tol=1e-9),
                        "STAGE_NATIVE_CALL_SUM_DRIFT")
                candidates.append((document["calls"], measured, record(ledger), record(seal)))
            if not candidates:
                states[stage], totals[stage], counts[stage] = "NOT_ENTERED", 0., 0
                details[stage] = {"reason": "NO_CURRENT_OR_PRIOR_STAGE_LEDGER_OR_NATIVE_RESULT_EXISTS"}
                continue
            # The latest attempt may fail before creating this stage. Its
            # earlier measured prefix still belongs to the date/stage budget.
            longest = max(enumerate(candidates), key=lambda item: (len(item[1][0]), item[0]))[1]
            calls, measured, ledger_receipts[stage], identity_receipts[stage] = longest
            require(all(calls[:len(candidate[0])] == candidate[0] for candidate in candidates),
                    "DISJOINT_NATIVE_ATTEMPTS_REQUIRE_EXPLICIT_ACCOUNTING")
            states[stage], totals[stage], counts[stage] = "MEASURED", measured, len(calls)
            details[stage] = {"reason": "PERSISTED_MEASURED_NATIVE_RUNTIME", "ledger": ledger_receipts[stage],
                              "identity": identity_receipts[stage],
                              "all_preserved_ledger_receipts": [candidate[2] for candidate in candidates]}
        except Exception as error:
            states[stage], totals[stage], counts[stage] = "UNKNOWN", None, None
            details[stage] = {"reason": str(error)}
    known = all(state != "UNKNOWN" for state in states.values())
    total = sum(totals.values()) if known else None
    return {"stage_native_runtime": totals, "stage_native_calls": counts, "stage_native_accounting": states,
            "stage_native_ledger_receipts": ledger_receipts, "stage_native_ledger_identity_receipts": identity_receipts,
            "native_accounting": {"stages": details, "native_budget_seconds_by_stage": {stage: native_limit(stage) for stage in STAGES}},
            "native_runtime_state": "KNOWN" if known else "UNKNOWN", "Native_Runtime": total,
            "native_seconds": total, "Native_calls": sum(counts.values()) if known else None}
