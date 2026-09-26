import sys,json,hashlib,ast
from pathlib import Path
sys.argv=['preflight','B2']
import actual_worker as w
import actual_electrical_speed as speed
from actual_speed_runner import PhysicalMemo
import numpy as np

def main():
    out=w.BASE/'ACTUAL_SPEED_PREFLIGHT_20260922/cache_equivalence_02';out.mkdir(exist_ok=False)
    def save(p,v):Path(p).write_text(json.dumps(v,indent=2,default=lambda x:x.item() if isinstance(x,np.generic) else str(x)),encoding='utf-8')
    with np.load(w.H/'B2/ACTUAL_INPUTS.npz') as z:data={k:z[k].copy() for k in z.files}
    q=data['Q_EXEC'].copy();cp=w.read(w.H/'B2/Q_ACCEPTED_CHECKPOINT.json');q[:cp['slots']]=cp['Q']
    calls=[]
    def physical(qt):
        calls.append(qt.copy());e=w.Electrical(out/f'physical_{len(calls)}',data)
        try:
            for t in range(36):r=e.apply(t,qt if t==35 else q[t])
            return r
        finally:e.close()
    a=np.zeros(6);b=np.zeros(6);a[0]=-200.;b[3]=-200.
    assert data['locations'][35,0]==data['locations'][35,3]=='STA06'
    speed.install(False);ra=physical(a);rb=physical(b)
    assert all(np.array_equal(ra[k],rb[k]) for k in ('v','line','tx','ipu','kva')) and ra['state']==rb['state']
    speed.install();memo=PhysicalMemo(physical,data,35,out,q,save,w.sha(w.H/'RULE_FREEZE.json'))
    x=memo(a,allow_state_cache=True);n=len(calls)
    y=memo(b,allow_state_cache=True);assert len(calls)==n and memo.hits==1
    z=memo(b);assert len(calls)==n+1 and memo.final_revalidations==1
    assert all(np.array_equal(ra[k],r[k]) for r in (x,y,z) for k in ('v','line','tx','ipu','kva'))
    # The controller body changes only the cache eligibility keyword.
    text=(w.METHOD/'robust_search.py').read_text(encoding='utf-8');tree=ast.parse(text)
    source=ast.get_source_segment(text,next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='correct_slot'))
    modified=source.replace('r=evaluate(q);cache[key]','r=evaluate(q,allow_state_cache=True);cache[key]')
    assert modified!=source and modified.replace('evaluate(q,allow_state_cache=True)','evaluate(q)')==source
    report=dict(status='PASS',co_located_Q_allocations_have_bit_identical_full_AC=True,duplicate_physical_state_avoids_engine=True,
        selected_Q_revalidation_forced_fresh=True,original_candidate_generation_and_cap_text_unchanged=True,
        runner_sha256=hashlib.sha256((w.BASE/'actual_speed_runner.py').read_bytes()).hexdigest())
    save(out.parent/'CACHE_EQUIVALENCE_PASS.json',report);print(json.dumps(report),flush=True)
if __name__=='__main__':main()
