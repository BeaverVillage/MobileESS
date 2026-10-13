"""Frozen optimization-derived conditional controls; no online solver.

The anonymous A-stage envelope is a resource budget, not a set of future jobs.
Only observed submissions can query this table. Whole gangs and continuous
service are checked atomically against both the envelope and physical capacity.
"""
from copy import deepcopy
from collections import OrderedDict
import hashlib
import json
import math
from pathlib import Path
import threading


POLICY_VERSION = "OPTIMIZATION_DERIVED_CONDITIONAL_POLICY_V1"
BINDING_FIELDS = ("science_sha", "qos_sha", "case_sha", "aidc_anchor", "mess_anchor")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def _finite(value, reason, minimum=0):
    value = float(value)
    if not math.isfinite(value) or value < minimum:
        raise ValueError(reason)
    return value


def _receipt(value):
    return value.to_dict() if hasattr(value, "to_dict") else deepcopy(value)


class ReservationLedger:
    """Single shared atomic GPU/WAN ledger, including cross-midnight holds."""

    def __init__(self, capacities, wan_capacities=None, reservations=None, max_active_transfers=1):
        self.capacities = {"gpu:" + str(k): int(v) for k, v in capacities.items()}
        self.capacities.update({"wan:" + str(k): float(v)
                                for k, v in (wan_capacities or {}).items()})
        # Preserve the adopted original network-wide one-transfer contract,
        # independently of whether two jobs use distinct WAN path budgets.
        self.capacities["active:WAN"] = int(max_active_transfers)
        if any(v <= 0 for v in self.capacities.values()):
            raise ValueError("POSITIVE_RESOURCE_CAPACITY")
        self.reservations = deepcopy(reservations or {})
        self.audit = []
        self._lock = threading.RLock()

    def _fits(self, segments, *, exclude=None, envelope=None, scope="physical"):
        existing = [s for uid, r in self.reservations.items() if uid != exclude
                    and r["status"] != "RELEASED" for s in r["segments"]]
        for segment in segments:
            resource = segment["resource"]
            if resource not in self.capacities:
                return "NO_RESOURCE_AUTHORITY"
            a, b = segment["begin"], segment["end"]
            peers = [s for s in existing + segments if s["resource"] == resource]
            endpoints = sorted({a, b} | {max(a, s["begin"]) for s in peers
                                        if s["begin"] < b and s["end"] > a}
                               | {min(b, s["end"]) for s in peers
                                  if s["begin"] < b and s["end"] > a})
            if envelope is not None and resource.startswith("gpu:"):
                endpoints = sorted(set(endpoints) | {
                    x for row in envelope if row["site"] == resource[4:]
                    for x in (row["slot_start"], row["slot_end"])
                    if a < x < b})
            for left, right in zip(endpoints, endpoints[1:]):
                t = (left + right) / 2
                active = [s for s in peers if s["begin"] <= t < s["end"]]
                if sum(s["quantity"] for s in active) > self.capacities[resource] + 1e-9:
                    return "NO_CAPACITY"
                if (envelope is not None and scope == "anonymous" and resource.startswith("gpu:")
                        and segment.get("envelope_guard", True)):
                    cap = next((r["gpu_capacity"] for r in envelope
                                if r["site"] == resource[4:]
                                and r["slot_start"] <= t < r["slot_end"]), 0.)
                    anonymous = sum(s["quantity"] for s in active if s.get("scope") == "anonymous")
                    if anonymous > cap + 1e-9:
                        return "NO_ENVELOPE_CAPACITY"
        return None

    def reserve(self, uid, segments, *, envelope=None, scope="physical", replace=False):
        """All resources succeed together, or none of the ledger is changed."""
        normalized = []
        for s in segments:
            a = _finite(s["begin"], "RESERVATION_BEGIN", minimum=-float("inf"))
            b = _finite(s["end"], "RESERVATION_END", minimum=-float("inf"))
            q = _finite(s["quantity"], "RESERVATION_QUANTITY")
            if b <= a or q <= 0:
                raise ValueError("NONEMPTY_RESERVATION")
            if s["resource"].startswith("gpu:") and int(q) != q:
                raise ValueError("WHOLE_GANG_REQUIRED")
            normalized.append(dict(s, begin=a, end=b, quantity=q, scope=scope))
        with self._lock:
            if uid in self.reservations and self.reservations[uid]["status"] != "RELEASED" and not replace:
                return False, "DUPLICATE_RESERVATION"
            reason = self._fits(normalized, exclude=uid if replace else None,
                                envelope=envelope, scope=scope)
            if reason:
                self.audit.append(dict(uid=uid, status="REJECTED", reason=reason))
                return False, reason
            self.reservations[uid] = dict(uid=uid, segments=normalized, status="PLANNED", scope=scope)
            self.audit.append(dict(uid=uid, status="RESERVED", segments=deepcopy(normalized)))
            return True, "RESERVED"

    def feasible(self, segments, *, envelope=None, scope="physical", exclude=None):
        with self._lock:
            return self._fits([dict(s, scope=scope) for s in segments],
                              exclude=exclude, envelope=envelope, scope=scope)

    def activate(self, uid):
        with self._lock:
            self.reservations[uid]["status"] = "ACTIVE"

    def release(self, uid, now):
        with self._lock:
            if uid in self.reservations:
                self.reservations[uid]["status"] = "RELEASED"
                self.audit.append(dict(uid=uid, status="RELEASED", at=float(now)))

    def retain_running(self, uid, site, now, next_control, gpu):
        """Observed overrun takes precedence; future intents must queue.

        A retained running gang cannot be evicted to make a nominal booking fit.
        The physical EpisodeLedger checks every actual admission independently.
        """
        with self._lock:
            r = self.reservations.get(uid)
            if r is None:
                self.reservations[uid] = dict(uid=uid, status="ACTIVE", scope="physical",
                    segments=[dict(resource="gpu:" + site, begin=float(now),
                                   end=float(next_control), quantity=float(gpu), scope="physical")])
            else:
                active = [s for s in r["segments"] if s["resource"] == "gpu:" + site
                          and s["begin"] <= now]
                if active:
                    active[-1]["end"] = max(active[-1]["end"], float(next_control))
                else:
                    r["segments"].append(dict(resource="gpu:" + site, begin=float(now),
                        end=float(next_control), quantity=float(gpu), scope=r["scope"]))
                r["status"] = "ACTIVE"

    def snapshot(self):
        with self._lock:
            return dict(capacities=deepcopy(self.capacities),
                        reservations=deepcopy(self.reservations), audit=deepcopy(self.audit))


def compile_policy(envelope, bindings, grid_coefficients, *, grammar=None):
    """Compile anonymous A variables and signed Grid coefficients, without solve.

    Coefficients are supplied by the A-stage producer as vectors for each
    time/site row. They are not absolute-valued or replaced by invented prices.
    """
    if any(not bindings.get(k) for k in BINDING_FIELDS):
        raise ValueError("COMPLETE_POLICY_ANCHORS_REQUIRED")
    grammar = deepcopy(grammar or {})
    rows = []
    for source in envelope:
        row = deepcopy(source)
        row["slot_start"] = _finite(row["slot_start"], "ENVELOPE_TIME", -float("inf"))
        row["slot_end"] = _finite(row["slot_end"], "ENVELOPE_TIME", -float("inf"))
        row["gpu_capacity"] = _finite(row["gpu_capacity"], "ENVELOPE_CAPACITY")
        if row["slot_end"] <= row["slot_start"] or not row.get("source_variable"):
            raise ValueError("A_STAGE_VARIABLE_PROVENANCE_REQUIRED")
        if row["slot_start"] % 900 or row["slot_end"] % 900:
            raise ValueError("FIFTEEN_MINUTE_ENVELOPE_GRID")
        key = (row["site"], row["slot_start"])
        coefficients = grid_coefficients.get(key, grid_coefficients.get(
            str(row["site"]) + ":" + str(int(row["slot_start"]))))
        if coefficients is None:
            raise ValueError("SIGNED_GRID_COEFFICIENT_REQUIRED")
        row["signed_grid_effect_vector"] = [_finite(v, "FINITE_GRID_COEFFICIENT", -float("inf"))
                                              for v in coefficients]
        rows.append(row)
    rows.sort(key=lambda r: (r["slot_start"], r["site"]))
    if not rows:
        raise ValueError("NONEMPTY_A_STAGE_ENVELOPE_REQUIRED")
    for i, row in enumerate(rows):
        if any(other["site"] == row["site"] and other["slot_start"] < row["slot_end"]
               and row["slot_start"] < other["slot_end"] for other in rows[:i]):
            raise ValueError("OVERLAPPING_ENVELOPE_ROWS")
    rules = [dict(rule_id="A_ENVELOPE:" + str(i), **deepcopy(row),
                  applies=dict(qos=grammar.get("qos", ["normal", "standby"]),
                               protected=False, is_observed=True, states=["PENDING", "RUNNING"]),
                  qos_window_provider_ref=bindings["qos_sha"],
                  start_generation="INTERSECT_RECEIPT_ALLOWED_STARTS_CURRENT_OBSERVATION",
                  candidate_sites=[row["site"]],
                  migration_destinations=grammar.get("migration_destinations", sorted({r["site"] for r in rows})),
                  reservation="WHOLE_GANG_CONTINUOUS_NOMINAL_SERVICE_ATOMIC_GPU_WAN",
                  guard=["SUBMITTED_OBSERVED", "CASE_ANCHORS_MATCH", "AUTHORIZED_QOS_WINDOW",
                         "SHARED_DELAY_INTERRUPTION_BUDGET", "ORIGINAL_SITE_RACK_GANG",
                         "CONTINUOUS_ENVELOPE_AND_PHYSICAL_CAPACITY"],
                  fallback="QUEUE_PENDING_OR_RUNNING_STAY_WITH_EXACT_REASON")
             for i, row in enumerate(rows)]
    body = dict(policy_version=POLICY_VERSION, bindings=deepcopy(bindings),
                control_grid_seconds=900, checkpoint_period_seconds=1800,
                policy_kind="optimization-derived conditional policy", envelope=rows,
                rules=rules, grammar=grammar, online_global_optimizer_calls=0,
                scope="anonymous time/site allocation plus fixed action grammar; not job-scenario global optimum")
    return FrozenControlPolicy(dict(body, content_sha=digest(body)))


class FrozenControlPolicy:
    def __init__(self, document):
        body = deepcopy(document)
        expected = body.pop("content_sha", None)
        if expected != digest(body) or body.get("policy_version") != POLICY_VERSION:
            raise ValueError("FROZEN_POLICY_SHA_MISMATCH")
        if not body.get("rules") or not body.get("envelope"):
            raise ValueError("NONEMPTY_CONDITIONAL_CONTROL_TABLE_REQUIRED")
        if any(not body["bindings"].get(k) for k in BINDING_FIELDS):
            raise ValueError("COMPLETE_POLICY_ANCHORS_REQUIRED")
        # Validate once, then keep the parsed document private. Public access
        # still returns independent copies; event lookups never parse a full
        # policy JSON or copy its entire electrical response repeatedly.
        self.__body = dict(body, content_sha=expected)
        self.__rows_by_site = {}
        rows_by_key = {}
        for row in body["envelope"]:
            self.__rows_by_site.setdefault(row["site"], []).append(row)
            rows_by_key[row["site"], row["slot_start"], row["slot_end"]] = row
        self.__rules_by_grid = {}
        self.__wide_rules = []
        for index, rule in enumerate(body["rules"]):
            row = rows_by_key.get((rule["site"], rule["slot_start"], rule["slot_end"]))
            left = rule.get("signed_grid_effect_vector", ())
            right = () if row is None else row["signed_grid_effect_vector"]
            # JSON duplicates the same numeric response in rule/envelope. Share
            # only exactly identical scalar types and signed zero internally.
            if (row is not None and len(left) == len(right) and all(type(a) is type(b) and a == b
                    and (a != 0 or math.copysign(1., a) == math.copysign(1., b))
                    for a, b in zip(left, right))):
                rule["signed_grid_effect_vector"] = right
            first = math.floor(rule["slot_start"] / 900)
            last = math.ceil(rule["slot_end"] / 900)
            if last-first > 4096:
                self.__wide_rules.append(index)
            else:
                for slot in range(first, last):
                    self.__rules_by_grid.setdefault(slot, []).append(index)
        self.__effect_cache = OrderedDict()
        self.__effect_lock = threading.RLock()
        self._json = json.dumps(dict(body, content_sha=expected), sort_keys=True, allow_nan=False)

    @property
    def document(self):
        document = deepcopy(self.__body)
        # Keep duplicated public lists independent as in a fresh JSON load.
        for rule in document["rules"]:
            if "signed_grid_effect_vector" in rule:
                rule["signed_grid_effect_vector"] = list(rule["signed_grid_effect_vector"])
        return document

    @property
    def bindings(self):
        return deepcopy(self.__body["bindings"])

    @property
    def sha(self):
        return self.__body["content_sha"]

    def _rules_at(self, now):
        indices = self.__rules_by_grid.get(math.floor(now / 900), ())
        if self.__wide_rules:
            indices = sorted((*indices, *self.__wide_rules))
        return [self.__body["rules"][i] for i in indices
                if self.__body["rules"][i]["slot_start"] <= now < self.__body["rules"][i]["slot_end"]]

    def rules_at(self, now):
        """Only current frozen rule copies, preserving original document order."""
        return deepcopy(self._rules_at(now))

    def envelope_for_interval(self, site, begin, end):
        """Safe copies of all original overlapping rows, including carryover."""
        return deepcopy([r for r in self.__rows_by_site.get(site, ())
                         if r["slot_start"] < end and r["slot_end"] > begin])

    def require_bindings(self, expected):
        if any(expected.get(k) != self.bindings[k] for k in BINDING_FIELDS):
            raise ValueError("FINAL_AIDC_MESS_POLICY_ANCHOR_MISMATCH")

    def save(self, path):
        Path(path).write_text(self._json + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path, *, bindings=None):
        policy = cls(json.loads(Path(path).read_text(encoding="utf-8")))
        if bindings is not None:
            policy.require_bindings(bindings)
        return policy

    def candidates(self, metadata, receipt, now):
        """Pure ranking, without future completion or private realized service."""
        receipt = _receipt(receipt)
        if receipt["uid"] != metadata["uid"]:
            raise ValueError("QOS_RECEIPT_UID_MISMATCH")
        if not metadata.get("is_observed", True) or metadata["submit_seconds"] > now:
            return [], "NOT_YET_SUBMITTED"
        if receipt["case_sha"] != self.bindings["case_sha"]:
            raise ValueError("QOS_RECEIPT_CASE_MISMATCH")
        if metadata.get("state", "PENDING") != "PENDING":
            return [], "RUNNING_START_IMMUTABLE"
        qos = metadata.get("qos", "normal")
        allowed = tuple(receipt["allowed_starts_seconds"])
        service = float(metadata.get("nominal_service_seconds", metadata["t50_seconds"]))
        gpu = int(metadata["gpu"])
        compatible = set(metadata.get("compatible_sites", ()))
        source_site = metadata.get("source_site")
        if source_site is not None and metadata.get("can_prestart_place") is not True:
            compatible &= {source_site}
        candidates = []
        for start in allowed:
            if start < now or start < metadata["submit_seconds"]:
                continue
            delay = max(0., start - receipt["reference_start_seconds"])
            if delay + float(metadata.get("cumulative_migration_interruption_seconds", 0.)) > receipt["budget_seconds"] + 1e-9:
                continue
            for rule in self._rules_at(start):
                if qos not in rule["applies"]["qos"] or metadata.get("protected", False):
                    continue
                if rule["site"] not in compatible or not rule["slot_start"] <= start < rule["slot_end"]:
                    continue
                end = start + max(service, 1e-9)
                effect = self._effect(rule["site"], start, end, gpu)
                if effect is None:
                    continue
                preplace = source_site is not None and source_site != rule["site"]
                candidates.append(dict(action="PREPLACE" if preplace else "DELAY" if start > now else "START",
                    uid=metadata["uid"], site=rule["site"], start_seconds=float(start),
                    nominal_end_seconds=end, additional_start_delay_seconds=delay,
                    rule_id=rule["rule_id"], signed_grid_effect_vector=effect,
                    segments=[dict(resource="gpu:" + rule["site"], begin=float(start),
                                   end=end, quantity=gpu)]))
        candidates.sort(key=lambda c: (tuple(c["signed_grid_effect_vector"]),
            c["action"] == "PREPLACE", c["start_seconds"], c["site"], c["uid"]))
        return candidates, "MATCH" if candidates else "NO_MATCH"

    def _effect(self, site, begin, end, gpu):
        key = (site, begin, end, gpu)
        with self.__effect_lock:
            if key in self.__effect_cache:
                self.__effect_cache.move_to_end(key)
                return list(self.__effect_cache[key])
        rows = [r for r in self.__rows_by_site.get(site, ())
                if r["slot_start"] < end and r["slot_end"] > begin]
        covered = sum(max(0., min(end, r["slot_end"]) - max(begin, r["slot_start"])) for r in rows)
        if covered < end - begin - 1e-7 or not rows:
            return None
        n = len(rows[0]["signed_grid_effect_vector"])
        if any(len(r["signed_grid_effect_vector"]) != n for r in rows):
            raise ValueError("GRID_EFFECT_VECTOR_AXIS")
        effect = [sum(r["signed_grid_effect_vector"][i] * gpu *
                    max(0., min(end, r["slot_end"]) - max(begin, r["slot_start"])) / 900.
                    for r in rows) for i in range(n)]
        with self.__effect_lock:
            self.__effect_cache[key] = tuple(effect)
            self.__effect_cache.move_to_end(key)
            if len(self.__effect_cache) > 256:
                self.__effect_cache.popitem(last=False)
        return effect

    def select(self, metadata, receipt, now, reservations, *, reserve=True):
        candidates, reason = self.candidates(metadata, receipt, now)
        rejects = []
        for candidate in candidates:
            if reserve:
                ok, reason = reservations.reserve(metadata["uid"], candidate["segments"],
                    envelope=self.__body["envelope"], scope="anonymous")
            else:
                reason = reservations.feasible(candidate["segments"],
                    envelope=self.__body["envelope"], scope="anonymous")
                ok = reason is None
            if ok:
                return dict(candidate, status="SELECTED", rejected_candidates=rejects, policy_sha=self.sha)
            rejects.append(dict(rule_id=candidate["rule_id"], site=candidate["site"], reason=reason))
        return dict(uid=metadata["uid"], action="QUEUE", status=reason, rejected_candidates=rejects,
                    policy_sha=self.sha, online_global_optimizer_calls=0)


def migration_guard(metadata, receipt, *, now, accumulated_compute_seconds, destination,
                    remaining_nominal_seconds, reservations, checkpoint_at=None):
    """Guard an already-observed RUNNING job using an explicit capability packet.

    Missing fields remain unconfirmed. No origin_unknown exclusion is used.
    Resource hold times must come from the inherited physical contract packet.
    """
    receipt = _receipt(receipt)
    if receipt["uid"] != metadata["uid"]:
        raise ValueError("QOS_RECEIPT_UID_MISMATCH")
    if not metadata.get("is_observed", True) or metadata.get("state") != "RUNNING":
        return None, "NO_OBSERVED_RUNNING_AUTHORITY"
    if metadata.get("migration_count", 0) >= 1:
        return None, "ONE_CHECKPOINT_MIGRATION_LIMIT"
    if remaining_nominal_seconds <= 0:
        return None, "Q50_OVERRUN_NO_NOMINAL_MIGRATION_ENVELOPE"
    cap = metadata.get("migration_capability") or {}
    required = ("source_sha", "checkpoint_authorized", "allowed_destinations", "gpu_type_confirmed",
                "rack_gang_confirmed", "data_residency_confirmed", "wan_path", "bandwidth_bytes_per_second",
                "payload_bytes", "restart_seconds", "source_wait_seconds", "source_hold_until",
                "destination_hold_from")
    if any(k not in cap for k in required):
        return None, "NO_AUTHORITY_CAPABILITY_UNCONFIRMED"
    if any(cap.get(k) is not True for k in ("checkpoint_authorized", "gpu_type_confirmed",
                                           "rack_gang_confirmed", "data_residency_confirmed")):
        return None, "NO_AUTHORITY_CHECKPOINT_SITE_RACK_RESIDENCY"
    if destination not in cap["allowed_destinations"] or destination == metadata["current_site"]:
        return None, "NO_AUTHORIZED_DESTINATION"
    if not cap["source_sha"]:
        return None, "NO_AUTHORITY_CAPABILITY_SOURCE"
    if accumulated_compute_seconds < 1800 or abs(accumulated_compute_seconds % 1800) > 1e-7:
        return None, "NOT_EXECUTION_ANCHORED_CHECKPOINT"
    physical_checkpoint = float(now if checkpoint_at is None else checkpoint_at)
    control_checkpoint = math.ceil(physical_checkpoint / 900.) * 900.
    if now < physical_checkpoint:
        return None, "CHECKPOINT_NOT_OBSERVED"
    if cap["source_hold_until"] not in ("transfer_start", "transfer_end", "restart_end") or cap["destination_hold_from"] not in ("checkpoint", "transfer_start", "transfer_end", "restart_start"):
        return None, "UNCONFIRMED_RESOURCE_HOLD_CONTRACT"
    bandwidth = _finite(cap["bandwidth_bytes_per_second"], "WAN_BANDWIDTH")
    if bandwidth <= 0:
        return None, "NO_WAN_BANDWIDTH"
    payload = _finite(cap["payload_bytes"], "WAN_PAYLOAD")
    transfer = max(900., math.ceil(payload / bandwidth / 900.) * 900.)
    wait = _finite(cap["source_wait_seconds"], "SOURCE_WAIT_SECONDS")
    restart = _finite(cap["restart_seconds"], "RESTART_SECONDS")
    if wait % 900 or restart % 900 or restart < 900:
        return None, "INHERITED_CONTROL_GRID_WAIT_RESTART_REQUIRED"
    interruption = control_checkpoint - physical_checkpoint + wait + transfer + restart
    used = float(metadata.get("additional_start_delay_seconds", 0.)) + float(metadata.get("cumulative_migration_interruption_seconds", 0.))
    if used + interruption > receipt["budget_seconds"] + 1e-9:
        return None, "SHARED_DELAY_INTERRUPTION_BUDGET_EXCEEDED"
    transfer_start = control_checkpoint + wait
    transfer_end = transfer_start + transfer
    restart_end = transfer_end + restart
    if metadata.get("completion_deadline_seconds") is not None and restart_end + remaining_nominal_seconds > metadata["completion_deadline_seconds"]:
        return None, "NOMINAL_COMPLETION_DEADLINE"
    times = dict(checkpoint=control_checkpoint, transfer_start=transfer_start,
                 transfer_end=transfer_end, restart_start=transfer_end, restart_end=restart_end)
    gpu = metadata["gpu"]
    source = metadata["current_site"]
    dest_begin = times[cap["destination_hold_from"]]
    segments = [dict(resource="gpu:" + source, begin=physical_checkpoint,
                     end=times[cap["source_hold_until"]], quantity=gpu),
                dict(resource="wan:" + cap["wan_path"], begin=transfer_start, end=transfer_end, quantity=bandwidth),
                dict(resource="active:WAN", begin=transfer_start, end=transfer_end, quantity=1),
                dict(resource="gpu:" + destination, begin=dest_begin,
                     end=restart_end + max(remaining_nominal_seconds, 1e-9), quantity=gpu)]
    segments = [s for s in segments if s["end"] > s["begin"]]
    reason = reservations.feasible(segments, exclude=metadata["uid"])
    if reason:
        return None, reason
    return dict(id="CHECKPOINT:" + metadata["uid"], job_id=metadata["uid"], source=source,
                destination=destination, physical_checkpoint_seconds=physical_checkpoint,
                control_checkpoint_seconds=control_checkpoint, times=times,
                interruption_seconds=interruption, accumulated_compute_seconds=accumulated_compute_seconds,
                capability_source_sha=cap["source_sha"], capability_assumption=cap.get("assumption", False),
                hold_contract=dict(source_hold_until=cap["source_hold_until"],
                                   destination_hold_from=cap["destination_hold_from"]), segments=segments,
                completed_at=restart_end), "AUTHORIZED"
