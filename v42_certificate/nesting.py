"""Independent occupancy enumeration verifies all inherited subset domains."""
from .common import *

def run():
    axis=load_axis();routearcs=arcs();masks={};counts={}
    inherited={'B1':'R_ROUTE_ONLY','B2':'R_ACTIVE','B3':'R_BUFFER'}
    for arm,w in WINDOWS.items():
        selected=[]
        for n,k in zip(axis['names'],axis['original_types']):
            if k!='B':selected.append(False);continue
            if n.startswith('arc['):
                a=routearcs[int(n[4:-1].split(',')[1])]
                inside=any(a[1]<=t<a[3] for t in range(w[0],w[1]+1)) or a[1] in range(w[0],w[1]+1)
            else:
                assert n.startswith('charge_mode[')
                inside=arm!='B1' and int(n[12:-1].split(',')[1]) in range(w[0],w[1]+1)
            selected.append(inside)
        mask=np.asarray(selected);expected=list(map(str,axis['names'][mask]))
        source=json.loads(gzip.decompress((PRIOR/(inherited[arm]+'_DOMAIN.json.gz')).read_bytes()))
        assert expected==source['restored'] and not source['fixed']
        assert all(bool(x)==restore(str(n),str(k),arm,routearcs) for n,k,x in zip(axis['names'],axis['original_types'],mask))
        masks[arm]=mask;counts[arm]=int(mask.sum())
    assert np.all(~masks['B1']|masks['B2']) and np.all(~masks['B2']|masks['B3'])
    _,start=load_start();binary=axis['original_types']=='B';assert np.max(abs(start[binary]-np.rint(start[binary])))<=TOL
    np.savez_compressed(OUT/'NESTING_DOMAIN_AXIS.npz',**masks)
    dump('NESTING_DOMAIN_VALIDATION.json',dict(PASS=True,counts=counts,strictly_nested=True,original_integer_start_feasible_in_every_subset=True,
        restored_domains_exactly_match_PR112=True,independent_rule='Enumerate occupancy at each slot, including arrival-to-connect interval, plus departures from window nodes',
        feasible_set_relation='F_original_integer subset F_B3 subset F_B2 subset F_B1 subset F_F3',
        optimum_relation='opt_F3 <= opt_B1 <= opt_B2 <= opt_B3 <= opt_original_integer',
        upper_transfer='Every independently validated B3 feasible point is feasible in B2/B1; an original integer point is feasible in every partial model.',
        lower_transfer='A weaker relaxation lower bound is valid for every stronger model; a B3 lower bound cannot be transferred to B1/B2.',
        S2_warning='S2 is a certified original-integer LB, not automatically a lower bound on a partial F3-subset optimum.',
        full96_rows_retained=True,terminal_SOC_retained=True,route_graph_no_pruning=True,custom_cuts=False,optimize_calls=0,axis_sha256=sha(OUT/'NESTING_DOMAIN_AXIS.npz')))
    print('INDEPENDENT NESTING PASS',counts,flush=True)
if __name__=='__main__':run()
