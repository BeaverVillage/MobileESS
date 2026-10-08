"""Batch graph ledger refresh; equivalent final union, no candidate deletion."""
from v42_a_stage_domain_v2.active import _ledger

def batch_graphs(data,domains,selected):
    graphs=dict(data[5])
    for c in selected:
        for member in data[7]['classes'][c['class_id']]:graphs[member]=c['graph']
    new=(*data[:5],graphs,data[6],data[7])
    return new,_ledger(new,domains,{key:{} for key in data[7]['classes']})
