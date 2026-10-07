"""Violation-first, at most ten LP-only rounds; no baseline row deletion."""
from collections import defaultdict
import json,re,time,sys,csv
import numpy as np
from scipy import sparse
from pure_lp import OUT,load,write,rows,replay,sha
from analyze_point import context
UB=.6694159238756877
BATCH=32;ROUNDS=10;MATERIAL=.001

def candidates(c):
    result=[];b=c['battery'];L=float(b.p_limit);assert L==300.
    def make(f,u,t,s,physical,rhs):
        terms=defaultdict(float);constant=0.
        for name,w in physical:
            e,k=c['expr'](name);constant+=w*k
            for j,v in e.items():terms[j]+=w*v
        terms={j:w for j,w in terms.items() if w}
        result.append(dict(id=f'{f}:{u}:{t}:{s}',family=f,MESS=u,slot=t,site=s,terms=terms,rhs=rhs-constant,added_rows=1,added_nnz=len(terms)))
    for u in sorted(c['initial']):
        for t in range(96):
            ch=[(f'Pch[{u},{s},{t}]',1.) for s in c['sites']];dis=[(f'Pdis[{u},{s},{t}]',1.) for s in c['sites']]
            stays=[(f'arc[{u},{i*96+t}]',-L) for i in range(len(c['sites']))]
            make('AGGREGATE_CHARGE_MODE',u,t,'ALL',ch+[(f'charge_mode[{u},{t}]',-L)],0.)
            make('AGGREGATE_DISCHARGE_MODE',u,t,'ALL',dis+[(f'charge_mode[{u},{t}]',L)],L)
            make('AGGREGATE_CONNECTED_POWER',u,t,'ALL',ch+dis+stays,0.)
            for i,s in enumerate(c['sites']):
                make('LOCAL_CONNECTED_POWER',u,t,s,[(f'Pch[{u},{s},{t}]',1.),(f'Pdis[{u},{s},{t}]',1.),(f'arc[{u},{i*96+t}]',-L)],0.)
    # Exact mode×PCS support, derived before looking at the baseline point.
    # Do not duplicate the C+D<=300*stay facet already represented above.
    hull=json.loads((OUT/'FOLDED_PCS_LOCAL_HULL.json').read_text())
    facets=[p for p in hull['facets'] if p['strengthening_candidate'] and p['beta']!=0.]
    for name in c['d']['names']:
        if not str(name).startswith('Pch['):continue
        u,s,t=str(name)[4:-1].split(',');t=int(t);arc=c['sites'].index(s)*96+t
        for p in facets:
            make('FOLDED_PCS_CONNECTED_POWER',u,t,s,[(f'Pch[{u},{s},{t}]',p['alpha']),(f'Pdis[{u},{s},{t}]',p['alpha']),(f'Q[{u},{s},{t}]',p['beta']),(f'arc[{u},{arc}]',-p['gamma'])],0.)
            result[-1].update(id=f"FOLDED:{p['id']}:{u}:{t}:{s}",alpha=p['alpha'],beta=p['beta'],gamma=p['gamma'],facet=p['id'])
    return result

def violation(cut,x):return float(sum(w*x[int(j)] for j,w in cut['terms'].items())-cut['rhs'])

def main():
    resume='--resume-after-round-1' in sys.argv
    if resume:
        assert (OUT/'CUT_LOOP_CHECKPOINT_TRANSITION.json').exists()
        assert (OUT/'LP_ROUND_01_RESULT.json').exists()
        assert not (OUT/'LP_ROUND_02_ONCE.json').exists()
    else:assert not (OUT/'LP_CUT_LOOP_ONCE.json').exists(),'CUT_LOOP_RETRY_FORBIDDEN'
    c=context();A,d,start=c['A'],c['d'],c['start'];x=c['point'];cuts=candidates(c)
    baseline=json.loads((OUT/'PURE_LP_RESULT.json').read_text());LP0=baseline['objective'];KNOWN_GLOBAL_LB=.5687116003498334
    # Barrier-only ObjBound has contradicted the captured primal estimate and
    # sign-clipped exact dual in this model. Preserve it; do not certify it.
    LB0=KNOWN_GLOBAL_LB
    if not resume:
        # Verifier reconstructs physical semantics independently; no production constructor.
        from independent_hull import verify_candidates
        worst=sorted(cuts,key=lambda q:(-violation(q,x),q['id']))[:2]
        core=json.loads((OUT/'FRACTIONAL_CORE.json').read_text())
        blocks=[(r['MESS'],int(r['slot'])) for r in core['top20_time_blocks'][:2]]+[(q['MESS'],q['slot']) for q in worst]
        basic=[q for q in cuts if q['family']!='FOLDED_PCS_CONNECTED_POWER'];folded=[q for q in cuts if q['family']=='FOLDED_PCS_CONNECTED_POWER']
        proof=verify_candidates(basic,c,audit_blocks=blocks)
        from folded_pcs_hull import verify_folded_candidates
        folded_proof=verify_folded_candidates(folded,c)
        assert folded_proof['PASS'];write('FOLDED_INEQUALITY_INDEPENDENT_VERIFICATION.json',folded_proof)
        proof.update(PASS=proof['PASS'] and folded_proof['PASS'],folded_independent_verification='FOLDED_INEQUALITY_INDEPENDENT_VERIFICATION.json',total_candidate_count=len(cuts))
        assert proof['PASS'];write('INEQUALITY_INDEPENDENT_VERIFICATION.json',proof)
        report=[]
        for cut in cuts:
            v=violation(cut,x)
            report.append({k:v0 for k,v0 in cut.items() if k!='terms'}|dict(baseline_signed_violation=v,baseline_violated=v>1e-8,validated_start_signed_violation=violation(cut,start),proof='Independent rational local-state verifier and DAG global-path implication'))
        rows('CANDIDATE_VALID_INEQUALITIES.csv',report)
        write('CANDIDATE_COEFFICIENTS.json',cuts)
        write('LP_CUT_LOOP_ONCE.json',dict(max_rounds=ROUNDS,batch_size=BATCH,material_absolute_LB_improvement=MATERIAL,baseline_LP_already_solved_once=True,baseline_rows_deleted=0,cut_loop_optimize_calls=0))
    else:
        assert json.loads((OUT/'INEQUALITY_INDEPENDENT_VERIFICATION.json').read_text())['PASS']
        saved_candidates=json.loads((OUT/'CANDIDATE_COEFFICIENTS.json').read_text())
        def canonical(q):
            return (q['id'],q['family'],q['MESS'],int(q['slot']),q['site'],tuple(sorted((int(j),float(w).as_integer_ratio()) for j,w in q['terms'].items())),float(q['rhs']).as_integer_ratio(),tuple((k,float(q[k]).as_integer_ratio()) for k in ['alpha','beta','gamma'] if k in q))
        saved_map={q['id']:canonical(q) for q in saved_candidates}
        assert len(saved_map)==len(saved_candidates)==len(cuts)
        assert all(saved_map[q['id']]==canonical(q) for q in cuts),'CANDIDATE_VERIFICATION_AUTHORITY_CHANGED'
    trace=[dict(round=0,family='C3A_BASELINE',cuts_this_round=0,total_cuts=0,rows=A.shape[0],columns=A.shape[1],nnz=A.nnz,LP_Runtime=baseline['Runtime'],Work=baseline['Work'],rho=baseline['objective'],native_LP_LB=baseline['native_global_LP_LB'],valid_global_LB=LB0,delta_LB=0.,LP_objective_gain=0.,gap_ref=(UB-LB0)/UB,delta_per_1000_rows=None,delta_per_100000_nnz=None,runtime_increase=0.,presolved_rows=None,presolved_cols=None,presolved_nnz=None,raw_matrix_replay_PASS=baseline['independent_relaxed_matrix_replay']['PASS'],max_raw_row_violation=baseline['independent_relaxed_matrix_replay']['max_row_violation'])]
    selected=[];used=set();model=None;stop='ROUND_LIMIT';first_round=1
    if resume:
        with (OUT/'LP_STRENGTHENING_TRACE.csv').open() as f:trace=list(csv.DictReader(f))
        for r in trace:
            for k,v in list(r.items()):
                if v=='True':r[k]=True
                elif v=='False':r[k]=False
                elif v=='':r[k]=None
                elif k not in ['family']:
                    try:r[k]=float(v)
                    except ValueError:pass
        assert [int(r['round']) for r in trace]==[0,1]
        selected=json.loads((OUT/'SELECTED_CUTS.json').read_text());assert len(selected)==BATCH
        used={q['id'] for q in selected}
        assert len(used)==BATCH and all(saved_map[q['id']]==canonical(q) for q in selected)
        assert trace[-1]['Status']==2 and trace[-1]['total_cuts']==BATCH
        assert trace[-1]['rows']==A.shape[0]+BATCH and trace[-1]['columns']==A.shape[1]
        assert trace[-1]['nnz']==A.nnz+sum(q['added_nnz'] for q in selected)
        with np.load(OUT/'LP_ROUND_01_POINT.npz') as z:x=z['x']
        write('CUT_LOOP_RESUME_IDENTITY.json',dict(PASS=True,candidate_count=len(cuts),candidate_SHA256=sha(OUT/'CANDIDATE_COEFFICIENTS.json'),selected_SHA256=sha(OUT/'SELECTED_CUTS.json'),round1_point_SHA256=sha(OUT/'LP_ROUND_01_POINT.npz'),all_regenerated_coefficients_equal_independently_verified_candidates=True,selected_IDs_unique=True,round1_not_repeated=True,next_round=2,original_selected_matrix_hashes_unchanged=True))
        first_round=2
    for rnd in range(first_round,ROUNDS+1):
        batch=[cut for cut in cuts if cut['id'] not in used and violation(cut,x)>1e-8]
        batch.sort(key=lambda q:(-violation(q,x),q['added_nnz'],q['id']));batch=batch[:BATCH]
        if not batch:
            stop='NO_VIOLATED_INEQUALITY_IN_TESTED_FAMILIES';break
        if model is None:
            import gurobipy as gp
            from v42_redundancy.model import build
            model=build(A,d);variables=model.getVars();model.setAttr('VType',variables,['C']*len(variables));model.update()
            for k,v in dict(Method=2,Threads=1,Crossover=0,FeasibilityTol=1e-8,OptimalityTol=1e-8,IntFeasTol=1e-8,TimeLimit=gp.GRB.INFINITY).items():model.setParam(k,v)
            model.Params.OutputFlag=1;model.Params.LogToConsole=0
            for cut in selected:
                model.addConstr(gp.LinExpr(list(cut['terms'].values()),[variables[int(j)] for j in cut['terms']])<=cut['rhs'],name='exact_hull_'+cut['id'])
        for cut in batch:
            model.addConstr(gp.LinExpr(list(cut['terms'].values()),[variables[int(j)] for j in cut['terms']])<=cut['rhs'],name='exact_hull_'+cut['id'])
            selected.append(cut);used.add(cut['id'])
        model.update();model.Params.LogFile=str(OUT/f'LP_STRENGTHENING_ROUND_{rnd:02d}.log')
        with (OUT/f'LP_ROUND_{rnd:02d}_ONCE.json').open('x') as f:json.dump(dict(round=rnd,optimize_calls=1),f)
        model.optimize()
        status=int(model.Status)
        x=np.asarray(model.getAttr('X'));check=replay(A,d,x)
        added_violation=max((violation(cut,x) for cut in selected),default=0.)
        dual=np.asarray(model.getAttr('Pi'));rc=np.asarray(model.getAttr('RC'));slack=np.asarray(model.getAttr('Slack'))
        np.savez_compressed(OUT/f'LP_ROUND_{rnd:02d}_POINT.npz',x=x,dual=dual,reduced_cost=rc,slack=slack)
        rr=[];cc=[];vv=[]
        for i,q in enumerate(selected):
            for j,w in q['terms'].items():rr.append(i);cc.append(int(j));vv.append(w)
        added=sparse.csr_matrix((vv,(rr,cc)),shape=(len(selected),A.shape[1]))
        S=sparse.vstack([A,added],format='csr');e=dict(d,rhs=np.r_[d['rhs'],[q['rhs'] for q in selected]],sense=np.r_[d['sense'],np.full(len(selected),'<')])
        from numerical_bound_audit import exact_bounded_lagrangian
        certificate,_,_,_=exact_bounded_lagrangian(S,e,dual)
        certificate.update(round=rnd,dual_point_SHA256=sha(OUT/f'LP_ROUND_{rnd:02d}_POINT.npz'),selected_cuts_count=len(selected),no_optimize_calls=True)
        write(f'LP_ROUND_{rnd:02d}_EXACT_LB_CERTIFICATE.json',certificate)
        native_lb=float(model.ObjBound);lb=max(KNOWN_GLOBAL_LB,certificate['lower_bound']);added_nnz=sum(q['added_nnz'] for q in selected)
        log=(OUT/f'LP_STRENGTHENING_ROUND_{rnd:02d}.log').read_text();m=re.search(r'Presolved: (\d+) rows, (\d+) columns, (\d+) nonzeros',log)
        trace.append(dict(round=rnd,family=';'.join(sorted({q['family'] for q in batch})),cuts_this_round=len(batch),total_cuts=len(selected),rows=model.NumConstrs,columns=model.NumVars,nnz=model.NumNZs,LP_Runtime=model.Runtime,Work=model.Work,rho=float(model.ObjVal),native_LP_LB=native_lb,exact_dual_LB=certificate['lower_bound'],valid_global_LB=lb,delta_LB=lb-LB0,LP_objective_gain=float(model.ObjVal)-LP0,gap_ref=(UB-lb)/UB,delta_per_1000_rows=(lb-LB0)*1000/len(selected),delta_per_100000_nnz=(lb-LB0)*100000/added_nnz,runtime_increase=model.Runtime-baseline['Runtime'],presolved_rows=int(m[1]) if m else None,presolved_cols=int(m[2]) if m else None,presolved_nnz=int(m[3]) if m else None,Status=status,raw_matrix_replay_PASS=check['PASS'],max_raw_row_violation=check['max_row_violation'],max_added_cut_violation=added_violation))
        write(f'LP_ROUND_{rnd:02d}_RESULT.json',dict(**trace[-1],independent_replay=check,diagnostic_only=True,raw_matrix_feasible_certificate=check['PASS'] and added_violation<=1e-8,tolerance_unchanged=1e-8))
        rows('LP_STRENGTHENING_TRACE.csv',trace);write('SELECTED_CUTS.json',selected)
        print('LP_STRENGTHENING_ROUND',rnd,lb,'cuts',len(selected),flush=True)
        if status!=gp.GRB.OPTIMAL:
            stop='NATIVE_LP_STATUS_NOT_OPTIMAL';break
    rows('LP_STRENGTHENING_TRACE.csv',trace);write('SELECTED_CUTS.json',selected)
    final=trace[-1]
    best=max(trace,key=lambda r:float(r['valid_global_LB']));gain=best['valid_global_LB']-LB0
    write('LP_STRENGTHENING_SUMMARY.json',dict(PASS=all(r.get('Status',2)==2 for r in trace),baseline_valid_global_LB=LB0,baseline_native_LP_LB=baseline['native_global_LP_LB'],best_valid_global_LB=best['valid_global_LB'],best_native_LB=max(r['native_LP_LB'] for r in trace),best_exact_LB=max((r.get('exact_dual_LB') or -1e100) for r in trace),best_objective=final['rho'],LP_objective_proxy_improvement=final['rho']-LP0,absolute_improvement=gain,material_absolute_LB_threshold=MATERIAL,materially_strengthened=gain>=MATERIAL,rounds=len(trace)-1,cuts=len(selected),added_nnz=sum(q['added_nnz'] for q in selected),stop=stop,remaining_violated_unselected=sum(q['id'] not in used and violation(q,x)>1e-8 for q in cuts),MILP_calls_during_loop=0,baseline_rows_deleted=0,required_LB_for_point5percent_gap=.995*UB,required_total_LB_increase=.995*UB-LB0,fraction_of_required_LB_increase_recovered=gain/(.995*UB-LB0),integer_optimum_not_proven=True,raw_matrix_replay_failures=sum(not r['raw_matrix_replay_PASS'] for r in trace),native_and_exact_bounds_reported_separately=True,barrier_only_native_ObjBound_not_used_as_independent_certificate=True,known_PR162_global_bound_transported_to_integer_equivalent_C3S=True))
    if model is not None:model.dispose()
    print('LP_LOOP_DONE',final,flush=True)

if __name__=='__main__':main()
