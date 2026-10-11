"""Small symbolic AA' adjacency example; no numerical factor/model/solver."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json

def adjacency(rows):
    graph={name:set() for name in rows}
    for name,columns in rows.items():
        for other,ocolumns in rows.items():
            if name!=other and set(columns)&set(ocolumns):graph[name].add(other)
    return graph

def symbolic_factor_count(graph,order):
    graph={n:set(v) for n,v in graph.items()};count=0;steps=[]
    for node in order:
        neighbors=graph[node];count+=1+len(neighbors);steps.append(dict(row=node,remaining_degree=len(neighbors)))
        for other in neighbors:
            graph[other].update(neighbors-{other});graph[other].discard(node)
        del graph[node]
    assert not graph
    return count,steps

before={f'f{t}_{k}':(f'x{t}_{k}','rho') for t in range(2) for k in range(3)}
after={f'f{t}_{k}':(f'x{t}_{k}',f'tau{t}') for t in range(2) for k in range(3)}
after.update({f'link{t}':(f'tau{t}','rho') for t in range(2)})
old=adjacency(before);new=adjacency(after)
old_count,old_steps=symbolic_factor_count(old,list(before))
bad_count,bad_steps=symbolic_factor_count(new,['link0','link1']+list(before))
good_count,good_steps=symbolic_factor_count(new,list(before)+['link0','link1'])
assert old_count==21 and bad_count==33 and good_count==21
result=dict(schema='RHO_TIME_EPIGRAPH_STRUCTURAL_FILL_ORDER_CAUTION_V1',PASS=True,UTC=datetime.now(timezone.utc).isoformat(),original_normal_graph_edges=sum(map(len,old.values()))//2,split_normal_graph_edges=sum(map(len,new.values()))//2,original_symbolic_factor_entries=old_count,split_links_first_symbolic_factor_entries=bad_count,split_faces_first_symbolic_factor_entries=good_count,links_first_steps=bad_steps,meaning='The split lowers raw normal-graph edges13versus15 but a valid elimination order raises symbolic factor entries33versus21. This disproves any unconditional raw-fanout-to-fill or RAM-nonincreasing implication. It is not a measured current-Gurobi factorization or memory prediction.',actual_native_factor_or_memory_measured=False,Native_calls=0,model_builds=0,full_matrix_mutations=0)
path=Path(r'D:\v42_multitime_audit_20261011\RHO_EPIGRAPH_FILL_ORDER_COUNTEREXAMPLE.json');path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(PASS=True,receipt=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),before_edges=result['original_normal_graph_edges'],after_edges=result['split_normal_graph_edges'],before_factor=old_count,bad_order_factor=bad_count,good_order_factor=good_count)))
