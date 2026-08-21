# Conversation A — R25E A5 Changelog

## Primary architectural change

A3 showed that approximately 99k MOVE binaries dominate issue152. A5 found a stronger exact implementation than restricted-column branch-and-price for the current BUILD7C mobility network: keep every A1/A2 feasible mobility arc, but move MOVE/STAY arcs to continuous `[0,1]` and place integrality on time-service node occupancy.

The post-A2 graph is required to be a simple DAG. If two transitions have the same `(MESS, tail-time, tail-service, head-time, head-service)`, A5 fails closed. Under this condition, binary node occupancy uniquely identifies an unsplit path; continuous arc flow cannot split fractionally without producing a fractional occupied child.

## Historical issue152 structural projection

Using the already-audited R24 counts only (no new long solve):

- MOVE binaries before A5: 99,283
- STAY/reachable state count for `h=0..H-1`: 4,299
- terminal occupancy adds at most `4 MESS × 24 services = 96`
- node occupancy binaries therefore `<= 4,395`
- charge/discharge mode binaries: 216
- issue152 dynamic Job binaries were 0
- total integer upper bound `<= 4,611`, versus the prior estimate 99,499
- minimum projected integer-domain reduction: 95.37%

This is a structural bound. Exact A6 model counts must be captured from the runtime model audit.

## A4 + A5 combined structural direction

A4 had already removed 13,122 continuous grid variables, 13,068 linear equalities and 3,510 line-circle QCP constraints. A5 adds at most 4,395 node binaries/equalities while removing 99,283 MOVE variables from the integer domain. The combined structure therefore remains smaller in total variables/rows while radically reducing combinatorial dimension.

## Persistent rolling architecture

A5 reuses static/immutable context and the A4 topology projection across issues. Each issue rechecks topology identity. Full cross-issue Gurobi model reuse is intentionally not adopted because actual queue/running/WAN state and issue-specific causal mobility coefficients are dynamic scientific inputs. This avoids stale-constraint and future-leakage risk.

## No scientific relaxation

No change to H54, 5-minute cadence, 3% acceptance, K=3 traffic authority, D2 connection delay, Safe-energy semantics, Rack/WAN gates, voltage/thermal hard limits, Fresh Exact OpenDSS, future-actual prohibition, future-D2 reinjection prohibition, or h0-only commit.

## Validation scope

Static/proof validation only. No long issue152 solve in A5. A6 is the first long closure execution after A1–A5.
