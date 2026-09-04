# V39B pre-implementation scientific diagnostic

This package does not implement or mutate a production scheduler. It audits
whether the frozen V37 RW/RSP schedules that fail V39A spatial placement could
be repaired using only D-1-visible, explicitly flexible PENDING jobs.

The diagnostic reconstructs every exact slot-local packing conflict, verifies
the 120-slot-to-96-slot coordinate mapping, tests the non-shiftable physical
floor, and compares necessary temporal relief with active flexible jobs.

V37 provides PENDING queue classes and an aggregate-capacity first-fit rule,
but it does not provide an authoritative latest start, deadline, maximum shift,
or terminal-service window. The code's 20,000-slot loop guard is not promoted
to scientific authority. Consequently, the diagnostic does not invent a
bounded legal window and does not run the temporal-recourse MILP. Any future
production V39B implementation requires an explicit workload-window authority.

All witnesses and outputs are labelled `NON_PRODUCTION_DIAGNOSTIC_ONLY`.
