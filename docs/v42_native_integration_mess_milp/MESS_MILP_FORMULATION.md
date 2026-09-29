# MESS formulation and conservative conversion

Time-network binary arc x selects a stay or an authorized route with departure, arrival and connection time. Flow conservation gives one continuous path per MESS. Reachability removes only source-unreachable arcs; no favorable-site screening. Each route keeps its source authority hash and full travel energy. Charge/discharge direction remains binary. All units are kW, kvar, kVA, kWh and hours.

At each connected site/time, for f=0,...,15 and theta_f=2*pi*f/16:

`cos(theta_f)*P + sin(theta_f)*Q <= S*cos(pi/16)*x_connected`.

P=Pdis-Pch. Physical Pch/Pdis bounds and Q bounds couple to connection. Opposite polygon normals force P=Q=0 at x=0. No unconstrained transit injection or oversized big-M. SOC obeys `E[t+1]=E[t]+0.25*(eta_c*Pch-Pdis/eta_d)-route_energy[t]`, with unchanged initial/terminal energy and SOC bounds. Route/connection, P, Q and SOC are joint decisions in M1 and M2.

**Proof.** Adjacent supporting lines intersect at angle theta_f+pi/16 and radius S*x. Thus every polygon vertex lies on the radius-S*x circle; convexity puts the entire polygon inside that circle. For any direction, radial support lies between S*x*cos(pi/16) and S*x. At x=0 the only point is the origin. Even for 0<=x<=1, norm squared <=S²*x²<=S²*x, so the quadratic row is redundant in the existing inner16 intersection, including its relaxation.

Worst radial conservatism against circle-only is 1-cos(pi/16)=1.921471960%. No outer polygon and no face-count sensitivity sweep. Latest `joint_mobility.py` had circle AND polygon; its feasible set is unchanged by removing the redundant circle. Historical `mobility.py` had circle only; this conversion deliberately restricts it. Do not conflate those two comparisons.

AST audit finds one generated quadratic PCS family in each of those two source implementations, no quadratic objective. The primary constructor checks `NumQConstrs=0`, quadratic objective terms=0, SOS=0 and general constraints=0 at every objective level; a hidden quadratic grid callback is rejected. Diagnostic circle modes are explicit and cannot silently become production.

Identical synthetic fixture (2 sites, 1 MESS, 8 slots, two declared route arcs): old intersection rho=0.805491712433, circle-only rho=0.805118135754, new MILP rho=0.805491571062. MILP minus circle-only = 0.000373435308472; intersection difference = -1.41371008344e-07 within solver numerical tolerance. Identical route domains, exact circle feasibility, full travel energy and terminal SOC pass. P/Q trajectories need not be unique; full P/Q/SOC differences are reported in the comparison CSV. This is not a native-day equivalence or runtime speedup result.
