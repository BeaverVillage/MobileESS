#!/usr/bin/env python3
from pathlib import Path
import json, random, sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from r25e_node_arc_exact import StateArc, validate_simple_dag, enumerate_paths, prove_path_signature_injective, structural_binary_bound

# Variable-duration simple DAG: several alternative paths, but no parallel tail/head transitions.
arcs=[
 StateArc('s0',(0,'A'),(1,'A'),'STAY'),
 StateArc('m0',(0,'A'),(2,'B'),'MOVE'),
 StateArc('m1',(0,'A'),(1,'B'),'MOVE'),
 StateArc('s1a',(1,'A'),(2,'A'),'STAY'),
 StateArc('m2',(1,'A'),(3,'B'),'MOVE'),
 StateArc('s1b',(1,'B'),(2,'B'),'STAY'),
 StateArc('m3',(1,'B'),(3,'A'),'MOVE'),
 StateArc('s2a',(2,'A'),(3,'A'),'STAY'),
 StateArc('s2b',(2,'B'),(3,'B'),'STAY'),
]
source=(0,'A');H=3
au=prove_path_signature_injective(arcs,source,H)
assert au['path_count']==5 and au['path_to_node_signature_injective']

# Parallel direct alternatives are deliberately rejected because binary node occupancy
# alone cannot distinguish a fractional mixture of two identical tail/head arcs.
parallel_rejected=False
try:
    validate_simple_dag(arcs+[StateArc('m0_parallel',(0,'A'),(2,'B'),'MOVE')],source,H)
except ValueError:
    parallel_rejected=True
assert parallel_rejected

# A2-equivalent route merge restores the simple-graph condition.
assert validate_simple_dag(arcs,source,H)['parallel_tail_head_count']==0

# Historical issue152 structural upper bound from R24 evidence: 4,299 reachable STAY
# states over h=0..H-1.  H can add at most 4*24 sink occupancy states.
b=structural_binary_bound(4299,4,24,216,0)
assert b['node_occupancy_binary_upper_bound']==4395
assert b['total_integer_upper_bound']==4611

print(json.dumps({
 'PASS':True,'stage':'A5/6','formulation':'BINARY_NODE_OCCUPANCY_PLUS_CONTINUOUS_SIMPLE_DAG_ARCS',
 'tiny_path_count':au['path_count'],'path_to_node_occupancy_injective':True,
 'parallel_tail_head_fail_closed':True,
 'historical_issue152_stay_state_count':4299,
 'historical_issue152_move_binary_count_before_A5':99283,
 'historical_issue152_integer_count_R24_estimate':99499,
 'A5_node_occupancy_binary_upper_bound':b['node_occupancy_binary_upper_bound'],
 'A5_total_integer_upper_bound_before_dynamic_job_binaries':b['total_integer_upper_bound'],
 'minimum_integer_reduction_fraction_vs_R24_estimate':1.0-b['total_integer_upper_bound']/99499.0,
 'long_solver_run':False
},indent=2,sort_keys=True))
