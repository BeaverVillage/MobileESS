"""Causal one-shot candidate, persistence and exact model-size audit; no solve."""
from dayahead.v41.preflight import OUT,record
from dayahead.v41.electrical import load
from dayahead.v41.snapshot import create
from dayahead.v41.persistence import pre_solve
from dayahead.v41.common import build
from dayahead.v41.reserve import bind
from dayahead.v41.scientific_archive import document
from dayahead.v40g_segments.canonical import import_frozen,planning_power
from dayahead.v40g.optimizer import solve
from .migration_audit import persist
from .migration import CONTRACT


def run():
    day='2025-05-01';folder=OUT/'PRE_MAY01_ONE_SHOT_AUDIT'
    print('Loading certified electrical and causal ML',flush=True)
    context=load(day)
    try:
        snapshot,seal=create(day);bind(context,snapshot,seal['snapshot']['sha256'])
        persistence=pre_solve(day,snapshot,context.capacity)
        reference,common=build(day,snapshot,context.capacity)
        jobs=import_frozen(reference);power=planning_power(jobs,context)
        print('Auditing final one-shot candidates',flush=True)
        candidates=persist(folder,day,'B1',reference,jobs,context)
        print({k:v for k,v in candidates.items() if k.startswith('N_') or k=='explicit_candidate_combination_count'},flush=True)
        print('Building the full compressed model without optimizing',flush=True)
        structure=solve(reference,power['pcc'],context,folder/'MODEL',build_only=True)
        document(folder/'PRE_MAY01_GATE.json',dict(status='PASS',contract=CONTRACT,
            candidate_summary=record(folder/'MIGRATION_ELIGIBILITY_SUMMARY.json'),
            model_structure=record(folder/'MODEL/PRIMARY_STRUCTURE.json'),
            day_boundary=record(folder/'MODEL/DAY_BOUNDARY_AUDIT.json'),
            persistence=persistence,common=common,
            explicit_candidate_combination_count=candidates['explicit_candidate_combination_count'],
            compressed_integer_variables=structure['integer_variables_including_binary'],
            compressed_constraints=structure['model_constraints']+structure['general_constraints'],
            Actual_reads=0,optimizer_calls=0,full_May_authorized=False))
        print('PRE_MAY01_ONE_SHOT_AUDIT PASS',flush=True)
    finally:
        context.electrical.voltage.close();context.electrical.current.close()


if __name__=='__main__':run()
