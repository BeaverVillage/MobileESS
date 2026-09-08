# GPU capacity dependency graph

```mermaid
flowchart TD
 C[V39C site GPU authority] --> R[V39D nonadditive rack envelopes]
 C --> I[Installed idle IT load]
 C --> F[Active GPU range and full IT ceiling]
 R --> B[Deterministic B0 resource feasibility]
 C --> B
 B --> G[Per-slot reserved GPU profile]
 G --> P[Site IT power]
 I --> P
 P --> Q[C1 weather-dependent PCC P/Q tables]
 C --> H[H4 physical cap and available reserve]
 C --> M[Initial placement and migration eligibility]
 A[Immutable exogenous AC anchor] --> E[Planning electrical coefficients]
 X[Topology, ratings, D1 background, generator] --> E
 E --> N[Planning evaluation at changed PCC P/Q]
 Q --> N
 Q -. only if explicitly recentered .-> A
```

- CASE 2: installed capacity contributes existing idle power, 104.1606964512843 W/GPU.
- Rack pools are four/site, nonadditive, not physical racks. Envelope update YES; modeled topology change NO; physical rack count unknown.
- Per-GPU power/C1 coefficients unchanged; aggregate 624-specific range and conservation authority must change.
- H4 physical cap, capped actionable reserve, power tables, B0 reference, candidate identities and eligibility require propagation.
- Electrical coefficient class A under exact unchanged exogenous anchor and generator inputs; reuse must be recertified, not relabeled as fresh generation.
- Recentered anchor means full 31-day regeneration. No generation performed in this audit.
- Capacity and baseline do not directly enter existing electrical coefficient arithmetic; they do enter the context power tables after coefficients.
- Current PCC: 500 kVA and 208.179183602 A per AIDC transformer phase, plus shared network constraints.

Exact file/line/hash dependencies are in GPU_CAPACITY_DEPENDENCY_AUDIT.json and ELECTRICAL_COEFFICIENT_IMPACT_AUDIT.json.
