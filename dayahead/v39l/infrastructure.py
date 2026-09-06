"""Process identity, durable heartbeat, resume audit, and detached launch helpers.

This module is deliberately outside the DA/Actual/Fresh science path.  It may
inspect existing authorities and checkpoints, but it never constructs or edits
a schedule.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from typing import Any, Iterator, Mapping
import uuid


ARTIFACT_RELATIVE = Path("dayahead/artifacts/v39l_detached_may_resume")
V39K_RELATIVE = Path(
    "dayahead/artifacts/v39k_may23_26_fallback_live_integration/"
    "V39K_PRODUCTION_INTEGRATION_AUTHORITY.json"
)
LOCK_NAME = "V39L_CAMPAIGN_INSTANCE.json"
ORCHESTRATOR_TOKENS = ("run_v39l_detached_may.py", "--scheduled-resume")
LEGACY_ORCHESTRATOR_TOKENS = ("run_v39h_production_close.py", "--resume")
DAY_WORKER_TOKEN = "dayahead.tools.run_v39e_may_day"
DAY_PATTERN = re.compile(r"--day(?:=|\s+)(2025-05-(?:0[1-9]|[12][0-9]|3[01]))")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def durable_atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    """Commit JSON through a flushed temporary file and atomic replacement."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(
        path.suffix + f".{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
    )
    data = (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str)
        + "\n"
    ).encode("utf-8")
    try:
        with temporary.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(300):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == 299:
                    raise
                time.sleep(0.1)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _parse_time(value: str) -> datetime:
    text = str(value)
    legacy = re.fullmatch(r"/Date\((\d+)(?:[+-]\d+)?\)/", text)
    if legacy:
        return datetime.fromtimestamp(int(legacy.group(1)) / 1000.0, tz=timezone.utc)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _process_rows() -> list[dict[str, Any]]:
    command = (
        "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,"
        "CreationDate,Name,ExecutablePath,CommandLine | ConvertTo-Json -Compress -Depth 3"
    )
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    text = completed.stdout.strip().lstrip("\ufeff")
    if not text:
        return []
    payload = json.loads(text)
    return [payload] if isinstance(payload, dict) else list(payload)


def process_inventory(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = _process_rows() if rows is None else rows
    orchestrators: list[dict[str, Any]] = []
    workers: list[dict[str, Any]] = []
    for row in rows:
        command = str(row.get("CommandLine") or "")
        lower = command.lower()
        normalized = {
            "pid": int(row.get("ProcessId") or 0),
            "parent_pid": int(row.get("ParentProcessId") or 0),
            "creation_time_utc": (
                _parse_time(str(row["CreationDate"])).isoformat()
                if row.get("CreationDate") else None
            ),
            "name": row.get("Name"),
            "executable_path": row.get("ExecutablePath"),
            "command_line": command,
        }
        if (
            all(token.lower() in lower for token in ORCHESTRATOR_TOKENS)
            or all(token.lower() in lower for token in LEGACY_ORCHESTRATOR_TOKENS)
        ):
            orchestrators.append(normalized)
        if DAY_WORKER_TOKEN.lower() in lower:
            match = DAY_PATTERN.search(command)
            normalized["day"] = match.group(1) if match else None
            workers.append(normalized)
    by_day: dict[str, list[int]] = {}
    for row in workers:
        by_day.setdefault(str(row.get("day")), []).append(int(row["pid"]))
    duplicates = {day: pids for day, pids in by_day.items() if len(pids) > 1}
    return {
        "captured_at_utc": now_utc(),
        "orchestrators": orchestrators,
        "workers": workers,
        "duplicate_day_worker_pids": duplicates,
        "ACTIVE_AUTHORITATIVE_ORCHESTRATORS": len(orchestrators),
        "DUPLICATE_DAY_WORKERS": sum(len(pids) - 1 for pids in duplicates.values()),
    }


def current_process_identity() -> dict[str, Any]:
    pid = os.getpid()
    for row in _process_rows():
        if int(row.get("ProcessId") or 0) == pid:
            inventory = process_inventory([row])
            records = inventory["orchestrators"]
            if records:
                return records[0]
            return {
                "pid": pid,
                "parent_pid": int(row.get("ParentProcessId") or 0),
                "creation_time_utc": _parse_time(str(row["CreationDate"])).isoformat(),
                "name": row.get("Name"),
                "executable_path": row.get("ExecutablePath"),
                "command_line": row.get("CommandLine"),
            }
    raise RuntimeError(f"V39L_CURRENT_PROCESS_NOT_FOUND:{pid}")


def identity_matches(saved: Mapping[str, Any], live: Mapping[str, Any]) -> bool:
    try:
        creation_delta = abs(
            (_parse_time(str(saved["creation_time_utc"])) -
             _parse_time(str(live["creation_time_utc"]))).total_seconds()
        )
    except (KeyError, TypeError, ValueError):
        return False
    saved_tokens = tuple(saved.get("command_match_tokens") or ORCHESTRATOR_TOKENS)
    command = str(live.get("command_line") or "").lower()
    return (
        int(saved.get("pid") or 0) == int(live.get("pid") or -1)
        and creation_delta <= 2.0
        and all(str(token).lower() in command for token in saved_tokens)
    )


def campaign_fingerprint(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    authority_path = repo / V39K_RELATIVE
    preflight_path = repo / "dayahead/artifacts/v39e_full_may_2025/V39E_FULL_PREFLIGHT.json"
    freeze_root = repo / "dayahead/artifacts/v39e_full_may_2025"
    freeze_shas = {
        path.name: sha256_file(path)
        for path in sorted(freeze_root.glob("V39E_DAYAHEAD_DECISION_FREEZE_*.json"))
    }
    inputs = {
        "authority_path": V39K_RELATIVE.as_posix(),
        "authority_sha256": sha256_file(authority_path),
        "preflight_sha256": sha256_file(preflight_path),
        "freeze_count": len(freeze_shas),
        "freeze_manifest_sha256": canonical_sha256(freeze_shas),
    }
    return {**inputs, "campaign_fingerprint_sha256": canonical_sha256(inputs)}


def validate_v39k(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    path = repo / V39K_RELATIVE
    authority = read_json(path)
    expected = {
        "2025-05-23": 4,
        "2025-05-24": 2,
        "2025-05-25": 8,
        "2025-05-26": 15,
    }
    observed: dict[str, int | None] = {}
    for day, count in expected.items():
        relative = authority.get("selective_preflight_certificate_paths", {}).get(day)
        certificate = read_json(repo / relative) if relative else {}
        observed[day] = certificate.get("migration_count")
    status = (
        authority.get("status") == "PASS"
        and authority.get("authority_kind") == "V39K_CERTIFIED_FALLBACK_PRODUCTION_AUTHORITY"
        and all(observed[day] == count for day, count in expected.items())
        and authority.get("minimum_RUNNING_migrations") == 105
        and authority.get("RUNNING_migration_days") == 12
    )
    return {
        "status": "PASS" if status else "FAIL",
        "authority": "V39K",
        "authority_path": V39K_RELATIVE.as_posix(),
        "authority_sha256": sha256_file(path),
        "May17_retained": "MAY17_REPAIR_REUSED" in str(authority.get("policy", "")),
        "fallback_migrations": observed,
        "minimum_RUNNING_migrations": authority.get("minimum_RUNNING_migrations"),
        "RUNNING_migration_days": authority.get("RUNNING_migration_days"),
    }


def protected_may01_12(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    base = repo / "dayahead/artifacts/v39e_full_may_2025"
    files: dict[str, dict[str, Any]] = {}
    for number in range(1, 13):
        day = f"2025-05-{number:02d}"
        for path in (
            base / "dates" / f"{day}.json",
            base / "certificates" / f"V39E_MAY_DAY_CERTIFICATE_{day}.json",
        ):
            stat = path.stat()
            files[path.relative_to(repo).as_posix()] = {
                "sha256": sha256_file(path),
                "bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
    return files


def verify_protected_may01_12(
    repo: Path, before: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    after = protected_may01_12(repo)
    changed = {
        path: {"before": dict(before[path]), "after": after.get(path)}
        for path in before if after.get(path) != dict(before[path])
    }
    return {
        "status": "PASS" if not changed and len(after) == 24 else "FAIL",
        "file_count": len(after),
        "changed": changed,
        "COMPLETED_MAY01_12_RERUN": 0 if not changed else None,
        "COMPLETED_MAY01_12_INVALIDATED": 0 if not changed else None,
        "before": dict(before),
        "after": after,
    }


def audit_may13_16(repo: Path) -> dict[str, Any]:
    """Apply the runner's exact checkpoint validator without running a case."""

    repo = repo.resolve()
    from dayahead.v39e.campaign_adapter import build_day, configure_v37_runner, freeze_path

    runner = configure_v37_runner()
    days: dict[str, Any] = {}
    unit_by_case = {"B0": 2, "B1": 4, "B2": 9, "B3": 14}
    for number in range(13, 17):
        day = f"2025-05-{number:02d}"
        status_path = repo / runner.STATUS_ROOT / f"{day}.json"
        status = read_json(status_path)
        objects: list[dict[str, Any]] = []
        last_valid_unit = 0
        last_valid_case = None
        latest_checkpoint_mtime_ns = 0
        da_shas: dict[str, str] = {}
        for case in runner.OFFICIAL_CASES:
            freeze = freeze_path(repo, day, case)
            da_shas[case] = sha256_file(freeze)
            trajectory = build_day(repo, day, case)
            fingerprint = runner.case_execution_fingerprint(repo, day, case, trajectory)
            checkpoint = runner._checkpoint_path(repo, day, case)
            valid = runner._valid_case_checkpoint(repo, day, case, fingerprint)
            if checkpoint.is_file():
                latest_checkpoint_mtime_ns = max(
                    latest_checkpoint_mtime_ns, checkpoint.stat().st_mtime_ns
                )
            classification = (
                "REUSABLE_VALID" if valid is not None
                else "STALE_INVALID" if checkpoint.is_file()
                else "INCOMPLETE_NONAUTHORITATIVE"
            )
            if valid is not None and unit_by_case[case] > last_valid_unit:
                last_valid_unit = unit_by_case[case]
                last_valid_case = case
            checkpoint_payload = read_json(checkpoint) if checkpoint.is_file() else {}
            result = checkpoint_payload.get("result", {})
            objects.append({
                "object": f"case_checkpoint:{case}",
                "path": checkpoint.relative_to(repo).as_posix(),
                "classification": classification,
                "current_execution_fingerprint_sha256": fingerprint[
                    "execution_fingerprint_sha256"
                ],
                "saved_execution_fingerprint_sha256": checkpoint_payload.get(
                    "execution_fingerprint_sha256"
                ),
                "DA_authority_SHA256": da_shas[case],
                "candidate_cache_fingerprint": fingerprint.get("candidate_table_SHA"),
                "Fresh_schedule_SHA256": result.get("Fresh_schedule_SHA256"),
                "restoration_resume_fingerprint_sha256": result.get(
                    "restoration_resume_fingerprint_sha256"
                ),
            })

        partial_roots = [
            repo / runner.CACHE_ROOT / runner.PASS_ID / "beam",
            repo / runner.CACHE_ROOT / runner.PASS_ID / "fresh" / day,
            repo / runner.CACHE_ROOT / runner.PASS_ID / "restoration" / day,
        ]
        partial_files = []
        for root in partial_roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_file() and (day in path.as_posix() or root.name == day):
                    partial_files.append(path)
        later_partial = [
            path.relative_to(repo).as_posix() for path in partial_files
            if path.stat().st_mtime_ns > latest_checkpoint_mtime_ns
        ]
        objects.append({
            "object": "interrupted_day_state",
            "path": status_path.relative_to(repo).as_posix(),
            "classification": "INCOMPLETE_NONAUTHORITATIVE",
            "reported_major_units": status.get("completed_units"),
            "reported_stage": status.get("stage"),
            "partial_files_after_last_valid_checkpoint": len(later_partial),
            "partial_file_examples": sorted(later_partial)[:25],
        })
        reusable = [
            item["object"].split(":", 1)[1] for item in objects
            if item["object"].startswith("case_checkpoint:")
            and item["classification"] == "REUSABLE_VALID"
        ]
        days[day] = {
            "resume_classification": "INCOMPLETE_NONAUTHORITATIVE",
            "day_PASS": False,
            "last_reported_major_unit": status.get("completed_units"),
            "last_reported_stage": status.get("stage"),
            "last_valid_major_unit": last_valid_unit,
            "last_valid_case_checkpoint": last_valid_case,
            "reusable_case_checkpoints": reusable,
            "DA_freeze_file_SHA256": da_shas,
            "partial_output_after_last_valid_checkpoint": bool(later_partial),
            "objects": objects,
        }
    return {
        "artifact_id": "V39L_MAY13_16_CHECKPOINT_AUDIT_V1",
        "status": "PASS",
        "audited_at_utc": now_utc(),
        "method": "V37 _valid_case_checkpoint exact fingerprint and file-hash validation",
        "optimization_calls": 0,
        "days": days,
    }


def write_exclusive_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
        os.write(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def authoritative_instance(repo: Path) -> Iterator[dict[str, Any]]:
    repo = repo.resolve()
    root = repo / ARTIFACT_RELATIVE
    lock_path = root / LOCK_NAME
    own = current_process_identity()
    own["command_match_tokens"] = list(ORCHESTRATOR_TOKENS)
    token = uuid.uuid4().hex
    inventory = process_inventory()
    others = [row for row in inventory["orchestrators"] if row["pid"] != os.getpid()]
    if others or inventory["DUPLICATE_DAY_WORKERS"]:
        raise RuntimeError(
            f"V39L_DUPLICATE_PROTECTION:{len(others)}:"
            f"{inventory['DUPLICATE_DAY_WORKERS']}"
        )
    if lock_path.is_file():
        try:
            saved = read_json(lock_path)
            live = next(
                (row for row in inventory["orchestrators"]
                 if row["pid"] == int(saved.get("pid") or -1)),
                None,
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            saved, live = {}, None
        if live is not None and identity_matches(saved, live):
            raise RuntimeError(f"V39L_LIVE_INSTANCE_LOCK:{saved.get('pid')}")
        stale = root / f"V39L_STALE_INSTANCE_{int(time.time())}.json"
        os.replace(lock_path, stale)
    lock = {
        **own,
        "token": token,
        "acquired_at_utc": now_utc(),
        "campaign_fingerprint": campaign_fingerprint(repo),
    }
    write_exclusive_json(lock_path, lock)
    try:
        yield lock
    finally:
        try:
            saved = read_json(lock_path)
            if saved.get("token") == token:
                lock_path.unlink()
        except (OSError, ValueError, json.JSONDecodeError):
            pass


def register_one_shot_task(task_name: str, command_path: Path) -> dict[str, Any]:
    start = (datetime.now() + timedelta(minutes=2)).strftime("%H:%M")
    action = f'cmd.exe /d /c "{command_path.resolve()}"'
    create = subprocess.run(
        ["schtasks.exe", "/Create", "/TN", task_name, "/TR", action,
         "/SC", "ONCE", "/ST", start, "/F"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30,
    )
    if create.returncode:
        raise RuntimeError(f"V39L_TASK_CREATE:{create.returncode}:{create.stderr}:{create.stdout}")
    escaped_name = task_name.replace("'", "''")
    settings_script = (
        "$s=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries "
        "-DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) "
        "-MultipleInstances IgnoreNew;"
        f"Set-ScheduledTask -TaskName '{escaped_name}' -Settings $s | Out-Null"
    )
    settings = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", settings_script],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    if settings.returncode:
        delete_task_registration(task_name)
        raise RuntimeError(
            f"V39L_TASK_SETTINGS:{settings.returncode}:{settings.stderr}:{settings.stdout}"
        )
    return {
        "task_name": task_name,
        "task_action": action,
        "registration_stdout": create.stdout.strip(),
        "allow_start_on_batteries": True,
        "do_not_stop_on_battery_transition": True,
        "execution_time_limit": "PT0S",
        "multiple_instances": "IgnoreNew",
        "registered_at_utc": now_utc(),
    }


def run_task_from_terminating_shell(
    task_name: str, launcher_record: Path,
) -> dict[str, Any]:
    escaped_task = task_name.replace("'", "''")
    escaped_record = str(launcher_record.resolve()).replace("'", "''")
    script = (
        f"$r=[ordered]@{{launcher_pid=$PID;started_at_utc="
        "[DateTime]::UtcNow.ToString('o')};"
        f"$r|ConvertTo-Json|Set-Content -LiteralPath '{escaped_record}' -Encoding UTF8;"
        f"schtasks.exe /Run /TN '{escaped_task}'; exit $LASTEXITCODE"
    )
    process = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )
    stdout, stderr = process.communicate(timeout=30)
    if process.returncode:
        raise RuntimeError(f"V39L_TASK_RUN:{process.returncode}:{stderr}:{stdout}")
    record = read_json(launcher_record)
    record.update({
        "initiating_shell_exit_code": process.returncode,
        "initiating_shell_exited": True,
        "initiating_shell_exited_at_utc": now_utc(),
        "run_stdout": stdout.strip(),
    })
    return record


def delete_task_registration(task_name: str) -> None:
    subprocess.run(
        ["schtasks.exe", "/Delete", "/TN", task_name, "/F"],
        capture_output=True, timeout=30,
    )


__all__ = [
    "ARTIFACT_RELATIVE", "ORCHESTRATOR_TOKENS", "audit_may13_16",
    "authoritative_instance", "campaign_fingerprint", "current_process_identity",
    "delete_task_registration", "durable_atomic_json", "identity_matches", "now_utc",
    "process_inventory", "protected_may01_12", "read_json", "register_one_shot_task",
    "run_task_from_terminating_shell", "sha256_file", "validate_v39k",
    "verify_protected_may01_12",
]
