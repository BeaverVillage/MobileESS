"""Export frozen IEEE123 electrical totals; no Greensboro AC or optimizer.

The April runner is not called. Applied Actual setpoints must reproduce the
120 archived May01 per-slot setpoint digests. Stored D1 backgrounds, final dated
generation authority and its certificate are independently sealed.
"""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import numpy as np
from ac import ROOT,DOC,RUN,save,csvout
sys.path.insert(0,str(ROOT))


def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def record(p):
    p=Path(p)
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(path=str(p),bytes=p.stat().st_size,sha256=h)


def definitions_only(assets):
    import opendssdirect as dss
    e=dss.NewContext();e.Basic.AllowChangeDir(False)
    target=RUN/'input_readback';target.mkdir(exist_ok=True);e.Basic.DataPath(str(target))
    def emit(path):
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            s=line.strip()
            if not s or s.startswith(('!','//')):continue
            if re.match(r'(solve|calcvoltagebases|plot|export)\b',s,re.I):continue
            m=re.match(r'Redirect\s+([^!]+)',s,re.I)
            if m:
                name=m[1].strip().strip('"')
                p=path.parent/name
                if not p.exists():p=next(q for q in path.parent.iterdir() if q.name.lower()==name.lower())
                emit(p);continue
            e.Text.Command(s)
    for path in (assets.master,assets.pcc,assets.ratings,assets.phase_pv):emit(path)
    return e


def main():
    from v42_regcontrol.authority import source
    from v43_actual.observations import load_observations
    from v44.inputs import resolve_receipt
    from v43_actual.vendor.policy import digest
    m=source();native=read('D:/MobileESS_V42/runtime/v42_may_campaign/candidate_20261009_implementation01/inputs/B1/2025-05-01/NATIVE_INPUT.json')
    certpath=Path(resolve_receipt(native['electrical_certificate'])['path']);cert=read(certpath)
    inputs=cert['input_identity']['identity']['inputs']
    binding=inputs['V41R4_FINAL_DATE_BINDING']
    scaler_record=resolve_receipt(binding['scaler_source']);entry_record=resolve_receipt(binding['source'])
    basedir=certpath.parents[2]/'audit'
    scale_authority=basedir/'V41R3_BACKGROUND_SCALE_AUTHORITY.json'
    scale=read(scale_authority)['selected_alpha_BG']
    assert scale==binding['alpha_BG']==native['alpha_BG']
    # This is the sealed historical generation operator, not a study tuning knob.
    original=basedir/'2025-05-01/inputs/ORIGINAL_DAYAHEAD_BACKGROUND.npz'
    with np.load(original) as z:
        planP=z['gross_P_kw'].copy()*scale;planQ=z['gross_Q_kvar'].copy()*scale;planPV=z['PV_P_kw'].copy()
        planKeys=z['bus_phase_keys'].copy()
    csvout('IEEE123_PLANNING_BACKGROUND_96.csv',[
        dict(slot=t,P_background_kw=float(planP[t].sum()),Q_background_kvar=float(planQ[t].sum()),
             PV_kw=float(planPV[t].sum()),role='D1_FORECAST_FROZEN_ORIGINAL_ELECTRICAL_INPUT') for t in range(96)])
    begin=read(RUN/'jobs/REPLAY_RECEIPT.json')['begin'];end=begin+120*900
    observations=load_observations(begin=begin,end=end)
    rows=[observations.at(begin+t*900,observed_now=begin+t*900) for t in range(120)]
    backgrounds=[]
    for first in (0,96):
        page=rows[first:first+96];padded=page+[page[-1]]*(96-len(page))
        stamps=[datetime.fromtimestamp(begin+(first+t+1)*900,timezone(timedelta(hours=10))).isoformat() for t in range(96)]
        bg=m['bg'].build_authority_background_binding(timestamps_fixed_aest=stamps,
            demand_mw_96=[r['demand']['values']['demand_mw'] for r in padded],
            rooftop_pv_mw_96=[r['pv']['values']['pv_mw'] for r in padded],paths=m['paths'])
        backgrounds.append(replace(bg,gross_p_kw_96=tuple({k:scale*v for k,v in r.items()} for r in bg.gross_p_kw_96),
            gross_q_kvar_96=tuple({k:scale*v for k,v in r.items()} for r in bg.gross_q_kvar_96)))
    fresh=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/2025-05-01/B0/attempt001/ACTUAL/FRESH_SVR12_TIME_AC.json')
    fr=read(fresh);audit=read(fr['physical_audit']['path']);slotpath=audit['slots_receipt']['path'];archived=read(slotpath)
    e=definitions_only(m['assets']);adapter=read(m['assets'].runtime_adapter)
    allocation=m['NativeAllocation'].from_adapter(adapter)
    from dayahead.v28r2.opendss_mapping import _set_load,_set_generator
    z=np.load(RUN/'jobs/ACTUAL_PHYSICAL.npz');P=z['PCC_P_kw'];Q=z['PCC_Q_kvar']
    keys=sorted(set().union(*(set(r) for b in backgrounds for r in b.gross_p_kw_96)))
    results=[];ap=[];aq=[];av=[]
    for t in range(120):
        b=backgrounds[t//96];k=t%96;allocation.apply(e,b,k)
        for item in adapter['pv_generators']:
            loc=(str(item['bus']).lower(),'ABC'[int(item['phase'])-1])
            _set_generator(e,item['generator_name'],b.pv_generation_kw_96[k].get(loc,0),0)
        for j in range(12):_set_load(e,f'IDC_IDC{j+1:02d}',P[t,j],Q[t,j])
        for n in e.Generators.AllNames():
            if n.lower().startswith('mess_dis_'):_set_generator(e,n,0,0)
        for n in e.Loads.AllNames():
            if n.lower().startswith('mess_chg_'):_set_load(e,n,0,0)
        setpoints={}
        for kind,col in [('Load',e.Loads),('Generator',e.Generators)]:
            for n in col.AllNames():
                if n.lower()=='none':continue
                col.Name(n);setpoints[kind+'.'+n]=[float(col.kW()),float(col.kvar())]
        got=digest(setpoints);match=got==archived[t]['original_inputs_SHA']
        ap.append([b.gross_p_kw_96[k].get(key,0) for key in keys])
        aq.append([b.gross_q_kvar_96[k].get(key,0) for key in keys])
        av.append([b.pv_generation_kw_96[k].get(key,0) for key in keys])
        results.append(dict(execution_slot=t,evaluation_slot=t-24,
            interval_start_AEST=datetime.fromtimestamp(begin+t*900,timezone(timedelta(hours=10))).isoformat(),
            interval_end_AEST=datetime.fromtimestamp(begin+(t+1)*900,timezone(timedelta(hours=10))).isoformat(),
            P_background_kw=math.fsum(ap[-1]),Q_background_kvar=math.fsum(aq[-1]),PV_kw=math.fsum(av[-1]),
            AIDC_actual_kw=float(P[t].sum()),AIDC_actual_kvar=float(Q[t].sum()),
            archived_setpoint_sha=archived[t]['original_inputs_SHA'],reconstructed_setpoint_sha=got,
            exact_archived_setpoint_match=match))
    csvout('IEEE123_ACTUAL_BACKGROUND_120.csv',results)
    csvout('IEEE123_ACTUAL_BACKGROUND_96.csv',results[24:])
    np.savez_compressed(RUN/'IEEE123_FROZEN_BACKGROUND.npz',actual_P=np.array(ap),actual_Q=np.array(aq),
        actual_PV=np.array(av),actual_bus_phase_keys=np.array([b+'::'+p for b,p in keys]),
        planning_P=planP,planning_Q=planQ,planning_PV=planPV,planning_bus_phase_keys=planKeys)
    sources=[record(p) for p in [certpath,scale_authority,original,fresh,fr['physical_audit']['path'],slotpath]]
    sources+=[scaler_record,entry_record]
    save('IEEE123_INPUT_AUTHORITY_AUDIT.json',dict(status='VERIFIED_APPLIED_SETPOINTS' if all(r['exact_archived_setpoint_match'] for r in results) else 'NOT_VERIFIED_APPLIED_SETPOINTS',
        actual_archived_setpoint_matches=sum(r['exact_archived_setpoint_match'] for r in results),expected=120,
        Greensboro_AC_calls=0,IEEE123_AC_calls=0,definition_only_readback=True,
        original_2025_sources_only=True,April_runner_called=False,
        original_generation_alpha=scale,new_study_scaling_operations=0,
        alpha_provenance='dated May01 V41 electrical certificate and final generation authority, not April runner',
        inherited_transitive_legacy_import='v44.worker.actual -> SVR12CurrentAC -> svr11_ac.probe_body -> OriginalCurrentAC._probe imports April runner; traced, not used as authority',
        forecast_actual_roles_separate=True,planning_prefix='No separate D1 prefix array in frozen coefficient packet; NOT_VERIFIED',
        actual_prefix_slots=24,actual_evaluation_slots=96,
        source_receipts=sources,raw_2025_observations=observations.sources,
        maximum_actual_background_kw=max(r['P_background_kw'] for r in results[24:]),
        maximum_actual_background_kvar=max(r['Q_background_kvar'] for r in results[24:]),
        maximum_actual_PV_kw=max(r['PV_kw'] for r in results[24:])))
    print(json.dumps(read(DOC/'IEEE123_INPUT_AUTHORITY_AUDIT.json'),ensure_ascii=False,indent=2)[:2500])


if __name__=='__main__':main()
