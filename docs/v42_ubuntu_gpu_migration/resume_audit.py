"""Resume checkpoint audits in Linux: bounded equivalence, independent classes, full F2 census."""
import json,time,csv,gc,subprocess
from collections import defaultdict,Counter
from pathlib import Path
from v42_root import common,gates
from v42_root.data import scientific_signature
from v42_root.profile import Census
from v42_boundary.boundaries import load_native
from v42_exact.support import ExactFactory
from v42_exact.native import build
H=Path.home();O=Path(__file__).absolute().parent;R=O.parents[1]
assert json.loads((O/'POST_CLEANUP_VALIDATION.json').read_text())['PASS']
common.frozen();source={str(p.relative_to(R)):common.sha(p) for p in (R/'v42_root').glob('*.py')}
# Redirect bounded evidence only; do not replace the checkpoint's scientific receipts.
old=common.OUT;common.OUT=O;gates.main();common.OUT=old
bounded=json.loads((O/'SCIENTIFIC_AGGREGATION_EQUIVALENCE.json').read_text());assert bounded['PASS'] and len(bounded['cases'])==35
bundle,jobs,bounds,seconds,r,raw=load_native();f=ExactFactory(r,max(b.latest_completion for b in bounds.values()))
classes=defaultdict(list);graphs={};original={};started=time.perf_counter()
for uid,j in sorted(jobs.items()):
    classes[common.digest(scientific_signature(j,bounds[uid],f.original.cache.identity,raw[uid],bundle))].append(uid)
    graphs[uid]=f.graph(j,bounds[uid]);original[uid]=f.original.graph(j,bounds[uid])
sizes=Counter(map(len,classes.values()));summary=dict(jobs=len(jobs),class_count=len(classes),singleton_classes=sizes[1],non_singleton_classes=sum(n for s,n in sizes.items() if s>1),jobs_covered_by_non_singletons=sum(s*n for s,n in sizes.items() if s>1),max_class_size=max(sizes))
assert summary==dict(jobs=1499,class_count=117,singleton_classes=20,non_singleton_classes=97,jobs_covered_by_non_singletons=1479,max_class_size=75)
class Context:
    folder=H/'mobileess_worktrees/RESUMED_ROOT_CENSUS_LOCAL'
    def check(self):pass
    def progress(self,d):common.atomic(self.folder/'build_progress.json',d)
ctx=Context();ctx.folder.mkdir(exist_ok=True)
data=(bundle,jobs,bounds,r,raw,graphs,original,dict(classes=dict(classes),graph_seconds=time.perf_counter()-started,data_prep_seconds=0))
print('RESUMED_FULL_F2_CENSUS_BUILD',flush=True)
with Census() as census:m,v,o,c,b=build(ctx,data,'F2')
rows,maxdensity=census.rows(m);by={x['family']:x for x in rows}
assert (by['Runtime_completion_risk']['rows'],by['Runtime_completion_risk']['nonzeros'])==(1152,34923402)
assert (by['tie']['rows'],by['tie']['nonzeros'])==(273614,14503274)
stats=dict(binary=m.NumBinVars,continuous=m.NumVars-m.NumIntVars,rows=m.NumConstrs,nonzeros=m.NumNZs)
assert stats==dict(binary=2796366,continuous=5124335,rows=9358534,nonzeros=100455768)
with (O/'UBUNTU_RESUMED_ROOT_CENSUS.csv').open('w',newline='') as out:
    writer=csv.DictWriter(out,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
m.dispose();del m,v,o,c,b,data,graphs,original;gc.collect();common.frozen()
assert all(common.sha(R/p)==s for p,s in source.items())
result=dict(ROOT_LP_COMPRESSION_RESUMED=True,PASS=True,runtime='Ubuntu-MobileESS-D Linux native',classes=summary,bounded_cases=35,bounded_equivalence_PASS=True,complete_F2_stats=stats,Runtime=by['Runtime_completion_risk'],tie=by['tie'],max_row_density=maxdensity,scientific_source_unchanged_from_checkpoint=True,global_MIP_start_complete=False,certified_incumbent=False,selected_full_reformulation=None,full_F2ABC_LP_diagnostics_completed=False,production_A1_run=False,next_step='Exact CPU root formulation compression; complete global Runtime/CC4/grid MIP start validation before any production A1',GPU_for_next_production_A1=False)
(O/'UBUNTU_ROOT_COMPRESSION_RESUMPTION.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
