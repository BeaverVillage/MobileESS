"""Clean Windows CPU LP diagnostic wrapper; gate checked before any timing."""
import argparse
from v42_root.common import *
from v42_root.diagnostics import measure
from .performance import source_freeze,performance_gate

def main():
    p=argparse.ArgumentParser();p.add_argument('kind');kind=p.parse_args().kind
    source_freeze();frozen_set=read(OUT/'CANDIDATE_FREEZE.json')
    if kind not in frozen_set['LP_candidates']:raise ValueError('NOT_FROZEN_LP_CANDIDATE')
    dump(kind+'_PERFORMANCE_GATE.json',performance_gate());measure(kind)
if __name__=='__main__':main()
