# Exact factorized WAN MILP
For each migrating job, select at most one authorized pair P[k,d] and one global WAN start S[t]. A[t] indicates an active transfer slot and F[t] its last active slot. No pair/time binary and no checkpoint/start binary exists. Continuous source departure and destination restart-entry flows select their unique site using the already selected pair. Continuous link-byte flows select path membership. Existing start/checkpoint/source completion/destination completion and r0/h/r1 balances are retained on exact complete-path supports.

Use an exact rational byte quantum q derived from payload B_phys and nominal pair bottleneck rates, with integer-valued units B=B_phys/q. Rates are capped at B INSIDE min; because remaining<=B this is an identity, not throttling. Authority with numerically unsafe unit range fails closed. U[t] is payload remaining before a possible start injection; D[t]=U[t]+B*S[t]. X[t] is bytes sent in quantum units. Selected nominal rate C[t]=sum rate[k,d,t]/q * P[k,d].

Balances and bounds for each slot t:

- A[t]=A[t-1]+S[t]-F[t-1]; F[t]<=A[t].
- A[t]<=D[t]<=B*A[t].
- 0<=X[t]<=D[t], X[t]<=C[t], X[t]<=B*A[t].
- X[t]>=C[t]-B*(1-A[t]+F[t]).
- X[t]>=D[t]-B*(1-F[t]).
- U[t+1]=D[t]-X[t].
- A[t]-F[t]<=U[t+1]<=B*(A[t]-F[t]).
- U[0]=U[H]=0; terminal active equals terminal final; sum S=sum F=sum P=sum q_checkpoint<=1.

Final events with t+1+restart_slots>=H have upper bound zero, exactly as Generator.transfer's strict restart<H contract. Transfer start sends DURING slot t. End=t_final+1 is the first inactive boundary; restart=end+restart_slots. Fixed WAN and active transfers retain their original global rows.

The source of P is bounded by the selected y site. A single destination is derived from P. Source departure sums to S and is bounded by source selection. Waiting balance q->h->departure forbids departure before checkpoint. Destination arrivals sum to shifted F and are bounded by destination selection. r1 balance forbids compute during waiting, WAN or restart. Full r0+r1 service equals frozen Q50 duration; no post-H service is removed.

Original deterministic w event rank is evaluated by one continuous rank variable per job and two finite conditional lookup rows per pair against S[t]. No pair/time product variable is used. All original y/q/w/f0/f1 global rank offsets, including removed events, are retained. Scientific grid/CC4/Runtime binding calls unchanged PR99 functions.

## Sparse exact implementation

Continuous migration_selected equals sum pair. For each t choose the most common authority rate c[t] and write selected rate as c[t]*migration_selected + sum((rate[p,t]-c[t])*pair[p]). This is algebraically identical to sum rate[p,t]*pair[p], with repeated common coefficients removed. The common rate is selected by coefficient frequency only, before optimization.

Active/final, residual/send, restart-entry and positive link-time indices are exact unions of the inherited transfer templates retained by Stage A. Missing indices are implicit zero; every feasible old profile remains represented. Departure indices are the projection (source,time) of retained w. No complete physical Option or pair/time binary is created. The same exact supported y/q/f0/f1/r0/h/r1 states are retained. Unique destination entry with nonnegative flow and one exit already forces r1/f1 to that destination, so duplicate destination gate rows are omitted.

The implementation also defines continuous source_selected[k], destination_selected[d], and link_selected[l] equal to their unique-pair sums once. Routing rows use those scalar totals rather than repeating dense pair sums in each time row. These variables are uniquely 0/1 for integral pairs, add no binary decisions, and have exactly the same LP projection as the expanded expressions.
