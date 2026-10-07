"""Read-only PR168 inputs and deterministic preregistration."""
from pathlib import Path
from dataclasses import replace
from fractions import Fraction
import gzip,pickle
import numpy as np
import scipy.sparse as sp
from v42_pr134_b1.common import atomic,read,record,sha,digest
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
from v42_a_stage_domain_v2.active import _graph,_ledger,option_from_json
from v42_a_stage_domain_v2.domain import physical_starts
from v42_a_stage_domain_v2.census import load_frozen
from v42_a_stage_domain_v2.fast_census import load_physical_cache,verify_partition
from . import BASE

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/v42_a_stage_phase1_pricing_20261007'
HISTORY=ROOT/'docs/v42_a_stage_fast_active_domain_20261007'
STATIC=ROOT.parent/'v42-a-stage-phase1-static'
OLD_STATIC=ROOT.parent/'v42-a-stage-fast-active-static'
DAY='2025-05-19'
POLICY=dict(schema='PHASE1_POLICY_V1',canary_day=DAY,cumulative_native_seconds=300,
    native_plus_pricing_wall_seconds=600,max_phase1_rounds=20,max_P1_rounds=4,
    batch_initial=32,batch_minimum=16,batch_maximum=64,high_density=.5,low_density=.1,
    epsilon_price='1/100000000',certified_zero_tolerance='1/100000000',
    raw_original_replay_tolerance=1e-6,RC_absolute_tolerance=1e-7,RC_relative_tolerance=1e-10,
    original_active_columns_limit=200000,active_STAY_fraction_limit=.5,
    active_migration_paths_limit=2000000,max_factor_nnz=250000000,max_factor_memory_GB=2.,
    max_new_native_columns_per_round=10000,
    candidate_order='exact rational oracle point price vs active local lower bound, class id, support SHA',
    batching_adaptation='negative block density only; no answer-dependent tuning',
    inactive_pool_scan='all STAY; full native compact block LP for migration and mixed fractional finishes',
    artificial_weight_rule='1 / 2**ceil(log2(max(1,abs(rhs),max_abs_original_row_coefficient)))',
    artificial_rows='all global/nonlocal original rows; class-local normalization and all local physics hard',
    dual_certificate_projection='separate saved attempt: clip global Pi to legal elastic weight/sense box; no primal modification',
    integer_production_lanes_aggregated=False,solver_parameter_sweep=False,
    other_27_dates=False,post_gate_native_execution_requires_separate_verified_full_LP_and_integer_architecture=True)


def preregister():
    OUT.mkdir(parents=True,exist_ok=True);STATIC.mkdir(parents=True,exist_ok=True)
    target=OUT/'PHASE1_ENGINEERING_POLICY.json'
    if target.exists() and read(target)!=POLICY:raise ValueError('PREREGISTERED_PHASE1_POLICY_DRIFT')
    atomic(target,POLICY)
    atomic(OUT/'BASE_IDENTITY.json',dict(PASS=True,exact_base=BASE,base_PR=168,
        base_head_branch='codex/v42-a-stage-domain-authority-v2',new_branch='codex/v42-a-stage-phase1-pricing',
        PR168_artifact_manifest=record(HISTORY/'SHA256_MANIFEST.json'),historical_evidence_read_only=True))
    atomic(OUT/'PHASE1_ROW_POLICY.json',dict(PASS=True,global_rows=POLICY['artificial_rows'],
        local_rows_hard=True,variable_bounds_hard=True,production_artificials=0,
        proof='A locally feasible STAY assignment exists in every retained class. Every global row can be satisfied by its nonnegative artificial(s). Original bound boxes must be nonempty.',
        singleton_and_class_normalization='retained hard; local feasible normalization does not require artificials'))
    atomic(OUT/'PHASE1_WEIGHT_POLICY.json',dict(PASS=True,rule=POLICY['artificial_weight_rule'],
        positive_dyadic_rational=True,per_native_row_weights_saved_before_optimize=True,
        fixed_before_May19=True,answer_tuned=False,zero_tolerance=POLICY['certified_zero_tolerance'],
        original_replay_tolerance=POLICY['raw_original_replay_tolerance']))
    text='''# Phase-I preregistration

Base PR168 exact publication HEAD: 9336d8f7fba243df86e8dff0276e70942855039c. All historical evidence is read-only. Only May19 LP canary and its complete local pricing LPs are initially authorized. No May17 native regression, May12/May10 native optimization, full A1, Planning, Actual or Fresh follows unless Speed Gate V2 and separate closure/architecture gates pass.

The scientific domain, original coefficients, bounds, objectives, tolerances and frozen Method2/Threads1 solver policy remain unchanged. Phase-I copies active columns and attaches positive-weight artificials only to global rows. Local normalization, checkpoint/WAN/service/finish physics remain hard. Positive dyadic weights use the fixed row scale rule in PHASE1_WEIGHT_POLICY.json; every concrete weight is written before optimize. Phi>0 is diagnostic, never production feasible.

Complete compact-domain graphs and unchanged native builders supply all local LP directions. Identical continuous optional migration lanes can be summed for PRICING ONLY: N copies of convex P project exactly to N*P. Local matrix A and coupling B are unchanged; RHS/boxes are exactly N-scaled (reject nonexact binary64 scaling). Production integer lanes are retained. A finite physical-path scan alone cannot certify mixed fractional closure.

Persist raw X,Pi,RC,Slack and all statuses before replay/assertions. Verify native c-A.T@Pi including original bounds. Exact rational local dual bounds include every finite box residual. A separate projected certificate attempt preserves raw Pi. Full lower bounds combine legal elastic global dual, original global bound box and every complete local LP block. Complete-block certificate lower bounds, not heuristic path scores, control closure. Missing coverage, a raw failure or an uncertified local solve fails closed.

Native cumulative budget300s; native plus pricing-wall budget600s (conservatively double-charge pricing-native overlap); at most20 Phase-I rounds and4 original-P1 rounds. Batches32, bounded16..64, change only with negative block density. Original active columns<=200000, active STAY<=50%, migration represented paths<=2000000, per-round native growth<=10000; factor thresholds250M nonzeros/2GB are checked after rounds. These are engineering stops, never scientific infeasibility. All parameter/tolerance/weight/cap choices precede May19 execution.
'''
    target=OUT/'PREREGISTRATION.md'
    if target.exists() and target.read_text(encoding='utf8')!=text:raise ValueError('PREREGISTRATION_DRIFT')
    target.write_text(text,encoding='utf8',newline='\n')
    (OUT/'PHASE1_AUTHORITY.md').write_text('''# Auxiliary Phase-I authority

For equality add u-v; for <= add -s; for >= add +s. Every artificial is nonnegative and has a strictly positive dyadic objective coefficient. They exist only in the auxiliary copy. Production/original-objective snapshots contain zero artificials.

Normalize each hard local class block with its ORIGINAL cardinality. All global rows (including grid/CC4 rows linked indirectly through GPU/Runtime) are elastic. Valid local STAY support plus nonempty global variable boxes proves auxiliary feasibility by construction; the actual constructed point and all hard rows are replayed before execution.

With global dual p, a full native local block oracle minimizes -p^T Bz over all original hard local rows/boxes. Class optional lane sums are exact for continuous LPs by convexity: sum(z_l) lies in N*P, and any sum vector is realizable by N equal copies. This does not aggregate integer production lanes or substitute a physical-path hull for native fractional finish directions.

The global Lagrangian bound is p^T b plus the minimum over the original global variable box plus all certified full local minima. Elastic dual row senses and the artificial-weight box must hold. Full-domain infeasibility requires this bound strictly positive, exhaustive class/block coverage and independently valid certificates. The active Phi alone is not sufficient. LP pricing closure is separate from integer-domain closure and never production acceptance.
''',encoding='utf8',newline='\n')


def load_initial():
    meta=read(HISTORY/'MAY19_CANARY/rho/LP_0000/BUILD_METADATA.json')
    for r in meta['static_artifacts']:
        if record(r['path'])!=r:raise ValueError('PR168_EXTERNAL_SNAPSHOT_DRIFT')
    files={Path(r['path']).name:Path(r['path']) for r in meta['static_artifacts']}
    attributes=np.load(files['INITIAL_ACTIVE_ATTRIBUTES.npz'])
    with gzip.open(files['SCIENTIFIC_INTERFACES.pkl.gz'],'rb') as f:descriptor=pickle.load(f)
    rho=next(e for n,e in descriptor['levels'] if n=='rho')
    objective=Objective('rho',((int(rho[1]),Fraction(1)),),Fraction(0))
    snapshot=LinearSnapshot(sp.load_npz(files['INITIAL_ACTIVE_MATRIX.npz']),attributes['lower'],
        attributes['upper'],attributes['senses'],attributes['rhs'],np.full(len(attributes['lower']),'C'),(objective,)).require()
    if snapshot.fingerprint()!=meta['lp_snapshot_sha256']:
        # Fingerprint includes all four objectives. Their immutable descriptor
        # definitions must be restored before comparing the original receipt.
        objectives=[]
        for name,source in [('rho','rho'),('migration_count','migration_count'),('shift_magnitude','shift_slots'),('prestart_relocation','prestart_changes')]:
            e=next(e for n,e in descriptor['levels'] if n==source)
            terms=((int(e[1]),Fraction(1)),) if e[0]=='v' else tuple((int(j),Fraction(float(c))) for j,c in zip(e[2],e[3])) if e[0]=='e' else ()
            constant=Fraction(float(e[1])) if e[0] in ('c','e') else Fraction(0)
            objectives.append(Objective(name,terms,constant))
        snapshot=replace(snapshot,objectives=tuple(objectives)).require()
    if snapshot.fingerprint()!=meta['lp_snapshot_sha256']:raise ValueError('ORIGINAL_ACTIVE_SNAPSHOT_IDENTITY')
    data,frozen=load_frozen(DAY)
    # Path relocation is engineering provenance, not permission to accept a
    # changed physical producer. Verify current bytes against every old source
    # record, then let the unchanged strict loader verify the original receipt.
    from v42_a_stage_domain_v2 import fast_census
    cache_receipt=read(OLD_STATIC/DAY/'PHYSICAL_DOMAIN_CACHE.json')
    current_sources=fast_census._producer_sources()
    for current,prior in zip(current_sources,cache_receipt['producer_sources']):
        if current['sha256']!=prior['sha256'] or current['bytes']!=prior['bytes']:
            raise ValueError('RELOCATED_PHYSICAL_PRODUCER_BYTE_DRIFT')
    saved=fast_census._producer_sources
    try:
        fast_census._producer_sources=lambda:cache_receipt['producer_sources']
        domains=load_physical_cache(DAY,data,frozen/'DATA.pkl',OLD_STATIC)
    finally:fast_census._producer_sources=saved
    support=read(HISTORY/'MAY19_INITIAL_ACTIVE_SUPPORT.json')
    bounds,graphs,retained={},{},[]
    for key,members in data[7]['classes'].items():
        uid=members[0]; job=data[1][uid]
        stays={(s,k) for k,ranges in support['active_STAY_intervals_by_class'][key].items() for lo,hi in ranges for s in range(lo,hi+1)}
        migration=tuple(option_from_json(o) for o in support['migration_explicit_seeds_by_class'].get(key,()))
        retain=len(members)==1 and bool(data[5][uid].events['w'])
        if retain:retained.append(uid)
        g=_graph(job,stays,migration,domains[uid],retain)
        for member in members:
            graphs[member]=g; bounds[member]=replace(data[2][member],allowed_starts=physical_starts(data[1][member],data[2][member]))
    prep=dict(data[7],domain_authority='AIDC_A_STAGE_DOMAIN_AUTHORITY_V2',
        preserve_singleton_mixed_flow=tuple(sorted(retained)),
        physical_domain_hash=meta['physical_authority_sha256'],full_migration_domain_active=False)
    active=(data[0],data[1],bounds,data[3],data[4],graphs,data[6],prep)
    ledger=_ledger(active,domains,{key:{} for key in prep['classes']})
    verify_partition(ledger)
    expected=meta['domain_census']
    for key in ('active_STAY','inactive_STAY','active_migration','inactive_migration','physical_STAY','physical_migration'):
        if ledger['receipt'][key]!=expected[key]:raise ValueError('EXACT_PR168_INITIAL_'+key+'_DRIFT')
    global_variables=read(files['INITIAL_ACTIVE_MATRIX.npz'].parent/'F2-CRA_MODEL_COMPLETE.json')['global_variables']
    axes={('GPU',site,t):int(e[1]) for (site,t),e in descriptor['known'].items()}
    axes.update({('RUNTIME',site,t):int(e[1]) for (site,t),e in descriptor['risk'].items()})
    cursor=max(axes.values())+1
    for link,t in data[3].wan_capacities:axes['WAN',link,t]=cursor;cursor+=1
    for t in range(data[3].control_end):axes['ACTIVE','',t]=cursor;cursor+=1
    axes=dict(sorted(axes.items()))
    return snapshot,descriptor,active,domains,ledger,axes,global_variables
