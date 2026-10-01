"""Constructive O1 upper witnesses bound every uncomputed beta's usefulness.

These upper bounds are NEVER cut coefficients. They certify that additional
O1 solves cannot improve the valid inherited default lower-bound coefficient.
"""
from collections import defaultdict
import math,gzip
import gurobipy as gp
from .common import *
from .oracle import add_slot_lines

def run():
    from v42_native.mess import validate
    from v42_bootstrap.grid import coefficients
    bundle,anchor,inc,sites,initial,routes,b=inputs();arcs=arcs_for(sites,routes)
    bytime=defaultdict(list)
    for k,a in enumerate(arcs):bytime[a[1]].append(k)
    slotset=read(OUT/'CRITICAL_SLOT_FREEZE.json')['slots'];axis=read(OUT/'ROOT_STATE_AXIS.json')
    _,coeff=coefficients(bundle);slotupper={}
    for t in slotset:
        model=gp.Model();model.Params.OutputFlag=0;rho=model.addVar(lb=0,ub=1)
        controls=[float(anchor['controls'][t][i]) if n.startswith('aidc_load_kw') else 0. for i,n in enumerate(coeff[t].control_names)]
        add_slot_lines(model,coeff[t],controls,rho);model.update()
        # Constant rows determine max loading without an optimize call.
        upper=max(0.,max(-r.RHS for r in model.getConstrs()))
        assert upper<DEFAULT-OBJ_TOL,(t,upper)
        slotupper[t]=upper;model.dispose()
    witnesses={};audit=[];fullchecks=[]
    for u,origin in sorted(initial.items()):
        best={(origin,0):(0.,[])}
        for time in range(96):
            for k in bytime[time]:
                a=arcs[k]
                if a[:2] not in best:continue
                cost,path=best[a[:2]];candidate=(cost+(a[-1].energy_kwh if a[-1] else 0),path+[k]);node=(a[2],a[3])
                if node not in best or candidate[0]<best[node][0]:best[node]=candidate
        for t in slotset:
            for s in axis[f'{u}:{t}']['states']:
                if s=='TRANSIT':
                    choices=[(best[a[:2]][0]+a[-1].energy_kwh,best[a[:2]][1]+[k],a[2],a[3]) for k,a in enumerate(arcs) if a[-1] is not None and a[1]<=t<a[3] and a[:2] in best]
                    total,path,loc,end=min(choices,key=lambda r:(r[0],r[3],r[1][-1]))
                else:
                    total,path=best[s,t];path=path+[sites.index(s)*96+t];loc=s;end=t+1
                path=path+[sites.index(loc)*96+j for j in range(end,96)]
                assert total<=min(b.initial-b.minimum,b.maximum-b.initial)+TOL,'PATH_ENERGY_NEEDS_STRONGER_LIFT'
                connected={arcs[k][1]:arcs[k][0] for k in path if arcs[k][-1] is None}
                charging={};remaining=total
                for time,site in sorted(connected.items(),reverse=True):
                    if time==t:continue
                    gain=min(remaining,b.dt_hours*b.eta_charge*b.p_limit)
                    if gain>0:charging[time]=(site,gain/(b.dt_hours*b.eta_charge));remaining-=gain
                assert remaining<=OBJ_TOL,'INSUFFICIENT_CONNECTED_CHARGE_CAPACITY'
                vals={f'{family}[{u},{site},{time}]':0. for family in ['Pch','Pdis','Q'] for site in sites for time in range(96)}
                for time,(site,power) in charging.items():vals[f'Pch[{u},{site},{time}]']=power
                E=b.initial;vals[f'SOC[{u},0]']=E
                for time in range(96):
                    E+=sum(b.dt_hours*b.eta_charge*power for j,(_,power) in charging.items() if j==time)
                    E-=sum(arcs[k][-1].energy_kwh for k in path if arcs[k][1]==time and arcs[k][-1] is not None)
                    vals[f'SOC[{u},{time+1}]']=E
                    vals[f'charge_mode[{u},{time}]']=float(time in charging)
                result=dict(values=vals,initial_sites={u:origin},chosen_arcs={u:path},mode='MILP')
                check=validate(result,sites,routes,b,96)
                assert check['PASS'] and abs(E-b.terminal)<=TOL,(u,t,s,check)
                occupied=[arcs[k] for k in path if arcs[k][1]<=t<arcs[k][3]];assert len(occupied)==1
                actual=occupied[0][0] if occupied[0][-1] is None else 'TRANSIT';assert actual==s
                assert all(vals[f'{f}[{u},{site},{t}]']==0 for site in sites for f in ['Pch','Pdis','Q'])
                witnesses[f'{u}:{t}:{s}']=dict(path=path,charging={str(j):v for j,v in charging.items()},travel_energy=total,physical_PASS=True)
                audit.append(dict(MESS=u,time=t,state=s,travel_energy=total,charging_slots=len(charging),O1_feasible_upper=slotupper[t],strictly_below_default=slotupper[t]<DEFAULT-OBJ_TOL,PASS=True))
    (OUT/'O1_ALL_STATE_WITNESSES.json.gz').write_bytes(gzip.compress(json.dumps(witnesses,sort_keys=True).encode(),mtime=0))
    # Validate actual full O1 matrices for every single-state witness. Line rows
    # see zero P/Q; all other units all-stay, SOC=initial=terminal.
    for t in slotset:
        env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();m=gp.read(str(LOCAL/f'O1_{t}.mps'),env=env)
        names=m.getAttr('VarName');positions={n:i for i,n in enumerate(names)};A=m.getA();rhs=np.array(m.getAttr('RHS'));sense=np.array(m.getAttr('Sense'));lo=np.array(m.getAttr('LB'));hi=np.array(m.getAttr('UB'))
        baseline=np.zeros(len(names));baseline[positions['rho_max']]=slotupper[t]
        for unit,site in initial.items():
            for time in range(96):baseline[positions[f'arc[{unit},{sites.index(site)*96+time}]']]=1.
            for time in range(97):baseline[positions[f'SOC[{unit},{time}]']]=b.initial
        for row in [r for r in audit if r['time']==t]:
            u,s=row['MESS'],row['state'];w=witnesses[f'{u}:{t}:{s}'];values=baseline.copy()
            for time in range(96):values[positions[f'arc[{u},{sites.index(initial[u])*96+time}]']]=0.
            for k in w['path']:values[positions[f'arc[{u},{k}]']]=1.
            energy=b.initial
            for time in range(96):
                if str(time) in w['charging']:
                    site,power=w['charging'][str(time)];values[positions[f'Pch[{u},{site},{time}]']]=power;values[positions[f'charge_mode[{u},{time}]']]=1.;energy+=b.dt_hours*b.eta_charge*power
                energy-=sum(arcs[k][-1].energy_kwh for k in w['path'] if arcs[k][1]==time and arcs[k][-1] is not None)
                values[positions[f'SOC[{u},{time+1}]']]=energy
            residual=A@values-rhs;error=np.where(sense=='=',abs(residual),np.where(sense=='<',residual,-residual))
            maximum=max(0.,float(error.max()),float((lo-values).max()),float((values-hi).max()))
            assert maximum<=TOL,(u,t,s,maximum)
            row['full_matrix_max_violation']=maximum
        fullchecks.append(dict(time=t,states=sum(r['time']==t for r in audit),matrix_max_violation=max(r['full_matrix_max_violation'] for r in audit if r['time']==t),PASS=True))
        m.dispose();env.dispose()
        print('UNIVERSAL O1 UPPER',t,slotupper[t],'all states full-matrix PASS',flush=True)
    table('O1_UNSOLVED_STATE_UPPER_AUDIT.csv',audit)
    dump('O1_UNIVERSAL_STOP_CERTIFICATE.json',dict(PASS=True,states=len(audit),slot_upper={str(t):z for t,z in slotupper.items()},full_matrix_checks=fullchecks,
        integer_paths_independently_validated=True,zero_P_Q_at_selected_slot=True,all_reachable_single_states_covered=True,
        all_pair_states_covered=True,pair_proof='Different units have disjoint MESS rows; combine their validated single-state witnesses. All selected-slot P/Q are zero, so every retained grid row is identical to the single-state case.',
        beta_upper_proof='Every O1 optimum <= constructed feasible upper < inherited global default. Therefore max(default, certified O1 lower bound)=default for every state and pair, even if solved later.',
        beta_coefficients_use_upper_bounds=False,stopping_rule='No further O1 conditional solve can change any beta or E1/E2 root-precheck decision; remaining reachable states retain certified global default.',
        priority_remaining_stopped=True,not_a_full_M1_feasibility_certificate=True,other_time_grid_rows_dropped=True))

if __name__=='__main__':run()
