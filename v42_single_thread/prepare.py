"""Freeze PR133 preservation and the user's new execution policy before build."""
import subprocess
from .common import ROOT,OUT,LOCAL,BASE,NORMALAMPS,ENV,sha,write,configure
from .resources import exclusive_gate

def run():
    configure()
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()==BASE
    p=OUT/'PR133_BYTE_PRESERVATION.json'
    if p.exists():raise ValueError('PREPARATION_ALREADY_FROZEN')
    gate=exclusive_gate('prepare')
    paths=subprocess.check_output(['git','ls-files'],cwd=ROOT).decode().splitlines()
    write('PR133_BYTE_PRESERVATION.json',dict(base=BASE,files=[dict(path=p,sha256=sha(ROOT/p)) for p in paths],PR133_inherited_files_modified=False))
    write('SINGLE_WORKER_RESOURCE_POLICY.json',dict(base=BASE,MAX_HEAVY_WORKERS=1,Gurobi_Threads=1,environment=ENV,external_python_or_solver_start_gate=True,no_tests_during_heavy=True,no_parallel_pytest=True,no_parameter_sweep=True,A1=dict(Method=1,Threads=1,MIPGap=.005,Seed=20260929,total_TimeLimit=3600,default_parameters=['Cuts','Presolve','Heuristics','NumericFocus'],attempts=1,lexicographic_execution='pending clarification of literal optimize-call restriction'),M1_root_LP=dict(Method=2,Threads=1,Crossover=0,TimeLimit=300),M1_P1=dict(Method=2,Threads=1,NodeMethod=1,Crossover=2,MIPFocus=3,MIPGap=.005,TimeLimit=1800,checkpoint=600,attempts=1),M1_P2=['movement_energy','movement_count'],NormalAmps_authority=NORMALAMPS,initial_resource_snapshot=gate,physics_changes=False,old_OOM_evidence_preserved=True))
    print('PR133_PRESERVED_SINGLE_WORKER_POLICY_FROZEN',flush=True)

if __name__=='__main__':run()
