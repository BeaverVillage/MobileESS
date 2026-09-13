# STA topology-only procedure: pre-selection freeze

The guarded v3 AIDC mapping is FINAL. FINAL_AIDC_HOST_AUTHORITY.json records its original 12 hosts; no selector may change them. Both AIDC and STA are MESS service locations. The output has 24 distinct electrical hosts (12+12), not new circuit elements or operational hosting-capacity approval.

## Inputs and eligibility

Join archived final_service_nodes_24.csv STATION records to v01_reduced48_nodes_v2.csv by traffic_node, retaining exactly STA01–STA12. Ignore the legacy feeder_bus column. Use existing longitude/latitude without replacement. Project all 24 anchors into one local east/north plane at their mean latitude/longitude, radius 6371.0088 km. STA shape calculations center/RMS-normalize only the 12 STA points. Allow proper rotation, translation and uniform scale, never reflection.

STA candidates are the 606 frozen 12.47-kV ABC primary buses with root distance >=1.3819547376654384 ohm, excluding the 12 final AIDC buses: 594. Keep all source/substation/regulator-terminal/secondary/single/two-phase exclusions and group IDs unchanged. AIDC positions are not optimization variables.

## Criteria and finite deterministic procedure

For continuity use the previous geometry and separation bounds for STA: E_coord<=0.20, E_pair<=0.20, two-nearest-neighbor retention>=0.50, every STA pair electrical distance>=0.9129072401559803 ohm and geographic distance>=2221.532547954318 original-coordinate units. Freeze these before searching, without recomputing them on 594 candidates. Keep original 638-pool objective normalization maxima.

Among hard-feasible mappings use the established lexicographic order: minimize maximum then mean shared-path ratio; maximize minimum electrical distance; maximize represented major laterals, then groups, then minimize group-count square sum; maximize minimum geographic distance; minimize E_coord then E_pair; maximize nearest-neighbor retention; lexical STA bus tuple. This enforces geometry preservation before feasible electrical comparison and does not claim global optimality.

Use unchanged finite search: 72 rotations (0:5:355), 7 scales (.30:.10:.90 times candidate RMS radius), 25 bounding-box centers (axis fractions .2,.35,.5,.65,.8); 12,600 Hungarian assignments; 32 feasible/64 infeasible retained starts; 12 repair sweeps; best 16 feasible starts with at most 20 local sweeps; all eligible one-site replacements and 66 label swaps. Seed=0 with no random draws, single-thread, objective rounding 1e-9. Seed bounds/RMS radius use the 594 pool. No manually chosen hosts or retuning after results.

Independently recalculate STA membership, immutable AIDC mapping, root guard, geometry and 66 STA pairs from frozen corridors/coordinates. Run the identical selection twice and compare final mapping and decision logs. Failure to find feasibility is reported without relaxing criteria or changing AIDC hosts.

## Cross-pair diagnostics and output

For 144 AIDC–STA pairs report shared-path intersection/union ratio, LCA, electrical distance, canonical geographic distance and Melbourne distance, with min/mean/max and nearest-AIDC identity diagnostics. Cross pairs are diagnostic only; no STA–STA spacing threshold is imposed on them. Distinct membership prevents colocated electrical hosts. Separately diagnose distance shape and residual to the common similarity transform fitted to the final AIDC mapping. Independent STA fitting does not guarantee preservation of all AIDC–STA relative directions; do not claim otherwise.

Save final 24-location mapping, 66 STA pairs, cross-pair diagnostics, topology figure and SHA256 manifest plus supporting reproducibility evidence. Coordinates have unverified CRS/native units. Do not claim operational benefit or global optimality.

Only frozen static topology/geography and selection evidence may be read. Never access V41R4/May/B0–B3, operational load, voltage, loading, loss, sensitivity or objective results. No OpenDSS compile, load/PCC generation, background scaling or B0–B3 execution. All writes remain here; all previous evidence remains immutable.
