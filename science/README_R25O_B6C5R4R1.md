# R25O B6-C5R4R1

This repair addresses the C5R4 root-CG failure where a finite QCP dual solution
produced an analytical/native path reduced-cost discrepancy of 1.5031e-4,
slightly outside the frozen 1e-4 audit envelope.

The discrepancy is never accepted by loosening the envelope. It enters the same
strict QCP-dual retry lifecycle as unavailable Pi/QCPi/RC attributes. Tighter
barrier tolerance, explicit scaling, and numerical focus are applied before the
iteration can generate columns or contribute a lower bound.

Run the outer release with `MOBILEESS_B6_PREFLIGHT_ONLY=1` for hash, regression,
and two licensed Gurobi smoke checks without the issue-152 solve. The shipped
production command runs issue 152 normally and remains diagnostic-only until all
B6 global-certificate and numerical gates pass.
