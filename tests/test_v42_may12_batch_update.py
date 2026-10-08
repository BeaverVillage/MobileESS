from v42_a_stage_phase1.backend import update_graph
from v42_may12_rescue.activation import batch_graphs

def test_batch_replays_serial_final_ledger(monkeypatch):
    import v42_a_stage_phase1.backend as old
    import v42_may12_rescue.activation as new
    calls=[]
    def ledger(data,domains,selection):
        calls.append(1);return {'graphs':dict(data[5]),'selection':selection,'domains':domains}
    monkeypatch.setattr(old,'_ledger',ledger);monkeypatch.setattr(new,'_ledger',ledger)
    d=(None,None,None,None,None,{'a':'g0','b':'g0','c':'h0'},None,{'classes':{'k':['a','b'],'l':['c']}})
    selected=[{'class_id':'k','graph':'g1'},{'class_id':'l','graph':'h1'}];domains={}
    serial=d
    for c in selected:serial,sledger=update_graph(serial,domains,c['class_id'],c['graph'])
    result,bledger=batch_graphs(d,domains,selected)
    assert result==serial and bledger==sledger and len(calls)==3
    assert d[5]=={'a':'g0','b':'g0','c':'h0'}
