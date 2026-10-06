"""Gated sequential proof pipeline. No native optimize call."""
import json
from .common import *

def run():
    assert json.loads((OUT/'PR134_ACCEPTED_WITNESS_REPLAY.json').read_text())['BASELINE_FEASIBLE_WITNESS_PASS']
    from . import reduce,verify,witness,domain_audit,audits,materialize
    for module in (reduce,verify,witness,domain_audit,audits,materialize):
        print('STATIC_PHASE',module.__name__,flush=True);module.run()
    print('STATIC_PROOF_AND_PRESOLVE_COMPLETE',flush=True)

if __name__=='__main__':run()
