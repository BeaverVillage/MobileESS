# R25M / B6R3 — Certified Branch-and-Price Fallback

B6R2 proved exact root pricing closure on issue152 but the all-column continuous root bound was too weak for the frozen 3% certificate. B6R3 keeps that exact root pricing and adds two exact-only mechanisms:

1. deterministic primal path-pool enrichment for a better feasible restricted-master incumbent;
2. an external best-bound-first branch-and-price lower-bound tree. Each branch node is repriced to all-column closure before its bound can be used.

Mobility branching is on the original node-occupancy 0/1 decision: a child either forbids or requires one time/service state. This partitions every integer path exactly and remains compatible with DAG pricing. Original non-mobility integer variables use ordinary floor/ceil branches.

No restricted-master ObjBound is scientific authority. No physical h0 commit occurs in this B6 screen.
