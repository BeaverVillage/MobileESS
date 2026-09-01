"""Process-local V28R2 heavy-backend dispatcher."""

from __future__ import annotations

import argparse
import os
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

    def load_or_create_state(self) -> DayState:
        if self.state_path.is_file():
            state = DayState.load(self.state_path)
            if state.run_spec_sha256 != self.spec.sha256:
                raise RuntimeError("V28R2_RUN_SPEC_CHANGED_FOR_EXISTING_DAY")
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
        for step in EXECUTION_STEPS[prefix:]:
            state.begin_step(step)
            state.save(self.state_path)
            try:
                handler = self.handlers.get(step)
                if handler is None:
                    raise RuntimeError(f"V28R2_PRODUCTION_STEP_HANDLER_MISSING:{step}")
                artifacts, counters = handler(self.spec, self.day_root, self.ledger)
                state.complete_step(step, artifacts, counters)
                state.save(self.state_path)
            except BaseException as error:
                state.fail_step(step, error, DEFECT_BY_STEP[step])
                state.save(self.state_path)
                raise
        return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", choices=("april",), required=True)
    parser.add_argument("--day", required=True)
    parser.add_argument("--mode", choices=("authority-preflight", "non-authority-smoke"), required=True)
    parser.parse_args(argv)
    raise RuntimeError("V28R2_HEAVY_BACKEND_FACTORY_NOT_YET_BOUND")


if __name__ == "__main__":
    raise SystemExit(main())
