from pathlib import Path
from v42_april_port.audit import read, record, write, table, sha
from v42_capacity.common import resolve, day_folder

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/v42_may_reg1a_phase_root_cause'
MAY = ROOT / 'docs/v42_may_b0_zero_margin_holdout'
BASE = '97ef9cc9b655d93a42b0b43d593aac01b951c6f3'
DAYS = ('2025-05-19', '2025-05-20', '2025-05-21', '2025-05-22')
VIOLATION_SLOTS = {DAYS[0]: (30,31,32), DAYS[1]: (30,31),
                   DAYS[2]: (28,29,30,31,32,33), DAYS[3]: (32,)}
# Fixed adjacent controls chosen before diagnostic reruns, without tuning.
CONTROL_SLOTS = {DAYS[0]: (29,33), DAYS[1]: (29,32),
                 DAYS[2]: (27,34), DAYS[3]: (31,33)}

def emit_csv(name, rows):
    table(OUT, name, rows, list(rows[0]))
