"""One frozen production, with explicit exact-zero intervention certificate."""
import argparse,subprocess,sys
from v42_root.common import *
from .quality import certified_gap
def run(candidate,threads,method):
    import v42_m1_sparse.solve as solver
    original=solver.relative_gap;solver.relative_gap=certified_gap
    try:solver.run(candidate,'production',threads,method)
    finally:solver.relative_gap=original
    result=read(OUT/'M1_OPTIMIZATION.json');result['zero_objective_quality_policy']='UB=LB=0 is exact optimum and gap certificate; every nonzero case uses inherited relative_gap unchanged'
    dump('M1_OPTIMIZATION.json',result)
def execute_production(candidate,threads,method):
    name=f'production_{candidate}_T{threads}'
    with (LOCAL/(name+'.stdout.log')).open('w',encoding='utf8') as out,(LOCAL/(name+'.stderr.log')).open('w',encoding='utf8') as err:
        code=subprocess.run([sys.executable,'-u','-m','v42_m1_sparse.production',candidate,'--threads',str(threads),'--method',str(method)],cwd=ROOT,stdout=out,stderr=err).returncode
    assert code==0,name
    return read(OUT/'M1_OPTIMIZATION.json')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('candidate');p.add_argument('--threads',type=int,required=True);p.add_argument('--method',type=int,required=True);a=p.parse_args();run(a.candidate,a.threads,a.method)
