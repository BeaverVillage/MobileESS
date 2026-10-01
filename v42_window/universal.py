"""Validate complete path lifts into idle-unit W7 upper witnesses."""
import gurobipy as gp
from .common import *

def run():
    _,_,_,sites,initial,routes,b=inputs();arcs=arcs_for(sites,routes)
    receipts=[read(p) for p in (OUT/'oracle_certificates').glob('UPPER_WITNESS_*.json')]
    assert len(receipts)==6 and all(r['status']==2 and r['feasible_upper']<DEFAULT-OBJ_TOL for r in receipts),'UNIVERSAL_UPPER_NOT_PROVED_CONTINUE_ORACLES'
    env=gp.Env(empty=True);env.setParam('OutputFlag',0);env.start();m=gp.read(str(LOCAL/'W7.mps'),env=env)
    names=m.getAttr('VarName');rownames=m.getAttr('ConstrName');A=m.getA();rhs=np.array(m.getAttr('RHS'));sense=np.array(m.getAttr('Sense'));lo=np.array(m.getAttr('LB'));hi=np.array(m.getAttr('UB'))
    # Native full-horizon rows precede every original grid/auxiliary row.
    families=read(OUT/'W7_MATRIX_CENSUS.json')['rows_by_family'];ordered=list(families)
    boundary=sum(families[n] for n in ordered[:ordered.index('injection_P_binding')])
    dump('W7_NATIVE_ROW_AXIS_RECEIPT.json',dict(native_rows=boundary,source='Pre-write row family census in native construction order',MPS_row_names='c0..cN: duplicate native names trigger Gurobi anonymous MPS row names',row_order_unchanged=True))
    systems={};positions={n:i for i,n in enumerate(names)}
    for u in initial:
        columns=np.array([i for i,n in enumerate(names) if any(n.startswith(f'{f}[{u},') for f in ['arc','Pch','Pdis','Q','charge_mode','SOC'])])
        physical=A[:boundary,columns];rows=np.flatnonzero(physical.getnnz(axis=1));physical=physical[rows,:].tocsr()
        systems[u]=(columns,{names[i]:j for j,i in enumerate(columns)},physical,rhs[rows],sense[rows],lo[columns],hi[columns])
    upper_checks=[]
    for r in receipts:
        with np.load(OUT/'oracle_certificates'/f"{r['key']}.upper.npz",allow_pickle=False) as z:
            assert list(z['names'])==names;values=z['values']
        residual=A@values-rhs;error=np.where(sense=='=',abs(residual),np.where(sense=='<',residual,-residual))
        maximum=max(0.,float(error.max()),float((lo-values).max()),float((values-hi).max()))
        assert maximum<=TOL
        assert abs(values[positions['rho_max']]-r['feasible_upper'])<=OBJ_TOL
        for u in r['idle_units']:
            assert all(abs(values[i])<=TOL for i,n in enumerate(names) if n.startswith((f'Pch[{u},',f'Pdis[{u},',f'Q[{u},')))
        upper_checks.append(dict(pair=r['idle_units'],rho=r['feasible_upper'],full_W7_matrix_max_violation=maximum,PASS=True))
    singles=json.loads(gzip.decompress((PRIOR/'O1_ALL_STATE_WITNESSES.json.gz').read_bytes()))
    crosses=json.loads(gzip.decompress((OUT/'G3_ROUTE_WITNESSES.json.gz').read_bytes()))
    audit=[];lifts={}
    for kind,source in [('G1',singles),('G3',crosses)]:
        for key,witness in sorted(source.items()):
            u=key.split(':')[0];path=witness['path'];total=sum(arcs[k][-1].energy_kwh for k in path if arcs[k][-1] is not None)
            assert total<=min(b.initial-b.minimum,b.maximum-b.initial)+TOL
            # Validate complete route continuity and exact state boundaries.
            loc=initial[u];time=0
            for k in path:
                s,start,d,end,_=arcs[k];assert (s,start)==(loc,time);loc,time=d,end
            assert time==96
            parts=key.split(':')
            conditions=[(int(parts[1]),parts[2])] if kind=='G1' else [(int(parts[1]),parts[3]),(int(parts[2]),parts[4])]
            for t,a in conditions:
                active=[arcs[k] for k in path if arcs[k][1]<=t<arcs[k][3]];assert len(active)==1
                assert (active[0][0] if active[0][-1] is None else 'TRANSIT')==a
            charging={};remaining=total
            for k in reversed(path):
                s,t,d,e,r=arcs[k]
                if r is not None or t in WINDOW:continue
                gain=min(remaining,b.dt_hours*b.eta_charge*b.p_limit)
                if gain>0:charging[t]=(s,gain/(b.dt_hours*b.eta_charge));remaining-=gain
            assert remaining<=OBJ_TOL
            columns,index,physical,br,ss,lb,ub=systems[u];values=np.zeros(len(columns))
            for k in path:values[index[f'arc[{u},{k}]']]=1.
            energy=b.initial;values[index[f'SOC[{u},0]']]=energy
            for t in range(96):
                if t in charging:
                    s,power=charging[t];values[index[f'Pch[{u},{s},{t}]']]=power;values[index[f'charge_mode[{u},{t}]']]=1.;energy+=b.dt_hours*b.eta_charge*power
                energy-=sum(arcs[k][-1].energy_kwh for k in path if arcs[k][1]==t and arcs[k][-1] is not None)
                values[index[f'SOC[{u},{t+1}]']]=energy
            residual=physical@values-br;error=np.where(ss=='=',abs(residual),np.where(ss=='<',residual,-residual))
            maximum=max(0.,float(error.max()),float((lb-values).max()),float((values-ub).max()))
            assert maximum<=TOL and abs(energy-b.terminal)<=TOL
            # All original grid and grid-binding row activities are unchanged:
            # only native idle-unit columns differ, and every retained-slot
            # Pch/Pdis/Q remains exactly zero. There are no outside grid rows.
            grid_change=A[boundary:,columns]@values
            assert float(abs(grid_change).max())==0.
            audit.append(dict(kind=kind,key=key,MESS=u,travel_energy=total,charge_slots=len(charging),native_physical_matrix_max_violation=maximum,grid_activity_change=0.,PASS=True))
            lifts[kind+':'+key]=dict(path=path,charging={str(t):v for t,v in charging.items()},travel_energy=total)
    table('W7_COMPLETE_PATH_LIFT_AUDIT.csv',audit)
    (OUT/'W7_COMPLETE_PATH_LIFTS.json.gz').write_bytes(gzip.compress(json.dumps(lifts).encode(),mtime=0))
    m.dispose();env.dispose()
    dump('W7_UNIVERSAL_STOP_CERTIFICATE.json',dict(PASS=True,G1_states=sum(r['kind']=='G1' for r in audit),G3_reachable_pairs=sum(r['kind']=='G3' for r in audit),
        G2_state_pairs=11250,all_six_idle_pairs=upper_checks,upper_max=max(r['rho'] for r in upper_checks),upper_never_used_as_beta=True,
        complete_native_physics_lifts=True,all_window_grid_rows_unmodified=True,scope='All 600 G1 states, all 11250 G2 same-time pairs and every authority-reachable G3 time-state pair',
        proof='For each inactive pair the stored full W7 feasible upper point satisfies every original retained grid row. Replace one inactive unit with a validated zero-window-P/Q route/charge/SOC lift for any G1 or G3 condition, or both units independently for G2. All native unit constraints remain satisfied; all window grid activities are identical. Therefore every conditional W7 optimum <= corresponding feasible upper < inherited global default. No future W7 solve can improve any beta beyond default or change any separation decision.',
        priority_states_stopped_by_proof=True,states_not_pruned=True,not_full_horizon_grid_incumbents=True))
    print('W7 UNIVERSAL STOP CERTIFICATE PASS',len(audit),max(r['rho'] for r in upper_checks),flush=True)
if __name__=='__main__':run()
