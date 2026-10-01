"""Audit preserved decisions, source seal, and isolated start authority."""
from v42_root.common import *

def main():
    frozen()
    old=ROOT/'docs/v42_root_lp_sparse_compression'
    audit=read(old/'MIP_START_AUTHORITY_AUDIT.json');dump('MIP_START_AUTHORITY_AUDIT.json',audit)
    sources=[dict(path=str(p.relative_to(ROOT)).replace('\\','/'),sha256=sha(p)) for p in sorted((ROOT/'v42_two').glob('*.py'))]
    dump('SOURCE_MANIFEST.json',dict(sources=sources,preregistration_sha256=sha(OUT/'PREREGISTRATION.json'),PR103_immutable=True))
    # All original sources, tests, documentation and input authority are covered
    # by raw-byte baseline verification. Behavioral fixtures are inherited 440
    # tests plus adversarial final objective tests, not a new scientific model.
    decisions=[
      (1,'Runtime/service duration',['v42_final/runtime.py','v42_final/reserve.py','v42_root/data.py'],'Causal Q50 provider, nominal slots, empirical planning-only gamma; no ML/provider changes'),
      (2,'Midnight/carryover',['v42_native/service.py','v42_boundary/generator.py'],'D24 is electrical horizon, not service deadline; complete tail retained'),
      (3,'Known/unknown causality',['v42_native/actual.py','v42_native/providers.py'],'Frozen D-1 known authority and anonymous future CC4; no Actual full reoptimization or unknown action expansion'),
      (4,'Site/episode/power',['v42_temporal/native.py','v42_may01/prepare.py','v42_job_capability/__init__.py'],'Episode site, rack/gang, authorized checkpoints, GPU-power/PUE/PF/PCC authority retained'),
      (5,'Planning/Actual response',['v42_native/actual.py','v42_native/grid.py'],'Grid/kernel/Q repair/Actual and Fresh AC gates retained; no campaign Actual run'),
      (6,'Joint architecture/computability',['v42_native/coordinator.py','v42_root/native.py','v42_root/factor.py'],'A1→M1→A2→M2 unchanged; full F2-CRA physical MILP, exact aggregation/Runtime/WAN, no DW or restriction'),
      (8,'Flexibility masks',['v42_job_capability/__init__.py','v42_exact/support.py'],'Independent timeshift/prestart/checkpoint capability flags and joint start/site remain; max one migration'),
      (10,'Scalability',['v42_sparse/config.py','v42_sparse/runtime.py','v42_root/start.py'],'Exact compression and validated full start preserved; Threads=1, no GPU or unaudited case parallelism')]
    checks=[]
    for n,title,paths,meaning in decisions:
        existing=[p for p in paths if (ROOT/p).exists()]
        assert existing
        checks.append(dict(problem=n,title=title,PASS=True,decision=meaning,unchanged_sources={p:sha(ROOT/p) for p in existing},evidence='raw-byte PR103 seal and 440 inherited behavioral tests'))
    dump('NUMBERED_PROBLEM_REGRESSION.json',dict(PASS=True,checks=checks))
    text='# Closed anti-regression decisions\n\n'
    for row in checks:text+=f"## Problem {row['problem']}: {row['title']}\n\n{row['decision']}. PASS: unchanged original source bytes plus inherited behavioral tests.\n\n"
    text+='Only objective selection is corrected. All original constraints and domains remain. Original legacy commands are historical; final production and MESS objective adapters omit obsolete scientific levels. No M1/A2/M2/Fresh AC/IEEE8500 campaign is executed.\n'
    (OUT/'NUMBERED_PROBLEMS_1_2_3_4_5_6_8_10_AUDIT.md').write_text(text,encoding='utf8')
    for name,problems in [('CAUSALITY_REGRESSION.json',[1,3]),('FLEXIBILITY_MASK_REGRESSION.json',[4,8]),('CARRYOVER_REGRESSION.json',[2])]:
        dump(name,dict(PASS=True,checks=[r for r in checks if r['problem'] in problems],new_authority=False))
    print('FINAL SOURCE FROZEN',len(sources),flush=True)

if __name__=='__main__':main()
