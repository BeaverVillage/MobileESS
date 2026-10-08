from .common import *
from collections import Counter,defaultdict
def main():
    paths_audit('static_initial')
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==BASE
    A,d,start=hc.load();identity=prior.objective_identity(A,d)
    write(REPORTS/'SCIENTIFIC_IDENTITY.json',dict(PASS=True,objective=identity,base=BASE,rows=A.shape[0],cols=A.shape[1],nnz=A.nnz,binaries=int((d['types']=='B').sum()),all_bounds_finite=bool(np.isfinite(d['lower']).all() and np.isfinite(d['upper']).all()),sources={str(hc.PARENT/n):sha(hc.PARENT/n) for n in ['C3A_A.npz','C3A_DATA.npz','C3A_VALID_START.npz']}))
    names=list(map(str,d['names']));rows=list(map(str,d['row_names']));fam=Counter(n.split('[')[0] for n in rows)
    from v42_strengthening.analysis import graph_inputs
    sites,initial,arcs,battery,receipt=graph_inputs()
    duplicate=[(k,n) for k,n in Counter(tuple(a[:4]) for a in arcs).items() if n>1]
    backward=[i for i,a in enumerate(arcs) if a[3]<=a[1]]
    pure_cols=np.array([n.startswith(('route_flow[','node_activity[','charge_mode[')) for n in names])
    pure_rows=np.flatnonzero(np.asarray(A[:,~pure_cols].getnnz(axis=1)).ravel()==0)
    f=Counter(rows[i].split('[')[0] for i in pure_rows)
    link=np.array([i for i,n in enumerate(rows) if n.startswith('node_activity_link[')])
    audit=[]
    for i in link:
        unit,site,t=rows[i].split('[',1)[1][:-1].split(',');t=int(t)
        rr=A.getrow(i);terms={names[j]:float(v) for j,v in zip(rr.indices,rr.data)}
        bad=[]
        for name,v in terms.items():
            if name.startswith('route_flow['):
                u,arc=name.split('[',1)[1][:-1].split(',');a=arcs[int(arc)]
                if (u,a[0],a[1],v)!=(unit,site,t,-1.):bad.append(name)
            elif name!=f'node_activity[{unit},{site},{t}]' or v!=1.:bad.append(name)
        if bad or d['sense'][i]!='=' or d['rhs'][i]!=0.:audit.append(dict(row=rows[i],bad=bad))
    reader=hc.physical_reader()
    points=[('current',prior.center()),('PR162_start',start)]
    candidates=[ROOT/'docs/v42_m1_gap_rootcause_20261007/UB_LOCAL_NEIGHBORHOOD_POINT.npz',ROOT/'docs/v42_m1_hamming48_20261007/BEST_VALID_POINT.npz']
    candidates+=sorted((ROOT/'docs/v42_m1_hamming48_600s_20261007/incumbents').glob('*.npz'))
    candidates+=sorted((ROOT/'docs/v42_m1_hamming48_20261007/incumbents').glob('*.npz'))
    B=np.flatnonzero(d['types']=='B');seen=set();valid=[];rejected=[]
    for label,x in points+[(str(p.relative_to(ROOT)),next(iter(np.load(p).values())).copy()) for p in candidates]:
        if x.shape!=start.shape:rejected.append(dict(label=label,reason='wrong_axis'));continue
        bid=hashlib.sha256(np.rint(x[B]).astype(np.uint8).tobytes()).hexdigest()
        if bid in seen:continue
        check=prior.prior.full_replay(A,d,x,reader)
        if check['PASS']:
            seen.add(bid);save(WORK/'artifacts/assignments'/f'{len(valid):03d}.npz',x=x,B=B,z=np.rint(x[B]))
            write(WORK/'artifacts/assignments'/f'{len(valid):03d}_REPLAY.json',check)
            flows=x[[j for j,n in enumerate(names) if n.startswith('route_flow[')]]
            valid.append(dict(id=bid,label=label,objective=float(d['objective']@x),route_hash=hashlib.sha256(flows.tobytes()).hexdigest()))
        else:rejected.append(dict(label=label,reason=check))
        if len(valid)>=20:break
    # Mode alternatives are witnessed by the same original feasible dispatch,
    # never by synthetic load, routes, grid data, or a restricted global domain.
    center=prior.center()
    for j in B:
        if len(valid)>=20:break
        if not names[j].startswith('charge_mode['):continue
        x=center.copy();x[j]=1.-x[j]
        if not hc.replay(A,d,x,True)['PASS']:continue
        check=prior.prior.full_replay(A,d,x,reader)
        if not check['PASS']:continue
        bid=hashlib.sha256(np.rint(x[B]).astype(np.uint8).tobytes()).hexdigest()
        if bid in seen:continue
        seen.add(bid);save(WORK/'artifacts/assignments'/f'{len(valid):03d}.npz',x=x,B=B,z=np.rint(x[B]))
        write(WORK/'artifacts/assignments'/f'{len(valid):03d}_REPLAY.json',check)
        valid.append(dict(id=bid,label='idle_mode_flip:'+names[j],objective=float(d['objective']@x),route_hash=hashlib.sha256(x[[k for k,n in enumerate(names) if n.startswith('route_flow[')]].tobytes()).hexdigest()))
    write(REPORTS/'ASSIGNMENT_CENSUS.json',dict(valid=valid,rejected=rejected,count=len(valid),historical_bytes_unchanged=True,sample_is_not_domain=True))
    # Audit all original vertex-occupancy identities through the saved exact
    # inverse. Missing link rows must be aliases/constants, not unlinked flow.
    outgoing=defaultdict(dict);offsets=defaultdict(float)
    for j in reader.arc:
        unit,ai=str(reader.d['names'][j]).split('[',1)[1][:-1].split(',');a=arcs[int(ai)];key=(unit,a[0],a[1])
        target=int(reader.target[j]);offsets[key]+=reader.offset[j]
        if target>=0:outgoing[key][target]=outgoing[key].get(target,0.)+1.
    name_index={n:j for j,n in enumerate(names)};link_index={rows[i]:int(i) for i in link}
    source_flow_rows=[]
    for i in pure_rows:
        if rows[i]=='flow' and d['sense'][i]=='=' and abs(d['rhs'][i])==1.:
            rr=A.getrow(i);source_flow_rows.append((dict(zip(rr.indices,rr.data)),float(d['rhs'][i])))
    vertex_classes=Counter();vertex_bad=[]
    for unit in initial:
        for site in sites:
            for t in range(96):
                key=(unit,site,t);terms=outgoing[key];off=offsets[key];n=f'node_activity[{unit},{site},{96 if t==95 else t}]';ni=name_index.get(n)
                if ni is None:
                    if not terms and off in (0.,1.):vertex_classes['constant_occupancy']+=1
                    elif t==0 and site==initial[unit] and any((terms==coeff and rhs==1.-off) or ({k:-v for k,v in terms.items()}==coeff and rhs==off-1.) for coeff,rhs in source_flow_rows):vertex_classes['source_unit_flow']+=1
                    else:vertex_bad.append(dict(vertex=key,reason='missing_binary',terms=terms,offset=off))
                elif terms=={ni:1.} and off==0.:vertex_classes['exact_alias']+=1
                else:
                    li=link_index.get(f'node_activity_link[{unit},{site},{t}]')
                    expected={k:-v for k,v in terms.items()};expected[ni]=expected.get(ni,0.)+1.;expected={k:v for k,v in expected.items() if v}
                    actual=dict(zip(A.getrow(li).indices,A.getrow(li).data)) if li is not None else {}
                    if li is not None and expected==actual and d['rhs'][li]==off:vertex_classes['explicit_link']+=1
                    else:vertex_bad.append(dict(vertex=key,reason='link_identity_failure',offset=off))
    terminal_stay_only=all(a[3]<96 for a in arcs if a[4] is not None)
    route=dict(PASS=not duplicate and not backward and not audit and not vertex_bad and terminal_stay_only,terminal_stay_only=terminal_stay_only,terminal_binary_label=96,last_stay_graph_slot=95,source_unit_rows=len(source_flow_rows),vertex_classes=vertex_classes,vertex_failures=vertex_bad,original_vertices_checked=4*24*96,graph_arcs=len(arcs),sites=len(sites),MESS=list(initial),duplicate_endpoint_arcs=duplicate,non_forward_arcs=backward,pure_rows=len(pure_rows),pure_row_families=f,all_row_families=fam,node_link_rows=len(link),link_semantics_failures=audit,retained_route_flows=sum(n.startswith('route_flow[') for n in names),node_activity_variables=sum(n.startswith('node_activity[') for n in names),graph_receipt=receipt)
    write(REPORTS/'ROUTE_PROJECTION_AUDIT.json',route)
    print(json.dumps(clean(dict(route=route,valid_assignments=len(valid))),ensure_ascii=False),flush=True)
if __name__=='__main__':main()
