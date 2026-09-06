"""Forensic search for preexisting site authority, with explicit scope checks.

Sibling-case or prior-version placements are evidence candidates, not an
automatic assignment authority for a different frozen schedule.
"""
from collections import Counter
from datetime import datetime,timedelta
import json
from pathlib import Path
import re
import subprocess
import pandas as pd
import pyarrow.parquet as pq
from dayahead.paper_analysis.storage import read, sha, reference, atomic, write_json, write_parquet
from .inputs import legacy_digest

SITE_FIELDS = ("initial_site", "origin_site", "baseline_site", "authoritative_site", "current_site", "home_site",
    "placement_site", "selected_site", "AIDC_site", "pre_day_site", "destination_AIDC", "initial_AIDC",
    "current_AIDC", "source_AIDC", "AIDC", "AIDC_id", "aidc_id", "AIDC_id_initial")


def normalized_site(value):
    if not isinstance(value, str):
        return None
    if re.fullmatch(r"AIDC\d{2}", value):
        return value
    # Historical IDC labels map explicitly to the same AIDC numbering in current adapters.
    if re.fullmatch(r"IDC\d{2}", value):
        return "A" + value
    return None


def records(value, wanted, pointer="", inherited_uid=None):
    if isinstance(value, dict):
        uid = next((str(value[k]) for k in ("job_uid", "job_id", "id") if k in value and str(value[k]) in wanted), inherited_uid)
        if uid in wanted:
            for field in SITE_FIELDS:
                site = normalized_site(value.get(field))
                if site:
                    yield {"job_uid": uid, "site": site, "field": field, "pointer": pointer,
                           "record_state": value.get("state_at_issue"), "record_date": value.get("operating_day", value.get("date"))}
        for k, v in value.items():
            if k in wanted and normalized_site(v):
                yield {"job_uid": k, "site": normalized_site(v), "field": "UID_KEYED_SITE", "pointer": pointer+"/"+k}
            elif isinstance(v, (dict, list)):
                yield from records(v, wanted, pointer+"/"+str(k), str(k) if k in wanted else uid)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from records(v, wanted, pointer+"/"+str(i), inherited_uid)


def run(repo, output):
    repo, output = Path(repo), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    audit = repo / "dayahead/artifacts/v40d_actual_realized_replay"
    failed = pd.read_parquet(audit / "pre_day_complete_preflight/PRE_DAY_COMPLETE_CLASSIFICATIONS.parquet")
    failed = failed[failed.status.ne("PRE_DAY_COMPLETE")].copy()
    wanted = set(failed.job_uid.astype(str))
    query = output / "FAILED_JOB_UIDS.txt"
    with atomic(query) as f:
        f.write(("\n".join(sorted(wanted))+"\n").encode())
    roots = [repo / "dayahead/artifacts", repo / "frozen_artifacts", repo / "dayahead/cache"]
    # Include the actual historical repository roots referenced by certified baseline files.
    bindings = read(audit / "V40D_ACTUAL_DECISION_BINDING_AUDIT.json")["cases"]
    for b in bindings:
        if b["case"] != "B3":
            p = Path(b["MESS_final_source"])
            ancestor = next((q for q in p.parents if q.name == "frozen_artifacts"), None)
            if ancestor is not None and ancestor not in roots:
                roots.append(ancestor)
    command = ["rg", "-l", "-F", "-f", str(query), "-g", "*.json",
               "-g", "!**/v40d_actual_realized_replay/**", "-g", "!**/paper_analysis_observability/**",
               "-g", "!**/v40a_bounded_iterative_aidc_mess_coopt/days/2025-05-*/**"] + [str(p) for p in roots if p.exists()]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode not in (0, 1):
        raise RuntimeError("SITE_AUTHORITY_SEARCH_FAILURE:" + result.stderr[:1500])
    paths = sorted({Path(p) for p in result.stdout.splitlines() if p})
    candidates, inventory, errors = [], [], []
    frozen_causal = {}
    for i, p in enumerate(paths):
        try:
            x = read(p)
            hits = list(records(x, wanted))
            if not hits:
                continue
            ref = reference(p)
            decision = x.get("decision", {}) if isinstance(x, dict) else {}
            is_freeze = bool(isinstance(x, dict) and x.get("SHA_created_before_Actual_namespace") is True
                and decision.get("status") == "PASS" and x.get("DA_decision_SHA256")==legacy_digest(decision))
            day = decision.get("operating_day")
            case = decision.get("case")
            if not day:
                m = re.search(r"2025-0[45]-\d{2}", str(p))
                day = m.group() if m else None
            if not case:
                m = re.search(r"(?:_|[\\/])(B[0-3])(?:\.|[\\/])", str(p))
                case = m.group(1) if m else None
            inventory.append({**ref, "matching_site_records": len(hits), "decision_date": day,
                "decision_case": case, "explicit_pre_actual_freeze": is_freeze})
            for hit in hits:
                candidates.append({**hit, "artifact": str(p), "artifact_sha": ref["sha256"],
                    "date": day, "case": case, "explicit_pre_actual_freeze": is_freeze,
                    "temporal_mode": decision.get("temporal_mode"),
                    "authority_scope": "CASE_SPECIFIC_D_DAY_ACTIVE_JOB_PLACEMENT" if is_freeze else "UNPROVEN_PRIOR_OR_DIAGNOSTIC_CONTEXT"})
        except (ValueError, OSError) as e:
            errors.append({"path": str(p), "error": repr(e)})
        if i % 100 == 0:
            print(f"Site JSON scan {i}/{len(paths)}", flush=True)
    # Inspect all Parquet schemas in the searched repository artifact/cache roots.
    parquet_paths = set()
    for root in roots:
        parquet_paths.update(root.rglob("*.parquet"))
    inspected = 0
    for p in sorted(parquet_paths):
        if "v40d_actual_realized_replay" in str(p) or "paper_analysis_observability" in str(p):
            continue
        if "v40a_bounded_iterative_aidc_mess_coopt" in str(p) and "2025-05-" in str(p):
            continue
        try:
            names = pq.read_schema(p).names
            uid_field = next((k for k in ("job_uid", "job_id", "id") if k in names), None)
            fields = [k for k in SITE_FIELDS if k in names]
            inspected += 1
            if uid_field is None or not fields:
                continue
            frame = pd.read_parquet(p, columns=list(dict.fromkeys([uid_field]+fields+[k for k in ("operating_day", "date", "case", "state_at_issue") if k in names])))
            frame = frame[frame[uid_field].astype(str).isin(wanted)]
            if not len(frame):
                continue
            ref = reference(p)
            inventory.append({**ref, "matching_job_rows": len(frame), "explicit_pre_actual_freeze": False})
            for r in frame.to_dict("records"):
                for hit in records(r, wanted):
                    candidates.append({**hit, "artifact": str(p), "artifact_sha": ref["sha256"],
                        "date": r.get("operating_day", r.get("date")), "case": r.get("case"),
                        "explicit_pre_actual_freeze": False, "authority_scope": "PARQUET_WITNESS_REQUIRES_PARENT_FREEZE_BINDING"})
        except (OSError, ValueError) as e:
            errors.append({"path": str(p), "error": repr(e)})
    frame = pd.DataFrame(candidates)
    write_parquet(output / "SITE_CANDIDATE_EVIDENCE.parquet", frame)
    write_json(output / "SITE_SEARCH_INVENTORY.json", {"roots": list(map(str, roots)), "JSON_UID_matching_files": len(paths),
        "Parquet_schemas_inspected": inspected, "candidate_source_files": inventory, "errors": errors})
    results = []
    for r in failed.to_dict("records"):
        uid, day, case = r["job_uid"], r["day"], r["case"]
        hits = frame[(frame.job_uid == uid) & (frame.date == day)] if len(frame) else pd.DataFrame()
        # An old/spatially different schedule is not silently promoted to this method's authority.
        binding = next(b for b in bindings if b["day"] == day and b["case"] == case)
        current_source = Path(binding["AIDC_decision_source"])
        accepted_candidates = hits[hits.artifact.eq(str(current_source))] if len(hits) else hits
        if case == "B3" and len(hits):
            a0_source = current_source.parent / "A0_AUTHORITY.json"
            accepted_candidates = hits[hits.artifact.isin([str(current_source), str(a0_source)])]
        # Only the job's own assignment/current initial state is eligible; unrelated ancestor fields are excluded.
        if len(accepted_candidates):
            accepted_candidates = accepted_candidates[accepted_candidates.field.isin(["AIDC_site", "destination_AIDC", "initial_AIDC", "UID_KEYED_SITE"])]
        sites = sorted(set(accepted_candidates.site)) if len(accepted_candidates) else []
        recovered = len(sites) == 1 and bool(accepted_candidates.explicit_pre_actual_freeze.all())
        causal = hits[hits.explicit_pre_actual_freeze.eq(True)] if len(hits) else hits
        exemplar = accepted_candidates.iloc[0] if recovered else causal.iloc[0] if len(causal) else hits.iloc[0] if len(hits) else None
        results.append({"job_uid": uid, "date": day, "case": case,
            "planned_start": r["planned_start_slot"], "planned_end": r["planned_end_slot"],
            "realized_end": r["observed_end"], "D_day_overlap_seconds": r["observed_overlap_seconds"],
            "final_export_site": "UNASSIGNED", "upstream_site_found": bool(len(hits)),
            "upstream_site": sites[0] if recovered else None,
            "upstream_candidate_sites": sorted(set(hits.site)) if len(hits) else [],
            "upstream_site_artifact": None if exemplar is None else exemplar.artifact,
            "upstream_site_sha": None if exemplar is None else exemplar.artifact_sha,
            "site_authority_time": ((datetime.fromisoformat(day)-timedelta(hours=6)).isoformat()+"+10:00") if recovered else None,
            "D1_information_cutoff": (datetime.fromisoformat(day)-timedelta(hours=6)).isoformat()+"+10:00",
            "site_authority_time_basis":"D1_INFORMATION_CUTOFF_NOT_FILESYSTEM_MTIME" if recovered else "NO_RECOVERABLE_AUTHORITY",
            "site_authority_is_D1_causal": bool(recovered and exemplar.explicit_pre_actual_freeze),
            "same_day_preexisting_comparator_site_found": bool(len(causal)),
            "site_authority_recovery_status": "RECOVERED_PREEXISTING_AUTHORITY" if recovered else "MISSING_PRE_DAY_SPATIAL_EXECUTION_AUTHORITY",
            "scope_note": "Other case/old-version D-day placements do not define this frozen schedule's pre-D00 site",
            "new_site_assignment_performed": False})
    table = pd.DataFrame(results)
    write_parquet(output / "V40D_UNASSIGNED_SPILLOVER_SITE_AUTHORITY_AUDIT.parquet", table)
    with atomic(output / "V40D_UNASSIGNED_SPILLOVER_SITE_AUTHORITY_AUDIT.csv") as f:
        f.write(table.to_csv(index=False).encode("utf-8-sig"))
    recovered = table[table.site_authority_recovery_status.eq("RECOVERED_PREEXISTING_AUTHORITY")]
    unresolved = table[table.site_authority_recovery_status.ne("RECOVERED_PREEXISTING_AUTHORITY")]
    summary = {"status": "PASS" if not len(unresolved) and not errors else "BLOCKED", "failed_unique_jobs_audited": len(wanted),
        "failed_case_job_rows": len(table), "recovered_case_job_rows": len(recovered), "recovered_unique_jobs": recovered.job_uid.nunique(),
        "unrecoverable_case_job_rows": len(unresolved), "unrecoverable_unique_jobs": unresolved.job_uid.nunique(),
        "blocked_cases_remaining": len(unresolved[["date", "case"]].drop_duplicates()),
        "upstream_candidate_rows_found": int(table.upstream_site_found.sum()),
        "same_day_preexisting_comparator_site_rows_found": int(table.same_day_preexisting_comparator_site_found.sum()),
        "candidate_records": len(frame), "search_errors": errors,
        "all_44_cases_resolved_without_new_spatial_science": not len(unresolved),
        "PRE_DAY_COMPLETE_exception_expanded": False, "new_pre_day_authority_executed": False,
        "full_Actual_campaign_authorized": False, "full_Actual_campaign_launched": False,
        "normative_stages": {"CURRENT_A0": "initial accepted AIDC (paper A1)", "CURRENT_M1": "first MESS search (paper M1)",
            "CURRENT_A1": "accepted AIDC feedback (paper A2)", "CURRENT_MF": "fixed-route electrical refinement (paper M2); Actual uses final AC-accepted P/Q"}}
    write_json(output / "V40D_UNASSIGNED_SPILLOVER_SITE_AUTHORITY_SUMMARY.json", summary)
    return summary
