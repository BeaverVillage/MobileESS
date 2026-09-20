"""Read-only monitor for the newly authorized IEEE8500 May-1 production run."""
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import psutil

HERE = Path(__file__).absolute().parent
RUN = HERE.parent / "production"
IEEE123 = HERE.parent.parent / "IEEE123_ACTUAL_QFIRST_MINP_20260920"


def read(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def process(pid):
    if not pid:
        return {"alive": False}
    try:
        p = psutil.Process(int(pid))
        info = {"pid": p.pid, "alive": p.is_running()}
        try:
            info.update(rss_gib=p.memory_info().rss / 2**30,
                        cpu_seconds=sum(p.cpu_times()[:2]))
        except psutil.Error:
            pass
        return info
    except (psutil.Error, ValueError):
        return {"pid": pid, "alive": False}


def status():
    now = time.time()
    supervisor = read(RUN / "MONITOR_STATUS.json") or {}
    live = read(RUN / "STATUS.json") or {}
    stage = supervisor.get("stage", live.get("stage", "B0_VERIFY"))
    if stage in ("B1", "B3_A1"):
        live.pop("MESS_progress", None)
        live.pop("solver_name", None)
    role = stage if stage in ("B1", "B3_A1") else "B1"
    clock = read(RUN / "SEARCH_CLOCK.json") or {}
    if stage not in ("B1", "B3_A1") or clock.get("start_unix", 0) < supervisor.get("stage_started_unix", 0):
        clock = {}
    elapsed = max(0, min(14400, now - clock["start_unix"])) if clock else 0
    incumbent = read(RUN / "DEADLINE_INCUMBENT.json") or {}
    checkpoints = []
    for path in (RUN / role / "timed_checkpoints").glob("*.json"):
        row = read(path)
        if row:
            checkpoints.append(dict(label=path.stem,
                                    seconds=row.get("target_seconds"), P1=row.get("P1")))
    checkpoints.sort(key=lambda row: row["seconds"] or 0)
    paths = {
        "B0": ("B0_ALIGNED_REPLAY/AC_VALIDATION.json", "B0_ALIGNED_REPLAY/AC_VALIDATION.json"),
        "B1": ("B1/final_exact/AC_VALIDATION.json", "B1/Fresh/AC_VALIDATION.json"),
        "B2": ("B2/accepted_final/exact_observation/AC_VALIDATION.json", "B2/Fresh/AC_VALIDATION.json"),
        "B3": ("B3_MF/exact_observation/AC_VALIDATION.json", "B3/Fresh/AC_VALIDATION.json"),
    }
    results = []
    for policy, (da_path, fresh_path) in paths.items():
        da = read(RUN / da_path) or {}
        fresh = read(RUN / policy / "aligned_final_Fresh/AC_VALIDATION.json") or read(RUN / fresh_path) or {}
        if policy == "B2" and da.get("status") == "FAIL":
            da = read(RUN / "B2/physical_closure/accepted_clean_exact/AC_VALIDATION.json") or da
        metric = fresh.get("metrics", {})
        rows = fresh.get("slots", [])
        witness = max(rows, key=lambda row: row["max_phase_line_loading_pu"]) if rows else {}
        actual = read(RUN / "Actual" / policy / "COMPLETE.json") or {}
        actual_progress = read(RUN / "Actual" / policy / "PROGRESS.json") or {}
        actual_summary = actual.get("summary", {})
        results.append(dict(policy=policy, fleet="OFF" if policy in ("B0", "B1") else "6대",
            DA=da.get("metrics", {}).get("max_phase_line_loading_pu"),
            Fresh=metric.get("max_phase_line_loading_pu"),
            Actual=actual_summary.get("max_phase_line_loading_pu"),
            Actual_partial=actual_progress.get("exact_rho_so_far") if not actual else None,
            Actual_slots=96 if actual else actual_progress.get("slots_complete", 0),
            Actual_PASS=actual.get("AC_PASS", actual.get("AC_feasible")), Vmin=metric.get("Vmin_pu"),
            Vmax=metric.get("Vmax_pu"), txI=metric.get("max_transformer_phase_current_pu"),
            txS=metric.get("max_transformer_winding_kva_pu"),
            critical_slot=witness.get("slot"), critical_line=witness.get("line_witness"),
            feasible=fresh.get("status") == "PASS" if fresh else None))
    labels = ["B0 · 96-slot / Fresh", "B1 · AIDC 4시간", "B2 · full route/PQ",
              "B3 · M1 route/PQ", "B3 · A2 AIDC 4시간", "B3 · M2 PQ/Fresh",
              "B0–B3 · Actual", "최종 검증·CSV"]
    complete_flags = [results[0]["feasible"] is True,
                      (RUN / "B1/COMPLETE.json").exists(),
                      (RUN / "B2/COMPLETE.json").exists(),
                      (RUN / "B3_M1/COMPLETE.json").exists(),
                      (RUN / "B3_A1/COMPLETE.json").exists(),
                      (RUN / "B3_MF/COMPLETE.json").exists(),
                      (RUN / "Actual/CAMPAIGN_COMPLETE.json").exists(),
                      (RUN / "FINAL_EXPORT_COMPLETE.json").exists()]
    index = {"B1": 1, "B2_PREFLIGHT": 2, "B2": 2, "B3_M1": 3,
             "B3_A1": 4, "B3_MF": 5, "REPORT": 5,
             "Actual": 6, "EXPORT": 7}.get(stage, 0)
    steps = [dict(name=name, state="complete" if complete_flags[i] else "running" if i == index else "pending")
             for i, name in enumerate(labels)]
    actual_mode = stage == "Actual"
    if actual_mode:
        live = read(RUN / "Actual/STATUS.json") or live
        live["interventions"] = live.get("Q_interventions", 0) + live.get("P_interventions", 0)
    failure = read(RUN / "SEMANTIC_ALIGNMENT_STOP.json") or (supervisor if supervisor.get("status") in ("FAILED", "STOP") else None)
    if not failure and stage in ("B1", "B2", "B3_M1", "B3_A1", "B3_MF"):
        path = RUN / (stage + "_ALIGNED_FAILURE.json")
        if path.exists() and path.stat().st_mtime >= supervisor.get("stage_started_unix", 0):
            failure = read(path)
    if not failure and stage == "B2_PREFLIGHT":
        failure = read(RUN / "K200_CLOSURE_FAILURE.json")
    fleet = read(RUN / "FLEET_AUTHORITY.json") or {}
    worker = process(live.get("pid") or supervisor.get("worker_pid"))
    if not worker.get("alive") and supervisor.get("worker_pid"):
        worker = process(supervisor["worker_pid"])
    final = read(RUN / "ALIGNED_FINAL_RESULT.json") or {}
    monthly = read(IEEE123 / "MONTHLY_CAMPAIGN_STATUS.json") or {}
    actual123 = []
    for day in range(1, 32):
        date = f"2025-05-{day:02d}"
        values = {}
        for pol in ("B0", "B1", "B2", "B3_1R", "B3_2R"):
            base = "replays_1round" if pol == "B3_1R" else "replays"
            path = IEEE123 / base / date / ("B3" if pol.startswith("B3_") else pol)
            done = read(path / "COMPLETE.json") or {}
            prog = read(path / "PROGRESS.json") or {}
            values[pol] = dict(rho=done.get("new_Actual_rho") if done else prog.get("exact_rho_so_far"),
                final=bool(done), slots=96 if done else prog.get("slots_complete", 0),
                AC_PASS=done.get("AC_PASS"), P_interventions=done.get("P_interventions", prog.get("P_interventions")),
                Q_interventions=done.get("Q_interventions", prog.get("Q_interventions")))
        actual123.append(dict(day=date, policies=values))
    return dict(scale_audit=read(RUN / "scale_audit/PHYSICAL_SCALE_AUDIT.json") or {}, prior_Actual_disposition=read(RUN / "PRIOR_ACTUAL_DISPOSITION.json") or {}, now=now, run=str(RUN), supervisor=supervisor, live=live,
                ieee123_actual=actual123, ieee123_status=monthly.get("status"),
                worker=worker, failure=failure, clock=clock, clock_role=role,
                elapsed=elapsed, incumbent=incumbent, checkpoints=checkpoints,
                results=results, steps=steps, current=index,
                complete=bool(complete_flags[-1]),
                authorization=dict(initial=fleet.get("initial_locations", {})),
                preparation=dict(bounds_slots=len(list((RUN / (role + "_electrical_rows")).glob("bounds_*.npz"))),
                                 active_slots=len(list((RUN / (role + "_electrical_rows")).glob("active_data_*.npz")))),
                system=dict(available_ram_gib=psutil.virtual_memory().available / 2**30),
                transport_preserved=(read(RUN / "INPUT_AUTHORITY_AUDIT.json") or {}).get("status") == "PASS",
                final=final, Actual=actual_mode)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        route = self.path.split("?", 1)[0]
        if route == "/api/status":
            body = json.dumps(status(), ensure_ascii=False).encode("utf-8")
            kind = "application/json"
        elif route == "/audit/slots.csv":
            body = (RUN / "scale_audit/B0_SCALE_DECOMPOSITION_96_SLOTS.csv").read_bytes()
            kind = "text/csv"
        elif route in ("/", "/index.html"):
            body = (HERE / "index.html").read_bytes()
            kind = "text/html"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", kind + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    import sys
    server = ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 63426), Handler)
    (HERE / "SERVER.json").write_text(json.dumps(dict(pid=os.getpid(), port=server.server_port,
        url=f"http://127.0.0.1:{server.server_port}", run=str(RUN)), indent=2), encoding="utf-8")
    server.serve_forever()
