"""One lightweight, read-only V40C health observation plus JSONL ledger append."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

import psutil


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v39l.infrastructure import identity_matches, process_inventory
from dayahead.v40b.common import ROOT, read, now_utc
from dayahead.v40b.supervision import inventory


METHOD_SHA = "9af44cb41650c0e3c5643800f6600a4f8e91bb213a775a12b8d4cc47560b584a"
LEDGER = ROOT / "V40C_OVERNIGHT_SUPERVISION.jsonl"
INCIDENTS = ROOT / "incidents"


def _age_seconds(value: str) -> float:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds())


def _last_observation() -> dict[str, Any] | None:
    if not LEDGER.exists():
        return None
    lines = [line for line in LEDGER.read_text(encoding="utf-8").splitlines() if line.strip()]
    return json.loads(lines[-1]) if lines else None


def _process_cpu(pid: int) -> float | None:
    try:
        times = psutil.Process(pid).cpu_times()
        return round(float(times.user + times.system), 3)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def _known_scientific_failures() -> set[str]:
    """Return preserved fail-closed dates that need no repeated retry alert."""
    known: set[str] = set()
    if not INCIDENTS.exists():
        return known
    for path in INCIDENTS.glob("*/V40C_INCIDENT_*_DISPOSITION.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            if (
                payload.get("status") == "PRESERVED_SCIENTIFIC_FAILURE"
                and payload.get("retry_permitted") is False
                and payload.get("SCIENCE_CHANGED") == "NO"
            ):
                known.add(str(payload["known_fail_closed_date"]))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue
    return known


def _progress_detail(day: str, outer: dict[str, Any]) -> dict[str, Any]:
    detail = {
        "case": outer.get("case"),
        "stage": outer.get("current_stage"),
        "completed_units": outer.get("completed_units"),
        "total_units": outer.get("total_units"),
    }
    solver = outer.get("solver_detail") or {}
    if solver:
        detail["solver_detail"] = {
            key: solver.get(key) for key in (
                "event", "mess_index", "parent_index", "parent_total",
                "search_level", "candidate_done", "candidate_total",
                "seed_done", "seed_total", "full_milp_status", "OpenDSS_slot",
            ) if solver.get(key) is not None
        }
    if outer.get("case") in ("B0", "B1", "B2"):
        path = ROOT / "baseline_status" / f"{day}.json"
        if path.exists():
            baseline = read(path)
            # A pre-retry status must not be attributed to the new worker.
            try:
                current = datetime.fromisoformat(str(baseline["last_update"]).replace("Z", "+00:00"))
                started = datetime.fromisoformat(str(outer["worker_creation_time_utc"]).replace("Z", "+00:00"))
                valid = baseline.get("date") == day and baseline.get("case") == outer.get("case") and current >= started
            except (KeyError, TypeError, ValueError):
                valid = False
            if valid:
                detail["baseline_detail"] = {
                    key: baseline.get(key) for key in (
                        "current_stage", "mess_index", "beam_parent_index", "beam_parent_total",
                        "search_level", "candidate_done", "candidate_total", "seed_done",
                        "seed_total", "full_milp_status", "last_update",
                    ) if baseline.get(key) is not None
                }
    return detail


def observe() -> dict[str, Any]:
    progress = read(ROOT / "V40A_MAY_PROGRESS.json")
    execution = read(ROOT / "V40B_EXECUTION_FREEZE.json")
    current = inventory()
    if (ROOT / 'USER_PAUSE.json').exists():
        unexpected = bool(current['orchestrators'] or current['workers'])
        return {'timestamp': now_utc(), 'campaign_status': 'PAUSED_BY_USER',
                'completed_days': len(progress.get('completed_days', [])),
                'running_days': [], 'failed_days': progress.get('failed_days', []),
                'active_worker_count': len(current['workers']),
                'incident_detected': unexpected,
                'issues': ['PROCESS_RUNNING_DURING_USER_PAUSE'] if unexpected else [],
                'action_taken': 'RESPECT_USER_PAUSE_NO_RESTART'}
    old = process_inventory()
    previous = _last_observation()
    issues: list[str] = []
    failed_days = {str(day) for day in progress.get("failed_days", [])}
    known_scientific_failures = _known_scientific_failures()
    unknown_failed_days = failed_days - known_scientific_failures

    if progress.get("method_SHA") != METHOD_SHA:
        issues.append("METHOD_SHA_MISMATCH")
    if progress.get("execution_SHA") != execution.get("execution_SHA"):
        issues.append("EXECUTION_SHA_MISMATCH")
    if unknown_failed_days:
        issues.append("FAILED_DAYS_PRESENT")
    if progress.get("status") == "FAIL":
        issues.append("CAMPAIGN_TERMINAL_FAIL")
    if len(current["orchestrators"]) != 1:
        issues.append("ORCHESTRATOR_COUNT")
    else:
        expected = {
            "pid": progress.get("orchestrator_pid"),
            "creation_time_utc": progress.get("orchestrator_creation_time_utc"),
            "command_match_tokens": progress.get("orchestrator_command_match_tokens"),
        }
        if not identity_matches(expected, current["orchestrators"][0]):
            issues.append("ORCHESTRATOR_IDENTITY")
    heartbeat_age = _age_seconds(progress.get("heartbeat_timestamp_utc") or progress.get("last_update"))
    if heartbeat_age > 45:
        issues.append("ORCHESTRATOR_STALE")

    workers = current["workers"]
    days = [str(row.get("day")) for row in workers]
    if len(workers) > 4:
        issues.append("TOO_MANY_WORKERS")
    if len(days) != len(set(days)):
        issues.append("DUPLICATE_DAY_WORKER")
    if set(days) != set(progress.get("running_days", [])):
        issues.append("WORKER_PROGRESS_SET_MISMATCH")
    if old["orchestrators"] or old["workers"]:
        issues.append("OLD_SEQUENTIAL_CAMPAIGN_RUNNING")

    day_rows: dict[str, Any] = {}
    for worker in workers:
        day = str(worker["day"])
        status_path = ROOT / "status" / f"{day}.json"
        if not status_path.exists():
            issues.append(f"MISSING_STATUS:{day}")
            continue
        status = read(status_path)
        expected = {
            "pid": status.get("worker_pid"),
            "creation_time_utc": status.get("worker_creation_time_utc"),
            "command_match_tokens": ["run_v40b_campaign.py", "--day", day],
        }
        if not identity_matches(expected, worker):
            issues.append(f"WORKER_IDENTITY:{day}")
        age = _age_seconds(status.get("heartbeat_timestamp_utc"))
        if age > 45:
            issues.append(f"WORKER_STALE:{day}")
        if status.get("status") != "RUNNING":
            issues.append(f"WORKER_STATUS:{day}:{status.get('status')}")
        if status.get("method_SHA") != METHOD_SHA:
            issues.append(f"WORKER_METHOD_SHA:{day}")
        failure = ROOT / "days" / day / "FAILURE.json"
        if failure.exists():
            issues.append(f"CURRENT_FAILURE_FILE:{day}")
        day_rows[day] = {
            "pid": worker["pid"],
            "creation_time_utc": worker["creation_time_utc"],
            "heartbeat_age_seconds": round(age, 1),
            "cpu_seconds": _process_cpu(worker["pid"]),
            **_progress_detail(day, status),
        }

    matrix = read(ROOT / "V40B_MAY_EXECUTION_MATRIX.json")["rows"]
    case_counts: dict[str, dict[str, int]] = {}
    for row in matrix:
        case = str(row["case"])
        state = str(row["status"])
        case_counts.setdefault(case, {})[state] = case_counts.setdefault(case, {}).get(state, 0) + 1
        if case == "B3" and state == "REUSE_CERTIFIED":
            issues.append("OLD_B3_REUSE_SELECTED")

    # One unchanged stage can be valid for a long full MILP. Escalate only after
    # two observations with neither progress signature nor meaningful CPU work.
    if previous and _age_seconds(previous["timestamp"]) >= 540:
        for day, row in day_rows.items():
            before = (previous.get("days_and_stages") or {}).get(day)
            if not before:
                continue
            signature = json.dumps({k: row.get(k) for k in ("case", "stage", "completed_units", "solver_detail", "baseline_detail")}, sort_keys=True)
            old_signature = json.dumps({k: before.get(k) for k in ("case", "stage", "completed_units", "solver_detail", "baseline_detail")}, sort_keys=True)
            old_cpu, new_cpu = before.get("cpu_seconds"), row.get("cpu_seconds")
            if signature == old_signature and old_cpu is not None and new_cpu is not None and new_cpu - old_cpu < 1.0:
                if before.get("no_progress_observations", 0) >= 1:
                    issues.append(f"POSSIBLE_STALL:{day}")
                row["no_progress_observations"] = int(before.get("no_progress_observations", 0)) + 1
            else:
                row["no_progress_observations"] = 0

    memory_available_mb = round(psutil.virtual_memory().available / 1024**2)
    disk_free_gb = round(psutil.disk_usage(str(REPO.anchor)).free / 1024**3, 2)
    if disk_free_gb < 5:
        issues.append("LOW_DISK")
    if memory_available_mb < 1024:
        issues.append("LOW_MEMORY")

    if issues:
        action = "EVIDENCE_AND_ROOT_CAUSE_REQUIRED"
    elif failed_days:
        action = "KNOWN_SCIENTIFIC_FAILURE_PRESERVED_CONTINUE_UNRELATED"
    else:
        action = "NONE_HEALTHY"

    return {
        "timestamp": now_utc(),
        "campaign_status": progress.get("status"),
        "completed_days": len(progress.get("completed_days", [])),
        "running_days": list(progress.get("running_days", [])),
        "failed_days": list(progress.get("failed_days", [])),
        "known_scientific_failures": sorted(failed_days & known_scientific_failures),
        "unknown_failed_days": sorted(unknown_failed_days),
        "orchestrator_alive": len(current["orchestrators"]) == 1,
        "orchestrator_pid": progress.get("orchestrator_pid"),
        "orchestrator_creation_time_utc": progress.get("orchestrator_creation_time_utc"),
        "heartbeat_sequence": progress.get("heartbeat_sequence"),
        "heartbeat_age_seconds": round(heartbeat_age, 1),
        "active_worker_count": len(workers),
        "days_and_stages": day_rows,
        "case_counts": case_counts,
        "method_SHA": progress.get("method_SHA"),
        "execution_SHA": progress.get("execution_SHA"),
        "MAY_RESULT_BASED_TUNING": 0 if execution.get("May_result_based_tuning_allowed") is False else 1,
        "disk_free_gb": disk_free_gb,
        "memory_available_mb": memory_available_mb,
        "incident_detected": bool(issues),
        "issues": sorted(set(issues)),
        "action_taken": action,
    }


def main() -> int:
    observation = observe()
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(observation, sort_keys=True) + "\n")
        stream.flush()
    print(json.dumps(observation, indent=2, sort_keys=True))
    return 2 if observation["incident_detected"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
