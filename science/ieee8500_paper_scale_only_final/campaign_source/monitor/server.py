"""Read-only monitor for the frozen paper-PCC final May-1 campaign."""
from __future__ import annotations

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
RUN = HERE.parent
ORDER = ("B0", "B2", "B1", "B3")


def read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def result(policy: str):
    folder = RUN / policy
    exact_paths = {
        "B0": folder / "DA_exact/AC_VALIDATION.json",
        "B2": folder / "independent_clean_exact/AC_VALIDATION.json",
        "B3": folder / "final_exact/AC_VALIDATION.json",
        "B1": folder / "final_exact/AC_VALIDATION.json",
    }
    da = read(exact_paths[policy]) or {}
    fresh = read(folder / "Fresh/AC_VALIDATION.json") or {}
    actual = read(RUN / "Actual" / policy / "COMPLETE.json") or {}
    actual_summary = actual.get("summary", {})
    da_metrics = da.get("metrics", {})
    fresh_metrics = fresh.get("metrics", {})
    slots = da.get("slots", [])
    witness = max(slots, key=lambda row: row.get("max_phase_line_loading_pu", -1)) if slots else {}
    return dict(policy=policy, DA_exact=da_metrics.get("max_phase_line_loading_pu"),
                DA_PASS=da.get("status") == "PASS" if da else None,
                Fresh=fresh_metrics.get("max_phase_line_loading_pu"),
                Fresh_PASS=fresh.get("status") == "PASS" if fresh else None,
                Actual=actual_summary.get("max_phase_line_loading_pu"),
                Actual_PASS=actual.get("AC_feasible"),
                Vmin=da_metrics.get("Vmin_pu"), Vmax=da_metrics.get("Vmax_pu"),
                transformer_current=da_metrics.get("max_transformer_phase_current_pu"),
                transformer_kva=da_metrics.get("max_transformer_winding_kva_pu"),
                critical_line=witness.get("line_witness"), critical_slot=witness.get("slot"),
                complete=bool(read(folder / "COMPLETE.json")),
                actual_complete=bool(actual),
                DA_metrics=da_metrics, Fresh_metrics=fresh_metrics,
                Actual_metrics=actual_summary,
                DA_slots=len(slots), Fresh_slots=len(fresh.get("slots", [])),
                actual_Q_intervention_slots=actual.get("Q_intervention_slots"),
                actual_runtime_s=actual.get("runtime_s"),
                sources=dict(DA=str(exact_paths[policy].relative_to(RUN)),
                             Fresh=str((folder / "Fresh/AC_VALIDATION.json").relative_to(RUN)),
                             Actual=f"Actual/{policy}/COMPLETE.json"))


def solver_history():
    trace = RUN / "B2" / "solver_trace"
    calls = sorted((p for p in trace.glob("call_*") if p.is_dir()),
                   key=lambda p: p.name) if trace.exists() else []
    rows = []
    for call in calls[-30:]:
        starts = sorted(call.glob("ITERATION_*_START.json"))
        results = sorted(call.glob("ITERATION_*_RESULT.json"))
        start = read(starts[-1]) if starts else {}
        last = read(results[-1]) if results else {}
        progress = read(call / "CURRENT.json") or {}
        build = read(call / "BUILD.json") or {}
        enter = read(call / "ENTER.json") or {}
        closure = read(call / "FULL_SEPARATION_CLOSURE.json") or {}
        separation = last.get("separation", {})
        rows.append(dict(call=call.name, updated_unix=call.stat().st_mtime,
                         iteration=start.get("iteration"), iterations_finished=len(results),
                         model=start.get("model", {}), build_seconds=build.get("model_build_seconds"),
                         entered_unix=enter.get("unix"), solve_seconds=last.get("solve_seconds"),
                         incumbent=progress.get("incumbent", last.get("incumbent")),
                         best_bound=progress.get("best_bound", last.get("best_bound")),
                         mip_gap=progress.get("relative_gap", last.get("mip_gap")),
                         explored_nodes=progress.get("explored_nodes", last.get("explored_nodes")),
                         progress_unix=progress.get("unix"),
                         new_rows=separation.get("new_rows"),
                         checked_rows=separation.get("all_logical_rows_checked"),
                         max_violation=separation.get("maximum_violation"),
                         closure=closure.get("status"),
                         closure_checked_rows=closure.get("checked_rows")))
    return dict(total_calls=len(calls), calls=rows)


def beam_stages():
    folder = RUN / "B2" / "beam" / "2025-05-01" / "B2" / "B2"
    stages = []
    for path in sorted(folder.glob("STAGE_*.json")):
        trace = (read(path) or {}).get("trace", {})
        stages.append(dict(file=str(path.relative_to(RUN)),
                           mess_id=trace.get("mess_id"),
                           best_objective=trace.get("current_best_objective"),
                           retained=trace.get("retained_beam_count"),
                           candidates=trace.get("restricted_logical_candidate_count"),
                           restricted_seconds=trace.get("restricted_wallclock_seconds"),
                           full_milp_seconds=trace.get("full_MILP_wallclock_seconds"),
                           cache_hits=trace.get("restricted_cache_hits"),
                           cache_misses=trace.get("restricted_cache_misses")))
    return stages


def recent_logs():
    paths = list((RUN / "logs").glob("*.log"))
    paths += list((RUN / "B2/physical_closure").glob("RESTORATION_SOLVER_*.log"))
    paths += list((RUN / "B2_ACTIVE_PRODUCTION_RUN_20260921").glob("*.log"))
    paths += list((RUN / "B2" / "solver_trace").glob("call_*/*.log"))
    paths = sorted((p for p in paths if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
    return paths


def log_tail(path: Path, limit: int = 16000):
    try:
        with path.open("rb") as stream:
            stream.seek(max(0, stream.seek(0, 2) - limit))
            return stream.read().decode("utf-8", errors="replace")[-limit:]
    except OSError:
        return ""


def active_b2():
    trace = RUN / "B2" / "solver_trace"
    calls = sorted((p for p in trace.glob("call_*") if p.is_dir()),
                   key=lambda p: p.stat().st_mtime) if trace.exists() else []
    benchmark = read(RUN / "B2_ACTIVE_SET_DIAGNOSTIC" / "BENCHMARK.json") or {}
    if not calls:
        return dict(benchmark_pass=bool(benchmark.get("full_separation_closed")),
                    call=None)
    call = calls[-1]
    starts = sorted(call.glob("ITERATION_*_START.json"))
    results = sorted(call.glob("ITERATION_*_RESULT.json"))
    current = read(call / "CURRENT.json") or {}
    started = read(starts[-1]) if starts else {}
    latest = read(results[-1]) if results else {}
    separation = latest.get("separation", {})
    closure = read(call / "FULL_SEPARATION_CLOSURE.json") or {}
    return dict(benchmark_pass=bool(benchmark.get("full_separation_closed")),
                call=call.name, iteration=started.get("iteration"),
                model=started.get("model", {}), progress=current,
                last_result=latest, last_added_rows=separation.get("new_rows"),
                last_max_violation=separation.get("maximum_violation"),
                closure=closure.get("status"),
                all_rows_checked=closure.get("checked_rows"))


def status():
    freeze = read(RUN / "FINAL_CANDIDATE_FREEZE.json") or {}
    stage = read(RUN / "CAMPAIGN_STATUS.json") or {}
    live = read(RUN / "STATUS.json") or {}
    coeff = read(RUN / "COEFFICIENT_PROGRESS.json") or {}
    preflight = read(RUN / "B2_PERFORMANCE_PREFLIGHT.json") or {}
    if (stage.get("status") == "RUNNING" and
            stage.get("stage") == "B2_PERFORMANCE_PREFLIGHT" and
            preflight.get("status") == "FAIL"):
        preflight = dict(status="RUNNING", prior_attempt="diagnostic_attempts/B2_PREFLIGHT_ATTEMPT_01_DATE_BINDING_FAIL.json",
                         detail="Corrected date binding; preflight rerun is in progress")
    policies = [result(policy) for policy in ORDER]
    logs = recent_logs()
    tail = log_tail(logs[0], 12000) if logs else ""
    progress = live.get("MESS_progress") or {}
    phase = dict(policy=stage.get("policy") or progress.get("case"),
                 stage=live.get("stage") or stage.get("stage"),
                 status=live.get("status") or stage.get("status"),
                 event=progress.get("event"),
                 mess_index=progress.get("mess_index"),
                 parent_index=progress.get("parent_index"),
                 parent_total=progress.get("parent_total"),
                 search_level=progress.get("search_level"),
                 candidate_done=progress.get("candidate_done"),
                 candidate_total=progress.get("candidate_total"),
                 updated_unix=live.get("updated_unix") or stage.get("updated_unix"),
                 worker_pid=live.get("pid") or stage.get("worker_pid"))
    if stage.get('status') == 'FAILED':
        phase.update(status='FAILED',stage=stage.get('stage'),error=stage.get('error'))
    elif stage.get('status') == 'RUNNING' and 'ACTUAL' in stage.get('stage', ''):
        actual_live = read(RUN / 'Actual' / str(stage.get('policy')) / 'STATUS.json') or {}
        q_progress = read(RUN / 'Actual' / str(stage.get('policy')) / str(stage.get('policy')) / 'Q_EVALUATION_PROGRESS.json') or {}
        phase.update(status='RUNNING',stage=stage.get('stage')+':'+str(actual_live.get('stage','STARTING')),
                     worker_pid=stage.get('worker_pid'),updated_unix=actual_live.get('updated_unix',stage.get('started_unix')),
                     actual_slots=actual_live.get('slots_complete',actual_live.get('slot',q_progress.get('slot'))),actual_interventions=actual_live.get('interventions'),
                     actual_unresolved=actual_live.get('unresolved'))
        if q_progress and q_progress.get('updated_unix',0)>=actual_live.get('updated_unix',0):
            phase.update(updated_unix=q_progress['updated_unix'],q_evaluation=q_progress)
    closure_root = RUN / 'B2/physical_closure'
    closure_live = read(closure_root / 'local/LIVE.json') or {}
    audits = sorted(closure_root.glob('NUMERICAL_ENTRY_*.json'))
    latest_audit = read(audits[-1]) if audits else {}
    rounds = sorted((closure_root / 'local_signed_ac').glob('round_*'))
    derivative_slots = sorted(rounds[-1].glob('slot_*')) if rounds else []
    ac_rounds = sorted((closure_root / 'local').glob('round_*/fresh/AC_VALIDATION.json'))
    last_ac = read(ac_rounds[-1]) if ac_rounds else {}
    fallback_ledger = read(closure_root / 'full_pq/SEARCH_LEDGER.json') or []
    fallback_active = live.get('stage') == 'B2:FULL_PHYSICAL_PQ_FALLBACK'
    if fallback_active:
        closure_live = dict(status='RUNNING', stage='FULL_PHYSICAL_PQ_FALLBACK')
        if fallback_ledger and fallback_ledger[-1].get('Fresh'):
            fresh = fallback_ledger[-1]['Fresh']
            last_ac = dict(status=fresh.get('status'), metrics=fresh)
    closure = dict(live=closure_live, entry_audit=latest_audit,
                   derivative_slot_count=len(derivative_slots),
                   latest_derivative_slot=derivative_slots[-1].name if derivative_slots else None,
                   latest_AC=last_ac, acceptance=read(closure_root / 'ACCEPTANCE.json'),
                   fallback_candidates=len(fallback_ledger),
                   fallback_pass_count=sum(bool(x.get('feasible')) for x in fallback_ledger),
                   latest_candidate=fallback_ledger[-1].get('label') if fallback_ledger else None)
    if (phase['status'] == 'RUNNING' and phase['policy'] == 'B2' and closure_live and
            live.get('stage') == 'B2:LOCAL_FIXED_DISCRETE_RESTORATION'):
        phase['stage'] = 'B2:AC_RESTORATION:' + closure_live.get('stage', '')
        phase['updated_unix'] = max(phase['updated_unix'] or 0, closure_live.get('updated_at', 0))
    return dict(now=time.time(), run=str(RUN), order=list(ORDER), freeze=freeze,
                campaign=stage, live=live, coefficients=coeff, B2_preflight=preflight,
                B2_active=active_b2(), B2_closure=closure,
                phase=phase, solver_history=solver_history(), beam_stages=beam_stages(),
                results=policies, latest_log=str(logs[0].relative_to(RUN)) if logs else None, log_tail=tail,
                recent_logs=[dict(name=str(p.relative_to(RUN)), updated_unix=p.stat().st_mtime,
                                  bytes=p.stat().st_size) for p in logs[:30]],
                paper_overlay_sha256=freeze.get("paper_overlay_sha256"),
                correct_candidate=(freeze.get("BG_SCALE") == .552 and
                                   freeze.get("AIDC_ABSOLUTE_SCALE") == 2.4 and
                                   freeze.get("MESS_SCALE") == 2.0))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlsplit(self.path)
        route = parsed.path
        if route == "/api/status":
            body = json.dumps(status(), ensure_ascii=False).encode("utf-8")
            kind = "application/json"
        elif route == "/api/log":
            name = parse_qs(parsed.query).get("name", [""])[0]
            permitted = {str(p.relative_to(RUN)): p for p in recent_logs()}
            if name not in permitted:
                self.send_error(404)
                return
            body = json.dumps(dict(name=name, text=log_tail(permitted[name], 40000)),
                              ensure_ascii=False).encode("utf-8")
            kind = "application/json"
        elif route in ("/", "/index.html"):
            body = (HERE / "index.html").read_bytes()
            kind = "text/html"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", kind + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 63426
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    (HERE / "SERVER.json").write_text(json.dumps(dict(pid=os.getpid(), port=port,
        run=str(RUN), url=f"http://127.0.0.1:{port}"), indent=2) + "\n", encoding="utf-8")
    server.serve_forever()
