"""Run once before experiments. Preserve every available BASE tracked file."""
import subprocess
from datetime import datetime, timezone
from .common import *

def main():
    require(not (OUT/'PREREGISTRATION.json').exists(), 'ALREADY_PREREGISTERED')
    require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==BASE,'BASE_HEAD')
    names=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE],cwd=ROOT,text=True).splitlines()
    rows=[dict(relative=p,**rec(ROOT/p)) for p in names if (ROOT/p).is_file()]
    dump('BASE_AVAILABLE_MANIFEST.json',dict(base=BASE,rows=rows,available=len(rows),absent=[p for p in names if not (ROOT/p).is_file()]))
    dump('PREREGISTRATION.json',dict(base=BASE,utc=datetime.now(timezone.utc).isoformat(),RC_TOL=RC_TOL,
        PHASE1_TOL=PHASE1_TOL,external_seconds=600,workers=1,threads=1,
        pricing='Exact DAG labels (source, completed service, time); checkpoint prefix minimum propagated through WAIT; all feasible deterministic WAN arcs evaluated. One reconstructed Option per pricing call; no complete-domain production import.',
        phase1='Elasticize every original nonconvexity global row. Equality two nonnegative artificial variables; <= negative artificial; >= positive artificial. Unit cost / max(1,abs(original RHS),max abs original row coefficient). Convexity remains exact. Fix every artificial to zero only after complete exact pricing and objective <=1e-9.',
        levels=['PHASE_I','rho','reserve_shortfall','CC4_reference_deviation','migration_count','shift_slots','prestart_changes','deterministic_tie'],
        locks=dict(rho=1e-7,other=1e-8),initial='One reference STAY if valid; otherwise exact zero-dual pricing. True PR99 graph singletons are constants.',
        coefficient_registry='GPU and risk balances: negative profiles; WAN/active: positive profiles; convexity: +1; intervention metric balances: negative metrics. Prior locks act on metric variables, so direct column coefficient is zero; balance dual propagates lock value.',
        gates=['exhaustive synthetic pricing','bounded real exhaustive pricing','manual RC versus cloned Gurobi RC','CG versus full-column LP','binary full-column versus compact MILP'],
        forbidden=['full option enumeration on May','global PR99 job event/state model','heuristic pricing','branch-and-price','pipeline advancement'],
        relocation='D workspace; legacy files untouched. Existing exact historical source paths remain accessible; record resolved source hashes.'))

if __name__=='__main__':main()
