"""Describe already frozen causal feature availability; no selection or refitting."""
from pathlib import Path
import json
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import study as s

s.guard(True)
names = json.loads((ROOT / 'FEATURE_NAMES.json').read_text(encoding='utf-8'))
features = s.feature_data()
rows = []
for role in s.ROLES:
    indices = s.old.role_ids(role)
    for window in [6, 12, 24, 168]:
        values = features[indices, 0, names.index(f'burst_work_{window}h_mature_fraction')]
        rows.append(dict(role=role, window_hours=window, N_issues=len(indices),
                         mean_mature_fraction=float(values.mean()),
                         median_mature_fraction=float(np.median(values)),
                         issues_without_observable_workload=int((values == 0).sum()),
                         issues_with_full_observable_workload=int((values == 1).sum())))
pd.DataFrame(rows).to_csv(ROOT / 'FEATURE_SUPPORT.csv', index=False, lineterminator='\n')
