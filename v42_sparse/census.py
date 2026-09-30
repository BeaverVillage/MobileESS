"""Measured sparse matrix census. No optimize call occurs here."""
import gc
import numpy as np
from v42_root.common import *
from v42_root.profile import Census,category
from v42_root.data import prepare
from v42_exact.native import build
import linecache

def sparse_category(frame):
    filename=frame.f_code.co_filename.replace('\\','/');code=linecache.getline(filename,frame.f_lineno);fn=frame.f_code.co_name
    if filename.endswith('/reserve.py'):
        if 'nominal_and_compute_headroom' in code:return 'Runtime_headroom'
        if 'RT_reserve_target' in code:return 'Runtime_reserve'
        if 'CC4_reserve_target' in code:return 'CC4_reserve'
    if filename.endswith('/v42_root/native.py'):
        if 'gpurows' in code:return 'resource_GPU'
        if 'riskrows' in code:return 'Runtime_completion_risk'
        if 'wanrows' in code:return 'resource_WAN'
        if 'active=' in code:return 'resource_active_transfers'
        if 'exact_Runtime_finish_count' in code:return 'Runtime_count_definition'
        if 'class_exact_cardinality' in code:return 'class_cardinality'
        return 'native_binding'
    if filename.endswith('/v42_root/factor.py'):
        if fn=='tie_expression':return 'tie'
        if 'active.get' in code:return frame.f_locals.get('n','state')+'_balance'
        if 'depart' in code:return 'depart_linking'
        if 'arrive' in code:return 'arrive_linking'
        if any(s in code for s in ['before','after','sent<=','sent>=','a==prev','f<=a',"remaining'][", "wan_active'][last]"]):return 'WAN_payload_dynamics'
        if 'u<=' in code or 'u>=' in code or 'member==' in code:return 'link_bytes_linking'
        if fn=='stay':return 'nonmigration_count_path'
        return 'factor_event_logic'
    return category(frame)

def measure(m,units,levels,census,prefix):
    m.update();A=m.getA();nz=np.diff(A.indptr);tags=np.asarray(census.tags)
    if len(tags)!=m.NumConstrs:raise ValueError('INCOMPLETE_ROW_CENSUS')
    names=m.getAttr('ConstrName');rows=[]
    for code,label in enumerate(census.labels):
        indices=np.flatnonzero(tags==code);counts=nz[indices];idx=int(indices[counts.argmax()])
        rows.append(dict(family=label,rows=len(counts),nonzeros=int(counts.sum()),average=float(counts.mean()),median=float(np.median(counts)),p95=float(np.percentile(counts,95)),p99=float(np.percentile(counts,99)),maximum=int(counts.max()),maximum_row_index=idx,maximum_row_identity=names[idx]))
    table(prefix+'_ROW_DENSITY.csv',rows)
    # Unique columns, including shared flow aliases, are counted once.
    groups={};seen=set()
    for unit in units:
        for family,items in unit['v'].items():
            for x in items.values():
                import gurobipy as gp
                variables=[x] if isinstance(x,gp.Var) else [x.getVar(i) for i in range(x.size())] if isinstance(x,gp.LinExpr) else []
                for variable in variables:
                    if variable.index not in seen:
                        groups.setdefault((family,variable.VType),[]).append(variable.index);seen.add(variable.index)
    for x in m.getVars():
        if x.index in seen:continue
        n=x.VarName
        family='Runtime_count' if n.startswith('finish_count[') else 'Runtime' if n.startswith(('RT_','risk[')) else 'CC4' if n.startswith('CC4') else 'known_GPU' if n.startswith('known[') else 'grid_global'
        groups.setdefault((family,x.VType),[]).append(x.index)
    objectives={}
    for name,e in levels:
        import gurobipy as gp
        ids={e.index} if isinstance(e,gp.Var) else {e.getVar(i).index for i in range(e.size())} if isinstance(e,gp.LinExpr) else set()
        objectives[name]=ids
    cols=[]
    for (family,typ),ids in sorted(groups.items()):
        sub=A[:,ids];touched=np.flatnonzero(np.diff(sub.indptr))
        cols.append(dict(family=family,type=typ,count=len(ids),objective_participation=';'.join(n for n,s in objectives.items() if s.intersection(ids)),constraints_touched=len(touched),coefficient_occurrences=int(sub.nnz)))
    table(prefix+'_MATRIX_CENSUS.csv',cols)
    assert sum(x['count'] for x in cols)==m.NumVars
    assert sum(x['nonzeros'] for x in rows)==m.NumNZs
    assert sum(x['coefficient_occurrences'] for x in cols)==m.NumNZs
    def ranges(xs):
        a=np.abs(np.asarray(xs));a=a[(a>0)&(a<1e99)]
        return dict(minimum_abs=float(a.min()) if len(a) else None,maximum_abs=float(a.max()) if len(a) else None)
    scaling=dict(matrix=ranges(A.data),RHS=ranges(m.getAttr('RHS')),bounds=ranges(m.getAttr('LB')+m.getAttr('UB')),objectives={})
    for n,e in levels:
        import gurobipy as gp
        scaling['objectives'][n]=ranges([1] if isinstance(e,gp.Var) else [e.getCoeff(i) for i in range(e.size())] if isinstance(e,gp.LinExpr) else [e])
    dump(prefix+'_NUMERICAL.json',scaling)
    return dict(columns=m.NumVars,rows=m.NumConstrs,nonzeros=m.NumNZs,binaries=m.NumBinVars,integers=m.NumIntVars-m.NumBinVars,continuous=m.NumVars-m.NumIntVars,max_row_density=int(nz.max()),p99_row_density=float(np.percentile(nz,99)),family_nonzeros={r['family']:r['nonzeros'] for r in rows},optimizer_called=False,timing_is_clean_benchmark=False)

def main():
    import v42_root.profile as profile
    profile.category=sparse_category
    frozen();data=prepare();print('full-May original matrix structural build; no optimization',flush=True)
    with Census() as census:m,v,o,c,b=build(Context(),data,'F2')
    units=[dict(v=vv) for vv in v.values()]
    stats=measure(m,units,o,census,'BASELINE');stats['build']=read(LOCAL/'F2_MODEL_COMPLETE.json')
    dump('BASELINE_STRUCTURAL.json',stats);print(stats,flush=True)
    m.dispose();gc.collect();frozen()
if __name__=='__main__':main()
