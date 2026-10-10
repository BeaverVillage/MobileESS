"""Full96 integer column search plus a bounded exhaustive region-cover certificate.

The MILP locates physical trajectories. Its best bound is never a certificate.
LP node duals certify a disjoint binary partition of *all* missing trajectories.
An incomplete tree remains a conservative integer-pricing lower bound.
"""
from fractions import Fraction as F
from time import perf_counter
from types import SimpleNamespace
import numpy as np
from v42_m1_hybrid.pricing import build_pricing_model
from v42_m1_hybrid.bound import local_exact_price_bound
from v42_m1_research.check_ub import matrix_replay
from .certificate import endpoints, check_cover
from .budget import write
from .case import file_sha


def signed_packet(model, block, attr='Pi'):
    try:
        raw = np.asarray(model.getAttr(attr), dtype=float)
    except Exception:
        return None
    if raw.shape != (block.A.shape[0],) or not np.isfinite(raw).all():
        return None
    if attr == 'FarkasDual':
        raw = -raw
    bad = ((block.d['sense'] == '<') & (raw > 0)) | ((block.d['sense'] == '>') & (raw < 0))
    if bad.any():
        return None  # Strict rejection; no sign clipping or equality repair.
    return {str(int(i)):str(F(float(raw[i]))) for i in np.flatnonzero(raw)}


def integer_price(block, exact_price, seed_dual, seed_point, budget, folder,
                  *, label, node_limit=7, node_seconds=8., mip_seconds=25.):
    folder.mkdir(parents=True, exist_ok=True)
    q = {int(j):F(v) for j, v in exact_price.items()}
    native = np.array([float(q.get(j, 0)) for j in range(block.A.shape[1])])
    columns = []
    begin = perf_counter()
    model, variables, build = build_pricing_model(block, native, 'MILP', seed_point)
    budget.build_seconds += perf_counter()-begin
    try:
        model.Params.MIPGap = 0.
        record = budget.optimize(model, label+'_INTEGER_COLUMN', mip_seconds)
        if model.SolCount:
            point = np.asarray(variables.X)
            admission = matrix_replay(block.A, block.d, point)
            if admission['PASS'] and admission['integer_pattern_exact'] and admission['exact_binary_0_1']:
                path = folder/'INTEGER_COLUMN.npz'
                np.savez_compressed(path, point=point, original_columns=block.original_columns)
                columns.append(dict(path=str(path), sha256=file_sha(path), admission=admission,
                                    source='FULL96_NATIVE_INTEGER_SEARCH_NUMERICAL_LOCAL_REPLAY'))
        write(folder/'INTEGER_SEARCH.json', dict(native=record, build=build, columns=columns,
                                               Native_ObjBound_certificate_authority=False))
    finally:
        model.dispose()
    result = certify_price(block, exact_price, seed_dual, budget, folder,
                           label=label, node_limits=[node_seconds]*node_limit)
    result['columns'] = columns
    write(folder/'INTEGER_PRICE_COVER.json', result)
    return result


def certify_price(block, exact_price, seed_dual, budget, folder, *, label,
                  node_limits=(8.,3.,3.), saved_duals=()):
    """Existing exhaustive binary cover, with current-box cross-Dual audits.

    Old numerical bounds are never reused. Every candidate dual is evaluated
    independently with the current exact price and the current branch bounds.
    """
    import json
    from hashlib import sha256
    from .certificate import node_bound_details
    folder.mkdir(parents=True, exist_ok=True)
    q={int(j):F(v) for j,v in exact_price.items()}
    native=np.array([float(q.get(j,0)) for j in range(block.A.shape[1])])
    seed=dict(kind='DUAL',dual=seed_dual)
    certificate_begin=perf_counter()
    initial=node_bound_details(block,exact_price,{},seed)
    budget.certificate_seconds+=perf_counter()-certificate_begin
    tree={'r':dict(fixes={},proof=seed,split=None)}
    floors={'r':F(initial['bound'])};pending=['r'];audits=[]
    available={json.dumps(seed_dual,sort_keys=True):(seed_dual,'ORIGINAL_SIGNED_SEED')}
    for i,dual in enumerate(saved_duals):
        available[json.dumps(dual,sort_keys=True)]=(dual,'SAVED_SAME_UNIT_'+str(i))
    begin=perf_counter();model,variables,build=build_pricing_model(block,native,'LP')
    budget.build_seconds+=perf_counter()-begin
    from v42_m1_hybrid.blocks import matrix_sha
    if matrix_sha(model.getA().tocsr())!=matrix_sha(block.A):
        model.dispose();raise ValueError('PRICING_ORIGINAL_MATRIX_NATIVE_DRIFT')
    model.Params.Method=1;model.Params.InfUnbdInfo=1
    binaries=np.flatnonzero(block.d['types']=='B');calls=0
    try:
        while pending and calls<len(node_limits) and budget.used<599:
            key=pending.pop(0);lo,hi=endpoints(block,tree[key]['fixes'])
            variables.LB,variables.UB=lo,hi
            record=budget.optimize(model,label+'_REGION_'+key,node_limits[calls]);calls+=1
            audit=dict(node=key,fixes=tree[key]['fixes'],native=record,
                       parent_bound=str(floors[key]),native_objective='UNAVAILABLE',
                       original_matrix_unmodified=True,only_branch_bounds_changed=True)
            try:audit['native_objective']=float(model.ObjVal)
            except Exception:pass
            point=None;raw=None
            try:point=np.asarray(variables.X)
            except Exception:pass
            try:raw=np.asarray(model.getAttr('Pi'),dtype=float)
            except Exception:pass
            data=dict(lower=lo,upper=hi,objective_native=native,
                      original_rows=block.original_rows,original_columns=block.original_columns)
            if point is not None:data['X']=point
            if raw is not None:data['Pi']=raw
            path=folder/(key+'_RAW.npz');np.savez_compressed(path,**data)
            audit['raw_file']=str(path);audit['raw_sha']=file_sha(path)
            if raw is None:
                audit.update(sign_validity='UNKNOWN',dual_rejection_reason='PI_UNAVAILABLE')
            elif raw.shape!=(block.A.shape[0],) or not np.isfinite(raw).all():
                audit.update(sign_validity=False,dual_rejection_reason='NONFINITE_OR_WRONG_AXIS')
            else:
                wrong=((block.d['sense']=='<')&(raw>0))|((block.d['sense']=='>')&(raw<0))
                audit.update(sign_validity=not wrong.any(),wrong_sign_count=int(wrong.sum()),
                             maximum_wrong_sign=float(max(abs(raw[wrong]),default=0.)))
                if wrong.any():audit['dual_rejection_reason']='WRONG_SIGN_STRICT_NO_CLIPPING'
                else:
                    dual={str(int(i)):str(F(float(raw[i]))) for i in np.flatnonzero(raw)}
                    available[json.dumps(dual,sort_keys=True)]=(dual,'NATIVE_'+key)
            certificate_begin=perf_counter()
            empty=False
            if int(model.Status)==3:
                ray=signed_packet(model,block,'FarkasDual')
                if ray is not None:
                    proof=dict(kind='FARKAS',dual=ray)
                    try:detail=node_bound_details(block,exact_price,tree[key]['fixes'],proof)
                    except ValueError:pass
                    else:
                        tree[key]['proof']=proof;empty=True;audit['empty_certificate']=detail
            comparisons=[];selected=None;selected_source='VALID_ANCESTOR'
            if not empty:
                for dual,source in list(available.values()):
                    proof=dict(kind='DUAL',dual=dual)
                    try:detail=node_bound_details(block,exact_price,tree[key]['fixes'],proof)
                    except ValueError as exc:
                        comparisons.append(dict(source=source,rejected=str(exc)));continue
                    value=F(detail['bound'])
                    comparisons.append(dict(source=source,**detail))
                    if value>floors[key]:
                        floors[key]=value;tree[key]['proof']=proof;selected=detail;selected_source=source
                audit.update(comparisons=comparisons,selected_source=selected_source,
                             selected_exact_bound=str(floors[key]),selected_terms=selected,
                             parent_reuse_reason='No valid current-box certificate exceeds ancestor' if selected is None else None)
                if point is not None and np.isfinite(point).all():
                    fractional=[int(j) for j in binaries if str(int(j)) not in tree[key]['fixes'] and 1e-8<point[j]<1-1e-8]
                    if fractional and calls+len(pending)+2<=len(node_limits):
                        j=max(fractional,key=lambda z:min(point[z],1-point[z]));tree[key]['split']=j
                        for bit in (0,1):
                            child=key+str(bit);fixes=dict(tree[key]['fixes'],**{str(j):bit})
                            tree[child]=dict(fixes=fixes,proof=None,split=None)
                            floors[child]=floors[key];pending.append(child)
            audit['independent_exact_seconds']=perf_counter()-certificate_begin
            budget.certificate_seconds+=audit['independent_exact_seconds']
            audits.append(audit)
            write(folder/'NODE_CERTIFICATE_AUDITS.json',audits)
            write(folder/'COVER_CHECKPOINT.json',dict(exact_price=exact_price,tree=tree,pending=pending))
    finally:model.dispose()
    certificate_begin=perf_counter()
    beta=check_cover(block,exact_price,tree)
    budget.certificate_seconds+=perf_counter()-certificate_begin
    result=dict(exact_price=exact_price,tree=tree,exact_price_lower_bound=str(beta),
                missing_trajectory_coverage='PASS',integer_optimum='NOT_PROVEN',
                pricing_node_calls=calls,columns=[],audits_file=str(folder/'NODE_CERTIFICATE_AUDITS.json'))
    write(folder/'INTEGER_PRICE_COVER.json',result)
    return result
