# R25M B6R2 — Batch Pricing + Numerical Certificate Guard

B6R1 reached CG iteration 90 in about 209 s and had already expanded each MESS path pool to 94 columns. The failure was not a pricing-sign error: the observed RC consistency discrepancy was only 1.2187e-5 while genuinely negative priced paths were O(1e-1 to 1).

B6R2 therefore keeps the exact shortest-path closure oracle, but adds up to 8 negative reduced-cost k-best paths per MESS and RMP solve. It also treats the RC comparison as a numerical audit with an explicit 1e-4 fail-closed envelope. Any final all-column lower bound is weakened by a conservative numerical safety amount before it may support the frozen global 3% certificate.

No physical/scientific feasible-set or objective change is introduced.
