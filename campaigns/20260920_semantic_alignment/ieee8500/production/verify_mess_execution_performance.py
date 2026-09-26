"""Equivalence checks for the I/O-only MESS adapters (no optimization)."""
from bootstrap import *
from mess_execution_performance import evaluate_grid as fast, install_short_candidate_paths
from full_electrical_rows import evaluate_grid as original
from dayahead.v40a.grid import controls_from_trajectory

class Counted(Coefficients):
 def __init__(self): self.passes=0;self.yields=0
 def __iter__(self):
  self.passes+=1
  for t in range(96):
   self.yields+=1
   yield self[t]

def main():
 out=P/'performance_verification';out.mkdir(exist_ok=True)
 with np.load(P/'MAY01_B0_AIDC_POWER.npz') as z:pcc=z['pcc'].copy()
 oldc=Counted();controls=controls_from_trajectory(oldc,pcc,())
 start=time.perf_counter();before=original(oldc,controls,AX['nodes']);old_seconds=time.perf_counter()-start
 newc=Counted();start=time.perf_counter();after=fast(newc,controls,AX['nodes']);new_seconds=time.perf_counter()-start
 assert before==after,'FULL_96_SLOT_EVALUATION_CHANGED'
 assert (oldc.passes,oldc.yields,newc.passes,newc.yields)==(2,192,1,96)
 from dayahead.v40h.candidate_cache import CandidateResultCache
 identities=sorted((P/'B2/inherited_search').glob('*/M1_IDENTITY.json'),key=lambda p:p.stat().st_mtime)
 identity=read(identities[-1])
 context=dict(V40H_execution_identity=identity,execution_fingerprint_sha256=identity['identity_SHA'],beam_parent_fingerprint='DIAGNOSTIC_ONLY',fixed_previous_MESS_trajectory_SHA='DIAGNOSTIC_ONLY',parent_state_content_SHA='DIAGNOSTIC_ONLY',fixed_previous_MESS_trajectory_exact_SHA='DIAGNOSTIC_ONLY')
 install_short_candidate_paths(out,save,read)
 long_root=out/('long_'+'a'*100)/('path_'+'b'*100)/'candidates'
 cache=CandidateResultCache(long_root,context);spec=cache.specification('DIAGNOSTIC_ONLY',0)
 cache.store(spec,dict(marker='NO_PRODUCTION_SOLUTION'))
 assert cache.load(spec)==dict(marker='NO_PRODUCTION_SOLUTION')
 stale=dict(spec,identity_sha256='CHANGED');assert cache.load(stale) is None
 # Restore the valid diagnostic cache after the deliberate mismatch check.
 cache.store(spec,dict(marker='NO_PRODUCTION_SOLUTION'))
 assert len(str(Path(spec['path']).with_suffix('.tmp.123456.12345678')))<260
 receipt=dict(status='PASS',full_96_slot_result_exactly_equal=True,original_coefficient_iterations=oldc.passes,new_coefficient_iterations=newc.passes,original_coefficient_loads=oldc.yields,new_coefficient_loads=newc.yields,original_wall_seconds=old_seconds,new_wall_seconds=new_seconds,cache_identity_checks_preserved=True,cache_roundtrip_PASS=True,temporary_path_length=len(str(Path(spec['path']).with_suffix('.tmp.123456.12345678'))),sources=[record(P/'mess_execution_performance.py'),record(P/'full_electrical_rows.py')])
 save(out/'RESULT.json',receipt);print(json.dumps(receipt),flush=True)

if __name__=='__main__':main()
