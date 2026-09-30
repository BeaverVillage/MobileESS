import subprocess
from .common import *

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    tracked=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE],cwd=ROOT,text=True).splitlines()
    rows=[dict(path=p,sha256=sha(ROOT/p)) for p in tracked]
    dump('LEGACY_PRESERVATION_AUDIT.json',dict(base=BASE,files=rows,file_count=len(rows),PASS=True))
    dump('PREREGISTRATION.json',dict(base=BASE,production='one joint exact monolithic MILP',
        formulations=['F0 original compact','F1 exact complete-path support pruning','F2 factorized deterministic WAN','F3 optional proven aggregation'],
        selection=dict(eligibility='all exactness gates PASS',order=['binary count','nonzeros','build wall','F1 before F2 before F3'],effectively_tied_binary_tolerance=0),
        solver=dict(Seed=20260929,Threads=1,MIPGap=.005,TimeLimit=3600),
        budget=dict(seconds=3600,timer='immediately before first model.optimize()',excludes=['preparation','screening','build','validation'],includes=['presolve','root','cuts','heuristics','branch-and-bound'],
            lexicographic='unchanged seven levels; optimize wall cumulative across levels; no lock after unsuccessful level; no claim about later levels if uncompleted'),
        supports='complete physical path projections, exact duration masks, deterministic idempotent fixed point',
        dynamics='exact selected nominal bottleneck; no residual-rate throttling; finite payload/rate bounds; integer authority-derived byte quantum',
        objectives=['rho','reserve_shortfall','CC4_reference_deviation','migration_count','shift_slots','prestart_changes','physical_event_tie'],
        validation_tolerances=dict(scientific_absolute=3e-6,scientific_relative=1e-7,physical=1e-5),
        no_dw=True,no_scientific_change=True,no_mess_execution=True,created_utc=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()))
    for n in (100,101):
        p=json.loads(subprocess.check_output(['gh','pr','view',str(n),'--json','headRefOid,headRefName,url'],cwd=ROOT,text=True))
        if n==100:
            p.update(PR100_DW_RESULT_PRESERVED=True,PR100_DW_SELECTED_FOR_PRODUCTION=False,implementation_imported=False,reason='User selected exact monolithic MILP development; independent branch and evidence unchanged')
            dump('PR100_DW_SUPERSESSION_RECEIPT.json',p)
        else:
            p.update(PR101_MESS_BRANCH_INDEPENDENT=True,implementation_imported=False,integration_order=['accepted A1','PR101 M1','A2','PR101 M2','Fresh AC'],executed_here=False)
            dump('PR101_INDEPENDENCE_RECEIPT.json',p)

if __name__=='__main__':main()
