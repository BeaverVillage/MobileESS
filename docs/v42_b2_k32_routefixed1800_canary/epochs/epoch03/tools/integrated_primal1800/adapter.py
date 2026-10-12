"""Extend PR216 restrictions without editing its source or FULL validator."""
from pathlib import Path
import hashlib
import json
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
DOCS = ROOT/'docs/v42_b2_integrated_primal1800_canary'
BASE = '38d98b99d1ea5ce9021fe0d727ab80309910b63d'
OLD = ROOT/'docs/v42_b2_u4_primal_alns_600x3'
from tools.u4_primal_alns import verify as v, resources as r, neighborhood as n, current_grid as g
from v42_common_mess.storage import write, record
from v42_common_mess.fixed_pattern import stationary_paths, values_for
from v42_common_mess.neighborhood import inventory, route_witness

ORIGINAL_AUDIT = v.audit_neighborhood


def configure():
    # Output relocation is confined to the new adapter process. Original files,
    # validator bodies, matrix coefficients and model builder remain unchanged.
    v.DOCS = DOCS
    r.DOCS, r.BASELINE = DOCS, DOCS/'PROTECTED_BASELINE.json'
    r.ORIGINALS = dict(r.ORIGINALS, PR216=(Path(r'D:\v42_b2_u4_primal_alns_600x3_20261012'), BASE))
    g.DOCS = DOCS


configure()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def guard():
    frozen = read(DOCS/'EXECUTED_SOURCE_HASHES.json')
    for path, expected in frozen.items():
        v.require(v.file_sha(ROOT/path) == expected, 'EXECUTION_SOURCE_DRIFT:'+path)


def initialize_protection():
    baseline = r.create_baseline()
    paths = {item['path'] for item in baseline['protected_files']}
    external = Path(r'D:\v42_b2_u4_primal_alns_600x3_20261012')
    index = read(external/'docs/v42_b2_u4_primal_alns_600x3/ARTIFACT_INDEX.json')
    additions = [external/item['path'] for item in index['files']]
    additions.append(external/'docs/v42_b2_u4_primal_alns_600x3/ARTIFACT_INDEX.json')
    for path in additions:
        if str(path) not in paths:
            baseline['protected_files'].append(r.digest(path))
            paths.add(str(path))
    baseline['PR216_exact_HEAD'] = BASE
    baseline['PR216_artifacts_readonly_and_separately_protected'] = len(additions)
    write(r.BASELINE, baseline)
    r.baseline.cache_clear()


def restriction(case, center, spec):
    d=case.d; binary=np.flatnonzero(d['types']!='C')
    if spec['method']=='INITIALIZE':
        ids=np.asarray(spec['fixed_representatives'],dtype=np.int64)
        vals=np.asarray(spec['representative_values'],dtype=np.float64)
        v.require(set(binary)<=set(ids) and np.isin(vals,(0.,1.)).all(), 'COLD_FIXED_LITERAL_INTEGER_REPRESENTATIVES')
        low,high=d['lower'].copy(),d['upper'].copy();low[ids]=vals;high[ids]=vals
        v.require(np.all(low>=d['lower']) and np.all(high<=d['upper']), 'COLD_BOX_INSIDE_SOURCE')
        return low,high,np.array([],dtype=np.int64),np.array([],dtype=float),0.,dict(PASS=True,
            cold_start=True,old_incumbent_used_as_start=False,fixed_representatives=len(ids),
            fixed_binary_count=len(binary),free_binary_count=0,Global_LB_admissible=False)
    free=np.asarray(spec['free_binary_columns'],dtype=np.int64)
    fixed=np.asarray(spec['fixed_binary_columns'],dtype=np.int64)
    route=np.asarray(spec['fixed_route_columns'],dtype=np.int64)
    ham=np.asarray(spec['hamming_columns'],dtype=np.int64)
    v.require(np.array_equal(np.sort(np.r_[free,fixed]),binary) and len(set(np.r_[free,fixed]))==len(binary),'BINARY_PARTITION')
    v.require(set(ham)<=set(free) and len(set(ham))==len(ham),'HAMMING_SUBSET')
    low,high=d['lower'].copy(),d['upper'].copy();fix=np.r_[fixed,route]
    low[fix]=center[fix];high[fix]=center[fix]
    v.require(np.all(low>=d['lower']) and np.all(high<=d['upper']) and np.all(center>=low) and np.all(center<=high),'CENTER_SOURCE_BOX')
    coeff=np.where(center[ham]==1.,-1.,1.);rhs=float(spec['hamming_radius'])-float(np.count_nonzero(center[ham]))
    return low,high,ham,coeff,rhs,dict(PASS=True,free_binary_count=len(free),fixed_binary_count=len(fixed),
        fixed_continuous_route_count=len(route),hamming_columns=len(ham),hamming_radius=spec['hamming_radius'],
        all384_Mode_free=spec['method']!='U4',Modes_in_Hamming=int(sum(str(d['names'][j]).startswith('charge_mode[') for j in ham)),
        center_always_included=True,Global_LB_admissible=False)


def audit(case,center,spec,low,high,output=None):
    d=case.d
    v.require(v.domain_sha(d)==v.DOMAIN_SHA and v.matrix_sha(case.A)==v.MATRIX_SHA,'ORIGINAL_SOURCE_NATIVE_MATRIX_DOMAIN')
    if spec['method']=='INITIALIZE':
        ids,vals=values_for(case,stationary_paths(case),lambda unit,t: spec['charge_pattern']=='before_peak' and t<48)
        v.require(np.array_equal(ids,spec['fixed_representatives']) and np.array_equal(vals,spec['representative_values']),'COLD_PATTERN_SOURCE_GENERATION')
        expected_l,expected_u=d['lower'].copy(),d['upper'].copy();expected_l[ids]=vals;expected_u[ids]=vals
        v.require(np.array_equal(low,expected_l) and np.array_equal(high,expected_u),'COLD_EXACT_BOUND_RESTRICTIONS')
        result=dict(PASS=True,old_saved_solver_start=False,all_original_integer_representatives_fixed_literal=True,
            all_original_rows_and_nonroute_continuous_bounds_preserved=True,all_original_terminal_rows_satisfied=True,
            Source_Physical_Stationary_Path_Construction=True,source_case=case.case_sha,Native_optimize_calls=0)
    else:
        replay=read(spec['center_full_replay']['path'])
        v.require(v.file_sha(spec['center_full_replay']['path'])==spec['center_full_replay']['sha256'] and replay['PASS']
            and replay['source_sha']==v.SOURCE_SHA and replay['case_sha']==v.CASE_SHA
            and replay['point_vector_sha256']==v.vector_sha(center),'EXPLICIT_FRESH_FULL_CENTER')
        if spec['method']=='U4':
            expected=restriction(case,center,spec)
            v.require(np.array_equal(expected[0],low) and np.array_equal(expected[1],high),'U4_EXACT_SOURCE_FIXINGS')
            v.require(spec['source_U4_route_openness']['PASS'],'U4_ROUTE_OPENNESS')
            result=dict(PASS=True,original_U4_select_reused_unchanged=True,Source_center_included=True,
                original_rows_bounds_and_integer_types_preserved=True,Native_optimize_calls=0)
        else:
            surrogate=spec['PR216_base_spec']
            sl,su=d['lower'].copy(),d['upper'].copy()
            ids=np.r_[surrogate['fixed_binary_columns'],surrogate['fixed_route_columns']].astype(np.int64)
            sl[ids]=center[ids];su[ids]=center[ids]
            base=ORIGINAL_AUDIT(case,center,surrogate,sl,su)
            v.require(base['PASS'],'UNCHANGED_PR216_ROUTE_ALIAS_AUDIT')
            expected=restriction(case,center,spec)
            v.require(np.array_equal(expected[0],low) and np.array_equal(expected[1],high),'NEW_BOX_FIXINGS_EXACT')
            modes=np.flatnonzero(np.char.startswith(d['names'],'charge_mode['))
            v.require(len(modes)==384 and set(modes)<=set(spec['free_binary_columns']),'ALL384_MODE_RELEASE')
            v.require(np.array_equal(low[modes],d['lower'][modes]) and np.array_equal(high[modes],d['upper'][modes]),'MODE_SOURCE_BOUNDS_UNCHANGED')
            ham=np.asarray(spec['hamming_columns'],dtype=np.int64)
            if spec['method']!='N1':
                v.require(all(str(d['names'][j]).startswith('node_activity[') for j in ham) and not set(ham)&set(modes),'ROUTE_ONLY_HAMMING')
                v.require(set(ham)==set(spec['free_binary_columns'])-set(modes),'ALL_FREE_ROUTE_NODES_IN_HAMMING')
            v.audit_hamming(center,ham,spec['hamming_radius'],expected[3],expected[4])
            nonroute=(d['types']=='C') & ~np.char.startswith(d['names'],'route_flow[')
            v.require(np.array_equal(low[nonroute],d['lower'][nonroute]) and np.array_equal(high[nonroute],d['upper'][nonroute]),'ALL_POWER_SOC_HELPERS_UNRESTRICTED_SOURCE_BOX')
            result=dict(PASS=True,PR216_surrogate_route_alias_proof=base,all384_Mode_free=True,
                Modes_in_Hamming=0 if spec['method']!='N1' else 384,
                hamming_column_count=len(ham),center_Hamming_distance=0,
                FULL_contains_new_restricted_model=True,old_and_new_route_fixings_identical=True,
                physical_coefficients_bounds_objective_and_original_terminal_unchanged=True,
                restricted_Bound_is_Global_LB=False,Native_optimize_calls=0)
    if output:write(output,result)
    return result


def cold_spec(case,pattern='all_discharge'):
    ids,vals=values_for(case,stationary_paths(case),lambda u,t:pattern=='before_peak' and t<48)
    return dict(method='INITIALIZE',candidate_id='COLD_'+pattern,charge_pattern=pattern,
        fixed_representatives=ids.tolist(),representative_values=vals.tolist(),Solver_Start=None,
        Cold_start_source='Source18r original graph stationary_paths/values_for, no stored optimization point')


def make_spec(case,center,method,candidate,replay):
    if method=='U4':
        from v42_common_mess.neighborhood import current_grid,select
        # The original U4 PCS selector reads CSR row pointers. PR216's lazy
        # validator interface intentionally lacks them. Materialize one verified
        # original CSR only in this solver-free selection scope, then release it
        # before constructing any Native model. No source selector is changed.
        import gc
        lazy=case.original_A
        try:
            case.original_A=lazy.tocsr()
            grid=current_grid(case,center,DOCS/'COLD_U4_SOURCE_GRID.json')
        finally:
            case.original_A=lazy;gc.collect()
        old=select(case,center,'U4',0,grid)
        spec=dict(old,method='U4',candidate_id='SOURCE18R_FRESH_U4',selected_units=[],
            fixed_route_columns=[],hamming_columns=old['free_binary_columns'],source_U4_route_openness=old['route_openness'])
    else:
        base_method=method.rstrip('+')
        old=n.make_spec(case,center,base_method,candidate)
        old['center_full_replay']=record(replay)
        modes=np.flatnonzero(np.char.startswith(case.d['names'],'charge_mode[')).tolist()
        free=sorted(set(old['free_binary_columns'])|set(modes))
        binary=set(np.flatnonzero(case.d['types']!='C'))
        ham=free if method=='N1' else sorted(set(free)-set(modes))
        spec=dict(old,method=method,free_binary_columns=free,fixed_binary_columns=sorted(binary-set(free)),
            hamming_columns=ham,all384_Mode_free=True,PR216_base_spec=old,
            Hamming_policy='N1 all384 unconstrained by radius384; N2+/N3+ radius48/96 on route Node-Activity only; all384 Modes excluded.',
            algorithm_center_source='New cold-start FULL-verified Best UB only; PR216 results never solver starts')
    spec['center_full_replay']=record(replay)
    spec['center_point_vector_sha256']=v.vector_sha(center)
    # Exact mathematical neighborhood signature ignores free continuous start
    # values and free Mode values, so equivalent problems cannot be retried.
    low,high,ham,coeff,rhs,_=restriction(case,center,spec)
    h=hashlib.sha256()
    for a in (low,high,ham,coeff,np.asarray([rhs])):h.update(np.ascontiguousarray(a).tobytes())
    spec['mathematical_model_signature']=h.hexdigest()
    return spec


def candidates(case,center):
    context,receipt=g.refresh(case,center)
    ranks=n._signed_ranking(case,center,context)
    units=sorted(case.graph[1],key=lambda u:(-next(c['score'] for c in ranks if c['unit']==u),u))
    single=[dict(candidate_id=f'N2PLUS_{u}_{variant}',selected_units=[u],variant=variant,
        requested_cap_seconds=150,hamming_radius=48) for variant in ('primary','expanded') for u in units]
    pairs=[]
    for i,u in enumerate(units):
        for w in units[i+1:]:pairs.append(dict(candidate_id=f'N3PLUS_{u}_{w}',selected_units=[u,w],variant='primary',requested_cap_seconds=180,hamming_radius=96))
    return single,pairs,receipt
