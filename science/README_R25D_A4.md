# R25D — A4/6 Radial Grid Exact Projection / Node-QCP Reduction

A4 reduces the grid block of the BUILD7C operational master without changing its scientific feasible set.

## Exact decomposition of the feeder planning model

All possible decision-dependent grid injections occur at the 24 MESS PCCs and 12 IDC PCCs. Their ancestor closure contains 100 of the 168 runtime nodes. The remaining 68 nodes form 31 decision-independent static subtrees.

For those static subtrees A4:

- computes branch FP/FQ exactly from causal background P/Q,
- substitutes the constant subtree flow into its retained parent balance,
- replaces each eliminated static LINE circle QCP by a fail-closed constant thermal check,
- analytically propagates every eliminated voltage state and every original voltage hard limit.

A4 retains voltage variables only on the 61 LINE nodes in the 100-node decision skeleton. Fixed-ratio transformer voltage states and all static-subtree voltage states remain available as exact affine expressions, so the full 168-node planning-voltage output is preserved.

## H54 structural reduction from the R24 grid formulation

- FP/FQ continuous variables removed: **7,344 / 18,036 = 40.72%**
- dU continuous variables removed: **5,778 / 9,072 = 63.69%**
- linear balance/voltage equalities removed: **13,068**
- LINE apparent-power QCP constraints removed from the optimization: **3,510 / 6,804 = 51.59%**
- total grid continuous variables structurally removed: **13,122**

The 3,510 removed line-circle constraints are not relaxed: each corresponds to a decision-independent static LINE branch and is checked numerically before optimization. Any violation fails closed.

## Exactness boundary

A4 does not change:

- 0.95–1.05 p.u. voltage limits,
- line apparent-power limits,
- MESS service-transformer kVA constraints,
- causal P/Q/PV inputs,
- objective or MIPGap acceptance,
- Fresh Exact OpenDSS full 168-bus first-step certification.

No issue152 long solve is performed in A4. A6 remains the only long closure run.
