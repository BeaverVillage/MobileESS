"""All 128 assignments per 2-slot joint physical fixture, no route pool."""
import copy,itertools,json
import numpy as np
import gurobipy as gp
from math import cos,sin,pi
from .canonical import from_model,matrix_audit
from .certificates import create,verify,Uncertifiable
from .engine import Recourse,solve,configure
from .common import *

CASES={
 'A':dict(label='route legal / SOC infeasible',high_energy=4.),
 'B':dict(label='SOC feasible / grid infeasible',threshold=.70),
 'C':dict(label='terminal SOC infeasible',terminal=14.),
 'D':dict(label='PCS16 infeasible route',q_requirement=15.8),
 'E':dict(label='upper voltage violation on travelling route',upper_voltage_case=True),
 'F':dict(label='transformer violation on travelling route',transformer_case=True),
 'G':dict(label='feasible threshold witness',threshold=.95),
 'H':dict(label='degenerate dual',duplicate=True),
 'I':dict(label='near-zero Farkas margin safeguard',near_zero=True),
 'J':dict(label='finite bound contribution essential',bound_case=True),
 'K':dict(label='travel energy infeasibility',high_energy=8.),
 'L':dict(label='route changes P/Q recourse feasibility',route_case=True),
}

def build(env,case='A',anchor=1.,initial=10.):
    cfg=CASES[case];m=gp.Model('FIXTURE_'+case,env=env);configure(m,1,30)
    # Stay A0->A1->A2 or either legal A0->B1 travel then B1->B2.
    names=['stay_A0','stay_A1','stay_B1','travel_low','travel_high','mode0','mode1']
    x=m.addVars(names,vtype='B',name='route_mode')
    m.addConstr(x['stay_A0']+x['travel_low']+x['travel_high']==1,name='flow_origin')
    m.addConstr(x['stay_A1']==x['stay_A0'],name='flow_A1')
    m.addConstr(x['stay_B1']==x['travel_low']+x['travel_high'],name='flow_B1')
    m.addConstr(x['stay_A1']+x['stay_B1']==1,name='terminal_location')
    soc=m.addVars(3,lb=0.,ub=20.,name='SOC')
    m.addConstr(soc[0]==initial,name='initial_SOC')
    m.addConstr(soc[2]==cfg.get('terminal',initial),name='terminal_SOC')
    ch={};dis={};react={}
    for s,t in [('A',0),('A',1),('B',1)]:
        connected=x['stay_'+s+str(t)];mode=x['mode'+str(t)]
        ch[s,t]=m.addVar(lb=0,ub=16,name=f'Pch[{s},{t}]')
        dis[s,t]=m.addVar(lb=0,ub=16,name=f'Pdis[{s},{t}]')
        react[s,t]=m.addVar(lb=-16,ub=16,name=f'Q[{s},{t}]')
        m.addConstr(ch[s,t]<=16*connected,name='connected_Pch')
        m.addConstr(dis[s,t]<=16*connected,name='connected_Pdis')
        m.addConstr(ch[s,t]<=16*mode,name='charge_mode')
        m.addConstr(dis[s,t]<=16*(1-mode),name='discharge_mode')
        m.addConstr(react[s,t]<=16*connected,name='connected_Q_upper')
        m.addConstr(react[s,t]>=-16*connected,name='connected_Q_lower')
        for f in range(16):
            m.addConstr(cos(2*pi*f/16)*(dis[s,t]-ch[s,t])+sin(2*pi*f/16)*react[s,t]
                <=16*cos(pi/16)*connected,name='PCS16')
    high=cfg.get('high_energy',4.)
    m.addConstr(soc[1]==soc[0]+.25*(.9*ch['A',0]-dis['A',0]/.9)
        -.2*x['travel_low']-high*x['travel_high'],name='travel_SOC0')
    m.addConstr(soc[2]==soc[1]+.25*(.9*(ch['A',1]+ch['B',1])-(dis['A',1]+dis['B',1])/.9),name='SOC1')
    rho=m.addVar(lb=0,name='rho_max')
    for t in [0,1]:
        p=gp.quicksum(dis[s,k]-ch[s,k] for s,k in ch if k==t)
        qq=gp.quicksum(react[s,k] for s,k in ch if k==t)
        m.addConstr(anchor-.01*p-.005*qq<=rho,name='line_threshold')
        voltage=1.+.0005*p+.0005*qq
        m.addConstr(voltage>=.955,name='voltage_lower');m.addConstr(voltage<=1.045,name='voltage_upper')
        m.addConstr(.02*p+.01*qq<=1.2,name='transformer_current')
        m.addConstr(-.02*p+.01*qq<=1.2,name='transformer_kVA')
        if cfg.get('duplicate'):m.addConstr(anchor-.01*p-.005*qq<=rho,name='degenerate_duplicate')
    if 'threshold' in cfg:m.addConstr(rho<=cfg['threshold'],name='hard_grid_threshold')
    if cfg.get('q_requirement'):m.addConstr(react['B',1]>=cfg['q_requirement']*x['stay_B1'],name='PCS_required_Q')
    if cfg.get('upper_voltage_case'):m.addConstr(1.+.0005*react['B',1]+.06*x['stay_B1']<=1.045,name='adversarial_voltage_upper')
    if cfg.get('transformer_case'):m.addConstr(1.3*x['stay_B1']+.001*react['B',1]<=1.2,name='adversarial_transformer')
    if cfg.get('bound_case'):
        amp=m.addVar(lb=0,ub=1,name='bounded_transformer_aux')
        m.addConstr(amp>=1.1*x['stay_B1'],name='finite_bound_required')
    if cfg.get('route_case'):m.addConstr(ch['B',1]>=16.5*x['stay_B1'],name='route_P_required')
    m.setObjective(rho);m.update();return m

def near_zero_test(env):
    m=gp.Model('NEAR_ZERO',env=env);configure(m,1,10)
    x=m.addVar(vtype='B');y=m.addVar(lb=0,ub=1)
    m.addConstr(y<=-5e-9+x);m.setObjective(y);m.update();can=from_model(m)
    # Exact lambda uses physical upper row and explicit y>=0 bound.
    w=np.zeros(len(can.b));w[0]=1;w[1]=1
    rejected=False
    try:create(can,w,np.array([0.]),'feasibility',3)
    except Uncertifiable as e:rejected=str(e)=='NO_STRICT_FARKAS_MARGIN'
    m.dispose();return rejected

def run():
    assert (OUT/'BENDERS_FEASIBILITY_CUT_DERIVATION.md').exists()
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start()
    enumeration=[];monolithic=[];decomposition=[];adversarial=[];matrix=[];case_audits=[]
    all_cut_payload=[];failure=None
    try:
        for case,cfg in CASES.items():
            m=build(env,case);can=from_model(m);matrix.append(dict(case=case,**matrix_audit(m,can)))
            assert len(can.xi)==7 and all(a['PASS'] for a in matrix)
            lp=Recourse(can,env);native=m.copy();native.setAttr('VType',['C']*native.NumVars);native.update()
            known=[];infeasible=[];cuts=[];native_match=True
            for index,bits in enumerate(itertools.product([0.,1.],repeat=7)):
                xv=np.asarray(bits);rr,y,w=lp.solve(xv,30)
                original=native.getVars()
                for j,val in zip(can.xi,xv):original[j].LB=val;original[j].UB=val
                native.optimize()
                terminal=rr['status'] in [2,3] and native.Status in [2,3]
                same=terminal and rr['status']==native.Status
                feasible=rr['status']==2
                if feasible:
                    same=same and abs(rr['objective']-native.ObjVal)<=1e-7
                    assert can.residual(xv,y)<=1e-7
                    known.append((xv,rr['objective']))
                    cut=create(can,w,xv,'optimality',2,index,rr['objective'])
                else:
                    cut=create(can,w,xv,'feasibility',rr['status'],index)
                    infeasible.append(xv)
                native_match=native_match and same;cuts.append(cut)
                enumeration.append(dict(case=case,assignment=index,bits=''.join(map(str,map(int,bits))),
                    canonical_status=rr['status'],native_status=native.Status,feasible=feasible,
                    optimum=rr['objective'],native_optimum=native.ObjVal if native.SolCount else None,
                    primal_residual=rr['primal_residual'],dual_residual=rr['dual_residual'],Farkas_residual=rr['Farkas_residual'],match=same))
            lp.close();native.dispose()
            for cut in cuts:
                audit=verify(can,cut,known);assert audit['PASS']
            # Necessary cuts plus the unchanged discrete rows exactly reproduce census.
            survived=[]
            for index,bits in enumerate(itertools.product([0.,1.],repeat=7)):
                xv=np.asarray(bits)
                if any(c['record']['type']=='feasibility' and c['record']['intercept']+c['coefficients']@xv < -1e-8 for c in cuts):continue
                survived.append(index)
            feasible_indices=[r['assignment'] for r in enumeration if r['case']==case and r['feasible']]
            assert survived==feasible_indices
            m.optimize();mono=m.ObjVal if m.SolCount else None
            result,best,engine_cuts=solve(can,env=env,seconds=60,known=known,target_gap=0)
            benders=None if best is None else float(can.c@best[can.yi])
            optimum=min([value for _,value in known],default=None)
            exact=(native_match and ((optimum is None and m.Status==3 and result['status']=='MASTER_INFEASIBLE')
                or (optimum is not None and mono is not None and benders is not None and abs(mono-optimum)<=1e-7 and abs(benders-optimum)<=1e-7)))
            selected_equivalence=best is None or any(np.array_equal(best[can.xi],x) and abs(v-optimum)<=1e-7 for x,v in known)
            assert exact and selected_equivalence,(case,result['status'],optimum,benders)
            monolithic.append(dict(case=case,status=m.Status,optimum=mono,enumeration_optimum=optimum))
            decomposition.append(dict(case=case,status=result['status'],optimum=benders,iterations=result['iterations'],
                feasibility_cuts=result['feasibility_cuts'],optimality_cuts=result['optimality_cuts'],selected_equivalence=selected_equivalence))
            # Mutate certificate payloads; independent recomputation must reject each.
            candidate=next(c for c in cuts if c['record']['type']=='feasibility')
            for mutation in ['ray_sign','bound_term','B_coefficient','RHS']:
                bad=copy.deepcopy(candidate)
                if mutation=='ray_sign':bad['multipliers']=-bad['multipliers']
                elif mutation=='bound_term':bad['record']['exact_bound_correction']='999'
                elif mutation=='B_coefficient':bad['coefficients'][0]+=1
                else:bad['record']['intercept']+=1
                rejected=False;reason=None
                try:verify(can,bad,known)
                except Uncertifiable as e:rejected=True;reason=str(e)
                assert rejected
                adversarial.append(dict(case=case,mutation=mutation,rejected=rejected,reason=reason))
            bound_nonzero=any(c['record']['bound_row_contribution']!='0' for c in cuts if c['record']['type']=='feasibility')
            case_audits.append(dict(case=case,label=cfg['label'],assignments=128,feasible=len(known),infeasible=len(infeasible),
                native_canonical_match=native_match,all_feasible_survive=True,all_infeasible_excluded=True,
                optimum_match=exact,selected_optimum_equivalence=selected_equivalence,finite_bound_ray_present=bound_nonzero,
                cut_count=len(cuts),engine=result))
            for cut in cuts:
                all_cut_payload.append(dict(case=case,record=cut['record'],coefficients=cut['coefficients'].tolist(),
                    source_x=cut['source_x'].tolist(),multipliers=cut['multipliers'].tolist()))
            m.dispose();print(case,'EXACT PASS',len(known),'feasible',result['status'],flush=True)
        assert near_zero_test(env)
        adversarial.append(dict(case='I',mutation='near_zero_margin',rejected=True,reason='NO_STRICT_FARKAS_MARGIN'))
        assert next(c for c in case_audits if c['case']=='J')['finite_bound_ray_present']
    except Exception as e:
        failure=repr(e);print('FIXTURE STOP',failure,flush=True)
    finally:env.dispose()
    table('FIXTURE_ENUMERATION.csv',enumeration,['case','assignment','bits','canonical_status','native_status','feasible','optimum','native_optimum','primal_residual','dual_residual','Farkas_residual','match'])
    table('FIXTURE_MONOLITHIC_RESULTS.csv',monolithic,['case','status','optimum','enumeration_optimum'])
    table('FIXTURE_DECOMPOSITION_RESULTS.csv',decomposition,['case','status','optimum','iterations','feasibility_cuts','optimality_cuts','selected_equivalence'])
    table('ADVERSARIAL_CUT_VALIDATION.csv',adversarial,['case','mutation','rejected','reason'])
    dump('FIXTURE_CANONICAL_MATRIX_VALIDATION.json',dict(PASS=all(m['PASS'] for m in matrix),cases=matrix))
    dump('FIXTURE_CUT_PAYLOADS.json',all_cut_payload)
    dump('FIXTURE_EXACTNESS.json',dict(PASS=failure is None and len(case_audits)==12,stop_reason=failure,
        assignments=len(enumeration),cases=case_audits,near_zero_margin_rejected=any(a['mutation']=='near_zero_margin' for a in adversarial),
        adversarial_rejections=len(adversarial),full_scale_authorized=failure is None and len(case_audits)==12))
    return failure is None

if __name__=='__main__':run()
