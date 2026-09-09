# May12 B3 reduced acceleration acceptance gate

PERFORMANCE_ONLY_EXACT_EQUIVALENT_ACCELERATION_PASS

Validation scope authorized by the user: one complete lightweight robust-Q search over 96 sequential slots, followed by 96 clean-engine full-prefix evaluations at the selected Q vectors. All selected-point voltage, line-current/loading, transformer-current/kVA, start/final tap arrays and final violation counts match bit-for-bit. P_EXEC and SoC/energy remain identical to the common eta=0.95 baseline.

This gate does **not** prove that an independently executed old full-day search would choose the same Q at every slot. No such search was completed or claimed. Prior 55-point/reverse-order evidence and the separately completed 4,558-candidate May12 slot30 exact search comparison remain supporting evidence. Scientific Q search rules are unchanged.

- Lightweight complete search: 922.187 seconds.
- Lightweight mean candidate: 0.008520 seconds.
- Lightweight mean intervention slot: 19.150 seconds.
- Old exact selected-96-point validation: 14.077 seconds.
- Lightweight peak working set: 0.357 GB.
- Intervention slots: 48; unresolved slots: 0.

No full-day search speedup is claimed because the old full-day search was cancelled. The previously measured slot30 search speedup was 20.28x.
