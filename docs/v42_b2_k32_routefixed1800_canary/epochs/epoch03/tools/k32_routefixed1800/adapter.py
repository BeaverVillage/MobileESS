"""Separate execution adapter; all original source builders/validators unchanged."""
from pathlib import Path
import hashlib, json, numpy as np
from tools.integrated_primal1800 import adapter as base
from v42_common_mess.fixed_pattern import values_for, stationary_paths
ROOT=Path(__file__).resolve().parents[2]
DOCS=ROOT/'docs/v42_b2_k32_routefixed1800_canary'
BASE='114f44330fbd995221c55385c6fde5b5b9e40d95'
OLD=base.OLD
v,r,n,g=base.v,base.r,base.n,base.g
write,record,read=base.write,base.record,base.read
base.DOCS=DOCS
base.configure()
r.ORIGINALS['PR217']=(Path('D:/v42_b2_integrated_primal1800_canary_20261012'),BASE)
cold_spec,make_spec=base.cold_spec,base.make_spec
guard=base.guard

def route_values(case, paths):
    ids,vals=values_for(case,paths,lambda u,t:False)
    keep=~np.char.startswith(case.d['names'][ids],'charge_mode[')
    return ids[keep],vals[keep]

def route_spec(case, candidate):
    ids,vals=route_values(case,candidate['paths'])
    binary=np.flatnonzero(case.d['types']!='C')
    modes=np.flatnonzero(np.char.startswith(case.d['names'],'charge_mode['))
    assert len(modes)==384 and set(binary)-set(ids)==set(modes)
    return dict(method='ROUTE_FIXED',candidate_id=candidate['candidate_id'],paths=candidate['paths'],
        route_fixed_columns=ids.tolist(),route_fixed_values=vals.tolist(),
        moves=candidate['moves'],travel_energy_kWh=candidate['travel_energy_kWh'],
        heuristic_score=candidate['score'],Solver_Start=None,free_mode_count=384,
        fixed_route_binary_and_flow_count=len(ids),restricted_ObjBound_is_Global_LB=False)

def restriction(case,center,spec):
    if spec['method']!='ROUTE_FIXED':return base.restriction(case,center,spec)
    ids=np.asarray(spec['route_fixed_columns'],dtype=np.int64)
    vals=np.asarray(spec['route_fixed_values'],dtype=float)
    low,high=case.d['lower'].copy(),case.d['upper'].copy()
    low[ids]=vals;high[ids]=vals
    assert np.all(low>=case.d['lower']) and np.all(high<=case.d['upper'])
    return low,high,np.array([],dtype=np.int64),np.array([],dtype=float),0.,dict(PASS=True,
        all384_Mode_free=True,free_binary_count=384,route_fixed_count=len(ids),
        Global_LB_admissible=False,new_route_start_absent=True)

def audit(case,center,spec,low,high,output=None):
    if spec['method']!='ROUTE_FIXED':return base.audit(case,center,spec,low,high,output)
    assert center is None
    assert v.matrix_sha(case.A)==v.MATRIX_SHA and v.domain_sha(case.d)==v.DOMAIN_SHA
    ids,vals=route_values(case,spec['paths'])
    actual_moves=[case.graph[2][k][-1] for path in spec['paths'].values() for k in path if case.graph[2][k][-1] is not None]
    assert len(actual_moves)==spec['moves'] and len(actual_moves)>=1
    assert abs(sum(float(a.energy_kwh) for a in actual_moves)-spec['travel_energy_kWh'])<=1e-10
    assert np.array_equal(ids,spec['route_fixed_columns']) and np.array_equal(vals,spec['route_fixed_values'])
    el,eu=case.d['lower'].copy(),case.d['upper'].copy();el[ids]=vals;eu[ids]=vals
    assert np.array_equal(el,low) and np.array_equal(eu,high)
    # Independent original-coordinate reconstruction, including eliminated aliases.
    x=np.zeros(len(low));x[ids]=vals;y=case.lift(x)
    chosen={u:set(p) for u,p in spec['paths'].items()}
    vertices={u:{(case.graph[2][k][0],case.graph[2][k][1]) for k in p}|{(case.graph[2][p[-1]][2],96)} for u,p in spec['paths'].items()}
    count=0
    for j,name in enumerate(map(str,case.original_d['names'])):
        family=name.split('[',1)[0]
        if family not in ('arc','node_activity'):continue
        axis=name.split('[',1)[1][:-1].split(',');u=axis[0]
        expected=float(int(axis[1]) in chosen[u]) if family=='arc' else float((axis[1],int(axis[2])) in vertices[u])
        assert y[j]==expected, 'ORIGINAL_ROUTE_ALIAS_MISMATCH:'+name
        assert case.original_d['lower'][j]<=y[j]<=case.original_d['upper'][j]
        count+=1
    modes=np.char.startswith(case.d['names'],'charge_mode[')
    assert np.count_nonzero(modes)==384 and np.array_equal(low[modes],case.d['lower'][modes]) and np.array_equal(high[modes],case.d['upper'][modes])
    result=dict(PASS=True,DAG_ROUTE_VALID=True,original_alias_route_coordinates_checked=count,
        all384_modes_free=True,all_nonroute_bounds_and_all_rows_objective_preserved=True,
        original_terminal_slot96_semantics=True,new_return_to_origin_condition=False,
        incompatible_N1_start_used=False,restricted_ObjBound_is_Global_LB=False,Native_optimize_calls=0)
    if output:write(output,result)
    return result

def signature(spec):
    return hashlib.sha256(json.dumps(spec.get('paths',spec.get('mathematical_model_signature',spec)),sort_keys=True,separators=(',',':')).encode()).hexdigest()
