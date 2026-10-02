"""Seal base bytes, scientific authority, mathematics and execution policy before solves."""
import gzip,json
from dataclasses import asdict
from collections import defaultdict
from .common import *

SETTINGS=dict(Threads=4,Seed=20260929,Method=1,NodeMethod=1,NumericFocus=1,
              FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,
              MIPFocus=0,Heuristics=0,MIPGap=.005)
def main():
    assert git('rev-parse','HEAD')==BASE
    OUT.mkdir(parents=True,exist_ok=True)
    tracked=git('ls-tree','-r','--name-only',BASE).splitlines()
    dump('PR120_BASE_RECEIPT.json',dict(PR=120,exact_head=BASE,branch=git('branch','--show-current'),
        created_utc=stamp(),files=[dict(path=p,sha256=sha(ROOT/p)) for p in tracked],
        separation='New sibling of PR120. Stopped Benders acceleration branch is neither resumed nor imported.'))
    dump('PREREGISTRATION.json',dict(created_utc=stamp(),base=BASE,primary='EXACT_NODE_ACTIVITY_COMPACT_MONOLITHIC',
        solver=SETTINGS,root_seconds_each=1800,canary_seconds_each=600,order=['ROOT_ORIGINAL','ROOT_COMPACT','C0_ORIGINAL','C1_COMPACT'],
        strengthening='Identical sealed F3, no S2 strengthening rows on either arm',inherited_valid_LB=LB,inherited_valid_UB=UB,
        root_objective_tolerance=1e-8,physical_tolerance=1e-5,mapping_tolerance=1e-12,binary_reduction_gate=.80,
        material_computation=dict(relative_gap_reduction_at_least=.20,OR_valid_LB_increase_at_least=.001,
            valid_LB='max(inherited valid original-M1 LB, independently obtained same-physics MILP BestBd)',
            no_node_speed_fallback=True),
        root_gate='Both fresh LP solves OPTIMAL, bidirectional mapped row/bound residual<=1e-5 and objective difference<=1e-8',
        canary_gate='Proof, exhaustive fixtures, exact sparse substitution, all routes, >=80% reduction, validated same MIP start, root gate',
        production_1800_run=False,production_authorization_artifact_only=True,P2_NOT_RUN=True,M1_ACCEPTED=False,
        A2_NOT_RUN=True,M2_NOT_RUN=True,Actual_NOT_RUN=True,Fresh_AC_NOT_RUN=True,Actual_PQ_repair=False,
        Benders_master=0,Benders_recourse=0,Farkas_cuts=0,Phase_I=0,
        RESOURCE_CONTENTION_ABSENCE_REQUIRED=False,resource_snapshot='CPU, cores, RAM, pagefile/swap, Python/solver processes and accessible command lines before each full solve',
        threadpools='BLAS/OpenMP=1 within worker; Gurobi=4; independent jobs allowed, own heavy solves sequential',
        pruning=False,route_pool=False,trajectory_limit=False,parallel_route_policy='Retain every route ID; make each flow on any parallel tail/head a binary selector, including identical effects. No deduplication.',
        stops=['proof fails','fractional integer movement','mapping fails','scientific row changes','root mismatch','start physics fails'],
        P2_contract='Original MIN_INTERVENTION: movement energy then movement count, only after accepted P1; NOT_RUN here'))
    graph,sites,initial,bundle,battery=graph_inputs()
    groups=defaultdict(list)
    for k,a in enumerate(graph):
        if a[-1] is not None:groups[a[:4]].append((k,a[-1]))
    route_path=bundle['route_table']['path']
    with gzip.open(route_path,'rt',encoding='utf8') as f:source=json.load(f)
    # Retain full authority record bytes/effects for parallel groups; no abbreviated scientific comparison.
    from v42_native.contracts import digest
    records=source['routes'] if isinstance(source,dict) else source
    authority={digest(r):r for r in records}
    rows=[]
    for key,rs in groups.items():
        if len(rs)<2:continue
        for k,r in rs:
            assert r.authority_sha256 in authority
            rows.append(dict(tail_head=json.dumps(key),arc_index=k,route_id=r.route_id,energy_kwh=r.energy_kwh,
                authority_sha256=r.authority_sha256,all_scientific_attributes=json.dumps(authority[r.authority_sha256],sort_keys=True,ensure_ascii=False),
                selector_policy='BINARY_FLOW_NO_DEDUP'))
    table('PARALLEL_ROUTE_AUDIT.csv',rows,['tail_head','arc_index','route_id','energy_kwh','authority_sha256','all_scientific_attributes','selector_policy'])
    dump('PARALLEL_ROUTE_SELECTOR_COUNT.json',dict(PASS=True,accepted_movement_records=len(graph)-len(sites)*96,
        all_graph_arcs=len(graph),parallel_groups=sum(len(v)>1 for v in groups.values()),parallel_routes=sum(len(v) for v in groups.values() if len(v)>1),
        full_route_file=route_path,full_route_file_sha256=sha(route_path),selector_count_pending_full_build=True,
        graph_sha256=digest([(a[:4],None if a[-1] is None else asdict(a[-1])) for a in graph]),
        no_new_route_filter=True,source_domain='Exact original PR120/native accepted records. Existing source exclusions and unreachable symbolic zero remain identical.'))
    docs={
    'ORIGINAL_MOBILITY_FORMULATION.md':'''# Original mobility authority
For each of four units, native reachable arcs carry binary x. A stay arc is (s,t)->(s,t+1); a movement is (source,depart)->(destination,connect). Arrive does not define flow endpoints. Every native accepted route retains its ID, authority digest, energy, departure and connect. Original flow rows impose outgoing-incoming=initial unit at t=0 and zero at t=1..95. Terminal inflow at t=96 is one. Unreachable arcs are symbolic zero, exactly as the original constructor; no new reachability pruning is performed.

Stay x gates Pch/Pdis, Q and every PCS16 face. Charge modes remain binary. SOC recurrence debits route energy at depart, retains charging/discharging efficiencies and quarter-hour duration, initial SOC and terminal equality. The complete sealed F3 matrix preserves the fixed AIDC anchor, every original grid row and original objective. Planning band 0.955–1.045 and all96 line/voltage/transformer constraints are inherited unchanged. P1 minimizes rho; P2 energy then count remains a separate gated contract.
''',
    'COMPACT_MOBILITY_FORMULATION.md':'''# Exact node-activity compact flow
At each original reachable node including terminal t=96, z is binary. Origin at t=0 is fixed one; other t=0 sites are symbolic zero. Every original reachable movement keeps a distinct flow f in [0,1]. For each tail, d=sum outgoing movement f; connected=z-d. Retain 0<=connected<=1, hence 0<=d<=z. Substitute original stay x=connected in every original row and objective, while each movement x=f. All physical continuous columns and charge-mode binaries are retained with identical bounds and objective coefficients.

Original flow rows become z(s,t)=connected(s,t-1)+sum movements whose destination=s and connect=t, with original initial supply. Add explicit terminal node definitions at t=96. Terminal unit inflow remains one. No arrive/connect shift is made. For every parallel transition, retain binary f selectors (including effect-identical routes) to preserve route-ID path multiplicity without fractional mixing. No route is deleted or deduplicated.

Implementation: x=T y, where T contains only -1,0,1. A_compact=A_original T, c_compact=c_original T; every row/RHS/sense remains. Removed stay bounds are added as expression bounds. Independent exact-rational accumulation verifies every changed row coefficient before any optimization. Solver API matrix transport is compared bit for bit. Total columns/rows/nnz may increase; compact refers to integer dimension.
''',
    'COMPACT_PATH_INTEGRALITY_PROOF.md':'''# Path integrality and exactness proof
Assumptions: finite directed acyclic time graph; every edge advances time strictly; one unit of initial flow; nonnegative flows and exact conservation; every reachable node has binary visit activity z; connected stay flow=z-sum departing movements lies in [0,1]; all parallel edges share a tail and head and are either absent or each has binary flow. The graph here has one stay edge per site-time and never a same-site movement. Terminal node activities are explicitly defined. These assumptions are audited, not inferred from a numerical optimum.

Lemma (unit cut): sum of flows crossing any time cut is one, by summing conservation over nodes before that cut. Thus each visited node's throughput is at most one. Nonnegative flow on a finite DAG decomposes into source-terminal paths and contains no circulation.

Induction: initial node throughput is one. Suppose the already selected prefix is a single integral path; all nodes outside this prefix before its current tail have zero flow. If outgoing flow splits, select the smallest head time among positive outgoing edges. No other positive source can feed a head at that time: all positive flow beyond the prefix comes from current outgoing edges, and by minimality none can have landed earlier and re-departed. At each head at that time, incoming throughput equals its binary activity. At least one head receives positive flow, so it receives exactly one. Outgoing total at the tail is one, hence every positive outgoing edge must have that same earliest head. Without parallel edges this selects exactly one edge with value one. With parallel edges their binary flow selectors and total one select exactly one edge, also with value one. All other outgoing edges are zero. Extend the prefix; strict time advancement ends at a terminal node. Every movement f and stay connected is therefore 0/1. Immediate departure at connect is an ordinary next DAG edge; skipped times are transit and have z=0. Energy or other side constraints can only remove paths, not defeat this integrality result.

Counterexample requiring selectors: two continuous parallel routes each with f=1/2 share binary tail/head z=1. Distinct energies or authority records would mix scientific effects. Binary flow selectors remove this ambiguity and preserve both original route-ID paths; even identical parallel records retain selectors for exact route census.

Integer bijection: original binary unit flow defines z as outgoing throughput at nonterminal nodes and incoming throughput at terminal nodes, f as movement x, connected as stay x. It satisfies compact bounds/balance/physics. Conversely the induction gives original binary arc values from f and connected. Charge mode and all physical columns are identity-mapped, so objectives and every constraint coincide.

LP projection: relax ALL binaries in both models, including charge modes and parallel selectors. Original nonnegative unit DAG flow has node throughput<=1 by the unit-cut lemma; define z/f/connected as above. All added compact bounds hold. Conversely x=T y satisfies all original rows and bounds by construction. Compact nonterminal balances and terminal definitions uniquely recover z from x. These linear maps are inverse on feasible points and identity on all physical coordinates; both LP projections and objectives are equal. Side constraints, PCS16, SOC and all grid rows are unchanged under this substitution. Fresh full-model objectives and bidirectional primal mappings are required numerical audits of this algebra, not replacements for it.
''',
    'ORIGINAL_COMPACT_MAPPING_SPEC.md':'''# Bidirectional reconstruction
Axis order is frozen from sealed F3 MPS. Keep all original non-stay columns. Rename original movement columns to movement_flow and relax their binary type unless a parallel transition requires a selector. Append node_activity columns. Forward: copy retained columns; z at t<96 is sum of original outgoing stay/move flows; z at t=96 is previous stay plus incoming movement at connect=96. Inverse: all movement/physical/mode values are copied, stay=z-sum outgoing movement. Both mappings preserve all route IDs and original unreachable symbolic zeros.

No incumbent variable is fixed. Complete validated start values are supplied through Start only. Full original independent route/SOC/PCS/grid/rho validation is called on inverse reconstruction. Every original named row is mapped to the same row position, RHS and sense. The implementation also audits exact rational coefficient sums and complete API transport. Root LP mappings use identical functions with every binary relaxed.
'''}
    for name,body in docs.items():(OUT/name).write_text(body,encoding='utf8',newline='\n')
    print('PREREGISTRATION, PROOF AND ROUTE AUTHORITY SEALED',flush=True)
if __name__=='__main__':main()
