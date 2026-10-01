"""Sequential durable census driver; no optimize calls."""
import subprocess,sys
from v42_root.common import *
def run():
    assert read(OUT/'FORMULATION_EQUIVALENCE.json')['PASS']
    for label in ['M1-F2','M1-F3','M1-F4','M1-FCRA']:
        with (LOCAL/(label+'.stdout.log')).open('w',encoding='utf8') as out,(LOCAL/(label+'.stderr.log')).open('w',encoding='utf8') as err:
            r=subprocess.run([sys.executable,'-u','-m','v42_m1_sparse.build',label],cwd=ROOT,stdout=out,stderr=err)
        assert r.returncode==0,label
        atomic(LOCAL/'STRUCTURAL_PROGRESS.json',dict(last_complete=label))
    atomic(LOCAL/'STRUCTURAL_FINISHED.json',dict(PASS=True,optimize_calls=0))
if __name__=='__main__':run()
