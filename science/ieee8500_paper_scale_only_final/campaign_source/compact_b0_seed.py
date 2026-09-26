"""Derive initial active rows from the current exact B0 state; never cap search."""
import json
from pathlib import Path

import numpy as np

H = Path(__file__).absolute().parent


def main():
    axes = json.loads((H / "AXES.json").read_text(encoding="utf-8"))
    with np.load(H / "B0_REPLAY/ANCHORS.npz") as z:
        line = np.abs(z["line"])
        voltage = np.sqrt(z["v2"])
        tx = np.abs(z["tx"])
        winding = np.abs(z["S"]) / np.asarray(axes["winding_rating_kVA"])
    rho = float(line.max())
    max_slot, max_index = np.unravel_index(int(line.argmax()), line.shape)
    # The current source's K/beam seed rule: top 20, >= 98% of B0 peak,
    # and a five-slot window for the same critical line-phase.
    top_flat = np.argsort(line, axis=None)[-20:]
    line_states = set(zip(*np.unravel_index(top_flat, line.shape)))
    line_states.update(zip(*np.where(line >= .98 * rho - 1e-12)))
    line_states.update((slot, int(max_index)) for slot in range(max(0, max_slot-2), min(96, max_slot+3)))
    # Voltage and transformer entries are only warm seed rows. Full closure
    # continues to inspect every state of the unchanged electrical model.
    voltage_states = set(zip(*np.where((voltage <= .96) | (voltage >= 1.04))))
    tx_states = set(zip(*np.where(tx >= .90)))
    kva_states = set(zip(*np.where(winding >= .90)))
    report = dict(status="PASS", B0_exact_rho=rho,
                  critical_slot=int(max_slot), critical_line=axes["line"][int(max_index)],
                  line_states=[[int(t), int(i)] for t, i in sorted(line_states)],
                  voltage_states=[[int(t), int(i)] for t, i in sorted(voltage_states)],
                  transformer_current_states=[[int(t), int(i)] for t, i in sorted(tx_states)],
                  transformer_kva_states=[[int(t), int(i)] for t, i in sorted(kva_states)],
                  counts=dict(line=len(line_states), voltage=len(voltage_states),
                              transformer_current=len(tx_states), transformer_kva=len(kva_states)),
                  seed_only=True, active_set_hard_cap=False, full_separation_required=True)
    (H / "COMPACT_B0_ACTIVE_SEED.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(report["counts"])


if __name__ == "__main__":
    main()
