# Conversation A R24 Permanent Exact Formulation Rebase

Resume: issue152..166 from the exact issue151 POST / issue152 PRE state.

R24 bundles exact-equivalent formulation and I/O improvements before a single final long Stage-1 closure run. It does **not** relax the 3% economic MIPGap, H54, 5-minute cadence, Threads=1, causality, Rack/WAN, h0-only commit, or Fresh Exact OpenDSS gates.

Adopted: continuous exact STAY projection with binary MOVE arcs, exact dispatch gate merge, departure-floor strengthening, branch-flow component bounds, unused root-flow auxiliary projection, voltage-row-to-bound projection, sparse debt/SOC valid inequalities, one-pass BUILD5 extraction, template-bank cache, empty-shadow fast path.

Not adopted: R17 SOS1, PCC-leaf elimination, post-hoc issue152 same-issue MIP Start, MIPGap relaxation, multithreading tuning.
