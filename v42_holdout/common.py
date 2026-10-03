from pathlib import Path
from v42_april_port.audit import read, record, sha, write, table, clean
from v42_capacity.common import resolve, day_folder

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_may_b0_zero_margin_holdout'
INPUT=OUT/'INPUT'
BASE='3872dea8130baa25fd3deaabeddeabee5fbd730f'
DAYS=tuple(f'2025-05-{d:02d}' for d in range(1,32))
RAW=ROOT.parent/'MobileESS_v28r2_heavy_backend/cache/v28r2_campaign_sources/may_2025/days'
SNAPS=Path('C:/codex_mobileess_workspace/MobileESS_v40a_bounded_iterative_coopt/dayahead/artifacts/v37_r4a_per_day_aidc/days')
EXO=SNAPS.parents[1]/'v40d_actual_realized_replay'
APRIL=ROOT/'docs/v42_actual_autonomous_regcontrol_fixed_cap'

def require_may(day):
    if day not in DAYS: raise ValueError('FROZEN_MAY_2025_DATE_REQUIRED')

def destination(day):
    require_may(day)
    return OUT/'BUNDLE'/day_folder(day)

def source_freeze():
    r=read(OUT/'PREREGISTRATION.json')
    if r['exact_base']!=BASE or r['margin_pu']!=0 or r['days']!=list(DAYS):
        raise ValueError('HOLDOUT_PREREGISTRATION_DRIFT')
    for s in r['frozen_sources']: resolve(s)
    return r
