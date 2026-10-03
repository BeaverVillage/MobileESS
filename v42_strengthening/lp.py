from .common import OUT,SOURCE,SCIENCE,REF,write,read,sha,once,material
from .analysis import graph_inputs,census
import numpy as np
import gurobipy as gp
from v42_integrated.matrix import arrays,audit
from v42_degen.identity import signature,digest

def cold_model():
    identity=read(OUT/'M1_STRENGTHENING_BASE_IDENTITY.json')
    assert sha(SOURCE/'REDUCED.mps')==identity['identity']['reduced_MPS_sha256']
    m=gp.read(str(SOURCE/'REDUCED.mps'))
    m.Params.LogToConsole=0;m.Params.Threads=1
    A,d=arrays(m)
    assert signature(A,d)==identity['scientific_signature']
    assert digest(d['row_names'])==identity['native_row_names_SHA']
    return m,A,d

def evaluate(label,installer):
    """Single cold continuous solve with the inherited fixed LP policy."""
    gp.setParam('Threads',1)
    m,A,d=cold_model()
    try:
        growth=installer(m)
        B,e=arrays(m)
        # Original rows/columns are preserved exactly; only appended cuts or
        # continuous auxiliary columns may differ in later extended stages.
        base=B[:A.shape[0],:A.shape[1]].tocsr()
        assert B[:A.shape[0],A.shape[1]:].nnz==0
        assert signature(base,{**d,'rhs':e['rhs'][:A.shape[0]],'sense':e['sense'][:A.shape[0]]})==signature(A,d)
        for k in ('names','lower','upper','types','objective'):
            assert np.array_equal(d[k],e[k][:A.shape[1]])
        assert d['constant']==e['constant']
        assert np.array_equal(d['row_names'],e['row_names'][:A.shape[0]])
        if m.NumVars>A.shape[1]:
            assert all(e['types'][A.shape[1]:]=='C') and all(e['objective'][A.shape[1]:]==0)
        m.setAttr('VType',m.getVars(),['C']*m.NumVars);m.update()
        policy=dict(read(SCIENCE/'ROOT_LP_reduced.json')['settings'])
        assert policy['Threads']==1 and policy['Method']==2 and policy['Crossover']==0
        for key,value in policy.items():m.setParam(key,value)
        # Gurobi's Windows log writer rejects this workspace's Unicode absolute
        # path. A relative ASCII path targets the same artifact directory.
        m.Params.LogFile=(OUT.relative_to(__import__('pathlib').Path.cwd())/(label+'.log')).as_posix()
        from .resources import gate
        gate(label+'_before_optimize')
        once(label)
        print('LP_BEGIN',label,growth,flush=True)
        m.optimize()
        result=dict(status=m.Status,settings=policy,runtime=m.Runtime,barrier_iterations=m.BarIterCount,
                    matrix_growth=growth,optimization_calls=1,model_base_preserved=True,
                    objective=float(m.ObjVal) if m.SolCount else None)
        if m.Status==gp.GRB.OPTIMAL:
            point=np.asarray(m.getAttr('X'))
            original_point=point[:len(d['names'])]
            result['base_rows_audit']=audit(A,d,original_point,tolerance=1e-6)
            result['strengthened_rows_audit']=audit(B,e,point,tolerance=1e-6)
            assert result['base_rows_audit']['PASS'] and result['strengthened_rows_audit']['PASS']
            result.update(material(m.ObjVal))
            sites,initial,arcs,_,_=graph_inputs()
            result['fractional_census'],_=census(d,original_point,sites,initial,arcs,label)
            np.savez_compressed(OUT/(label+'_SOLUTION.npz'),names=e['names'],values=point,integer_types=e['types'])
            result['solution_SHA']=sha(OUT/(label+'_SOLUTION.npz'))
        write(label+'_RESULT.json',result)
        print('LP_END',label,result.get('objective'),result.get('delta_LB'),result.get('material'),flush=True)
        return result
    finally:m.dispose()

def stage_A():
    from .cuts import add_A,proof_A,bounded_A
    violations=read(OUT/'CUT_A_ROOT_VIOLATION_SUMMARY.json')
    if not violations['violated_cut_count']:
        write('CUT_A_ROOT_RESULT.json',dict(status='NOT_RUN',selected=False,reason='NOT_SUPPORTED'))
        return
    assert proof_A()['PASS'] and bounded_A()['PASS']
    sites,initial,_,battery,_=graph_inputs()
    result=evaluate('CUT_A_ROOT',lambda m:add_A(m,sites,initial,battery.p_limit))
    result['selected']=bool(result['status']==gp.GRB.OPTIMAL and result['objective']>=read(OUT/'BASELINE_ROOT_LP_RECEIPT.json')['primal_objective']-1e-8 and result['material'] and result['matrix_growth']['added_nnz']/8447855<.1)
    result['exact_integer_equivalence_PASS']=True
    write('CUT_A_ROOT_RESULT.json',result)

if __name__=='__main__':stage_A()
