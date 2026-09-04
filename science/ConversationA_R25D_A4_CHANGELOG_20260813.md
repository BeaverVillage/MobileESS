# Conversation A — R25D A4/6 Changelog

## Stage
A4/6 — Radial Grid Exact Projection + Node-QCP Reduction.

## Implemented
- Bound the grid decision skeleton to the ancestor closure of all 36 possible decision-dependent PCC injections (24 MESS + 12 IDC).
- Identified 100 retained skeleton nodes and 68 decision-independent static nodes in the actual BUILD7AR2 168-node runtime topology.
- Added exact static-subtree FP/FQ condensation and constant parent-balance substitution.
- Replaced 65 static LINE circle QCPs per horizon step by fail-closed constant thermal checks.
- Retained dU variables only on the 61 decision-skeleton LINE nodes.
- Projected all fixed-ratio transformer voltage states and all static-subtree voltage states as exact affine functions of one retained dU anchor or the anchored root constant.
- Propagated all 168 original voltage hard limits into exact retained-anchor variable-bound intersections.
- Preserved the full 168-node planning-voltage output through affine expressions.
- Added `ConversationA_R25D_RADIAL_GRID_EXACT_PROJECTION_AUDIT.json` runtime construction evidence.

## H54 structural reduction versus R24 grid form
- 7,344 FP/FQ continuous variables removed.
- 7,344 P/Q balance equalities removed.
- 5,778 dU continuous variables removed.
- 5,724 voltage recursion equalities removed.
- 3,510 LINE apparent-power QCP constraints removed from Gurobi and converted to exact constant fail-closed checks.
- 13,122 total grid continuous variables structurally removed.
- 13,068 total linear equalities structurally removed.

## Proof
Actual BUILD7AR2 topology was used in 300 randomized algebraic-equivalence trials. Maximum observed errors:
- skeleton balance: 1.4211e-14,
- static branch-flow projection: 8.8818e-16,
- projected voltage: 1.7347e-18.

Projected voltage-bound interval equivalence and static-line QCP constant replacement both passed.

## Long-run policy
No issue152 long solve was executed in A4. No bash runner is required now.

## Next
A5/6 integrates the A3 exact path-decomposition/column-completeness mechanism with this A4 compact operational grid master and builds the persistent rolling architecture. A6 remains the only long 152→166 closure run.
