"""Preserve measured stage Native costs across formal B3 repair attempts."""
import json
import math
from pathlib import Path

from v42_b3_joint.contracts import canonical, require
from v42_b3_joint.native_ledger import SourceStageLedger
from .admission import read, record, checked


def prior_prefix(context, attempts):
    documents, receipts = [], []
    for attempt in attempts:
        path = Path(attempt).resolve() / "PIPELINE" / context.request.stage / "NATIVE_RUNTIME_LEDGER.json"
        if not path.is_file():
            continue
        identity_path = path.with_name("NATIVE_RUNTIME_LEDGER_IDENTITY.json")
        identity = read(identity_path)
        require(identity.get("stage") == context.request.stage and
                identity.get("day") == context.request.authority.day and
                identity.get("input_sha") == context.request.authority.input_sha and
                identity.get("native_limit_seconds") == 5400,
                "B3_REPAIR_PRIOR_LEDGER_SCIENTIFIC_IDENTITY_DRIFT")
        document = read(path)
        require(document.get("inflight") is None and
                not any(row.get("runtime_unavailable") for row in document["calls"]),
                "B3_REPAIR_PRIOR_UNKNOWN_NATIVE_RUNTIME_QUARANTINE")
        measured = document["measured_Native_Runtime"]
        require(type(measured) in (int, float) and math.isfinite(measured) and measured >= 0 and
                math.isclose(sum(row["Native_Runtime"] for row in document["calls"]), measured, abs_tol=1e-9),
                "B3_REPAIR_PRIOR_NATIVE_RUNTIME_LEDGER_DRIFT")
        documents.append(document)
        receipts.extend((record(path), record(identity_path)))
    longest = max((doc["calls"] for doc in documents), key=len, default=[])
    require(all(doc["calls"] == longest[:len(doc["calls"])] for doc in documents),
            "B3_REPAIR_DISJOINT_NATIVE_ATTEMPTS_REQUIRE_EXPLICIT_ACCOUNTING")
    return json.loads(canonical(longest)), receipts


class CumulativeStageLedger(SourceStageLedger):
    def __init__(self, context, *, previous_attempts=(), progress=None):
        prior, receipts = prior_prefix(context, previous_attempts)
        carry_path = context.output / "PRIOR_STAGE_NATIVE_ACCOUNTING.json"
        was_existing = (context.output / "NATIVE_RUNTIME_LEDGER.json").exists()
        super().__init__(context, progress=progress)
        if was_existing:
            saved = read(carry_path)
            require(saved["prior_receipts"] == receipts and self.budget.calls[:len(prior)] == prior,
                    "B3_REPAIR_CARRYFORWARD_RESTART_DRIFT")
        else:
            self.budget.calls = prior
            self.budget.native_used = sum(row["Native_Runtime"] for row in prior)
            require(self.budget.native_used < 5400 or context.request.stage == "A1" and not prior,
                    "B3_REPAIR_STAGE_NATIVE_BUDGET_EXHAUSTED")
            self.budget.persist()
            carry_path.write_text(canonical({"prior_receipts": receipts,
                "prior_native_runtime": self.budget.native_used, "prior_native_calls": len(prior),
                "old_points_bounds_models_reused": False}) + "\n", encoding="utf-8")
        self.carry_path = carry_path
        self.carry = read(carry_path)
        # Original ledger validation checks every carried-forward native call's
        # effective limit and high-precision settings against the cumulative
        # runtime. Unknown/inflight costs block retries rather than become zero.
        self._verify_document(read(self.path))

    def receipt(self):
        receipt = super().receipt()
        carry = read(self.carry_path)
        require(carry == self.carry, "B3_NATIVE_PRIOR_ACCOUNTING_RECEIPT_DRIFT")
        for origin in carry["prior_receipts"]:
            checked(origin)
        return dict(receipt, prior_attempt_native_accounting=carry,
                    new_attempt_native_runtime=receipt["measured_native_runtime"] - carry["prior_native_runtime"])
