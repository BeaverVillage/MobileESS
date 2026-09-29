"""Strict boundaries shared by the four V42 stages."""
from time import monotonic
import hashlib
import json
from pathlib import Path


class ContractError(ValueError):
    pass


def require(value, message):
    if not value:
        raise ContractError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def file_sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


class Deadline:
    """Start before generating candidates. A check never replenishes the budget."""
    def __init__(self, stage, seconds=600., clock=monotonic):
        require(stage in ('A1', 'M1', 'A2', 'M2'), 'UNKNOWN_STAGE')
        require(0 < seconds <= 600, 'INVALID_STAGE_BUDGET')
        self.stage, self.seconds, self.clock = stage, seconds, clock
        self.started = clock()

    @property
    def remaining(self):
        return max(0., self.seconds - (self.clock() - self.started))

    def check(self):
        if self.remaining <= 0:
            raise TimeoutError(self.stage + '_DEADLINE')

    def receipt(self):
        elapsed = self.clock() - self.started
        return dict(stage=self.stage, budget_seconds=self.seconds,
                    wall_seconds=elapsed, deadline_exceeded=elapsed > self.seconds)


def lex_not_worse(candidate, incumbent, tolerance=1e-7):
    require(len(candidate) == len(incumbent) > 0, 'OBJECTIVE_DIMENSIONS')
    for new, old in zip(candidate, incumbent):
        if new < old - tolerance:
            return True
        if new > old + tolerance:
            return False
    return True
