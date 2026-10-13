"""Common causal Job-event Actual, extending PR125's queue and physical ledger.

The simulator retains realized service privately. The controller only receives
submissions, elapsed compute, checkpoint phases and observed completions. No
anonymous forecast, runtime reserve or Planning power is physical execution.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass, field, fields
import heapq
import math
import numpy as np

from v42_capacity.actual import Request, Controller, Environment, CachedProvider
from v42_final.state import EpisodeLedger
from v42_final.workload import ForecastBook
from .policy import ReservationLedger, migration_guard, digest
from .qos import ObservedJob, CausalReferenceScheduler


PRIVATE_REALIZATION_FIELDS = frozenset({
    "realized_duration", "realized_duration_seconds", "realized_seconds", "realized_service_seconds",
    "actual_runtime", "actual_runtime_seconds", "actual_remaining", "actual_remaining_seconds",
    "actual_end", "actual_end_seconds", "actual_end_time", "end_time", "end_seconds", "source_end_time",
    "actual_start", "actual_start_seconds", "start_observed_by_day_end", "end_observed_by_day_end",
    "future_completion", "future_completion_seconds", "future_completion_receipt", "future_queue",
})


def _require_public_metadata(value):
    """Reject private aliases before submission or provider/forecast mutation."""
    if isinstance(value, dict):
        if PRIVATE_REALIZATION_FIELDS.intersection(value):
            raise ValueError("PRIVATE_REALIZATION_IN_CONTROLLER_METADATA")
        for child in value.values():
            _require_public_metadata(child)
    elif isinstance(value, (tuple, list)):
        for child in value:
            _require_public_metadata(child)


@dataclass(frozen=True)
class JobRequest(Request):
    metadata: dict = field(default_factory=dict)


class ExecutionLedger(EpisodeLedger):
    """Preserve PR125 Running/overrun/release semantics during physical phases."""
    def __init__(self, capacities):
        super().__init__(capacities)
        self.in_flight = {}

    def physical(self, t):
        if t < self.last_time:
            raise ValueError("PAST_PHYSICAL_STATE")
        use = {s: 0 for s in self.capacities}
        for uid, job in self.jobs.items():
            if uid in self.in_flight:
                for segment in self.in_flight[uid]["segments"]:
                    if segment["resource"].startswith("gpu:") and segment["begin"] <= t < segment["end"]:
                        use[segment["resource"][4:]] += segment["quantity"]
                continue
            active = (job["latest_observed_state"] == "RUNNING" or
                      job["latest_observed_state"] == "COMPLETED" and t < job["release_control_time"])
            if active:
                use[job["current_site"]] += job["gpu"]
        return use


class _PrivateService:
    """Simulator-only state; never included in a controller or policy request."""
    def __init__(self, environment, remaining=None):
        if not isinstance(environment, Environment):
            raise ValueError("PR125_PRIVATE_ENVIRONMENT_REQUIRED")
        self.environment = environment
        self.__remaining = deepcopy(remaining or {})
        self.epoch = {}

    def start(self, uid, now, *, initial_running=False):
        if uid not in self.__remaining:
            self.__remaining[uid] = (self.environment.running_completion(uid) - now if initial_running
                                     else self.environment.started(uid, now) - now)
        self.epoch[uid] = self.epoch.get(uid, 0) + 1
        return now + self.__remaining[uid], self.epoch[uid]

    def advance(self, uids, seconds):
        for uid in uids:
            self.__remaining[uid] = max(0., self.__remaining[uid] - seconds)

    def pause(self, uid):
        self.epoch[uid] = self.epoch.get(uid, 0) + 1

    def completion_valid(self, uid, epoch):
        return self.epoch.get(uid) == epoch and self.__remaining[uid] <= 1e-7

    def snapshot(self):
        return deepcopy(self.__remaining)


class JobEventController(Controller):
    """PR125 Controller with frozen QoS/policy adapters, shared by every Arm."""
    def __init__(self, capacities, *, arm, qos_window_provider, frozen_policy=None,
                 known_schedule=None, reference=None, forecast=None, wan_capacities=None):
        super().__init__(capacities)
        if arm not in {"B0", "B1", "B2", "B3"}:
            raise ValueError("COMPARISON_ARM_REQUIRED")
        self.ledger = ExecutionLedger(capacities)
        self.arm = arm
        self.qos = qos_window_provider
        self.policy = frozen_policy
        self.flexible = arm in {"B1", "B3"}
        self.known_schedule = deepcopy(known_schedule or {})
        self.reference = reference or CausalReferenceScheduler(capacities, reference_sha="CAUSAL_REFERENCE_START")
        self.forecast = forecast
        self.reservations = ReservationLedger(capacities, wan_capacities)
        self.observed = {}
        self.metadata = {}
        self.budgets = {}
        self.decisions = {}
        self.events = []
        self.qos_ledger = []
        self.cc4_ledger = []
        self.migrations = []
        self.rule_ledger = []

    def _event(self, uid, now, kind, **extra):
        self.events.append(dict(uid=uid, time_seconds=float(now), event=kind, **extra))

    def submit(self, request, now):
        if request.submit > now:
            raise ValueError("FUTURE_SUBMISSION")
        raw = deepcopy(getattr(request, "metadata", {}))
        _require_public_metadata(raw)
        reference_sha = self.reference.reference_sha
        if raw.get("reference_sha", reference_sha) != reference_sha:
            # The DD00 execution reference can advance without replacing a
            # Known job's immutable issue-time research budget.
            proof = raw.get("reused_planning_qos_authority", {})
            prior = self.qos.receipts.get(request.uid)
            expected = None if prior is None else dict(uid=request.uid,
                case_sha=self.qos.case_sha, provider_sha=self.qos.provider_sha,
                stats_sha=self.qos.stats.sha, reference_sha=prior.reference_sha,
                authority_sha=prior.authority_sha, gpu=request.gpu)
            if (not raw.get("common_initial_state_sha") or proof != expected
                    or prior is None or prior.hard_contract["gpu"] != request.gpu
                    or raw.get("reference_sha") != prior.reference_sha
                    or raw.get("reference_start_seconds") != prior.reference_start_seconds
                    or raw.get("origin_unknown") is not False):
                raise ValueError("IMMUTABLE_PLANNING_QOS_REUSE_PROOF_REQUIRED")
            reference_sha = prior.reference_sha
            reuse_args = {f.name: raw[f.name] for f in fields(ObservedJob) if f.name in raw}
            reuse_args.update(uid=request.uid, submit_seconds=request.submit, event_seconds=now,
                t50_seconds=request.q50, gpu=request.gpu, is_observed=True,
                provider_sha=self.qos.provider_sha, reference_sha=reference_sha)
            if ObservedJob(**reuse_args).authority_sha != prior.authority_sha:
                raise ValueError("IMMUTABLE_PLANNING_QOS_METADATA_CHANGED")
        # This is the original PR125 submit/queue/EpisodeLedger admission path.
        super().submit(request, now)
        reference = (self.reference.assigned[request.uid] if request.uid in self.reference.assigned
                     else self.reference.submit(request, event_seconds=now))
        args = {f.name: raw[f.name] for f in fields(ObservedJob) if f.name in raw}
        args.update(uid=request.uid, submit_seconds=request.submit, event_seconds=now,
                    reference_start_seconds=raw.get("reference_start_seconds", reference["reference_start_seconds"]),
                    t50_seconds=request.q50, gpu=request.gpu, is_observed=True,
                    provider_sha=self.qos.provider_sha, reference_sha=reference_sha)
        if "representation_starts_seconds" not in args:
            raise ValueError("SOURCE_REPRESENTATION_STARTS_REQUIRED")
        observed = ObservedJob(**args)
        budget = self.qos.issue(observed)
        self.observed[request.uid] = observed
        self.budgets[request.uid] = budget
        self.metadata[request.uid] = {**raw, **asdict(observed),
            "compatible_sites": list(request.compatible), "source_site": request.source_site,
            "reference_site": reference["reference_site"],
            "state": "PENDING", "additional_start_delay_seconds": 0.,
            "cumulative_migration_interruption_seconds": 0., "accumulated_compute_seconds": 0., "migration_count": 0}
        if self.metadata[request.uid].get("nominal_service_seconds") is None:
            self.metadata[request.uid]["nominal_service_seconds"] = request.q50
        if (self.forecast is not None and observed.origin_unknown and
                self.forecast.day_start <= request.submit < self.forecast.day_start + 86400
                and raw.get("cc4_eligible", True)):
            row = self.forecast.submit(request.uid, request.submit, now, request.gpu, request.q50)
            self.cc4_ledger.append(dict(uid=request.uid, **row,
                excess_submitted_nominal_GPUh=max(0., row["realized_submitted_nominal_work_GPUh"] - self.forecast.q50[row["hour"]]),
                depletion_count=1, anonymous_forecast_is_physical=False))
        self._event(request.uid, now, "SUBMISSION_OBSERVED", origin_unknown=observed.origin_unknown,
                    qos_budget_seconds=budget.budget_seconds)

    def _reference_decision(self, uid, now):
        request = self.requests[uid]
        reference = self.reference.assigned[uid]
        metadata = self.metadata[uid]
        start = max(reference["reference_start_seconds"], now,
                    metadata.get("release_seconds") or -float("inf"),
                    metadata.get("hard_earliest_start_seconds") or -float("inf"))
        start = math.ceil(start/900.)*900.
        for field in ("hard_latest_start_seconds", "completion_deadline_seconds"):
            limit = metadata.get(field)
            if limit is not None and (start if field == "hard_latest_start_seconds" else start+request.q50) > limit:
                return dict(uid=uid, action="QUEUE", status="EMPTY_AUTHORIZED_HARD_WINDOW")
        return dict(action="START", site=reference["reference_site"], start_seconds=start,
                    nominal_end_seconds=start + max(request.q50, 1e-9), status="CAUSAL_REFERENCE_START",
                    uid=uid, additional_start_delay_seconds=0.)

    def _known_decision(self, uid, now):
        schedule = self.known_schedule[uid]
        receipt = self.budgets[uid]
        start = float(schedule["start_seconds"])
        site = schedule["site"]
        r = self.requests[uid]
        boundary = self.metadata[uid].get("dday_initialization_seconds")
        if boundary is not None and start < boundary:
            return dict(self._reference_decision(uid, now),
                status="PRE_DDAY_START_COMMAND_NOT_REPLAYED", plan_start_seconds=start)
        if start not in receipt.allowed_starts_seconds:
            return dict(uid=uid, action="QUEUE", status="PLAN_OUTSIDE_AUTHORIZED_WINDOW")
        if site not in r.compatible or (r.source_site is not None and site != r.source_site
                                       and self.metadata[uid].get("can_prestart_place") is not True):
            return dict(uid=uid, action="QUEUE", status="PLAN_SITE_NO_AUTHORITY")
        if start < now:
            start = now
        return dict(uid=uid, action="START", site=site, start_seconds=start,
                    nominal_end_seconds=start + max(r.q50, 1e-9), status="KNOWN_EXECUTION_COMMAND",
                    plan_start_seconds=float(schedule["start_seconds"]),
                    additional_start_delay_seconds=max(0., schedule["start_seconds"] - receipt.reference_start_seconds))

    def _policy_resource_guard(self, now, *, lookup_at=None, observed_use=None):
        """Observed current occupancy must lie inside explicit frozen support.

        This is a necessary template-support check, not an Actual grid safety
        certificate. A future control row uses only current observed state.
        Legacy resource-only policies retain their original execution path.
        """
        if self.policy is None or not hasattr(self.policy, "resource_support_at"):
            return None, {}
        control = now if lookup_at is None else lookup_at
        observed = (self.ledger.physical(now) if observed_use is None else dict(observed_use))
        support = self.policy.resource_support_at(control)
        diagnostic = dict(observed_at_seconds=now, frozen_support_control_seconds=control,
            observed_GPU_by_site=observed, grid_safety_guaranteed=False)
        if support is None:
            return "NO_FROZEN_RESOURCE_SUPPORT_AUTHORITY", diagnostic
        lower, upper = support.get("lower_by_site", {}), support.get("upper_by_site", {})
        diagnostic.update(resource_support_source_sha=support.get("source_sha"),
            resource_support_scenario_ids=support.get("scenario_ids", []))
        if (set(lower) != set(observed) or set(upper) != set(observed)
                or not support.get("source_sha") or not support.get("scenario_ids")
                or any(not math.isfinite(float(lower[s])) or not math.isfinite(float(upper[s]))
                       or lower[s] < 0 or upper[s] < lower[s] for s in observed)):
            return "FROZEN_RESOURCE_SUPPORT_AUTHORITY_INVALID", diagnostic
        if hasattr(self.policy, "resource_baseline_at"):
            baseline = self.policy.resource_baseline_at(control)
            if baseline is not None and set(baseline) == set(observed):
                diagnostic["observed_GPU_deviation_from_frozen_nominal"] = {
                    s: observed[s]-baseline[s] for s in observed}
        diagnostic["outside_support_sites"] = [s for s in observed
            if observed[s] < lower[s]-1e-9 or observed[s] > upper[s]+1e-9]
        return ("OBSERVED_RESOURCE_OUTSIDE_FROZEN_TEMPLATE_SUPPORT" if diagnostic["outside_support_sites"]
                else None), diagnostic

    def admit(self, now):
        starts = []
        # Submissions and physical checkpoints can be off-grid observations;
        # execution commands reflect only at the frozen 15-minute grid.
        if now % 900:
            return starts
        # Preserve strict FCFS queue ordering for nonflexible B0/B2.
        queue = sorted(self.pending)
        # No completion or migration event interleaves this serial pass.
        # Starts are the only physical mutation: update this exact local
        # snapshot after every whole-gang start, and discard it on return.
        use = self.ledger.physical(now)
        for _, uid in queue:
            request = self.requests[uid]
            if uid not in self.decisions or self.decisions[uid]["action"] == "QUEUE":
                if not self.flexible:
                    decision = self._reference_decision(uid, now)
                elif uid in self.known_schedule:
                    decision = self._known_decision(uid, now)
                elif self.policy is not None:
                    reason, observation = self._policy_resource_guard(now, observed_use=use)
                    if reason:
                        decision = dict(uid=uid, action="QUEUE", status="NO_FEASIBLE_ACTION", reason=reason,
                            policy_sha=self.policy.sha, grid_safety_guaranteed=False)
                    else:
                        decision = self.policy.select(self.metadata[uid], self.budgets[uid], now, self.reservations)
                    decision.update(observation)
                    self.rule_ledger.append(dict(time_seconds=now, **deepcopy(decision)))
                    # Protected/unsupported jobs still execute through the safe
                    # grid-blind queue. No deliberate delay authority is issued.
                    if decision["action"] == "QUEUE" and (self.metadata[uid]["protected"] or
                        self.metadata[uid]["qos"] not in {"normal", "standby"} or
                        self.budgets[uid].budget_seconds == 0):
                        decision = dict(self._reference_decision(uid, now),
                                        policy_reject_reason=decision.get("reason", decision["status"]),
                                        grid_safety_guaranteed=False)
                else:
                    decision = dict(self._reference_decision(uid, now), policy_reject_reason="NO_POLICY")
                self.decisions[uid] = decision
            decision = self.decisions[uid]
            if decision["action"] == "QUEUE" or decision["start_seconds"] > now:
                if not self.flexible:
                    break
                continue
            site = decision["site"]
            meta = self.metadata[uid]
            hard_latest = meta.get("hard_latest_start_seconds")
            deadline = meta.get("completion_deadline_seconds")
            if ((hard_latest is not None and now > hard_latest) or
                    (deadline is not None and now + request.q50 > deadline)):
                self._event(uid, now, "QUEUED", reason="EMPTY_AUTHORIZED_HARD_WINDOW")
                if not self.flexible:
                    break
                continue
            if use[site] + request.gpu > self.ledger.capacities[site]:
                self._event(uid, now, "QUEUED", reason="PHYSICAL_CAPACITY_RUNNING_RETAINED")
                if not self.flexible:
                    break
                continue
            segment = dict(resource="gpu:" + site, begin=now,
                           end=now + max(request.q50, 1e-9), quantity=request.gpu)
            if uid not in self.reservations.reservations or self.reservations.reservations[uid]["status"] == "RELEASED":
                ok, reason = self.reservations.reserve(uid, [segment])
                if not ok:
                    self._event(uid, now, "QUEUED", reason=reason)
                    if not self.flexible:
                        break
                    continue
            elif now > decision["start_seconds"]:
                # Nominal bookings do not evict an observed overrun. Rebind the
                # command only after physical capacity is available.
                ok, reason = self.reservations.reserve(uid, [segment], replace=True)
                if not ok:
                    self._event(uid, now, "QUEUED", reason=reason)
                    if not self.flexible:
                        break
                    continue
            self.ledger.start(uid, site, now, self.metadata[uid].get('episode_id',"COMMON_ACTUAL:" + uid))
            use[site] += request.gpu
            self.reservations.activate(uid)
            self.pending.remove((request.submit, uid))
            heapq.heapify(self.pending)
            self.metadata[uid].update(state="RUNNING", current_site=site,
                additional_start_delay_seconds=decision.get("additional_start_delay_seconds", 0.))
            wait = now - max(request.submit, 0.)
            self.audit[uid].update(admitted_time=now, capacity_wait_seconds=wait,
                capacity_wait_slots=math.ceil(wait/900), site=site,
                plan_start_seconds=decision.get("plan_start_seconds", decision["start_seconds"]),
                plan_actual_start_deviation_seconds=now-decision.get("plan_start_seconds", decision["start_seconds"]),
                intentional_delay_seconds=decision.get("additional_start_delay_seconds", 0.),
                unavoidable_queue_seconds=max(0., now - max(decision["start_seconds"], self.budgets[uid].reference_start_seconds)),
                policy_action=decision["action"], rule_id=decision.get("rule_id"))
            self._event(uid, now, "RUNNING", site=site, action=decision["action"])
            starts.append(uid)
        return starts

    def completion(self, uid, now):
        release = super().completion(uid, now)
        self.metadata[uid]["state"] = "COMPLETED"
        self._event(uid, now, "COMPLETION_OBSERVED", release_control_seconds=release)
        return release

    def migration(self, uid, now, physical_checkpoint):
        metadata = self.metadata[uid]
        if not self.flexible or self.policy is None:
            return None
        command = self.known_schedule.get(uid, {})
        requested_destination = command.get("migration_destination")
        boundary = metadata.get("dday_initialization_seconds")
        if (requested_destination is not None and boundary is not None
                and command.get("checkpoint_control_seconds", now) < boundary):
            self._event(uid, now, "RUNNING_STAY", reason="PRE_DDAY_COMMAND_NOT_REPLAYED")
            return None
        if requested_destination is not None and now < command.get("checkpoint_control_seconds", now):
            self._event(uid, now, "RUNNING_STAY", reason="KNOWN_CHECKPOINT_COMMAND_NOT_DUE")
            return None
        if requested_destination is not None:
            remaining = max(0., self.requests[uid].q50 - metadata["accumulated_compute_seconds"])
            receipt, reason = migration_guard(metadata, self.budgets[uid], now=now,
                accumulated_compute_seconds=metadata["accumulated_compute_seconds"],
                destination=requested_destination, remaining_nominal_seconds=remaining,
                reservations=self.reservations, checkpoint_at=physical_checkpoint)
            if receipt is not None:
                ok, reason = self.reservations.reserve(uid, receipt["segments"], replace=True)
                if ok:
                    return self._record_migration(uid, receipt, now, physical_checkpoint,
                        policy_rule_id="KNOWN_FROZEN_EXECUTION_COMMAND")
            self._event(uid, now, "RUNNING_STAY", reason=reason)
            return None
        if requested_destination is None and hasattr(self.policy, "select_migration"):
            if uid in self.known_schedule and not metadata["origin_unknown"]:
                self._event(uid, now, "RUNNING_STAY", reason="KNOWN_FROZEN_STAY_COMMAND")
                return None
            control = math.ceil(physical_checkpoint/900)*900
            reason, observation = self._policy_resource_guard(now, lookup_at=control)
            if reason:
                decision = dict(uid=uid, action="STAY", status="NO_FEASIBLE_ACTION", reason=reason,
                    policy_sha=self.policy.sha, grid_safety_guaranteed=False)
            else:
                # The lookup row is frozen. It does not advance observed time
                # or expose a future completion. Original guards use the
                # physical checkpoint and charge the control-roundup wait.
                decision = self.policy.select_migration(metadata, self.budgets[uid], now,
                    self.reservations, checkpoint_at=physical_checkpoint, reserve=True)
                decision.setdefault("uid", uid)
            decision.update(observation)
            self.rule_ledger.append(dict(time_seconds=now, event="OBSERVED_EXECUTION_CHECKPOINT",
                Event30_activation="NOT_AUTHORIZED_WITHOUT_FROZEN_THRESHOLD_METRIC", **deepcopy(decision)))
            if decision["action"] != "CHECKPOINT_MIGRATE":
                self._event(uid, now, "RUNNING_STAY", reason=decision.get("reason", decision["status"]))
                return None
            return self._record_migration(uid, decision["migration"], now, physical_checkpoint,
                policy_rule_id=decision.get("rule_id"), policy_sha=decision.get("policy_sha"))
        current_rules = self.policy.rules_at(now) if hasattr(self.policy, "rules_at") else self.policy.document["rules"]
        rules = [r for r in current_rules if
                 r["slot_start"] <= now < r["slot_end"] and metadata["qos"] in r["applies"]["qos"]
                 and not metadata["protected"]]
        destinations = ([requested_destination] if requested_destination is not None
                        else sorted({site for r in rules for site in r["migration_destinations"]}))
        if not destinations:
            self._event(uid, now, "RUNNING_STAY", reason="NO_MATCH_MIGRATION_RULE")
            return None
        remaining = max(0., self.requests[uid].q50 - metadata["accumulated_compute_seconds"])
        ranked = []
        for destination in destinations:
            effect = self.policy._effect(destination, math.ceil(now/900)*900,
                                         math.ceil(now/900)*900 + max(remaining, 1e-9), metadata["gpu"])
            source_effect = self.policy._effect(metadata["current_site"], math.ceil(now/900)*900,
                math.ceil(now/900)*900 + max(remaining, 1e-9), metadata["gpu"])
            if requested_destination is not None:
                ranked.append(((), destination))
            elif effect is not None and (source_effect is None or tuple(effect) < tuple(source_effect)):
                ranked.append((tuple(effect), destination))
        reason = "NO_MATCH_MIGRATION_ENVELOPE"
        for _, destination in sorted(ranked):
            receipt, reason = migration_guard(metadata, self.budgets[uid], now=now,
                accumulated_compute_seconds=metadata["accumulated_compute_seconds"],
                destination=destination, remaining_nominal_seconds=remaining,
                reservations=self.reservations, checkpoint_at=physical_checkpoint)
            if receipt is None:
                continue
            unknown = metadata["origin_unknown"] and requested_destination is None
            if unknown:
                # The retained source gang is physical truth. The new
                # destination reservation must fit the shifted A envelope,
                # including restart and resumed continuous nominal compute.
                receipt["segments"] = [dict(segment, envelope_guard=(
                    segment["resource"] == "gpu:"+destination)) for segment in receipt["segments"]]
            ok, reason = self.reservations.reserve(uid, receipt["segments"], replace=True,
                envelope=(self.policy.envelope_for_interval(destination,
                    min(s["begin"] for s in receipt["segments"]), max(s["end"] for s in receipt["segments"]))
                    if hasattr(self.policy, "envelope_for_interval") else self.policy.document["envelope"])
                    if unknown else None,
                scope="anonymous" if unknown else "physical")
            if not ok:
                continue
            return self._record_migration(uid, receipt, now, physical_checkpoint)
        self._event(uid, now, "RUNNING_STAY", reason=reason)
        return None

    def _record_migration(self, uid, receipt, now, physical_checkpoint, **provenance):
        """Shared existing physical phase transition; no service/budget reset."""
        receipt["episode_id"] = self.ledger.jobs[uid]["episode_id"]
        receipt.update({k:v for k,v in provenance.items() if v is not None})
        self.ledger.in_flight[uid] = receipt
        metadata = self.metadata[uid]
        metadata["migration_count"] += 1
        metadata["cumulative_migration_interruption_seconds"] += receipt["interruption_seconds"]
        self.migrations.append(deepcopy(receipt))
        self._event(uid, now, "CHECKPOINT", physical_checkpoint_seconds=physical_checkpoint,
                    control_checkpoint_seconds=receipt["control_checkpoint_seconds"])
        self._event(uid, now, "SOURCE_WAIT", source=receipt["source"])
        return receipt

    def migration_finished(self, uid, now):
        receipt = self.ledger.in_flight.pop(uid)
        self.ledger.migrate(uid, receipt["destination"], now, receipt,
            lambda value, job: value["completed_at"] == now and value["capability_source_sha"] ==
                self.metadata[uid]["migration_capability"]["source_sha"])
        self.metadata[uid]["current_site"] = receipt["destination"]
        self.audit[uid]["site"] = receipt["destination"]
        self._event(uid, now, "DESTINATION_RUNNING", destination=receipt["destination"])

    def snapshot(self, now):
        return dict(arm=self.arm, at_seconds=now, episode_jobs=deepcopy(self.ledger.jobs),
            used_receipts=sorted(self.ledger.used_receipts), in_flight=deepcopy(self.ledger.in_flight),
            requests={uid: asdict(r) for uid, r in self.requests.items()},
            pending=deepcopy(self.pending), audit=deepcopy(self.audit), metadata=deepcopy(self.metadata),
            observed={uid: asdict(j) for uid, j in self.observed.items()},
            qos_budget_ledger=self.qos.export_ledger(), decisions=deepcopy(self.decisions),
            reservations=self.reservations.snapshot(), reference=self.reference.to_dict(),
            forecast=None if self.forecast is None else dict(q50=list(self.forecast.q50),
                q90=list(self.forecast.q90), day_start=self.forecast.day_start,
                consumed=deepcopy(self.forecast.consumed), submissions=deepcopy(self.forecast.submissions),
                last_event=self.forecast.last_event if math.isfinite(self.forecast.last_event) else None),
            job_event_ledger=deepcopy(self.events), migration_receipts=deepcopy(self.migrations),
            cc4_depletion_ledger=deepcopy(self.cc4_ledger), rule_consumption=deepcopy(self.rule_ledger))

    def restore(self, snapshot):
        if snapshot["arm"] != self.arm:
            raise ValueError("CARRYOUT_ARM_MISMATCH")
        self.ledger.jobs = deepcopy(snapshot["episode_jobs"])
        self.ledger.used_receipts = set(snapshot["used_receipts"])
        self.ledger.in_flight = deepcopy(snapshot["in_flight"])
        self.ledger.last_time = snapshot["at_seconds"]
        self.requests = {uid: JobRequest(**dict(value, compatible=tuple(value["compatible"])))
                         for uid, value in snapshot["requests"].items()}
        self.pending = [tuple(p) for p in snapshot["pending"]]
        heapq.heapify(self.pending)
        self.audit = deepcopy(snapshot["audit"])
        self.metadata = deepcopy(snapshot["metadata"])
        self.observed = {uid: ObservedJob(**dict(value, representation_starts_seconds=tuple(value["representation_starts_seconds"])))
                         for uid, value in snapshot["observed"].items()}
        for uid, observed in self.observed.items():
            self.budgets[uid] = self.qos.issue(observed)
        if self.qos.export_ledger() != snapshot["qos_budget_ledger"]:
            # JSON changes tuples to lists; normalize before comparison.
            if digest(self.qos.export_ledger()) != digest(snapshot["qos_budget_ledger"]):
                raise ValueError("CARRYOUT_QOS_BUDGET_MISMATCH")
        self.decisions = deepcopy(snapshot["decisions"])
        resources = snapshot["reservations"]
        self.reservations.reservations = deepcopy(resources["reservations"])
        self.reservations.audit = deepcopy(resources["audit"])
        self.reference = CausalReferenceScheduler.from_dict(snapshot["reference"])
        if snapshot["forecast"] is not None:
            value = deepcopy(snapshot["forecast"])
            value["consumed"] = {int(k): v for k, v in value["consumed"].items()}
            value["last_event"] = -math.inf if value["last_event"] is None else value["last_event"]
            self.forecast = ForecastBook(**value)
        self.events = deepcopy(snapshot["job_event_ledger"])
        self.migrations = deepcopy(snapshot["migration_receipts"])
        self.cc4_ledger = deepcopy(snapshot["cc4_depletion_ledger"])
        self.rule_ledger = deepcopy(snapshot["rule_consumption"])


def run_actual(capacities, requests, environment, *, arm, qos_window_provider,
               frozen_policy=None, known_schedule=None, running=(), begin=0., end=86400.,
               reference=None, forecast=None, wan_capacities=None, power_model=None,
               weather=None, carryout=None, expected_bindings=None):
    """One independent daily Case or an explicit small carryout continuation."""
    if end <= begin or begin % 900 or end % 900:
        raise ValueError("ACTUAL_CONTROL_GRID_HORIZON")
    if frozen_policy is not None:
        if expected_bindings is not None:
            frozen_policy.require_bindings(expected_bindings)
        if frozen_policy.bindings["case_sha"] != qos_window_provider.case_sha:
            raise ValueError("ACTUAL_QOS_POLICY_CASE_MISMATCH")
    controller = JobEventController(capacities, arm=arm, qos_window_provider=qos_window_provider,
        frozen_policy=frozen_policy, known_schedule=known_schedule, reference=reference,
        forecast=forecast, wan_capacities=wan_capacities)
    if carryout is not None:
        if carryout["controller"]["at_seconds"] != begin:
            raise ValueError("CARRYOUT_TIME_DISCONTINUITY")
        if carryout["case_sha"] != qos_window_provider.case_sha or carryout["policy_sha"] != (None if frozen_policy is None else frozen_policy.sha):
            raise ValueError("CARRYOUT_POLICY_CASE_MISMATCH")
        controller.restore(carryout["controller"])
    simulator = _PrivateService(environment, None if carryout is None else carryout["simulator_only_remaining_compute_seconds"])
    events = []
    counter = 0
    def event(t, kind, payload=None):
        nonlocal counter
        counter += 1
        if begin <= t <= end:
            heapq.heappush(events, (float(t), kind, counter, payload))
    def schedule_compute(uid, now, *, initial_running=False):
        completion, epoch = simulator.start(uid, now, initial_running=initial_running)
        event(completion, 0, (uid, epoch))
        elapsed = controller.metadata[uid]["accumulated_compute_seconds"]
        checkpoint_delay = 1800. - elapsed % 1800.
        event(now + checkpoint_delay, 3, (uid, epoch))
    if carryout is None:
        # Observed initial RUNNING is a pinned historical episode, not a new
        # submission whose reference site can be selected again.
        for request,site,start in sorted(running,key=lambda row:(row[0].submit,row[0].uid)):
            if request.uid not in controller.reference.assigned:
                controller.reference.observe_running(request,site=site,start_seconds=start,
                    event_seconds=begin,elapsed_compute_seconds=float(getattr(request,'metadata',{}).get('elapsed_compute_seconds',begin-start)))
        for request, site, start in sorted(running, key=lambda row: (row[0].submit, row[0].uid)):
            elapsed = float(getattr(request, "metadata", {}).get("elapsed_compute_seconds", begin - start))
            controller.submit(request, begin)
            controller.pending.remove((request.submit, request.uid))
            heapq.heapify(controller.pending)
            controller.ledger.start(request.uid, site, begin, getattr(request,'metadata',{}).get('episode_id','OBSERVED:'+request.uid))
            controller.ledger.jobs[request.uid]["start_time"] = start
            controller.metadata[request.uid].update(state="RUNNING", current_site=site,
                accumulated_compute_seconds=elapsed)
            controller.audit[request.uid].update(admitted_time=start, site=site, capacity_wait_seconds=0.,
                capacity_wait_slots=0, plan_start_seconds=start, intentional_delay_seconds=0.)
            controller.reservations.retain_running(request.uid, site, begin, end, request.gpu)
            schedule_compute(request.uid, begin, initial_running=True)
    else:
        for uid, job in controller.ledger.jobs.items():
            if uid in controller.ledger.in_flight:
                migration = controller.ledger.in_flight[uid]
                for phase in ("transfer_start", "transfer_end", "restart_end"):
                    if migration["times"][phase] > begin:
                        event(migration["times"][phase], 4, (uid, phase))
            elif job["latest_observed_state"] == "RUNNING":
                schedule_compute(uid, begin)
            elif job["latest_observed_state"] == "COMPLETED" and job["release_control_time"] >= begin:
                event(job["release_control_time"], 1, uid)
    for request in requests:
        if request.uid in controller.requests:
            raise ValueError("CARRYOUT_DUPLICATE_SUBMISSION")
        event(max(begin, request.submit), 2, request)
    for t in np.arange(begin, end + 1, 900.):
        event(t, 9)
    sites = sorted(capacities)
    occupancy = np.zeros((int((end-begin)/900), len(sites)))
    compute_occupancy = np.zeros_like(occupancy)
    last = begin
    max_site = np.zeros(len(sites))
    def integrate(a, b):
        use = controller.ledger.physical(a)
        live = [uid for uid, job in controller.ledger.jobs.items()
                if job["latest_observed_state"] == "RUNNING" and uid not in controller.ledger.in_flight]
        simulator.advance(live, b-a)
        compute = {s: 0. for s in sites}
        for uid in live:
            controller.metadata[uid]["accumulated_compute_seconds"] += b-a
            compute[controller.metadata[uid]["current_site"]] += controller.requests[uid].gpu
        values = np.array([use[s] for s in sites], float)
        compute_values = np.array([compute[s] for s in sites], float)
        if np.any(values > np.array([capacities[s] for s in sites]) + 1e-9):
            raise ValueError("ACTUAL_PHYSICAL_CAPACITY_VIOLATION")
        max_site[:] = np.maximum(max_site, values)
        for slot in range(max(0, int((a-begin)//900)), min(len(occupancy), int(math.ceil((b-begin)/900)))):
            overlap = max(0., min(b, begin+(slot+1)*900) - max(a, begin+slot*900))
            occupancy[slot] += values*overlap/900.
            compute_occupancy[slot] += compute_values*overlap/900.
    while events:
        now = events[0][0]
        integrate(last, now)
        last = now
        batch = []
        while events and events[0][0] == now:
            batch.append(heapq.heappop(events))
        for _, kind, _, payload in batch:
            if kind == 0:
                uid, epoch = payload
                if simulator.completion_valid(uid, epoch) and uid not in controller.ledger.in_flight:
                    event(controller.completion(uid, now), 1, uid)
            elif kind == 1:
                controller.reservations.release(payload, now)
                controller._event(payload, now, "GPU_RELEASE_CONTROL")
            elif kind == 2:
                controller.submit(payload, now)
            elif kind == 3:
                uid, epoch = payload
                if simulator.epoch.get(uid) != epoch or controller.metadata[uid]["state"] != "RUNNING":
                    continue
                migration = controller.migration(uid, now, now)
                if migration is not None:
                    simulator.pause(uid)
                    for phase in ("transfer_start", "transfer_end", "restart_end"):
                        event(migration["times"][phase], 4, (uid, phase))
                else:
                    event(now + 1800., 3, (uid, epoch))
            elif kind == 4:
                uid, phase = payload
                if phase == "restart_end":
                    controller.migration_finished(uid, now)
                    schedule_compute(uid, now)
                else:
                    controller._event(uid, now, "TRANSFER" if phase == "transfer_start" else "RESTART")
        for uid, job in controller.ledger.jobs.items():
            if job["latest_observed_state"] == "RUNNING" and uid not in controller.ledger.in_flight:
                controller.reservations.retain_running(uid, job["current_site"], now,
                    math.floor(now/900)*900+900, job["gpu"])
        if now < end:
            for uid in controller.admit(now):
                schedule_compute(uid, now)
            for decision in controller.decisions.values():
                if decision["action"] != "QUEUE" and now < decision["start_seconds"] <= end:
                    event(decision["start_seconds"], 9)
    integrate(last, end)
    for uid, audit in controller.audit.items():
        job = controller.ledger.jobs[uid]
        receipt = controller.budgets[uid]
        meta = controller.metadata[uid]
        if audit["admitted_time"] is None:
            audit["capacity_wait_seconds"] = end - max(controller.requests[uid].submit, begin)
            audit["capacity_wait_slots"] = math.ceil(audit["capacity_wait_seconds"]/900)
        audit.update(carryout=job["latest_observed_state"] != "COMPLETED" or job["release_control_time"] > end,
                     latest_state=job["latest_observed_state"],
                     origin_unknown=meta["origin_unknown"], migration_count=meta["migration_count"],
                     accumulated_compute_seconds=meta["accumulated_compute_seconds"])
        start = audit["admitted_time"]
        actual_wait = (end if start is None else start) - controller.requests[uid].submit
        beyond = max(0., (end if start is None else start) - receipt.latest_start_seconds)
        controller.qos_ledger.append(dict(uid=uid, budget_seconds=receipt.budget_seconds,
            intentional_start_delay_seconds=meta["additional_start_delay_seconds"],
            migration_interruption_seconds=meta["cumulative_migration_interruption_seconds"],
            total_intentional_burden_seconds=meta["additional_start_delay_seconds"] + meta["cumulative_migration_interruption_seconds"],
            actual_wait_seconds=actual_wait, latest_start_excess_seconds=beyond,
            unfinished=job["latest_observed_state"] != "COMPLETED",
            actual_completion_deadline_excess_seconds=(None if meta.get("completion_deadline_seconds") is None
                or job["completion_observed_time"] is None else max(0., job["completion_observed_time"] - meta["completion_deadline_seconds"])),
            window_status=receipt.status))
    carry = dict(case_sha=qos_window_provider.case_sha,
        policy_sha=None if frozen_policy is None else frozen_policy.sha, controller=controller.snapshot(end),
        simulator_only_remaining_compute_seconds=simulator.snapshot(),
        simulator_state_provenance="private realized service; forbidden controller/provider input")
    physical = None if power_model is None else power_model.recompute(occupancy, sites, weather)
    return dict(engine="PR125_COMMON_JOB_EVENT_ACTUAL_V1", arm=arm, sites=sites,
        occupancy_GPU=occupancy, compute_occupancy_GPU=compute_occupancy, physical=physical,
        job_event_ledger=controller.events, reservation_ledger=controller.reservations.snapshot(),
        cc4_depletion_ledger=controller.cc4_ledger, migration_receipts=controller.migrations,
        qos_ledger=controller.qos_ledger, qos_budget_ledger=qos_window_provider.export_ledger(),
        rule_consumption_receipt=controller.rule_ledger, queue_ledger=list(controller.audit.values()), carryout=carry,
        receipt=dict(capacity_violations=0, dropped_jobs=0, submitted_jobs=len(controller.requests),
            completed_jobs=sum(j["latest_observed_state"] == "COMPLETED" for j in controller.ledger.jobs.values()),
            carryout_jobs=sum(a["carryout"] for a in controller.audit.values()),
            max_per_site_GPU=dict(zip(sites, max_site.tolist())),
            actual_compute_GPUh=float(compute_occupancy.sum()/4), actual_occupation_GPUh=float(occupancy.sum()/4),
            anonymous_physical_GPU=0, runtime_reserve_physical_GPU=0,
            optimizer_calls=0, actual_global_reoptimization=0, future_duration_controller_reads=0,
            future_completion_controller_reads=0, actual_power_recomputed=physical is not None,
            planning_power_copied=False, physical_ac_status="NOT_EXECUTED"))


@dataclass(frozen=True)
class FrozenPowerModel:
    """Exact inherited C1 callback with frozen original coefficient authority."""
    idle_kw_per_installed_gpu: float
    swing_kw_per_active_gpu: float
    capacities: dict
    power_factor: float
    c1_exact: object
    authority_sha: str

    def recompute(self, occupancy, sites, weather):
        if not self.authority_sha or not callable(self.c1_exact):
            raise ValueError("FROZEN_C1_POWER_AUTHORITY_REQUIRED")
        if weather is None or len(weather) != len(occupancy) or not 0 < self.power_factor <= 1:
            raise ValueError("ACTUAL_WEATHER_POWER_AXIS")
        installed = np.array([self.capacities[s] for s in sites], float)
        it = self.idle_kw_per_installed_gpu * installed + self.swing_kw_per_active_gpu * occupancy
        p = np.array([self.c1_exact(row, weather[t]) for t, row in enumerate(it)], float)
        if p.shape != occupancy.shape or not np.isfinite(p).all():
            raise ValueError("EXACT_C1_PCC_OUTPUT_AXIS")
        q = p * np.tan(np.arccos(self.power_factor))
        return dict(IT_kw=it, PCC_P_kw=p, PCC_Q_kvar=q, authority_sha=self.authority_sha,
                    IT_recomputed_from_actual_occupation=True, planning_power_copied=False,
                    anonymous_forecast_or_runtime_reserve_added=False)
