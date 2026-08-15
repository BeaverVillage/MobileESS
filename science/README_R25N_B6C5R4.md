# R25N B6-C5R4 numerical conditioning and incumbent polish

C5R4 preserves the frozen H54, five-minute, full-cost 3% scientific contract.
It changes only the internal coordinates of MESS power and energy variables from
kW/kvar/kWh to MW/Mvar/MWh, converting explicitly at every external boundary.

After the restricted integer master finds an incumbent, every discrete decision
is fixed and converted to a continuous variable. The remaining convex QCP is
then re-optimized with a tight barrier schedule. This produces the incumbent
used for extraction and the numerical-quality gate without using a post-hoc
same-issue MIP start.

The C5R3 fixed-dual prepass is disabled because its measured budget produced no
material bound lift. Exact child QCP re-optimization and exact pricing closure
remain the only branch-and-price certificate path.

Set `MOBILEESS_B6_PREFLIGHT_ONLY=1` when running the one-command release to
verify hashes, static proofs, release regressions, and the licensed Gurobi polish
smoke test without starting the long issue-152 solve.
