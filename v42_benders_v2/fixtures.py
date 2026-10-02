"""Re-enumerate all inherited assignments across six exact paths."""
import itertools, json
import numpy as np
import gurobipy as gp
from v42_benders.fixtures import build,CASES
from v42_benders.canonical import from_model as canonical
from v42_benders.engine import Recourse as V1
from .common import *
from .representation import from_model,audit
from .recourse import Recourse
from .engine import certified,solve
from .independent import verify

def run():
    assert read('DERIVATION_FREEZE.json')['created_before_optimize']
    for r in read('DERIVATION_FREEZE.json')['files']:assert sha(OUT/r['path'])==r['sha256']
    assert read('EXECUTION_FREEZE.json')['commit']==git('rev-parse','HEAD')
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start()
    census=[];cases=[];native_audits=[];phase_audits=[]
    try:
        for case in CASES:
            m=build(env,case);n=from_model(m);assert audit(m,n)['PASS']
            c=canonical(m);v1=V1(c,env);v2=Recourse(n,env,OUT/'RAW'/case/'native');phase=Recourse(n,env,OUT/'RAW'/case/'phase1',phase=True)
            original=m.copy();original.setAttr('VType',['C']*original.NumVars);original.update()
            feasible=[];cuts=[];pcuts=[];case_rows=[]
            for idx,bits in enumerate(itertools.product([0.,1.],repeat=7)):
                x=np.array(bits);vs=original.getVars()
                for j,val in zip(n.xi,x):vs[j].LB=val;vs[j].UB=val
                original.optimize();r1,y,w=v1.solve(x,30);r2=v2.solve(x,30);p=phase.solve(x,30)
                assert original.Status in [2,3] and original.Status==r1['status']==r2['status'],(case,idx,'CLASSIFICATION')
                assert p['status']==2 and phase.primal_valid(p)
                isfeas=r2['status']==2
                if isfeas:
                    assert v2.primal_valid(r2) and n.residual(x,np.array(r2['primal']))<=1e-7
                    assert abs(original.ObjVal-r1['objective'])<=1e-7 and abs(original.ObjVal-r2['objective'])<=1e-7
                    assert p['objective']<=1e-8 and n.residual(x,np.array(p['primal'])[:len(n.yi)])<=1e-7
                    feasible.append((x,r2['objective']));cut=certified(n,r2,'optimality')
                else:
                    assert p['objective']>1e-8
                    cut=certified(n,r2,'native_farkas');pcut=certified(n,p,'phase1');pcuts.append(pcut)
                    phase_audits.append(dict(case=case,assignment=idx,**pcut['record'],independent_validation=pcut['independent_validation']))
                cuts.append(cut);native_audits.append(dict(case=case,assignment=idx,**cut['record'],independent_validation=cut['independent_validation']))
                case_rows.append(dict(case=case,assignment=idx,bits=''.join(map(str,map(int,bits))),
                    original_native_status=original.Status,V1_status=r1['status'],V2_status=r2['status'],
                    phase1_status=p['status'],phase1_optimum=p['objective'],feasible=isfeas,
                    original_optimum=original.ObjVal if isfeas else None,V1_optimum=r1['objective'],V2_optimum=r2['objective'],
                    native_cut_hash=cut['record']['cut_hash'],phase1_cut_hash=None if isfeas else pcut['record']['cut_hash'],match=True))
            for cut in cuts+pcuts:verify(n,cut,feasible)
            survived=[]
            for idx,bits in enumerate(itertools.product([0.,1.],repeat=7)):
                x=np.array(bits)
                if all(cut['record']['intercept']+float(cut['coefficients']@x)>=-1e-8 for cut in cuts if cut['record']['type']=='feasibility'):survived.append(idx)
            assert survived==[r['assignment'] for r in case_rows if r['feasible']]
            m.optimize();mono=m.ObjVal if m.SolCount else None
            result,best,bcuts=solve(n,env=env,directory=OUT/'RAW'/case/'loop',known=feasible,seconds=60,target_gap=0.)
            optimum=min([o for _,o in feasible],default=None)
            exact=(optimum is None and m.Status==3 and result['status']=='MASTER_INFEASIBLE') or (optimum is not None and best is not None and abs(mono-optimum)<=1e-7 and abs(float(n.c@best[n.yi]+n.objective_constant)-optimum)<=1e-7)
            assert exact,(case,result,optimum)
            assert result['status']!='STOP_UNCERTIFIABLE'
            for r in case_rows:r.update(monolithic_status=m.Status,monolithic_optimum=mono,Benders_V2_status=result['status'],Benders_V2_optimum=None if best is None else float(n.c@best[n.yi]+n.objective_constant))
            census+=case_rows;cases.append(dict(case=case,assignments=128,feasible=len(feasible),infeasible=128-len(feasible),
                PASS=True,all_feasible_survive=True,all_infeasible_excluded=True,monolithic_optimum=mono,enumeration_optimum=optimum,Benders_V2=result))
            original.dispose();v1.close();v2.close();phase.close();m.dispose()
            print(case,'V2 SIX-PATH EXACT PASS',len(feasible),'feasible',flush=True)
    finally:env.dispose()
    table('V2_FIXTURE_CENSUS.csv',census,list(census[0]))
    dump('V2_FIXTURE_EXACTNESS.json',dict(PASS=True,assignments=len(census),agreement=sum(r['match'] for r in census),
        feasible=sum(r['feasible'] for r in census),infeasible=sum(not r['feasible'] for r in census),
        all_feasible_survive=True,paths=['original native LP','V1 canonical LP','V2 native LP','Phase-I','monolithic MILP','V2 Benders'],
        PhaseI_all_assignment_diagnostic=True,PhaseI_engine_fallback_only=True,cases=cases))
    dump('NATIVE_FARKAS_CERTIFICATE_AUDIT.json',dict(PASS=True,records=native_audits,
        native_Farkas_valid=sum(r['kind']=='native_farkas' for r in native_audits),optimality_valid=sum(r['kind']=='optimality' for r in native_audits),
        full_scale_valid=0,raw_persisted_before_validation=True))
    dump('PHASE1_CERTIFICATE_AUDIT.json',dict(PASS=True,diagnostic_cuts=len(phase_audits),records=phase_audits,
        all_feasible_zero=True,full_scale_fallback_used=False,production_artificial_slack=False))

if __name__=='__main__':run()
