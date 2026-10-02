"""Repeat every inherited assignment, N1-N10, and a free-support reproducer."""
import csv,itertools
import numpy as np
import gurobipy as gp
from v42_benders.fixtures import build,CASES
from v42_benders_v2.adversarial import build as numerical
from v42_benders_v2.representation import from_model
from v42_benders_v2.recourse import Recourse
from v42_benders_v2.engine import certified
from v42_benders.certificates import Uncertifiable
from .common import *
from .exact import create
from .independent import verify
from .scaling import scaled

def proof(n,raw,known=()):
    cut=create(n,raw);cut['independent_validation']=verify(n,cut,known);return cut

def reproducer(env):
    m=gp.Model('REDUCED_FREE_SUPPORT',env=env)
    x=m.addVar(vtype='B',name='route');b=m.addVar(lb=0,ub=1,name='boxed_P')
    y=m.addVar(lb=-gp.GRB.INFINITY,name='injection_P');z=m.addVar(lb=-gp.GRB.INFINITY,name='response_line_P')
    m.addConstr(y==b+x);m.addConstr(z==.1*y);m.addConstr(z>=.2-.1*x);m.setObjective(b);m.update();return m

def run():
    preserve();p=read('PREREGISTRATION.json');assert p['fullscale_master_before_valid_cut']==0
    expected=list(csv.DictReader((ROOT/'docs/v42_mess_benders_v2_native_recourse/V2_FIXTURE_CENSUS.csv').open()))
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();rows=[];numerics=[];allcuts=0
    try:
        for case in CASES:
            m=build(env,case);n=from_model(m);ns=scaled(n,(np.arange(len(n.b))%9)-4)
            native=Recourse(n,env,OUT/'FIXTURE_RAW'/case/'native');rescaled=Recourse(ns,env,OUT/'FIXTURE_RAW'/case/'scaled')
            phase=Recourse(n,env,OUT/'FIXTURE_RAW'/case/'phase1',phase=True)
            known=[];cuts=[];case_rows=[]
            for idx,bits in enumerate(itertools.product([0.,1.],repeat=7)):
                x=np.array(bits);raw=native.solve(x,30);sr=rescaled.solve(x,30);aux=phase.solve(x,30)
                old=next(r for r in expected if r['case']==case and int(r['assignment'])==idx)
                assert raw['status']==sr['status']==int(old['V2_status']) and raw['status'] in [2,3]
                assert aux['status']==2 and phase.primal_valid(aux)
                if raw['status']==2:
                    assert native.primal_valid(raw) and rescaled.primal_valid(sr)
                    assert abs(raw['objective']-sr['objective'])<=1e-7 and abs(raw['objective']-float(old['V2_optimum']))<=1e-7
                    assert n.residual(x,sr['primal'])<=1e-7 and aux['objective']<=1e-8
                    known.append((x,raw['objective']));certified(n,raw,'optimality')
                else:
                    pc=proof(n,aux);cuts.append((n,pc));allcuts+=1
                    for representation,r in [(n,raw),(ns,sr)]:
                        try:cut=proof(representation,r)
                        except Uncertifiable:continue
                        cuts.append((representation,cut));allcuts+=1
                case_rows.append(dict(case=case,assignment=idx,native_status=raw['status'],standard_form_identity_status=raw['status'],
                    power2_scaled_status=sr['status'],feasible=raw['status']==2,optimum=raw['objective'],scaled_optimum=sr['objective'],PASS=True))
            for representation,cut in cuts:verify(representation,cut,known)
            assert sum(r['feasible'] for r in case_rows)==sum(r['feasible']=='True' for r in expected if r['case']==case)
            rows+=case_rows;native.close();rescaled.close();phase.close();m.dispose()
            print(case,'128 assignments / scaling / exact cuts / all feasible survive PASS',flush=True)
        for num in range(1,12):
            m=numerical(env,num) if num<=10 else reproducer(env);n=from_model(m);ns=scaled(n,(np.arange(len(n.b))%9)-4)
            lp=Recourse(n,env,OUT/'NUMERICAL_RAW'/f'N{num}'/'native');sp=Recourse(ns,env,OUT/'NUMERICAL_RAW'/f'N{num}'/'scaled')
            raw=lp.solve(np.array([0.]),30);sr=sp.solve(np.array([0.]),30);assert raw['status']==sr['status']
            if num==6:
                assert raw['status']==2
                ar=Recourse(n,env,OUT/'NUMERICAL_RAW'/'N6'/'phase1',phase=True);aux=ar.solve(np.array([0.]),30)
                try:proof(n,aux);raise AssertionError('NEAR_ZERO_ACCEPTED')
                except Uncertifiable:pass
                ar.close();numerics.append(dict(case='N6',PASS=True,classification='INCONCLUSIVE_NEAR_ZERO',cut=False))
            elif raw['status']==2:
                assert lp.primal_valid(raw) and sp.primal_valid(sr) and abs(raw['objective']-sr['objective'])<=1e-7
                certified(n,raw,'optimality');numerics.append(dict(case=f'N{num}',PASS=True,classification='FEASIBLE',cut=False))
            else:
                try:cut=proof(n,raw)
                except Uncertifiable:
                    ar=Recourse(n,env,OUT/'NUMERICAL_RAW'/f'N{num}'/'phase1',phase=True);aux=ar.solve(np.array([0.]),30);assert ar.primal_valid(aux)
                    cut=proof(n,aux);ar.close()
                feasible=lp.solve(np.array([1.]),30)
                if feasible['status']==2:verify(n,cut,[(np.array([1.]),feasible['objective'])])
                numerics.append(dict(case=f'N{num}',PASS=True,classification='CERTIFIED_INFEASIBLE',cut_hash=cut['record']['cut_hash']))
            lp.close();sp.close();m.dispose();print('N'+str(num),'PASS',flush=True)
    finally:env.dispose()
    assert len(rows)==1536 and sum(r['feasible'] for r in rows)==49
    table('FIXTURE_CENSUS.csv',rows,list(rows[0]))
    dump('FIXTURE_REGRESSION.json',dict(PASS=True,assignments=1536,feasible=49,infeasible=1487,all_known_feasible_preserved=True,
        source_infeasible_separated=True,certificates_validated=allcuts,numerical_N1_N10=numerics[:10],reduced_unsupported_support_fixture=numerics[10],
        native_identity_and_power2_classification_equal=True,optima_equal=True,mapped_solution_native_residual_PASS=True,
        raw_before_validation=True,fullscale_master_optimize_calls=0))
    dump('STANDARD_FORM_EQUIVALENCE.json',dict(PASS=True,production_transform='IDENTITY',original_rows_deleted=0,
        original_variables_removed=0,bijection=True,forward='y -> y',inverse='y -> y',
        native_identity_classification_assignments=1536,nontrivial_power2_fixture_assignments=1536))

if __name__=='__main__':run()
