# V33M2 pre-integration API

The isolated MESS pipeline is:

`load_road_graph_authority` → `LinkTravelTimeForecast(Q10,Q50,Q90)` →
`build_mobility_route_table` → `add_mess_mobility_block` →
`extract_mess_trajectory`.

Routing uses one Q50-weighted, deterministic single-source Dijkstra per
departure/origin. Q10, Q50, and Q90 are then summed on that same K=1 path.
Q90 controls travel/connection availability. Safe energy is the maximum of
the frozen physics calculation at Q10, Q50, and Q90 ETA; no energy ML exists.

The Gurobi block owns feasibility only: destination/departure/STAY/MOVE flow,
location-gated P/Q, the frozen 16-face PCS inner polygon, and SoC with safe
route energy debited at departure. A MOVE is emitted only when its ready
arrival is within the horizon. The returned service/PCC P/Q expressions are
for a parent grid model and objective; this package does not import AIDC or
Fresh OpenDSS.

`extract_mess_trajectory` records connected, transit, and connection-delay
slots. Its planned move commitments define the future Actual contract:
destination and route remain fixed, while realized travel time and
physics-only energy may replace their planned values. Rerouting is outside
the present authority.
