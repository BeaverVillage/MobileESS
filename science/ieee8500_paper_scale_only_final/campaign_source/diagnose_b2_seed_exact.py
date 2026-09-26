"""Read-only 96-slot AC replay of the saved MESS01 opportunity seed."""
from bootstrap import *
from electrical_engine import Engine


def main():
    path=H/'B2/beam/2025-05-01/B2/B2/s1/B2-ROOT/SEEDS.json'
    seed=read(path)[0]['dispatch']
    route=seed['candidate']
    services=tuple(name[10:-1] for name in map(str,NAMES) if name.startswith('mess_p_kw['))
    with np.load(H/'MAY01_B0_AIDC_POWER.npz') as z: aidc=z['pcc'].copy()
    energy=np.asarray(seed['energy_kwh'],dtype=float)
    p=np.asarray(seed['p_discharge_kw'],dtype=float)-np.asarray(seed['p_charge_kw'],dtype=float)
    q=np.asarray(seed['q_kvar'],dtype=float)
    rows=[]
    engine=Engine(H/'B2_seed_exact_diagnostic/runtime')
    try:
        for slot in range(96):
            x=np.r_[aidc[slot],np.zeros(48)]
            service=(route['origin'] if slot<route['departure_slot'] else
                     route['destination'] if slot>=route['connection_ready_slot'] else None)
            if service is not None:
                i=services.index(service);x[12+i]=p[slot];x[36+i]=q[slot]
            engine.inputs(slot,x);engine.solve();v2,line,tx,winding=engine.arrays()
            rows.append(dict(slot=slot,rho=float(np.abs(line).max()),
                Vmin=float(np.sqrt(v2).min()),Vmax=float(np.sqrt(v2).max()),
                transformer_current=float(np.abs(tx).max()),
                transformer_kva=float((np.abs(winding)/np.asarray(AX['winding_rating_kVA'])).max()),
                settled=bool(engine.d.Solution.ControlActionsDone())))
    finally:engine.close()
    metrics=dict(rho=max(r['rho'] for r in rows),Vmin=min(r['Vmin'] for r in rows),
        Vmax=max(r['Vmax'] for r in rows),
        transformer_current=max(r['transformer_current'] for r in rows),
        transformer_kva=max(r['transformer_kva'] for r in rows))
    good=all(r['settled'] and r['Vmin']>=.95-1e-9 and r['Vmax']<=1.05+1e-9 and
        max(r['rho'],r['transformer_current'],r['transformer_kva'])<=1+1e-9 for r in rows)
    report=dict(status='PASS' if good else 'FAIL',candidate=route,metrics=metrics,
        max_abs_P=float(np.abs(p).max()),max_abs_Q=float(np.abs(q).max()),
        SOC_min_kWh=float(energy.min()),SOC_max_kWh=float(energy.max()),
        route_PQ_diagnostic_only=True,not_production=True,slots=rows)
    save(H/'B2_seed_exact_diagnostic/RESULT.json',report)
    print(report['status'],metrics,flush=True)


if __name__=='__main__':main()
