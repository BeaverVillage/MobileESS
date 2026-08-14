# R25J / B3 MIQCP Kernel Batch Screen

Diagnostic-only screen on authoritative issue152 PRE state. It compares `MIQCPMethod=-1,0,1` with the same B1 certificate-focused policy and B2 exact grid rescaling. Each method has a 300 s wall-clock ceiling, Threads=1, MIPGap=3%, MIPFocus=3, ImproveStartGap=0. No physical h0 state is committed by the diagnostic if a solve returns early; a diagnostic stop fires immediately after `build_full` returns. TIME_LIMIT with gap >3% remains fail-closed evidence only.

The output is not Stage-1 scientific authority. It is used only to select the B3 solver kernel for B4/B5.
