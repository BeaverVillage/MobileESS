"""Independent full native/AIDC/MESS element readback and component accounting."""
from contextlib import contextmanager
from collections import defaultdict
import math
import pandas as pd
from dayahead.paper_analysis.storage import write_json,write_parquet
from dayahead.v40e.mapping import NativeAllocation,TOLERANCE


@contextmanager
def observe(output,case,namespace):
    from dayahead.v28r2 import opendss_backend as backend
    from dayahead.v40d_actual.power_scale_audit import engine_inventory
    old=backend.apply_trajectory_slot;oldv=backend._voltage_vector;rows=[];summary=[];result={}
    def applied(odd,adapter,context,trajectory,slot):
        old(odd,adapter,context,trajectory,slot)
        background=context.legacy_context[2];native,_,_=NativeAllocation.from_adapter(adapter).allocate(background.gross_p_kw_96[slot],background.gross_q_kvar_96[slot])
        pv={r['generator_name'].lower():background.pv_generation_kw_96[slot].get((r['bus'].lower(),'ABC'[r['phase']-1]),0.) for r in adapter['pv_generators']}
        sums=defaultdict(lambda:[[],[]]);active=odd.CktElement.Name();services=defaultdict(lambda:[0.,0.])
        for k,loc in enumerate(trajectory.mess_locations_96x4[slot]):
            if str(loc).upper().startswith('TRANSIT_'):
                assert trajectory.mess_p_kw[slot,k]==0 and trajectory.mess_q_kvar[slot,k]==0;continue
            services[str(loc).lower()][0]+=float(trajectory.mess_p_kw[slot,k]);services[str(loc).lower()][1]+=float(trajectory.mess_q_kvar[slot,k])
        try:
            for kind,api in [('load',odd.Loads),('generator',odd.Generators)]:
                for name in sorted(api.AllNames()):
                    api.Name(name);n=name.lower();p=float(api.kW());q=float(api.kvar());sign=1 if kind=='load' else -1
                    if n in native:component='background';ep,eq=native[n]
                    elif n in pv:component='PV';ep,eq=pv[n],0.
                    elif n.startswith('idc_idc'):
                        component='AIDC';idx=int(n[-2:])-1;ep,eq=trajectory.pcc_p_kw[slot,idx],trajectory.pcc_q_kvar[slot,idx]
                    elif n.startswith('mess_'):
                        component='MESS';mp,mq=services[n.split('_',2)[2]];ep,eq=(max(-mp,0),0) if kind=='load' else (max(mp,0),mq)
                    else:raise RuntimeError('UNCLASSIFIED_ENGINE_ELEMENT:'+n)
                    error=max(abs(p-ep),abs(q-eq));assert error<=TOLERANCE
                    sums[component][0].append((sign if component=='MESS' else 1)*p)
                    sums[component][1].append((sign if component=='MESS' else 1)*q)
                    rows.append({'slot':slot,'case':case,'namespace':namespace,'component':component,'element':kind+'.'+n,
                        'P_kw':p,'Q_kvar':q,'expected_P_kw':float(ep),'expected_Q_kvar':float(eq),'setpoint_error':error,
                        'net_sign':sign,'AIDC_site_id':'AIDC'+n[-2:] if component=='AIDC' else None,
                        'OpenDSS_bus':str(odd.CktElement.BusNames()[0])})
            totals={k:[math.fsum(x) for x in v] for k,v in sums.items()}
            expectedP=math.fsum(background.gross_p_kw_96[slot].values());expectedQ=math.fsum(background.gross_q_kvar_96[slot].values())
            assert abs(totals['background'][0]-expectedP)<TOLERANCE and abs(totals['background'][1]-expectedQ)<TOLERANCE
            summary.append({'slot':slot,'case':case,'namespace':namespace,
                **{f'{k}_{field}':v[i] for k,v in totals.items() for i,field in enumerate(['P_kw','Q_kvar'])},
                'intended_background_P_kw':expectedP,'intended_background_Q_kvar':expectedQ,
                'P_net_kw':totals['background'][0]-totals['PV'][0]+totals['AIDC'][0]+totals['MESS'][0],
                'Q_net_kvar':totals['background'][1]+totals['AIDC'][1]+totals['MESS'][1]})
        finally:odd.Circuit.SetActiveElement(active)
    def voltage(odd,nodes):
        values=oldv(odd,nodes)
        if 'inventory' not in result:
            active=odd.CktElement.Name()
            try:result['inventory']=engine_inventory(odd)
            finally:odd.Circuit.SetActiveElement(active)
        return values
    backend.apply_trajectory_slot=applied;backend._voltage_vector=voltage
    try:
        yield result
        assert len(summary)==96
        write_parquet(output/'OPENDSS_COMPONENT_ELEMENTS.parquet',pd.DataFrame(rows))
        f=pd.DataFrame(summary);write_parquet(output/'OPENDSS_COMPONENTS_96.parquet',f)
        f.to_csv(output/'OPENDSS_COMPONENTS_96.csv',index=False,float_format='%.17g')
        write_json(output/'ENGINE_MAPPING_RATINGS_SOURCE.json',result['inventory'])
        result['max_setpoint_error']=max(r['setpoint_error'] for r in rows)
        result['AIDC_positive_all_slots']=all(r['AIDC_P_kw']>0 for r in summary)
    finally:backend.apply_trajectory_slot=old;backend._voltage_vector=oldv
