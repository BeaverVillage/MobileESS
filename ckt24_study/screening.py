"""Predeclared, original-network-only electrical screening, never a MILP result."""
from .preflight import *

def quick(e, lines, xfs):
    c=e.ActiveCircuit;curr=[]
    for row in lines:
        c.Lines.Name=row['line'];a=c.ActiveCktElement
        amps=np.asarray(a.CurrentsMagAng)[::2]
        curr.extend((row['line'],int(n),float(v/row['normamps'])) for n,v in zip(row['nodes'],amps) if n>0)
    by={}
    for name,n,rho in curr:
        by[name,n]=max(by.get((name,n),0),rho)
    volts=np.asarray(c.AllBusVmagPu);volts=volts[volts>0]
    tx=0
    for xf in xfs:
        c.Transformers.Name=xf['transformer'];a=c.ActiveCktElement;nc=a.NumConductors
        powers=np.asarray(a.Powers).reshape(-1,2)
        for w in xf['windings']:
            pq=powers[(w['winding']-1)*nc:w['winding']*nc].sum(axis=0)
            tx=max(tx,float(np.hypot(*pq)/w['kva']))
    return dict(rho_max=max(by.values()),v_min=float(min(volts)),v_max=float(max(volts)),
                transformer_max=tx,p_kw=-float(c.TotalPower[0])),by

def settle(e,slot,k=1,mode='static'):
    e.Text.Command=f'set mode=yearly number=1 stepsize=900s controlmode={mode} loadmult={k}'
    e.Text.Command=f'set hour={2880+slot//4} sec={slot%4*900}'
    for _ in range(3):e.ActiveCircuit.Solution.SolveSnap()
    if not e.ActiveCircuit.Solution.Converged:raise RuntimeError('AC_NOT_CONVERGED')

def scenario_screen():
    # Record before solving any scaled candidate, selecting a PCC, or seeing B3.
    declared=dict(UTC=dt.datetime.now(dt.timezone.utc).isoformat(),
        candidates=[dict(k_BG=k,k_AIDC=1,k_PV=1) for k in [1,.75,.5]],
        voltage_limits=[.95,1.05],thermal_limit_pu=1,perturbation_P_kw=30,perturbation_Q_kvar=25,
        spatial_traffic_tolerance_m=.01,spatial_epri_tolerance_coordinate_units=.01,
        near_zero_rho_change=1e-6,near_zero_derivative_per_kw=1e-8,
        no_scaling_selection_based_on_B3=True,
        coordinates='Original EPRI drawing coordinates only. No GIS co-location claim.',
        no_candidate_additions_without_new_declaration=True)
    if (DOC/'SCREENING_PREREGISTRATION.json').exists():
        old=json.loads((DOC/'SCREENING_PREREGISTRATION.json').read_text())
        if old['candidates']!=declared['candidates']:raise ValueError('PREREGISTRATION_DRIFT')
    else:save('SCREENING_PREREGISTRATION.json',declared)
    inv=json.loads((DOC/'NETWORK_INVENTORY.json').read_text());lines=inv['lines'];xfs=inv['transformers']
    rows=[];selection=[]
    for k,mode in [(1,'off'),(1,'static'),(.75,'static'),(.5,'static')]:
        e=context(f'candidate_{k}_{mode}');series=[]
        for slot in range(96):
            settle(e,slot,k,mode);m,_=quick(e,lines,xfs);series.append(dict(k_BG=k,mode=mode,slot=slot,**m))
        rows+=series
        s=dict(k_BG=k,mode=mode,scope='ORIGINAL_BACKGROUND_ONLY_NO_AIDC',
            rho_max=max(r['rho_max'] for r in series),v_min=min(r['v_min'] for r in series),
            v_max=max(r['v_max'] for r in series),transformer_max=max(r['transformer_max'] for r in series),
            peak_kw=max(r['p_kw'] for r in series),r_MESS=2400/max(r['p_kw'] for r in series),
            r_PV=0,APPLIED_SCALING=k!=1,selected=False)
        s['background_physical_PASS']=s['v_min']>=.95 and s['v_max']<=1.05 and s['transformer_max']<=1 and s['rho_max']<=1
        s['reason']='FINAL_SELECTION_PENDING_AIDC_PCC_JOB_AND_FULL_AC_GATES'
        selection.append(s);print('SCENARIO',s,flush=True)
    csvout('POWER_RATIO_SCREENING.csv',selection);csvout('POWER_RATIO_96.csv',rows)

def sensitivity():
    inv=json.loads((DOC/'NETWORK_INVENTORY.json').read_text());lines=inv['lines'];xfs=inv['transformers']
    prereg=json.loads((DOC/'SCREENING_PREREGISTRATION.json').read_text())
    slot=json.loads((DOC/'ORIGINAL_BASELINE_SUMMARY.json').read_text())['peak_slot']
    candidates=[b for b in inv['buses'] if b['coord_defined'] and 1<=b['kv_ll']<69 and {1,2,3}<=set(b['nodes'])]
    csvout('MV_PCC_CANDIDATES.csv',candidates)
    baseline_context=context('sensitivity_reference');settle(baseline_context,slot)
    base,basecurr=quick(baseline_context,lines,xfs)
    baseline_context.ClearAll()
    out=DOC/'MESS_PQ_CONTROLLABILITY.csv'
    topout=RUNTIME/'SENSITIVITY_TOP20.csv'
    fields=['bus','slot','k_BG','p_kw','q_kvar','base_rho','rho','delta_rho','derivative','v_min','v_max','transformer_max','worst_line','worst_phase','converged','scope']
    with out.open('w',newline='',encoding='utf-8-sig') as f,topout.open('w',newline='',encoding='utf-8-sig') as tf:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        tw=csv.DictWriter(tf,fieldnames=['bus','p_kw','q_kvar','line','phase','base_rho','rho','delta_rho']);tw.writeheader()
        for i,b in enumerate(candidates):
            for dp,dq in [(30,0),(-30,0),(0,25),(0,-25)]:
                e=context('sensitivity');settle(e,slot)
                e.Text.Command=f'new load.STUDY_PERTURB phases=3 bus1={b["bus"]}.1.2.3 kv={b["kv_ll"]} kw={-dp} kvar={-dq} model=1 status=fixed vminpu=.5 vmaxpu=1.5'
                for _ in range(3):e.ActiveCircuit.Solution.SolveSnap()
                if not e.ActiveCircuit.Solution.Converged:raise RuntimeError('SENSITIVITY_AC_FAILED')
                m,curr=quick(e,lines,xfs);worst=max(curr,key=curr.get)
                w.writerow(dict(bus=b['bus'],slot=slot,k_BG=1,p_kw=dp,q_kvar=dq,base_rho=base['rho_max'],rho=m['rho_max'],
                    delta_rho=m['rho_max']-base['rho_max'],derivative=(m['rho_max']-base['rho_max'])/(dp or dq),
                    v_min=m['v_min'],v_max=m['v_max'],transformer_max=m['transformer_max'],worst_line=worst[0],worst_phase=worst[1],converged=True,
                    scope='INSTANTANEOUS_VIRTUAL_MV_PORT_NOT_ENGINEERED_PCC_OR_SCHEDULE_CERTIFICATE'))
                for name,n in sorted(basecurr,key=basecurr.get,reverse=True)[:20]:
                    tw.writerow(dict(bus=b['bus'],p_kw=dp,q_kvar=dq,line=name,phase=n,base_rho=basecurr[name,n],rho=curr[name,n],delta_rho=curr[name,n]-basecurr[name,n]))
                e.ClearAll()
            f.flush();tf.flush()
            if i%20==0:print('SENSITIVITY',i+1,'/',len(candidates),flush=True)
    save('SENSITIVITY_RAW_RECEIPT.json',dict(path=str(topout),sha256=sha(topout),rows=len(candidates)*4*20,slot=slot,
        candidate_count=len(candidates),fresh_independent_circuit_per_perturbation=True,independent_context_solves=len(candidates)*8))

if __name__=='__main__':
    import sys
    if sys.argv[1]=='scenarios':scenario_screen()
    elif sys.argv[1]=='sensitivity':sensitivity()
