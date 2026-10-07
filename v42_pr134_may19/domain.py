"""Domain union through original graph interfaces, original equations untouched."""
from dataclasses import replace
from collections import defaultdict
import json
from .common import *

def expand(data,selected):
    from v42_compact.graph import Graph
    from v42_job_capability import Option,validate
    from v42_boundary.generator import Generator
    from v42_pr134_adaptive.pool import physical_starts
    bundle,jobs,bounds,r,raw,graphs,old,prep=data
    bounds=dict(bounds);graphs=dict(graphs);by=defaultdict(list)
    for row in selected:by[row['class_id']].append(row)
    gen=Generator(r,max(b.latest_completion for b in bounds.values()))
    for key,rows in by.items():
        members=prep['classes'][key];j=jobs[members[0]];b=bounds[members[0]];g=graphs[members[0]]
        events={n:set(v) for n,v in g.events.items()};states={n:set(v) for n,v in g.states.items()}
        compat={k:set(v) for k,v in g.compatible.items()};physical=dict(g.physical);transfers=dict(g.transfers)
        for row in rows:
            if row['classification'] not in ('CERTIFICATE_BREAKING','CERTIFICATE_NEUTRAL'):raise PermissionError('UNUSEFUL_CANDIDATE')
            site=str(row['site']);start=int(row['start']);cp=int(row['checkpoint']);parts=tuple(tuple(x) for x in json.loads(row['segments']))
            if start not in physical_starts(j,b):raise PermissionError('HARD_TEMPORAL_AUTHORITY')
            wide=replace(b,allowed_starts=tuple(sorted(set(b.allowed_starts)|{start})))
            if cp<0:option=Option(start,site,parts)
            else:
                tau=int(row['transfer_start']);dest=row['destination'];tr=gen.transfer(site,dest,j.gpu,tau)
                option=Option(start,site,parts,cp,float(row['physical_checkpoint_seconds']),dest,tau,tr.end,tr.restart,tr.wan)
                compat.setdefault((site,cp),set()).add(start);physical[site,cp,start]=option.physical_checkpoint_seconds
                transfers[site,dest,tau]=tr;events['q'].add((site,cp));events['w'].add((site,dest,tau))
                events['f1'].add((dest,parts[-1][2]));states['h'].update((site,t) for t in range(cp,tau))
                states['r1'].update((dest,t) for t in range(parts[-1][1],parts[-1][2]))
            for uid in members:validate(jobs[uid],option,wide,r)
            events['y'].add((site,start));states['r0'].update((site,t) for t in range(start,parts[0][2]))
            if cp<0:events['f0'].add((site,parts[0][2]))
        allowed=tuple(sorted(set(b.allowed_starts)|{int(x['start']) for x in rows}))
        new=Graph({n:tuple(sorted(v)) for n,v in events.items()},{n:tuple(sorted(v)) for n,v in states.items()},
                  {k:tuple(sorted(v)) for k,v in compat.items()},physical,transfers,None)
        new.sha=digest(dict(events=new.events,states=new.states,compatible=new.compatible,physical=new.physical,
                           transfer_keys=sorted(new.transfers),old_sha=g.sha))
        for uid in members:graphs[uid]=new;bounds[uid]=replace(bounds[uid],allowed_starts=allowed)
    return bundle,jobs,bounds,r,raw,graphs,old,prep

def build(shell):
    import v42_pr134_adaptive.restricted as original
    folder=CASE/shell
    if folder.exists():raise PermissionError('FRESH_STATIC_IDENTITY_REQUIRED')
    selected=read(CASE/(shell+'_DOMAIN.json'));folder.mkdir(parents=True)
    atomic(folder/'SELECTED_DOMAIN_INPUT.json',selected)
    prior=original.expand;original.expand=expand
    try:m,*_=original.build(DAY,selected,folder);m.dispose()
    finally:original.expand=prior
    census=read(folder/'CENSUS.json')
    census.update(added_migration_candidates=sum(int(x['checkpoint'])>=0 for x in selected),
                  added_prestart_site_candidates=sum(int(x['checkpoint'])<0 and x.get('kind')=='PRESTART_SITE' for x in selected))
    atomic(folder/'CENSUS.json',census)
    atomic(folder/'STATIC_ONLY.json',dict(PASS=True,optimizer_calls=0,base=BASE,selected=record(folder/'SELECTED_DOMAIN_INPUT.json'),
        matrix=record(folder/'EXPANDED_MATRIX.npz'),attributes=record(folder/'EXPANDED_ATTRIBUTES.npz'),descriptor=record(folder/'SCIENTIFIC_INTERFACES.pkl.gz'),
        producers=[record(Path(__file__)),record(ROOT/'v42_pr134_adaptive/restricted.py')]))
    verify(shell)
    import v42_pr134_adaptive.compress_static as compact
    prior_case=compact.CASE;compact.CASE=CASE.parent
    # Adapter uses CASE/day/tag. New task uses CASE/tag: an explicit static-only
    # namespace route, no scientific or model edit.
    try:compact.main(CASE.name,shell)
    finally:compact.CASE=prior_case

def verify(shell):
    import pickle
    from dataclasses import asdict
    from v42_pr134_adaptive.common import load
    old=load(DAY);folder=CASE/shell
    with (folder/'DATA.pkl').open('rb') as f:new=pickle.load(f)
    selected=read(folder/'SELECTED_DOMAIN_INPUT.json');s38=read(START/'SELECTED_DOMAIN_INPUT.json')
    if not {digest(x) for x in s38}<={digest(x) for x in selected}:raise ValueError('S38_OPTION_REMOVED')
    assert old[1]==new[1] and old[3]==new[3] and old[4]==new[4] and old[7]['classes']==new[7]['classes'] and digest(old[0])==digest(new[0])
    for uid,j in old[1].items():
        b=asdict(old[2][uid]);q=asdict(new[2][uid]);before=b.pop('allowed_starts');after=q.pop('allowed_starts')
        assert b==q and set(before)<=set(after)
        g,h=old[5][uid],new[5][uid]
        for kind in ('events','states'):
            for name,v in getattr(g,kind).items():assert set(v)<=set(getattr(h,kind)[name])
        for k,v in g.compatible.items():assert set(v)<=set(h.compatible[k])
        for k,v in g.physical.items():assert h.physical[k]==v
        for k,v in g.transfers.items():assert h.transfers[k]==v
    atomic(folder/'INDEPENDENT_DOMAIN_INCLUSION.json',dict(PASS=True,S0_retained=True,S38_retained=True,
           original_job_class_counts_service_Runtime_resources_inputs_unchanged=True,old_checkpoint_transfer_authority_retained=True,
           new_data=record(folder/'DATA.pkl'),optimizer_calls=0))
if __name__=='__main__':
    import sys
    build(sys.argv[1])
