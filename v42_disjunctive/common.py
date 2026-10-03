import os
from pathlib import Path
ENV = dict.fromkeys(('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS'), '1')
os.environ.update(ENV)
from v42_strengthening.common import sha, read, BASE_LB, UB_REF, SOURCE, SCIENCE, REF
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/v42_m1_location_grid_disjunctive_cuts'
LOCAL = ROOT.parent / 'DISJUNCTIVE_LOCAL'
BASE = '94f8a38b7ef7b60cf5d7ffd91c86b109589fcaef'

def write(name, value):
    import json
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / name
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf8')
    tmp.replace(p)

def table(name, rows, fields):
    import csv
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT/name).open('w', encoding='utf8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)

def once(label):
    LOCAL.mkdir(parents=True, exist_ok=True)
    with (LOCAL/(label+'_STARTED.json')).open('x', encoding='utf8') as f:
        f.write('{"retries_allowed":0}\n')

def material(lb, exact=True):
    delta = None if lb is None else lb-BASE_LB
    closure = None if delta is None else delta/(UB_REF-BASE_LB)
    return dict(PASS=bool(exact and lb is not None and lb>=BASE_LB-1e-8 and (delta>=.005 or closure>=.05)),
                delta_LB=delta, relative_diagnostic_gap_closure=closure,
                baseline_gap=(UB_REF-BASE_LB)/UB_REF,
                strengthened_gap=None if lb is None else (UB_REF-lb)/UB_REF,
                absolute_gate=.005, relative_gate=.05, numerical_tolerance=1e-8,
                reference=UB_REF, reference_is_diagnostic_only=True, UB_certificate=None)
