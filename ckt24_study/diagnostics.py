"""Independent zero-input floor and small multiport AC probes."""
from .preflight import *
from .screening import settle,quick
from .traffic import readcsv

def null_check():
    inv=json.loads((DOC/'NETWORK_INVENTORY.json').read_text());rows=[]
    for trial,bus,kv in [(1,'05410',34.5),(2,'05410',34.5),(3,'subxfmr_lsb',34.5)]:
        e=context('null_'+str(trial));settle(e,67);base,_=quick(e,inv['lines'],inv['transformers'])
        e.Text.Command=f'new load.STUDY_NULL phases=3 bus1={bus}.1.2.3 kv={kv} kw=0 kvar=0 model=1 status=fixed vminpu=.5 vmaxpu=1.5'
        for _ in range(3):e.ActiveCircuit.Solution.SolveSnap()
        after,_=quick(e,inv['lines'],inv['transformers'])
        rows.append(dict(trial=trial,bus=bus,base_rho=base['rho_max'],null_rho=after['rho_max'],delta_rho=after['rho_max']-base['rho_max']))
        e.ClearAll()
    save('AC_NULL_PERTURBATION_CHECK.json',dict(trials=rows,max_abs_observed_null_delta=max(abs(r['delta_rho']) for r in rows),
        scope='Empirical numerical floor, not a rigorous error bound',
        original_conditioning='Other_Feeders uses original R1=1e-8 and X1=1e-9 ohm; no impedance changes allowed',
        weak_response_warning='Compare P/Q finite differences against this floor; do not certify weak near-zero responses'))

def multiport():
    p=DOC/'CKT24_SERVICE_SITE_MAPPING.csv'
    if not p.exists():
        save('INSTANTANEOUS_MULTIPORT_STATUS.json',dict(status='NOT_RUN_NO_24_SITE_WITNESS'));return
    inv=json.loads((DOC/'NETWORK_INVENTORY.json').read_text());sites=[r for r in readcsv(p) if r['type']=='STATION' and r['ckt24_bus']]
    if len(sites)<8:
        save('INSTANTANEOUS_MULTIPORT_STATUS.json',dict(status='NOT_RUN_NEEDS_8_MAPPED_STATION_PORTS'));return
    sites=sites[:8]  # deterministic diagnostic roster, never an initial placement freeze
    trials=[('OFF',[])]
    for r in sites:trials.extend([(r['service_id']+'_P',[(r,30,0)]),(r['service_id']+'_Q',[(r,0,25)])])
    trials.extend([('ALL8_P',[(r,30,0) for r in sites]),('ALL8_Q',[(r,0,25) for r in sites]),
                   ('ALL8_PQ',[(r,30,25) for r in sites])])
    rows=[]
    for name,perturbations in trials:
        e=context('multiport');settle(e,67)
        for i,(r,pp,qq) in enumerate(perturbations):
            if not (abs(pp)<=300 and abs(qq)<=250 and np.hypot(pp,qq)<=400):raise ValueError('PROBE_RATING')
            e.Text.Command=f'new load.PROBE_{i} phases=3 bus1={r["ckt24_bus"]}.1.2.3 kv={r["voltage_base_ll_kv"]} kw={-pp} kvar={-qq} model=1 status=fixed vminpu=.5 vmaxpu=1.5'
        for _ in range(3):e.ActiveCircuit.Solution.SolveSnap()
        m,_=quick(e,inv['lines'],inv['transformers'])
        rows.append(dict(trial=name,slot=67,**m,virtual_port_count=len(perturbations),
            p_total_kw=sum(p for _,p,_ in perturbations),q_total_kvar=sum(q for _,_,q in perturbations),
            SOC_route_job_or_PCC_capacity_certified=False))
        e.ClearAll()
    base=rows[0]['rho_max']
    for r in rows:r['delta_rho']=r['rho_max']-base
    csvout('INSTANTANEOUS_8PORT_AC.csv',rows)
    save('INSTANTANEOUS_MULTIPORT_STATUS.json',dict(status='ELECTRICAL_DIAGNOSTIC_ONLY',
        ports=[r['service_id'] for r in sites],initial_placement_frozen=False,physical_8_vehicle_control_certified=False,
        sum_of_individual_effects_not_used_as_joint_effect=True,AIDC_job_joint_witness=False))

if __name__=='__main__':
    import sys
    null_check() if sys.argv[1]=='null' else multiport()
