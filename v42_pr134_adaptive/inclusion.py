"""Independent semantic S0 inclusion and domain-only authority audit."""
import pickle,sys
from dataclasses import asdict
from .common import *
def verify(day,tag):
    folder=CASE/day/tag;old=load(day)
    with (folder/'DATA.pkl').open('rb') as f:new=pickle.load(f)
    changes=[]
    for uid,j in old[1].items():
        if j!=new[1][uid]:raise ValueError('JOB_IMMUTABLE_FIELDS_CHANGED')
        b=asdict(old[2][uid]);q=asdict(new[2][uid]);before=b.pop('allowed_starts');after=q.pop('allowed_starts')
        if b!=q or not set(before)<=set(after):raise ValueError('HARD_BOUNDARY_CHANGED_OR_S0_REMOVED')
        g=old[5][uid];h=new[5][uid]
        for kind in ('events','states'):
            for name,keys in getattr(g,kind).items():
                if not set(keys)<=set(getattr(h,kind)[name]):raise ValueError('S0_STATE_REMOVED')
        if g.compatible!=h.compatible or g.physical!=h.physical or g.transfers!=h.transfers:raise ValueError('EXISTING_CHECKPOINT_WAN_AUTHORITY_CHANGED')
        if before!=after:changes.append(dict(uid=uid,starts_added=sorted(set(after)-set(before))))
    if old[7]['classes']!=new[7]['classes'] or old[3]!=new[3] or digest(old[0])!=digest(new[0]) or old[4]!=new[4]:raise ValueError('SCIENTIFIC_CLASS_CAPACITY_SERVICE_RUNTIME_INPUT_CHANGED')
    support={}
    for key,us in old[7]['classes'].items():
        g,h=old[5][us[0]],new[5][us[0]]
        support[key]={kind+'_'+name:len(set(vals)-set(getattr(g,kind)[name])) for kind in ('events','states') for name,vals in getattr(h,kind).items()}
    totals={name:sum(row[name] for row in support.values()) for name in next(iter(support.values()))}
    result=dict(PASS=True,original_S0_all_paths_retained=True,only_allowed_starts_and_support_states_extended=True,
        logical_class_support_state_increases=totals,per_class_support_state_increases=support,
        original_classes_counts_unchanged=True,original_resource_service_Runtime_and_bundle_unchanged=True,
        old_migration_checkpoint_WAN_support_unchanged=True,changed_member_jobs=len(changes),changes=changes,
        raw_input=record(PRODUCTION/'inputs'/day/'NATIVE_INPUT.json'),old_data=record(SOURCE/day/'DATA.pkl'),new_data=record(folder/'DATA.pkl'),
        optimizer_calls=0,old_historical_freeze_used_as_current_witness=False,original_reference_fields_changed=False)
    atomic(folder/'INDEPENDENT_S0_INCLUSION.json',result);print('DOMAIN_ONLY_INCLUSION_PASS',day,len(changes),flush=True)
    return result
if __name__=='__main__':verify(*sys.argv[1:])
