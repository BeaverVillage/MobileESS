import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from v42_campaign.authority import digest
from v42_orchestrator.ledger import atomic as _atomic, now

ROOT = Path(__file__).resolve().parents[1]
BASE = 'c6c2f733d8196e90c0cda5f849f3e894c872697f'
CODE = Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
HISTORY = Path('C:/codex_mobileess_workspace/MobileESS_v41r2_780gpu_capacity_rebase')
CHECKER = '0cffff2af474221a7a5693f3c2b7a83026bd1522de2d3f66032c1757b9735d51'
VERSION = 'V42_B1_V39E_V37_PORT_V1'
STAGES = ('A1', 'PLANNING_FREEZE', 'ACTUAL', 'FRESH_AC', 'VALIDATION_FREEZE')
STATEMENTS = [
    '2025년 5월 B1 production campaign은 Codex 세션과 독립적인 Windows detached task로 실행한다.',
    'PowerShell monitor는 atomic status/heartbeat를 읽는 read-only 프로세스이며 campaign process를 소유하거나 제어하지 않는다.',
    'B1은 AIDC workload/data centers PRESENT, AIDC grid flexibility ON, MESS OFF 정의를 유지한다.',
    'B1은 1 day-worker, Gurobi Threads=1로 실행하고 다른 full-scale native heavy solve와 자원이 충돌하면 detached scheduler가 WAIT_RESOURCE 후 자동 재개한다.',
    'B1 완료 후 B2/B3로 자동 진입하지 않는다.',
]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def atomic(path,value,**kwargs):
    from v42_april_port.audit import clean
    return _atomic(path,clean(value),**kwargs)


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def record(path):
    p = Path(path).resolve()
    return dict(path=str(p), sha256=sha(p), bytes=p.stat().st_size)


@dataclass(frozen=True)
class Config:
    arm: str = 'B1'
    B1_DAY_WORKERS: int = 1
    GUROBI_THREADS: int = 1
    A1_TIME_LIMIT: int = 1800
    RAM_FLOOR_GIB: float = 1
    COMMIT_STOP_PERCENT: float = 95
    SAMPLE_SECONDS: float = 1
    CATASTROPHIC_PAGES_INPUT_PER_SECOND: float = 8192
    CATASTROPHIC_PAGING_SUSTAINED_SECONDS: float = 30
    MESS_OFF: bool = True
    ML_OFF: bool = False
    AUTO_ADVANCE: bool = False

    def __post_init__(self):
        if (self.arm != 'B1' or self.B1_DAY_WORKERS != 1 or self.GUROBI_THREADS != 1
                or self.A1_TIME_LIMIT != 1800 or self.RAM_FLOOR_GIB != 1
                or self.COMMIT_STOP_PERCENT != 95 or self.SAMPLE_SECONDS != 1
                or self.MESS_OFF is not True or self.ML_OFF is not False or self.AUTO_ADVANCE):
            raise PermissionError('FROZEN_B1_SCOPE_OR_POLICY_DRIFT')


def identity(freeze, day, stage):
    if day not in freeze['days'] or stage not in STAGES:
        raise PermissionError('B1_DAY_STAGE_SCOPE')
    return dict(run_id=freeze['run_id'], arm='B1', day=day, stage=stage,
                stage_version=VERSION, Git_SHA=freeze['Git_SHA'],
                scientific_SHA=freeze['scientific_SHA'], input_SHA=freeze['day_input_SHA'][day],
                checker_SHA=CHECKER)


def admission(row):
    hard = (row['available_GiB'] < 1 or row['commit_percent'] >= 95
            or row['catastrophic_sustained_paging'])
    return 'HARD_GUARD' if hard else 'WAIT_RESOURCE' if row['foreign_heavy'] else 'SAFE'


def verify_freeze(freeze,config):
    Config(**config)
    if (freeze['mode']!='B1_PRODUCTION' or freeze['configuration']!=config or freeze['checker_SHA']!=CHECKER
            or freeze['base_Git_SHA']!=BASE or freeze['days']!=[f'2025-05-{i:02d}' for i in range(1,32)]
            or freeze['stage_order']!=list(STAGES) or not freeze['run_id'].startswith('B1_202505_')):
        raise PermissionError('CAMPAIGN_FREEZE_SCOPE_DRIFT')
    expected=digest(dict(configuration=config,checker=CHECKER,version=VERSION,sources=freeze['sources'],
                         stage_order=list(STAGES),days=freeze['days']))
    if expected!=freeze['scientific_SHA']: raise PermissionError('CAMPAIGN_SCIENTIFIC_SHA_DRIFT')
    return True


def python_environment():
    import sys
    import importlib.metadata as metadata
    names=('numpy','pandas','pyarrow','psutil','gurobipy','opendssdirect.py','dss-python')
    return dict(Python=str(Path(sys.executable).resolve()),version=sys.version,
                packages={n:metadata.version(n) for n in names})
