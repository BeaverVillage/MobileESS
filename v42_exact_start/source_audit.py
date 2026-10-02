"""Two-row source replay and direct compact correspondence, without optimize."""
import math,re
import gurobipy as gp
from scipy import sparse
from .common import *

def run():
    from v42_forensic.common import inputs
    from v42_bootstrap.grid import coefficients
    from v42_m1_sparse.grid import expr,response
    bundle,anchor,*_=inputs();_,coeff=coefficients(bundle)
    original_names,old=old_start('original');compact_names,compact_old=old_start('compact')
    compact_A=sparse.load_npz(OLD_CACHE/'COMPACT_A.npz').tocsr();compact_A.sort_indices()
    with np.load(OLD_CACHE/'COMPACT_DATA.npz') as z:compact_rhs=z['rhs']
    rows=[]
    with gp.Env(params={'OutputFlag':0}) as env:
        for record in read('START_RESIDUAL_ROOT_CAUSE.json')['rows']:
            t,k=map(int,re.findall(r'\d+',record['dependent_variable']));c=coeff[t]
            cos=np.cos(2*np.pi*np.arange(16)/16);sin=np.sin(2*np.pi*np.arange(16)/16)
            ap=np.asarray(c.branch_limits)*math.cos(math.pi/16)
            pa=c.flow_p_constant+c.flow_p_matrix@c.anchor;qa=c.flow_q_constant+c.flow_q_matrix@c.anchor
            raw=(pa[:,None]*cos+qa[:,None]*sin)/ap[:,None];active=np.argmax(raw,axis=1)
            grad=(cos[active,None]*c.flow_p_matrix+sin[active,None]*c.flow_q_matrix)/ap[:,None]
            correction=c.current_matrix.T-grad
            m=gp.Model(env=env);controls=[]
            for j,name in enumerate(c.control_names):
                site=name.split('[')[1][:-1]
                if name.startswith('aidc_load_kw'):controls.append(float(anchor['controls'][t][j]))
                elif name.startswith('mess_p_kw'):controls.append(m.addVar(lb=-gp.GRB.INFINITY,name=f'injection_P[{site},{t}]'))
                elif name.startswith('mess_q_kvar'):controls.append(m.addVar(lb=-gp.GRB.INFINITY,name=f'injection_Q[{site},{t}]'))
                else:raise ValueError(name)
            bindings=[];response(m,record['dependent_variable'],expr(-correction[k]@c.anchor,correction[k],controls),bindings);m.update()
            row=m.getA().tocsr()[0];names=m.getAttr('VarName')
            replay={names[j]:float(a) for j,a in zip(row.indices,row.data)}
            sealed={v['variable']:v['coefficient'] for v in record['LHS']}
            assert replay.keys()==sealed.keys()
            coefdiff=max(abs(replay[n]-sealed[n]) for n in sealed)
            rhsdiff=abs(m.getConstrs()[0].RHS-record['RHS'])
            # Source replay is audited against the immutable serialized scientific matrix.
            assert coefdiff<=1e-14 and rhsdiff<=1e-14,(coefdiff,rhsdiff)
            index=record['original_index'];cr=compact_A[index]
            compact={str(compact_names[j]):float(a) for j,a in zip(cr.indices,cr.data)}
            assert compact==sealed and float(compact_rhs[index])==record['RHS']
            residual=float((cr@compact_old)[0]-compact_rhs[index]);assert residual==record['saved_residual']
            primary_dependencies=[]
            for name in sealed:
                if not name.startswith('injection_'):continue
                suffix=name.split('[',1)[1][:-1]
                site,slot=suffix.rsplit(',',1)
                prefixes=('Pch','Pdis') if name.startswith('injection_P') else ('Q',)
                selected=[str(n) for n in original_names if any(str(n).startswith(p+'[') for p in prefixes) and str(n).endswith(','+site+','+slot+']')]
                primary_dependencies.append(dict(auxiliary=name,primary_controls=selected,
                    formula='sum(Pdis-Pch over MESS units)' if len(prefixes)==2 else 'sum(Q over MESS units)',
                    source='v42_native.mess.solve p/q dictionaries -> v42_m1_sparse.grid.compressed_grid injection helpers'))
            rows.append(dict(original_index=index,compact_row=record['compact_row'],source_replay_coefficient_max_abs_difference=coefdiff,
                source_replay_RHS_abs_difference=rhsdiff,compact_LHS_coefficients_bitwise_identical_to_original=True,
                compact_RHS_bitwise_identical_to_original=True,compact_saved_residual=residual,direct_primary_variables=[],
                primary_dependency_chain=primary_dependencies,source_replay_terms=replay,source_replay_RHS=m.getConstrs()[0].RHS,
                source_function='v42_m1_sparse.grid.expr/response; exact add_compressed correction formula replayed for these two source slots/branches'))
            m.dispose()
    dump('START_SOURCE_MATRIX_REPLAY.json',dict(PASS=True,rows=rows,optimizer_calls=0,
        no_scientific_model_change=True,no_new_optimization=True,source_replay_comparison_tolerance=1e-14,
        source_replay_roundoff_note='This audit reports source-expression vs sealed serialized matrix differences explicitly; reconstruction uses the unchanged sealed matrix, never modifies its coefficients/RHS.',
        source_hashes={n:sha(ROOT/n) for n in ['v42_m1_sparse/grid.py','v42_native/mess.py','v42_bootstrap/grid.py']}))
    root=read('START_RESIDUAL_ROOT_CAUSE.json');root['direct_source_and_compact_row_replay_artifact']='START_SOURCE_MATRIX_REPLAY.json'
    dump('START_RESIDUAL_ROOT_CAUSE.json',root)
    print('SOURCE_MATRIX_REPLAY_PASS',[(r['source_replay_coefficient_max_abs_difference'],r['source_replay_RHS_abs_difference']) for r in rows],flush=True)

if __name__=='__main__':run()
