"""One frozen original continuous LP, exact dyadic weak-duality certificate."""
from .common import *
import numpy as np,gurobipy as gp
from .support import certify

def fixtures(intervals):
    from scipy import sparse
    cases=[('min_le',-1,0,3,[1],'<',2,0,-2,-1),('min_ge',1,0,3,[1],'>',2,0,2,1),('equality',2,0,3,[1],'=',2,0,4,2),('finite_LB',1,1,3,None,None,None,0,1,None),('finite_UB',-1,0,3,None,None,None,0,-3,None),('free',2,-np.inf,np.inf,[1],'=',2,0,4,2),('fixed',-1,2,2,None,None,None,0,-2,None),('objective_constant',1,1,3,None,None,None,7,8,None)]
    rows=[]
    for name,c,lb,ub,a,s,rhs,const,opt,expected in cases:
        m=gp.Model('ARC_SIGN_'+name);m.Params.LogToConsole=0;x=m.addVar(lb=lb,ub=ub,obj=c)
        if a is not None:m.addConstr(x<=rhs if s=='<' else x>=rhs if s=='>' else x==rhs)
        m.ObjCon=const;m.update()
        for k,v in dict(Threads=1,Method=1,FeasibilityTol=EPS,OptimalityTol=EPS).items():m.setParam(k,v)
        start=time.perf_counter();m.optimize();end=time.perf_counter();intervals.append([start,end]);assert m.Status==2
        pi=np.array(m.getAttr('Pi'));A=m.getA().tocsr();d=dict(objective=np.array([c]),constant=np.array(const),rhs=np.array([] if rhs is None else [rhs]),sense=np.array([] if s is None else [s]),lower=np.array([lb]),upper=np.array([ub]))
        cert=certify(A,d,pi)
        assert abs(m.ObjVal-opt)<=EPS and abs(cert['L_dual_support']-opt)<=EPS
        if expected is not None:assert pi[0]==expected
        rows.append(dict(fixture=name,native_status=m.Status,native_objective=m.ObjVal,Pi=pi.tolist(),expected_Pi=expected,L_support=cert['L_dual_support'],expected_optimum=opt,PASS=True,interval=[start,end]));m.dispose()
    value=dict(PASS=True,fixtures=rows,all_continuous=True,global_parameter_sweep=False,native_Threads=1);write('ARC_LP_DUAL_CONVENTION_FIXTURES.json',value);return value

def run():
    from v42_degen.identity import inputs
    from v42_dw_root.models import build
    from v42_dw_resume.audit import corrected_rows,pure_binary_equalities
    from .prepare import identity
    import threading
    commit=verify_freeze();preserve_old();assert not STOP.exists()
    with (OUT/'ARC_STARTED.json').open('x',encoding='utf8') as f:json.dump(dict(preopt_commit=commit),f)
    intervals=[];fixture=fixtures(intervals);A,d,*_=inputs();lpdata=dict(d,types=np.full(len(d['types']),'C',dtype=d['types'].dtype));model=build(A,lpdata,'FROZEN_ORIGINAL_ARC_LP');assert identity(A,d,model)['PASS']
    settings=dict(Threads=1,Method=2,Crossover=0,PreDual=0,BarConvTol=1e-11,FeasibilityTol=EPS,OptimalityTol=EPS,TimeLimit=max(.001,ARC_BUDGET-union_seconds(intervals)-2))
    for k,v in settings.items():model.setParam(k,v)
    model.Params.LogFile=(OUT.relative_to(ROOT)/'logs/ARC_LP_PRIMARY.log').as_posix()
    done=threading.Event()
    def watch():
        while not done.wait(.2):
            if STOP.exists():model.terminate()
    thread=threading.Thread(target=watch,daemon=True);thread.start()
    def callback(m,where):
        if STOP.exists():m.terminate()
    start=time.perf_counter();model.optimize(callback);end=time.perf_counter();intervals.append([start,end]);done.set();thread.join()
    def attr(name):
        try:
            x=float(getattr(model,name));return x if np.isfinite(x) and abs(x)<1e90 else None
        except (AttributeError,gp.GurobiError):return None
    receipt=dict(status=model.Status,objective=attr('ObjVal'),ObjBound=attr('ObjBound'),runtime=model.Runtime,iterations=model.IterCount,barrier_iterations=model.BarIterCount,method=model.Params.Method,settings=settings,IsMIP=model.IsMIP,discrete_variables=model.NumIntVars,ConstrVio=attr('ConstrVio'),BoundVio=attr('BoundVio'),DualVio=attr('DualVio'),interval=[start,end],optimize_budget_seconds=ARC_BUDGET,optimize_union_seconds=union_seconds(intervals),preopt_commit=commit)
    raw=(OUT/'logs/ARC_LP_PRIMARY.log').read_text(encoding='utf8',errors='replace');receipt['presolve_statistics']=[x.strip() for x in raw.splitlines() if x.startswith(('Presolve','Presolved:'))];write('ARC_LP_NATIVE_RECEIPT.json',receipt);write('ARC_OPTIMIZE_INTERVALS.json',dict(intervals=intervals,union_seconds=union_seconds(intervals),budget=600,second_LP=False));assert union_seconds(intervals)<=600
    passed=False;cert=None;primal=None
    if model.Status==2:
        x=np.array(model.getAttr('X'));pi=np.array(model.getAttr('Pi'));rc=np.array(model.getAttr('RC'));np.savez_compressed(OUT/'ARC_LP_NATIVE_POINT.npz',x=x,Pi=pi,RC=rc)
        primal=corrected_rows(A,d,x,False,pure_binary_equalities(A,d));primal['objective_recompute_error']=abs(primal['objective']-model.ObjVal);primal['PASS']=primal['PASS'] and primal['objective_recompute_error']<=EPS;write('ARC_LP_PRIMAL_AUDIT.json',primal)
        with np.load(OUT/'ARC_ORIGINAL_EQUALITY_PIVOTS.npz') as z:pivots=z['row_column']
        try:
            cert=certify(A,d,pi,pivots,OUT/'ARC_LP_RATIONAL_DUAL.npz');cert.update(dual_artifact='ARC_LP_RATIONAL_DUAL.npz',dual_SHA=sha(OUT/'ARC_LP_RATIONAL_DUAL.npz'),native_point_SHA=sha(OUT/'ARC_LP_NATIVE_POINT.npz'),matrix_SHA=sha(SOURCE/'FULL_A.npz'))
            cert['numerical_PASS']=cert['L_dual_support']<=model.ObjVal+EPS;write('ARC_LP_DUAL_SUPPORT_CERTIFICATE.json',cert)
            passed=bool(primal['PASS'] and fixture['PASS'] and cert['PASS'] and cert['numerical_PASS'])
        except (ValueError,AssertionError) as error:
            cert=dict(PASS=False,L_dual_support=None,error=repr(error),infinite_support_not_used=True);write('ARC_LP_DUAL_SUPPORT_CERTIFICATE.json',cert)
    else:
        write('ARC_LP_PRIMAL_AUDIT.json',dict(PASS=False,status='NOT_OPTIMAL'));write('ARC_LP_DUAL_SUPPORT_CERTIFICATE.json',dict(PASS=False,status='NOT_OPTIMAL',L_dual_support=None))
    native=receipt['objective'] if model.Status==2 else None;lower=cert['L_dual_support'] if passed else None
    result=dict(ARC_LP_CERTIFIED=passed,native_optimum=native,L_arc_cert=lower,primal_dual_gap=None if lower is None else native-lower,scope='Actual frozen FULL original ARC LP: all integrality relaxed, original rows/bounds/objective preserved.',second_LP=False,arc_budget_spent=union_seconds(intervals),CG_budget=900,CG_budget_granted_only_after_certificate=passed,legacy_used_as_authority=False);write('ARC_LP_CERTIFIED_RESULT.json',result)
    comparison=dict(legacy_bestbd=BASE_LB,native_optimum=native,L_arc_cert=lower,difference_native_vs_legacy=None if native is None else native-BASE_LB,difference_cert_vs_legacy=None if lower is None else lower-BASE_LB,legacy_provenance='Interrupted integer MIP terminal global BestBd; diagnostic only',authority_from_similarity=False)
    comparison['classification']='MATERIALLY_DIFFERENT' if native is None or abs(native-BASE_LB)>1e-7 else 'NUMERICALLY_MATCHES' if lower is not None and max(abs(native-BASE_LB),abs(lower-BASE_LB))<=EPS else 'CLOSE_BUT_NOT_AUTHORITY';write('ARC_LP_LEGACY_COMPARISON.json',comparison)
    if passed:
        transfer=dict(PASS=True,L_arc_cert=lower,dominance_SHA=sha(DOMINANCE/'DW_FULL_SCALE_DOMINANCE_PROOF.json'),arc_certificate_SHA=sha(OUT/'ARC_LP_DUAL_SUPPORT_CERTIFICATE.json'),proof='Weak duality gives L_arc_cert <= z_arc_LP. PR143 full projected inclusion gives z_arc_LP <= z_DW_root. Transitivity gives the independent floor on that SAME full D-W root optimum.');write('DW_ARC_FLOOR_TRANSFER_CERTIFICATE.json',transfer)
        old=read(PR142/'DW_THROUGHPUT_FINAL.json');aggregate=max(lower,old['best_corrected_LB']);write('DW_AGGREGATED_LOWER_BOUND.json',dict(PASS=True,L_arc_cert=lower,L_corr_best_old=old['best_corrected_LB'],L_DW_cert=aggregate,proof='Maximum of two independently valid lower bounds on the same frozen full DW root.',legacy_MIP_bound_used=False))
        authority=thresholds(native,lower);authority.update(PASS=True,native_arc_reference=native,certified_lower_reference=lower,legacy_threshold=T_MATERIAL,legacy_authority=False,initial_interval=[aggregate,old['smallest_RMP_upper']],pre_CG_decision=decision(aggregate,old['smallest_RMP_upper'],authority));write('DW_MATERIAL_THRESHOLD_AUTHORITY.json',authority)
    model.dispose();print('ARC_CERT_DONE',result,flush=True)
    return passed

if __name__=='__main__':
    ok=run()
    if ok:
        from .cg import Experiment
        Experiment().run()
