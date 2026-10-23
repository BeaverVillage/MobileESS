"""Separately registered first4-morning/extra4-evening physical witness."""
from pathlib import Path
import csv
import numpy as np
from .prestart import OUT,RUN,RUNTIME,INITIAL,read,put,table,record,resources

def main():
    from . import correction as c,correction_svr_run as runner
    from .correction_svr_implicit import source_svr
    from .correction_projection import project
    name='PRESTART_ORIGINAL4_MORNING_EXTRA4_EVENING'
    path=OUT/'SPLIT_FLEET_PREREGISTRATION.json'
    reg=dict(name=name,beta=2.,configuration='S1_03',initial=INITIAL,
        groups={'original4':list(INITIAL)[:4],'extra4':list(INITIAL)[4:]},
        discharge_original4=list(range(27,35)),discharge_extra4=list(range(68,76)),
        charge=list(range(8,16)),each_vehicle_cycle_SOC_kWh=320,Q_support=0,
        rule='Original vs additional4, fixed before this case AC; not selected by Actual/B3 or PCC response rankings',
        purpose='Can separate groups control both peaks with same8car energy?',witness_only=True,Native_calls=0)
    if path.exists():assert read(path)==reg
    else:put(path.name,reg)
    resources();runner.source_svr=source_svr;runner.RUN=RUN/'two_peak';runner.install('S1_03')
    def trajectory(s):
        p=np.zeros((96,8));q=p.copy();soc=np.full((97,8),760.)
        p[8:16]=320/.95/2
        p[27:35,:4]=-320*.95/2;p[68:76,4:]=-320*.95/2
        for t in range(96):soc[t+1]=soc[t]+.25*(.95*np.maximum(p[t],0)-np.maximum(-p[t],0)/.95)
        assert soc.min()>=440 and soc.max()<=1080+1e-8 and np.max(abs(soc[-1]-760))<1e-8
        return p,q,soc
    c.trajectory=trajectory;original=c.fingerprint
    c.fingerprint=lambda:dict(original(),prestart_split_code=record(Path(__file__)),preregistration=record(path))
    _,r=c.run_case(2.,'ACTUAL',schedule=dict(name=name));_,fr=c.run_case(2.,'ACTUAL',schedule=dict(name=name),fresh=True)
    check=c.fresh_check(r,fr);assert check['PASS']
    base,_,_,_=project(RUNTIME/'correction_svr/TIME_2.00_ACTUAL_S1_03/RECEIPT.json')
    s,slots,_,_=project(Path(r['archive_path']).parent/'RECEIPT.json');p,q,soc=trajectory(None)
    s.update(schedule=name,baseline_rho=base['rho_objective'],improvement_pp=100*(base['rho_objective']-s['rho_objective']),
        certified_B3_result=False,optimizer_calls=0,initial_final_SOC=760,charge_kWh=float(np.maximum(p,0).sum()*.25),discharge_kWh=float(np.maximum(-p,0).sum()*.25))
    def append_csv(file,new):
        old=list(csv.DictReader((OUT/file).open(encoding='utf-8')))
        old=[x for x in old if x.get('schedule')!=name];table(file,old+new)
    append_csv('TWO_PEAK_CONTROLLABILITY_ANALYSIS.csv',[s])
    append_csv('TWO_PEAK_SLOT_RESULTS.csv',[dict(schedule=name,**x) for x in slots[24:]])
    units=[]
    for u,(vehicle,site) in enumerate(INITIAL.items()):
        for t in range(96):units.append(dict(schedule=name,vehicle=vehicle,site=site,slot=t,P_demand_kw=float(p[t,u]),Q_demand_kvar=0.,SOC_start=float(soc[t,u]),SOC_end=float(soc[t+1,u]),route='ORIGINAL_STAY',travel_energy_kWh=0))
    append_csv('TWO_PEAK_UNIT_TRAJECTORIES.csv',units)
    checks=[x for x in read(OUT/'TWO_PEAK_FRESH_CHECKS.json') if x['case']!=check['case']]
    put('TWO_PEAK_FRESH_CHECKS.json',checks+[check])

if __name__=='__main__':main()
