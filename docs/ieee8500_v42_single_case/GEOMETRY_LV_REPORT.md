# IEEE8500 V42 geometry and low-voltage eligibility audit

Result: **STOP_FIXED_AIDC_GEOMETRY_INFEASIBLE**. No final low-voltage STA mapping is selected.

The immutable v3 AIDC electrical buses conflict with the traffic east/west and north/south orders. Both independent affine row feasibility problems have empty exact angular feasible sets. Therefore no common affine transform, including any proper rotation and positive uniform scaling, can preserve every fixed AIDC direction. STA re-selection cannot repair this fixed-anchor conflict. This proof covers affine/similarity transforms; arbitrary nonlinear warps are not an approved mapping policy.

The geometry tolerance was frozen before candidate scoring: near-pair distance 0.001 km and per-axis zero tolerance 0.001 km (1 m) in traffic coordinates. No fixed AIDC pair is distance-exempt. No threshold was relaxed. The fitted similarity is diagnostic only, uses all 12 AIDC anchors, has positive determinant, and is applied unchanged to all 24 service locations and candidate proxies.

## Reproducible infeasibility certificate

For every required axis sign, form v = sign(traffic delta) × (grid_b − grid_a). A preserving affine row r requires r·v > 0. Each witness below has strictly positive convex weights whose vector sum is zero, making simultaneous strict inequalities impossible. Exact interval enumeration also verifies the empty feasible sets without a sampled-angle search.

### east_west

| Pair | Traffic axis delta km | Signed grid delta x | Signed grid delta y | Positive weight |
|---|---:|---:|---:|---:|

| AIDC02–AIDC03 | -0.387487772 | -2676.690946 | -12171.300875 | 0.4739314708265087 |

| AIDC07–AIDC11 | 0.567960636 | 5600.514053 | 10577.141770 | 0.46810856005429 |

| AIDC11–AIDC12 | -31.515441645 | -23345.086486 | 14097.866765 | 0.0579599691192012 |


Weighted vector residual: `[-4.547473508864641e-13, -5.684341886080801e-13]`.

### north_south

| Pair | Traffic axis delta km | Signed grid delta x | Signed grid delta y | Positive weight |
|---|---:|---:|---:|---:|

| AIDC09–AIDC12 | -0.150312221 | -14739.824654 | 4893.675524 | 0.31680315444818713 |

| AIDC10–AIDC12 | 1.904598756 | 4981.026821 | -940.986369 | 0.6142251062989824 |

| AIDC11–AIDC12 | 12.921441285 | 23345.086486 | -14097.866765 | 0.0689717392528305 |


Weighted vector residual: `[-2.2737367544323206e-13, 0.0]`.

## All required pair classes

`RELATIVE_POSITION_AUDIT.csv` contains 276 pairs: 66 fixed AIDC–AIDC, 66 STA–STA, and 144 AIDC–STA. It compares traffic directions with the one common fitted transform. STA electrical positions in this diagnostic audit are the retained original MV registry, not a selected LV mapping.

| Pair class | Pairs | Violated pairs | X violations | Y violations |
|---|---:|---:|---:|---:|

| AIDC-AIDC | 66 | 17 | 2 | 15 |

| AIDC-STA | 144 | 36 | 15 | 25 |

| STA-STA | 66 | 8 | 1 | 7 |


## Complete original customer-side triplex pool

The active unbalanced feeder declares **1177 customer-side candidates** reached by traversal from actual service-transformer secondary terminals across the full triplex graph. The transformer identity is obtained from terminal connectivity rather than bus-name guesses. Every candidate records the primary phase, three original winding ratings, customer load on both legs, and the exact triplex support path. A 240 V connection is `.1.2`; the two 120 V legs are `.1.0` and `.2.0`.

`Buscoords.dss` explicitly says X/SX coordinates were added by script on 2019-06-06. Most transformer secondary points were shifted (5, 0) and customer points (45, 40) from primary points. Of this pool, 1,171 customer points use (45, 40) offsets; six special rows are manual near-primary schematic placements with (0, 9) offsets, separately identified in the candidate CSV. `AddBusXY.py` provides matching source provenance. These are schematic offsets, not surveyed customer geography. The candidate location basis is therefore the actual upstream primary bus coordinate, explicitly labeled a proxy with unknown CRS. Source schematic coordinates are stored in separate columns and never treated as surveyed locations.

The maximum original service-transformer primary rating in this pool is 250 kVA. Triplex NormAmps are original source ratings. The reported minimum of transformer primary kVA and 0.240 kV × conductor NormAmps is only a balanced-connection engineering upper bound. It is not available headroom, an approved inverter rating, or permission to inject. Original triplex neutral is grounded and Kron-reduced; independent neutral ampacity is not provided.

All candidates remain physically unqualified: original data does not establish MESS ports, inverter/isolating interface, reverse-power protection, vehicle access, or connection times. Candidate voltage/current feasibility and transformer loading must also be checked by actual AC. The 450 kW / 600 kVA vehicle rating cannot be applied to these service connections. Allowed PCC P and Q are left unset, so no undocumented port is enabled.

`FINAL_STA_MAPPING.csv` contains all 12 unchanged STA service and traffic identities. Its final LV fields are blank and `is_final_selection=False`; original MV buses are retained only for separately labeled diagnostic AC work. Original MV electrical eligibility is not proved by this geometry audit. No equipment was created or frozen evidence modified.

The gate can be resolved only by an explicit change to the conflicting fixed-anchor/direction contract or independently supported source-coordinate corrections, and by supplying defensible LV port equipment/protection/access data. The implementation makes neither decision implicitly.
