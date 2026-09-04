"""Process-local V28R2 heavy-backend dispatcher."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path
from typing import Callable, Mapping

from .backend_contract import EXECUTION_STEPS, DayRunSpec
from .day_state import DayState
from .runtime_ledger import RuntimeLedger


StepHandler = Callable[[DayRunSpec, Path, RuntimeLedger], tuple[Mapping[str, Path], Mapping[str, object]]]


DEFECT_BY_STEP = {
    step: "V28R2_BLOCK_END_TO_END_HEAVY_SMOKE_FAIL" for step in EXECUTION_STEPS
}


class HeavyBackend:
    def __init__(self, spec: DayRunSpec, day_root: Path, state_path: Path, handlers: Mapping[str, StepHandler]):
        spec.validate()
        self.spec = spec
        self.day_root = day_root
        self.state_path = state_path
        self.handlers = dict(handlers)
        self.ledger = RuntimeLedger(spec.day)

    def _log_event(self, message: str) -> None:
        log_path = Path(self.spec.output_roots["logs"]) / f"{self.spec.day}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(f"{time.time():.6f} pid={os.getpid()} {message}\n")

    def load_or_create_state(self) -> DayState:
        if self.state_path.is_file():
            state = DayState.load(self.state_path)
            if state.run_spec_sha256 != self.spec.sha256:
                if state.status == "PASS":
                    raise RuntimeError("V28R2_IMMUTABLE_PASS_RUN_SPEC_CHANGED")
                archive_name = f"{int(time.time())}_{state.run_spec_sha256[:12]}"
                state_archive = self.state_path.parent / "failed_attempts" / archive_name
                output_archive = self.day_root / "_failed_attempts" / archive_name
                if self.day_root.resolve() not in output_archive.resolve().parents:
                    raise RuntimeError("V28R2_FAILED_ATTEMPT_ARCHIVE_SCOPE")
                state_archive.mkdir(parents=True, exist_ok=False)
                output_archive.mkdir(parents=True, exist_ok=False)
                shutil.copy2(self.state_path, state_archive / "DAY_STATE.json")
                for child in list(self.day_root.iterdir()):
                    if child.name == "_failed_attempts":
                        continue
                    shutil.move(str(child), str(output_archive / child.name))
                archived = {
                    "artifact_id": "V28R2_FAILED_ATTEMPT_ARCHIVE_V1",
                    "old_run_spec_sha256": state.run_spec_sha256,
                    "new_run_spec_sha256": self.spec.sha256,
                    "status": state.status,
                    "failure": state.failure,
                    "defect_ids": state.defect_ids,
                    "completed_steps": state.completed_steps,
                }
                (state_archive / "ROLLOVER.json").write_text(
                    json.dumps(archived, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n",
                )
                (output_archive / "ROLLOVER.json").write_text(
                    json.dumps(archived, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n",
                )
                state = DayState(
                    self.spec.day, self.spec.campaign, self.spec.sha256,
                    attempts=dict(state.attempts), defect_ids=list(state.defect_ids),
                )
                state.save(self.state_path)
            return state
        state = DayState(self.spec.day, self.spec.campaign, self.spec.sha256)
        state.save(self.state_path)
        return state

    def execute(self) -> DayState:
        os.environ.update({
            "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
        })
        state = self.load_or_create_state()
        prefix = state.reusable_prefix_length()
        if prefix != len(state.completed_steps):
            raise RuntimeError("V28R2_EXISTING_STEP_ARTIFACT_TAMPERED")
        if state.completed_steps:
            snapshot = state.step_counters[state.completed_steps[-1]].get("_runtime_ledger_snapshot")
            if not isinstance(snapshot, Mapping):
                raise RuntimeError("V28R2_RUNTIME_LEDGER_SNAPSHOT_MISSING")
            self.ledger = RuntimeLedger.from_snapshot(snapshot)

        def progress(values: dict[str, object]) -> None:
            state.counters.update(values)
            state.heartbeat_epoch = time.time()
            state.pid = os.getpid()
            state.save(self.state_path)

        self.ledger.set_progress_callback(progress)
        for step in EXECUTION_STEPS[prefix:]:
            state.begin_step(step)
            state.save(self.state_path)
            self._log_event(f"START step={step} attempt={state.attempts[step]}")
            try:
                handler = self.handlers.get(step)
                if handler is None:
                    raise RuntimeError(f"V28R2_PRODUCTION_STEP_HANDLER_MISSING:{step}")
                artifacts, counters = handler(self.spec, self.day_root, self.ledger)
                measured = dict(counters)
                measured["_runtime_ledger_snapshot"] = self.ledger.payload()
                state.complete_step(step, artifacts, measured)
                state.save(self.state_path)
                if step != EXECUTION_STEPS[-1]:
                    self.ledger.save(self.day_root / "RUNTIME_LEDGER_CHECKPOINT.json")
                self._log_event(f"COMPLETE step={step}")
            except BaseException as error:
                state.fail_step(step, error, DEFECT_BY_STEP[step])
                state.save(self.state_path)
                self._log_event(f"FAIL step={step} error={type(error).__name__}:{error}")
                raise
        return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", choices=("april",), required=True)
    parser.add_argument("--day", required=True)
    parser.add_argument("--mode", choices=("authority-preflight", "non-authority-smoke"), required=True)
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[2]
    from .certificate import verify_certificate
    from .gatekeeper import verify_authority_launch, verify_smoke_launch
    from .production_handlers import ProductionHandlers, build_day_run_spec

    if args.mode == "authority-preflight":
        verify_authority_launch(repo)
    else:
        verify_smoke_launch(repo)
    spec = build_day_run_spec(repo, args.day, args.mode)
    day_root = Path(spec.output_roots["frozen_artifacts"]) / args.day
    state_path = Path(spec.output_roots["progress"]) / args.day / "DAY_STATE.json"
    day_root.mkdir(parents=True, exist_ok=True)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    production = ProductionHandlers(repo, spec, day_root, state_path, args.mode)
    state = HeavyBackend(spec, day_root, state_path, production.handlers).execute()
    if state.status != "PASS":
        raise RuntimeError("V28R2_HEAVY_BACKEND_DID_NOT_REACH_PASS")
    if args.mode == "authority-preflight":
        certificate = day_root / f"APRIL_DAY_CERTIFICATE_{args.day.replace('-', '_')}.json"
        verify_certificate(certificate)
        final_path = certificate
    else:
        if list(day_root.glob("APRIL_DAY_CERTIFICATE_*.json")):
            raise RuntimeError("V28R2_SMOKE_ISSUED_APRIL_CERTIFICATE")
        final_path = day_root / "V28R2_NON_AUTHORITY_HEAVY_SMOKE_RESULT.json"
        if not final_path.is_file():
            raise RuntimeError("V28R2_SMOKE_RESULT_MISSING")
    print(json.dumps({
        "day": args.day, "mode": args.mode, "status": state.status,
        "completed_steps": len(state.completed_steps), "final_artifact": str(final_path),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
