"""Check original DA PCC controls equal original six-MESS trajectory sums."""
import numpy as np
from stage_b import CONTROL_FILES, PAPER
from stage_a_strong import read
from stage_c_strong_old import SERVICE_INDEX

for policy in ("B2", "B3"):
    with np.load(CONTROL_FILES[policy]) as z:
        x = z["x"]
    y = np.zeros((96, 48))
    for r in read(PAPER / policy / "FINAL_AUTHORITY.json")["trajectory_slots"]:
        if r["service_id"] is not None:
            t, i = r["slot"], SERVICE_INDEX[r["service_id"]]
            y[t, i] += r["p_kw"]
            y[t, 24 + i] += r["q_kvar"]
    difference = float(np.max(np.abs(x[:, 12:] - y)))
    print(policy, difference)
    assert difference < 1e-8
