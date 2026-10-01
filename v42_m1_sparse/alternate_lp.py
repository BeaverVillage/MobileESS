"""One bounded barrier fallback, isolated output, identical original model code."""
import argparse
from v42_root.common import *
def run(candidate):
    import v42_m1_sparse.solve as solver
    target=OUT/'METHOD2_LP';target.mkdir(exist_ok=True);(target/'census').mkdir(exist_ok=True)
    source=read(OUT/'census'/(candidate+'.json'))
    atomic(target/'census'/(candidate+'.json'),{k:source[k] for k in ('stats','start','numerical')})
    folder=LOCAL/'METHOD2_LP';folder.mkdir(exist_ok=True)
    # Only worker output locations change. inputs() and frozen() retain their
    # immutable original PR106 source directories. The same solver receives
    # Method=2 as its already-supported explicit diagnostic argument.
    solver.OUT=target;solver.LOCAL=folder
    solver.run(candidate,'lp',1,2)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('candidate');run(p.parse_args().candidate)
