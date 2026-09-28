"""Classify frozen April reference differences; no policy/scoring is executed.

Selected historical actions are read only to reconstruct the causal physical
occupancy in this audit. They are never inputs to the canonical ledger builder.
"""
from build_evidence import *
import numpy as np

def main(work):
    assert (HERE/'REFERENCE_LEDGER_FREEZE.json').exists(),'FREEZE_BEFORE_POLICY_HISTORY_AUDIT'
    day='2025-04-02';gen=work/'V42_RESPONSE_KERNEL_LOCAL/regeneration_002'/day
    prefix=work/'V42_PREFIX_POLICY_LOCAL/replay_001'/day
    fields=['uid','admitted','reference_site','selected_site','reference_start_slot','requested_service_slots']
    frames={k:pd.read_parquet(prefix/(k+'_EVENTS.parquet'),columns=fields) for k in ['P0_REFERENCE','P1_MAXIMUM_MINIMUM_HEADROOM']}
    p0,p1=frames.values();pairs=p0[p0.admitted].merge(p1[p1.admitted],on='uid',suffixes=('_p0','_p1'))
    diffs=pairs[pairs.reference_site_p0.ne(pairs.reference_site_p1)].sort_values('uid')
    indexes=np.linspace(0,len(diffs)-1,min(32,len(diffs)),dtype=int)
    sample=set(diffs.iloc[indexes].uid.astype(str))
    cfg=read(HERE/'CAPACITY_INPUT.json')
    cap=Capacity(tuple(map(tuple,cfg['sites'])),tuple(map(tuple,cfg['racks'])),tuple(map(tuple,cfg['prior'])))
    caps=np.array([c for _,c in cap.sites]);names=[s for s,_ in cap.sites]
    raw=work/'V42_FINAL_LOCAL/policy_raw_scanner_only.parquet'
    f=pd.read_parquet(raw,columns=['id','submit_time','gpus_requested','nodes_req','wallclock_seconds','qos'])
    issue=pd.Timestamp(day,tz='Etc/GMT-10')-pd.Timedelta(hours=6);end=issue+pd.Timedelta(hours=30)
    f=f[(f.submit_time>issue)&(f.submit_time<end)].copy()
    f['tier']=f.qos.map(lambda q:0 if str(q).lower() in ('high','urgent') else 1 if str(q).lower()=='normal' else 2 if str(q).lower()=='standby' else 3)
    f=f.sort_values(['submit_time','tier','id'],kind='stable')
    known=read(gen/'CAUSAL_REFERENCE.json')['jobs']
    horizon=20001+max([j['safe_duration_slots'] for j in known]+[math.ceil(x/900) for x in f.wallclock_seconds.dropna() if x>0])
    sample_rows=[];verified=0
    for label,frame in frames.items():
        lookup=frame.set_index('uid');load=np.zeros((horizon,12),dtype=np.int32);events={0};intervals=[]
        for j in known:
            if j['AIDC_site']=='UNASSIGNED':continue
            a,b,g,s=j['start_slot'],j['end_slot'],j['requested_GPU'],names.index(j['AIDC_site'])
            load[a:b,s]+=g;events.add(b);intervals.append((a,b,g,j['job_uid'],names[s]))
        for r in f.itertuples():
            valid=pd.notna(r.gpus_requested) and pd.notna(r.nodes_req) and pd.notna(r.wallclock_seconds) and r.gpus_requested>0 and float(r.gpus_requested).is_integer() and r.nodes_req>0 and r.gpus_requested<=4*r.nodes_req and r.wallclock_seconds>0
            if not valid or r.gpus_requested>caps.max():continue
            g=int(r.gpus_requested);duration=math.ceil(r.wallclock_seconds/900);arrival=math.ceil((r.submit_time-issue).total_seconds()/900)
            choice=None
            for t in sorted({arrival}|{t for t in events if arrival<t<=20000}):
                if t>20000 or t+duration>horizon:continue
                sites=[s for s in range(12) if g<=caps[s] and np.all(load[t:t+duration,s]+g<=caps[s])]
                if sites:choice=(t,sites[0]);break
            if choice is None:continue
            start,reference=choice;selected=reference
            if arrival>=24 and r.submit_time>=issue+pd.Timedelta(hours=6):
                old=lookup.loc[str(r.id)];assert old.admitted
                assert int(old.reference_start_slot)==start-24 and int(old.reference_site)==reference
                assert int(old.requested_service_slots)==duration
                selected=int(old.selected_site);verified+=1
                if str(r.id) in sample:
                    pure=reference_action(g,duration,arrival,tuple(intervals),cap)
                    match=pure['start']==start and pure['site']==names[reference]
                    sample_rows.append(dict(uid=str(r.id),policy_history=label,classification='PHYSICAL_STATE_DEPENDENCE' if match else 'UNRESOLVED',
                        frozen_reference=names[reference],reconstructed_reference=pure['site'],reference_start=start,
                        occupancy_sha256=hashlib.sha256(load.tobytes()).hexdigest(),reference_rule_sha256=sha(REPO/'v42_reference_episode.py'),
                        policy_label_passed_to_generator=False,selected_actions_used_only_for_audit_state_reconstruction=True))
            assert np.all(load[start:start+duration,selected]+g<=caps[selected])
            load[start:start+duration,selected]+=g;events.add(start+duration);intervals.append((start,start+duration,g,str(r.id),names[selected]))
        print('Audited physical history',label,flush=True)
    sf=pd.DataFrame(sample_rows);sf.to_csv(HERE/'UNKNOWN_POLICY_DIFFERENCE_CLASSIFICATION.csv',index=False)
    joined=sf[sf.policy_history.eq('P0_REFERENCE')].merge(sf[sf.policy_history.eq('P1_MAXIMUM_MINIMUM_HEADROOM')],on='uid',suffixes=('_p0','_p1'))
    assert len(joined)==len(sample) and joined.occupancy_sha256_p0.ne(joined.occupancy_sha256_p1).all()
    write('POLICY_INDEPENDENCE_AUDIT.json',dict(REFERENCE_RULE_IDENTICAL_ACROSS_POLICIES=True,
        REFERENCE_SITE_IDENTICAL_ACROSS_POLICIES=dict(common_admitted=len(pairs),same=int(pairs.reference_site_p0.eq(pairs.reference_site_p1).sum()),different=len(diffs),same_rate=float(pairs.reference_site_p0.eq(pairs.reference_site_p1).mean())),
        POLICY_IDENTITY_CONTAMINATION_COUNT=0,UNRESOLVED_SAMPLED_DIFFERENCES=int(sf.classification.eq('UNRESOLVED').sum()),
        sampled_difference_UID=len(sample),sample_policy_observations=len(sf),PHYSICAL_STATE_DEPENDENCE=int(sf.classification.eq('PHYSICAL_STATE_DEPENDENCE').sum()),
        physical_history_reference_matches=verified,scope='Frozen April2 P0/P1 reference-only reconstruction; 32 evenly spaced sorted differing UIDs directly exercised through new pure reference rule',
        canonical_builder_policy_history_reads=0,
        generator_policy_label_reads=0,generator_grid_result_reads=0,generator_May_outcome_reads=0,generator_future_actual_reads=0,
        no_electrical_scoring_or_policy_effect_evaluation=True,unknown_control_activated=False,
        input_evidence=[rec(prefix/(k+'_EVENTS.parquet')) for k in frames]+[rec(raw),rec(gen/'CAUSAL_REFERENCE.json')],
        qualification='Prior committed actions are used here to audit current physical state, never to construct the canonical cross-day reference. Rule identity does not imply identical sites under different physical availability.'))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);main(p.parse_args().work)
