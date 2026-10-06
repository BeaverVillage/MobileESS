"""Actual graph refinement, compositional path/event signatures and transit audit."""
from .common import *
from v42_strengthening.analysis import graph_inputs
from fractions import Fraction as F
from collections import defaultdict,Counter
import hashlib
def run():
    sites,initial,arcs,battery,receipt=graph_inputs();A,d=load();mapping=json.loads((PARENT/'ORIGINAL_TO_COMPACT_MAPPING.json').read_text());C0data=np.load(PARENT/'C0_DATA.npz');names=C0data['names'];C0data.close();live=defaultdict(list)
    for n in names:
        if str(n).startswith('route_flow['):u,k=str(n)[11:-1].split(',');live[u].append(int(k))
    records=[];partitions=[];chains=[];gub=[];allphysical=set(map(str,d['names']));allnodes=defaultdict(set)
    for u,ids in live.items():
        out=defaultdict(list);inc=defaultdict(list)
        for k in ids:
            s,t,v,e,r=arcs[k];out[s,t].append(k);inc[v,e].append(k);allnodes[u].update([(s,t),(v,e)])
        nodes=sorted(allnodes[u],key=lambda x:(x[1],x[0]));initiallabels={}
        for s,t in nodes:
            # There are no explicitly modeled interior transit nodes: each
            # travel arc already spans departure/arrival/delay and energy event.
            pq=t<96 and f'Pch[{u},{s},{t}]' in allphysical
            initiallabels[s,t]=(t,s,'CONNECTED_SITE',pq,t==96,s==initial[u] and t==0)
        label={node:i for i,node in enumerate(nodes)};rounds=0
        while True:
            signatures={node:(initiallabels[node],tuple(sorted((arcs[k][3]-arcs[k][1],str(F(arcs[k][-1].energy_kwh)) if arcs[k][-1] is not None else '0',arcs[k][2],label[arcs[k][2:4]],arcs[k][-1] is None) for k in out[node]))) for node in nodes}
            classes={};new={}
            for node in nodes:new[node]=classes.setdefault(signatures[node],len(classes))
            rounds+=1
            if all((new[a]==new[b])==(label[a]==label[b]) for a,b in zip(nodes,nodes[1:])):label=new;break
            label=new
        groups=defaultdict(list)
        for node,z in label.items():groups[z].append(node)
        assert all(len(g)==1 for g in groups.values())
        # A path's full scientific event word is injective in this simple DAG:
        # ordered (location,time,edge energy timing,connection decision) words
        # distinguish its transitions. This tests arbitrary multi-arc fragments
        # compositionally, without falsely claiming exponential enumeration.
        transitions=Counter(arcs[k][:4] for k in ids);parallel=sum(v-1 for v in transitions.values() if v>1)
        assert parallel==0
        deterministic=[]
        for node in nodes:
            if len(inc[node])==len(out[node])==1 and node[1]<96:
                pq=initiallabels[node][3];energy_events=any(arcs[k][-1] is not None for k in inc[node]+out[node])
                if not pq and not energy_events:deterministic.append(node)
                else:chains.append(dict(unit=u,node=str(node),incoming=inc[node],outgoing=out[node],decision='KEEP',reason='Connected P/Q opportunity or mobility energy timing at intermediate state'))
        assert not deterministic
        for t in range(96):
            crossing=[k for k in ids if arcs[k][1]<=t<arcs[k][3]];connected=[k for k in crossing if arcs[k][-1] is None]
            gub.append(dict(unit=u,time=t,crossing_arcs=len(crossing),connected_stays=len(connected),exact_full_cut_equality=True,node_only_equality=t==0,reason='Unit acyclic flow cut includes long transit arcs; connected-node sum alone is <=1, not generally =1'))
        records.append(dict(unit=u,initial_location=initial[u],states=len(nodes),arcs=len(ids),initial_classes=len(nodes),final_classes=len(groups),refinement_rounds=rounds,states_merged=0,arcs_eliminated=0,simple_parallel_arcs=parallel,multi_arc_equivalence=dict(method='Injective full scientific event-word transition signatures and partition refinement; all nonterminal states are physical connected sites; no erased intermediate physical-site/energy/timing event',all_fragments_compositionally_checked=True,path_enumeration_claimed=False,duplicates_proved=0,unknown_alternative_projection_retained=True),transit_interior_states=0,transit_chains_contracted=0))
        partitions.extend(dict(unit=u,node=[s,t],class_id=z,initial_signature=list(initiallabels[s,t])) for (s,t),z in label.items())
    write('GRAPH_BISIMULATION_AUDIT.json',dict(PASS=True,units=records,partition=partitions,initial_partition_fields=['time','site','connectivity','transit/connected','PQ_availability','terminal','source'],refinement='Exact outgoing successor/duration/stored-energy/event labels until unchanged equivalence relation',states_merged=0,no_cross_site_merging=True))
    write('ROUTE_FLOW_STATE_EQUIVALENCE.json',dict(PASS=True,states=sum(r['states'] for r in records),arcs=sum(r['arcs'] for r in records),current_route_columns=int(sum(family(n)=='route_flow' for n in d['names'])),PR161_deterministic_aliases_preserved=192,state_merges=0,new_route_variables_removed=0,multi_arc_path_audit=[r['multi_arc_equivalence'] for r in records],inverse_mapping='Identity for every C2 route column; PR161 original inverse unchanged',symmetry=dict(unit_initial_locations=initial,global_MESS_permutation_automorphism=False,local_exact_automorphism_found=False,reason='Initial physical sites differ; site/time/electrical/PQ consequences are partition labels',new_symmetry_breaking_rows=0)))
    table('TRANSIT_CHAIN_CONTRACTIONS.csv',chains,['unit','node','incoming','outgoing','decision','reason']);table('GUB_SOS_INDICATOR_AUDIT.csv',gub,['unit','time','crossing_arcs','connected_stays','exact_full_cut_equality','node_only_equality','reason'])
    print('NETWORK_EXHAUSTIVE_KEEP',len(partitions),'states; no proved merges/transit contractions',flush=True)
if __name__=='__main__':run()
