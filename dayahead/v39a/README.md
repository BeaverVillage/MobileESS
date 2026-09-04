# V39A causal AIDC site placement and power

V39A asks whether the accepted V37 RW/RSP temporal schedules can be placed on
the frozen 12 modeled AIDC sites while preserving GPU-gang indivisibility and
causal `current_AIDC` state. It does not redesign the temporal scheduler.

The implementation first solves a deliberately more permissive lower-bound
model: each operating day and temporal mode may select AIDCs independently,
with no cross-day state or inter-AIDC WAN restriction. If that model is
infeasible, the stricter causal model is necessarily infeasible.

The production interval is extracted from the V37 scheduler's 120-slot frame
using slots 24 through 119. PENDING placement has no source AIDC and is not a
migration. Continuously RUNNING jobs carry `current_AIDC`; any change would
have to use the frozen V38 checkpoint and fixed-path inter-AIDC WAN state
machine.

Site power is a synthetic capacity-proportional decomposition of the frozen
aggregate AIDC power model. It is not measured site power. Frozen legacy
`source_idc_id` values are exposed only as feeder PCC-node compatibility
aliases; all current placement terminology is AIDC.

V39A currently fails closed because the May 21 V37 schedule contains 15
simultaneous indivisible 32-GPU gangs, while the fixed capacities can host at
most 14. The site trajectory Parquets are therefore schema-only blocked
artifacts, May execution is not launched, and V39B is not implemented here.
