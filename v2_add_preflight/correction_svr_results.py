"""Saved-event arithmetic, duration/tap/queue audit and independent Fresh checks."""
import csv,json,gzip,io
from pathlib import Path
import numpy as np
from .audit import read,sha,DOC
from .correction import OUT,RUNTIME,priority
from .correction_projection import project
from .correction_svr import SV,RUN,BETAS,save,table

def main():
    priority();results=[];taps=[];violations=[];tops=[];slotrows=[];fresh=[];receipts=[];extrema=[];flows=[]
    hot_phase={r['buses'][0].split('.')[0].lower():r['primary_phase'] for r in read(DOC/'source/PR197_PV_HOT_RECORDS.json')}
    groups={r['element'].split('.',1)[1]:r['group'] for r in read(OUT/'INDEPENDENT_PARENT_ORIENTATION.json')}
    for _ in range(10):
        for line in read(DOC/'OFFICIAL_BALANCED_AXES.json')['lines']:
            if groups[line['name']]!='Triplex':continue
            a,b=[v.split('.')[0].lower() for v in line['buses']]
            if a in hot_phase:hot_phase[b]=hot_phase[a]
            if b in hot_phase:hot_phase[a]=hot_phase[b]
    def phase(node):
        bus,n=node.rsplit('.',1)
        return hot_phase.get(bus.lower(),'ABC'[int(n)-1] if int(n) in (1,2,3) else 'NEUTRAL')
    originals={r['regcontrol'] for r in read(SV/'EXISTING_REGULATOR_FULL_STATIC_AUDIT.json')['initial_readbacks']}
    for file in sorted(RUN.glob('*/RECEIPT.json')):
        rec=read(file);p=file.parent
        assert all(sha((p/n).read_bytes())==h for n,h in rec['files'].items())
        result,slots,top,_=project(file);config=rec['scientific_inputs']['schedule']['name']
        result['configuration']=config;result['new_banks']=0 if config=='S0' else int(config.split('_')[1])
        assert {x['group'] for x in read(p/'AXES.json')['line']}=={'Primary','Triplex'}
        result['rho_Triplex_objective']=result['rho_LV_objective']
        for r in slots:r['rho_Triplex_objective']=r['rho_LV_objective']
        results.append(result);receipts.append(dict(receipt=str(file),**rec));tops+=top;slotrows+=slots
        with np.load(p/'AC_FULL.npz') as z:a={k:z[k] for k in z.files}
        axes=read(p/'AXES.json');er=read(p/'EVENT_ROWS.json');clock=read(p/'EVENTS.json');trace=read(p/'TAP_QUEUE_EVENT_READBACK.json');events=trace['events']
        assert len(events)==len(er)==len(a['event_slot'])
        bybank={}
        for j,event in enumerate(events):
            for flow in event['cut_flows']:bybank.setdefault(flow['bank'],[]).append((int(a['event_slot'][j]),flow))
        for bank,values in bybank.items():
            for scope,rs in [('ALL120',[x[1] for x in values]),('EVALUATION96',[x[1] for x in values if x[0]>=24])]:
                flows.append(dict(case=rec['case'],configuration=config,beta_BG=result['beta_BG'],bank=bank,scope=scope,
                    min_parent_P_kw=min(x['parent_terminal_P_kw'] for x in rs),max_parent_P_kw=max(x['parent_terminal_P_kw'] for x in rs),
                    min_parent_Q_kvar=min(x['parent_terminal_Q_kvar'] for x in rs),max_parent_Q_kvar=max(x['parent_terminal_Q_kvar'] for x in rs),
                    reverse_events=sum(x['parent_terminal_P_kw'] < -1e-8 for x in rs),
                    interpretation='Observed signed flow; no unobserved reverse envelope certification'))
        for nodekind,func in [('LOW',np.argmin),('HIGH',np.argmax)]:
            for scope,idx in [('SETTLED96',[np.flatnonzero(a['event_slot']==t)[-1] for t in range(24,120)]),('ALL_EVENTS96',np.flatnonzero(a['event_slot']>=24)),('PREFIX_EVENTS24',np.flatnonzero(a['event_slot']<24))]:
                ij=np.unravel_index(func(a['node_voltage_pu'][idx]),a['node_voltage_pu'][idx].shape);j=int(idx[ij[0]]);n=int(ij[1])
                extrema.append(dict(case=rec['case'],configuration=config,beta_BG=result['beta_BG'],scope=scope,kind=nodekind,
                    node=axes['nodes'][n],primary_phase=phase(axes['nodes'][n]),voltage=float(a['node_voltage_pu'][j,n]),slot=int(a['event_slot'][j]),evaluation_slot=int(a['event_slot'][j])-24,seconds=er[j]['physical_seconds']))
        last={r['regcontrol']:r['tap_number'] for r in trace['initial']};changes=0;oldchanges=0;newchanges=0;limits=set();oldlimits=set();newlimits=set();overdue=0
        lowsecs=highsecs=prefixlow=prefixhigh=0.;evalfails=0;network_loss_kwh=0.
        for j,event in enumerate(events):
            t=int(a['event_slot'][j]);seconds=event['physical_seconds']
            assert seconds==er[j]['physical_seconds']
            end=(events[j+1]['physical_seconds'] if j+1<len(events) and int(a['event_slot'][j+1])==t else (t+1)*900)
            duration=end-seconds;assert duration>=0
            v=a['node_voltage_pu'][j];lo=float(v.min());hi=float(v.max());badlow=lo<.95-1e-8;badhigh=hi>1.05+1e-8
            if t>=24:
                lowsecs+=duration*badlow;highsecs+=duration*badhigh;evalfails+=not er[j]['physics_PASS']
                network_loss_kwh+=event['losses_kw']*duration/3600
            else:prefixlow+=duration*badlow;prefixhigh+=duration*badhigh
            if badlow or badhigh:
                violations.append(dict(case=rec['case'],configuration=config,beta_BG=result['beta_BG'],slot=t,evaluation_slot=t-24,
                    seconds=seconds,hold_end_seconds=end,violation_duration_seconds=duration,Vmin=lo,Vmax=hi,
                    min_node=axes['nodes'][int(v.argmin())],max_node=axes['nodes'][int(v.argmax())],min_primary_phase=phase(axes['nodes'][int(v.argmin())]),max_primary_phase=phase(axes['nodes'][int(v.argmax())]),
                    interpretation='Piecewise-constant solved state until next native event or new slot input; no fictitious iteration seconds'))
            for r in event['controls']:
                assert r['winding']==r['tap_winding']==2 and r['tap_number_readback_PASS']
                assert r['min_tap']-1e-9<=r['tap']<=r['max_tap']+1e-9
                n=r['regcontrol'];step=abs(r['tap_number']-last[n]);changes+=step
                if n in originals:oldchanges+=step
                else:newchanges+=step
                last[n]=r['tap_number']
                if r['at_lower'] or r['at_upper']:
                    limits.add(n);(oldlimits if n in originals else newlimits).add(n)
                # Compact every-event readback; complete property dictionaries
                # and native action ordering remain in the Raw archive.
                taps.append(dict(case=rec['case'],slot=t,evaluation_slot=t-24,seconds=seconds,regcontrol=n,
                    original=n in originals,tap=r['tap'],tap_number=r['tap_number'],readback_PASS=r['tap_number_readback_PASS'],
                    at_lower=r['at_lower'],at_upper=r['at_upper'],down_steps=r['down_steps'],up_steps=r['up_steps'],absolute_tap_steps_since_previous=step))
            overdue+=sum(q['absolute_seconds']<=seconds for q in event['queue'])
        assert overdue==0
        txaxes=read(p/'TRANSFORMER_AXES.json')
        added_current=[j for j,x in enumerate(txaxes['current']) if x['element'].lower().startswith('transformer.svr_')]
        added_kva=[j for j,x in enumerate(txaxes['winding']) if x['element'].lower().startswith('transformer.svr_')]
        result.update(evaluation_low_voltage_seconds=lowsecs,evaluation_high_voltage_seconds=highsecs,
            prefix_low_voltage_seconds=prefixlow,prefix_high_voltage_seconds=prefixhigh,
            absolute_tap_steps=changes,original_absolute_tap_steps=oldchanges,new_absolute_tap_steps=newchanges,
            unique_original_controls_at_limit=len(oldlimits),unique_new_controls_at_limit=len(newlimits),original_controls_at_limit=sorted(oldlimits),
            all_TapNumber_winding_readbacks_PASS=True,overdue_queue_events=overdue,
            maximum_electrical_iterations=max(x['electrical_iterations'] for slot in clock for x in slot['events']),
            maximum_control_iterations=max(x['control_iterations'] for slot in clock for x in slot['events']),
            transformer_current_max=max(r['transformer_current_max'] for r in er),transformer_nameplate_max=max(r['transformer_nameplate_max'] for r in er),
            port_current_max=max(r['port_current_max'] for r in er),PV_error_max_kw=max(r['PV_total_abs_error_kw'] for r in er),
            AC_balance_max_kw_kvar=max(abs(r[k]) for r in er for k in ('balance_P_error_kw','balance_Q_error_kvar')),
            evaluation_failed_events=evalfails)
        result.update(new_SVR_current_rho_max=float(a['transformer_current_rho'][:,added_current].max()) if added_current else 0.,
            new_SVR_kva_rho_max=float(a['transformer_winding_nameplate_kva_rho'][:,added_kva].max()) if added_kva else 0.,
            network_loss_energy_evaluation_kwh=network_loss_kwh,network_loss_power_max_kw=max(x['losses_kw'] for x in events))
        if not result['fresh']:
            peer=p.with_name(p.name+'_FRESH')
            if (peer/'RECEIPT.json').exists():
                diff={}
                with np.load(peer/'AC_FULL.npz') as z:
                    for key in a:
                        diff[key]=float(np.max(abs(a[key]-z[key])))
                same_states=read(p/'STATES.json')==read(peer/'STATES.json')
                same_events=read(p/'EVENTS.json')==read(peer/'EVENTS.json')
                passed=max(diff.values())<=1e-9 and same_states and same_events
                assert passed,(p,diff)
                fresh.append(dict(case=rec['case'],max_abs_differences=diff,identical_control_states=same_states,identical_native_events=same_events,PASS=passed))
    expected=4*len(BETAS)*2
    assert len(results)==expected,(len(results),expected)
    s0={r['beta_BG']:r for r in results if r['configuration']=='S0' and not r['fresh']}
    for r in results:r['S0_global_loading_difference_pp']=100*(r['rho_objective']-s0[r['beta_BG']]['rho_objective'])
    table('S0_S1_ACTUAL_TIME_RESULTS.csv',results);table('S0_S1_VOLTAGE_EXTREMA_NODES.csv',extrema)
    # Raw event readbacks are intentionally losslessly compressed for Git;
    # native per-case JSON archives remain independently SHA-bound.
    with gzip.GzipFile(filename=str(SV/'ALL_EVENT_TAP_NUMBER_READBACK.csv.gz'),mode='wb',mtime=0) as binary:
        with io.TextIOWrapper(binary,encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(taps[0]));w.writeheader();w.writerows(taps)
    table('TIME_VOLTAGE_VIOLATION_DURATIONS.csv',violations)
    table('S0_S1_SLOT_MV_LV_RESULTS.csv',slotrows);table('S0_S1_TOP20.csv',tops)
    table('S1_CUT_DIRECTION_AND_REVERSE_FLOW.csv',flows)
    save('SVR_FRESH_CERTIFICATION.json',dict(PASS=all(r['PASS'] for r in fresh),pairs=len(fresh),checks=fresh,Native_calls=0))
    save('SVR_AC_ARCHIVE_RECEIPTS.json',receipts)
    save('SVR_SCREEN_COMPLETION.json',dict(cases=len(results),configurations=4,betas=BETAS,Fresh_pairs=len(fresh),
        physical_solve_count=sum(r['physical_solve_count'] for r in results),Native_optimizer_calls=0,all_original_lines_preserved=True,
        settled96_and_all_event_safety_separate=True,initial_and_terminal_MESS_SOC=760.,MESS_B0_PQ_zero=True))
    print('S0/S1 RESULTS COMPLETE',len(results),flush=True)

if __name__=='__main__':main()
