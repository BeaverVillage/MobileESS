from pathlib import Path
from v42_april_port.audit import read, record, sha, write, table
from v42_capacity.common import resolve, day_folder

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'docs/v42_actual_autonomous_regcontrol_fixed_cap'
OLD = ROOT/'docs/v42_april_b0_capacity_queue_voltage_calibration'
AUDIT = ROOT/'docs/v42_autonomous_grid_controls_april_b0'
INPUT = ROOT/'docs/v42_april_modelable_population_b0'
BASE = 'f535cc2671b285068f6b5ffbec55b951ffb7ea6d'
CODE = Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
DAYS = tuple(f'2025-04-{d:02d}' for d in range(1,31))
DIAGNOSTIC = ('2025-04-15','2025-04-16','2025-04-30')


def require_april(day):
    if day not in DAYS:
        raise ValueError('SCIENTIFIC_EXECUTION_APRIL_ONLY_MAY_NOT_RUN')


def output_day(day):
    require_april(day)
    return OUT/'BUNDLE'/day_folder(day)
