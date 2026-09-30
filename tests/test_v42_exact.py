from dataclasses import replace
import pytest
import gurobipy as gp
from v42_exact.gates import fixture,model
from v42_exact.support import ExactFactory
from v42_exact.factor import mapping,reconstruct
from v42_compact.formulation import values
from v42_job_capability import build_domain
from v42_exact.common import ROOT,OUT,BASE,read,sha

@pytest.mark.parametrize('case',list('ABCDEFGHIJ'))
def test_complete_projection_and_fixed_point(case):
    j,b,r,_=fixture(case);f=ExactFactory(r,max(b.latest_completion,r.control_end));g=f.graph(j,b)
    options,_=build_domain(j,b,r)
    from v42_compact.graph import old_to_compact
    for o in options:
        a=old_to_compact(o)
        for n,keys in {**g.events,**g.states}.items():assert set(a[n]).issubset(keys)
    assert f.graph(j,b).sha==g.sha
    assert all(a['fixed_point'] and a['second_pass_removed']==0 for a in f.audits.values())

def test_full_remaining_interval_removes_one_slot_false_support():
    j,b,r,_=fixture('F');r=replace(r,fixed_gpu={('B',5):8,('A',6):8})
    f=ExactFactory(r,16);g=f.graph(j,b);old=f.original.graph(j,b)
    assert len(g.events['w'])<len(old.events['w'])
    opts,_=build_domain(j,b,r)
    from v42_compact.graph import old_to_compact
    for o in opts:
        for n,keys in {**g.events,**g.states}.items():assert set(old_to_compact(o)[n]).issubset(keys)

@pytest.mark.parametrize('family',('pair','wan_start','wan_active','wan_final','remaining','sent','depart','arrive','link_bytes','r0','h','r1','q','y','f0','f1'))
def test_wrong_single_state_is_infeasible(family):
    j,b,r,_=fixture('F');f=ExactFactory(r,16);g=f.graph(j,b);opts,_=build_domain(j,b,r);o=next(x for x in opts if x.migrated)
    m,v,*_=model({j.uid:j},{j.uid:b},r,{j.uid:g},True);a=mapping(j,g,r,o)
    key=next(iter(v[j.uid][family]));wanted=a.get(family,{}).get(key,0)
    for n,items in v[j.uid].items():
        for k,x in items.items():m.addConstr(gp.LinExpr(x)==(a.get(n,{}).get(k,0)+1 if n==family and k==key else a.get(n,{}).get(k,0)))
    m.optimize();assert m.Status==gp.GRB.INFEASIBLE;m.dispose()

@pytest.mark.parametrize('name',('SYNTHETIC_EXHAUSTIVE_EQUIVALENCE.json','ADVERSARIAL_WAN_TESTS.json','WAN_TEMPLATE_EQUIVALENCE.json','REAL_SUBSET_EQUIVALENCE.json'))
def test_receipt_complete(name):
    p=read(OUT/name);assert p['PASS'] is True
    if name=='WAN_TEMPLATE_EQUIVALENCE.json':assert p['standalone_all_pairs_starts_PASS'] is True

def test_no_product_binary_and_pure_milp():
    j,b,r,_=fixture('F');g=ExactFactory(r,16).graph(j,b);m,v,*_=model({j.uid:j},{j.uid:b},r,{j.uid:g},True);m.update()
    assert not v[j.uid]['w']
    assert all(len(k)==2 for k in v[j.uid]['pair'])
    assert all(isinstance(k,int) for k in v[j.uid]['wan_start'])
    assert m.NumQConstrs==m.NumQNZs==m.NumSOS==m.NumGenConstrs==0
    m.dispose()

def test_pr99_bytes_preserved():
    for row in read(OUT/'LEGACY_PRESERVATION_AUDIT.json')['files']:assert sha(ROOT/row['path'])==row['sha256']

def test_no_dw_production_import():
    from v42_exact import native
    import sys
    assert not any(n=='v42_dw' or n.startswith('v42_dw.') for n in sys.modules)

def test_original_deterministic_event_tie_every_bounded_path():
    from v42_exact.factor import tie_expression
    from v42_compact.graph import old_to_compact
    j,b,r,_=fixture('F');f=ExactFactory(r,16);g=f.graph(j,b);old=f.original.graph(j,b);opts,_=build_domain(j,b,r)
    m,v,*_=model({j.uid:j},{j.uid:b},r,{j.uid:g},True);expr,end=tie_expression(m,j,old,g,v[j.uid],1234)
    ranks={};i=1234
    for n in ('y','q','w','f0','f1'):
        for key in old.events[n]:i+=1;ranks[n,key]=i
    for o in opts:
        a=mapping(j,g,r,o);pin=[]
        for n,items in v[j.uid].items():
            if n=='tie_rank':continue
            for key,x in items.items():pin.append(m.addConstr(gp.LinExpr(x)==a.get(n,{}).get(key,0)))
        m.setObjective(expr);m.optimize();assert m.Status==gp.GRB.OPTIMAL
        compact=old_to_compact(o);want=sum(ranks[n,key] for n in ('y','q','w','f0','f1') for key in compact[n])
        assert m.ObjVal==pytest.approx(want,abs=1e-6);m.remove(pin);m.update()
    m.dispose()

@pytest.mark.parametrize('case',('source_mismatch','destination_switch','before_checkpoint','two_checkpoints','two_starts','two_pairs','active_without_start',
    'send_before_start','compute_while_waiting','compute_while_WAN','compute_while_restart','split_gang','throttled_nonfinal',
    'positive_send_zero_rate','lost_payload','delayed_finish','fixed_WAN_collision','fixed_active_collision','checkpoint_without_migration','finish_without_migration'))
def test_forbidden_physical_behavior_without_fixing_other_states(case):
    j,b,r,_=fixture('F')
    if case in ('throttled_nonfinal','positive_send_zero_rate'):
        r=replace(r,wan_capacities={('AB',t):0 if case=='positive_send_zero_rate' and t==2 else 200 for t in range(12)})
    if case=='fixed_WAN_collision':r=replace(r,fixed_wan={('AB',2):400})
    if case=='fixed_active_collision':r=replace(r,fixed_transfers={2:r.max_active_transfers})
    f=ExactFactory(r,16);g=f.graph(j,b);m,v,*_=model({j.uid:j},{j.uid:b},r,{j.uid:g},True);v=v[j.uid]
    pins=[]
    def pin(n,k,x=1):
        if k not in v[n]:
            # Exact support has already proved that this event/state cannot
            # occur; an attempted positive value is algebraically impossible.
            m.addConstr(gp.LinExpr(0)==x)
        else:m.addConstr(gp.LinExpr(v[n][k])==x)
    if case=='source_mismatch':pin('y',('A',0));pin('pair',('B','A'))
    elif case=='destination_switch':pin('pair',('A','B'));pin('f1',('A',8))
    elif case=='before_checkpoint':pin('q',('A',4));pin('wan_start',2)
    elif case=='two_checkpoints':pin('q',('A',2));pin('q',('A',4))
    elif case=='two_starts':pin('wan_start',2);pin('wan_start',3)
    elif case=='two_pairs':pin('pair',('A','B'));pin('pair',('B','A'))
    elif case=='active_without_start':m.addConstr(gp.quicksum(v['wan_start'].values())==0);pin('wan_active',2)
    elif case=='send_before_start':pin('wan_start',4);pin('sent',2)
    elif case=='compute_while_waiting':pin('q',('A',2));pin('wan_start',4);pin('r0',('A',3))
    elif case=='compute_while_WAN':pin('pair',('A','B'));pin('wan_start',4);pin('r1',('B',4))
    elif case=='compute_while_restart':pin('pair',('A','B'));pin('wan_start',3);pin('r1',('B',4))
    elif case=='split_gang':pin('r0',('A',1),.5)
    elif case=='throttled_nonfinal':pin('pair',('A','B'));pin('wan_start',2);pin('sent',2,4)
    elif case=='positive_send_zero_rate':pin('wan_start',2);pin('sent',2)
    elif case=='lost_payload':pin('remaining',r.control_end)
    elif case=='delayed_finish':pin('wan_start',2);pin('wan_final',4)
    elif case in ('fixed_WAN_collision','fixed_active_collision'):pin('pair',('A','B'));pin('wan_start',2)
    elif case=='checkpoint_without_migration':m.addConstr(gp.quicksum(v['pair'].values())==0);pin('q',('A',2))
    elif case=='finish_without_migration':m.addConstr(gp.quicksum(v['pair'].values())==0);pin('wan_final',2)
    m.optimize();assert m.Status==gp.GRB.INFEASIBLE;m.dispose()
