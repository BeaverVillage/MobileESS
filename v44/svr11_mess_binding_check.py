"""Compiled SVR11 readback of the unchanged four-MESS signed IO mapper."""
from pathlib import Path
import numpy as np
from .common import RUNTIME,DOC,read,record,atomic,verify,now
from .config import axis
from .locks import coordinator
from .svr11_hardware import HARDWARE,scope,compile_context

OUT=RUNTIME/'svr11_revision01/MESS_SIGN_BINDING_NATIVE0_002'


def run():
    from .svr11_ac import SVR11CurrentAC
    from v42_may_campaign_native90.preflight import native_zero
    if OUT.exists():raise FileExistsError('NEW_MESS_BINDING_TEST_ROOT_REQUIRED')
    OUT.mkdir(parents=True);a=axis('2025-05-01')
    values=dict(MESS01=('STA01',1.,1.),MESS02=('STA12',-1.,-1.),
        MESS03=('STA08',0.,.5),MESS04=('STA06',0.,0.))
    plan=dict(connection_site={u:[s]*96 for u,(s,p,q) in values.items()},
        P_kW={u:[p]+[0.]*95 for u,(s,p,q) in values.items()},
        Q_kvar={u:[q]+[0.]*95 for u,(s,p,q) in values.items()})
    frozen=[record(Path(__file__)),record(Path(__file__).with_name('svr11_ac.py')),record(HARDWARE/'HARDWARE.json')]
    with coordinator(OUT/'LEASE'),native_zero() as denied,scope():
        from v42_regcontrol import authority
        from v42_svr11.context_lifecycle import retire_completed_probe,flush_completed_probes
        authority.source()
        from dayahead.v28r2.opendss_mapping import _set_generator,_set_load
        e,*_=compile_context('ACTUAL','2025-05-01')
        try:
            for name in e.Generators.AllNames():
                if name.lower().startswith('mess_dis_'):_set_generator(e,name,0.,0.)
            for name in e.Loads.AllNames():
                if name.lower().startswith('mess_chg_'):_set_load(e,name,0.,0.)
            oracle=SVR11CurrentAC(arm='B3',mess_plan=plan,day_start_seconds=a['day_start_seconds'],
                issue_seconds=a['issue_seconds'],sites=(),power_model=None,observations=None)
            def measured():
                rows=[]
                for unit,(site,p,q) in values.items():
                    e.Generators.Name('MESS_DIS_'+site);gp=float(e.Generators.kW());gq=float(e.Generators.kvar())
                    e.Loads.Name('MESS_CHG_'+site);lp=float(e.Loads.kW());lq=float(e.Loads.kvar())
                    rows.append(dict(unit=unit,site=site,generator_P_kW=gp,generator_Q_kvar=gq,
                        charging_P_kW=lp,charging_Q_kvar=lq,net_grid_injection_P_kW=gp-lp,net_grid_injection_Q_kvar=gq-lq,
                        expected_P=p,expected_Q=q,PASS=gp-lp==p and gq-lq==q))
                return rows
            oracle._apply_frozen_mess(e,dict(start_seconds=a['issue_seconds']))
            prefix=measured();prefix_zero=all(r['net_grid_injection_P_kW']==r['net_grid_injection_Q_kvar']==0. for r in prefix)
            oracle._apply_frozen_mess(e,dict(start_seconds=a['day_start_seconds']))
            rows=measured();inventory=authority.source()['inventory'](e)
            passed=prefix_zero and all(r['PASS'] for r in rows) and inventory['RegControl_count']==40 and not denied
            result=dict(PASS=passed,UTC=now(),rows=rows,prefix_dispatch_zero=prefix_zero,
                exact_original_mapper=oracle.mapping_source,sources=frozen,hardware=record(HARDWARE/'HARDWARE.json'),
                fixture='SYNTHETIC_ONE_SLOT_SIGN_AND_SITE_READBACK_NOT_A_PLANNING_DECISION',
                existing_device_only=True,new_Q_devices=0,physical_solve_calls=0,Native_optimizer_calls=0,
                Actual96_runs=0,Fresh96_runs=0,old_MESS_plans_modified=False)
            atomic(OUT/'RESULT.json',result);verify(frozen)
        finally:retire_completed_probe(e)
        del e;flush_completed_probes()
    if not passed:raise ValueError('SVR11_ORIGINAL_MESS_SIGN_OR_SITE_BINDING_FAILED')
    report=read(DOC/'V44_PHYSICAL_DRIVER_CERTIFICATION.json');report['MESS_sign_and_site_readback']=record(OUT/'RESULT.json')
    atomic(DOC/'V44_PHYSICAL_DRIVER_CERTIFICATION.json',report)
    print(dict(PASS=passed,vehicles=4,prefix_dispatch_zero=prefix_zero,physical_solve_calls=0),flush=True)


if __name__=='__main__':run()
