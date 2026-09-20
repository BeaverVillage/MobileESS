from bootstrap import *
import mess_anchor_cache as cache
import dayahead.v28r2.electrical_subproblem as electrical

def main():
 cs=[build(0),build(74)];controls=[c.anchor.copy() for c in cs]
 started=time.perf_counter();expected=[]
 for _ in range(12):
  for c,x in zip(cs,controls):expected.append(electrical.anchored_polygon_loading(c,x))
 old=time.perf_counter()-started
 fn,stats,original=cache.make_cache(cs,256*2**20)
 electrical.anchored_polygon_parameters=fn
 try:
  started=time.perf_counter();actual=[]
  for _ in range(12):
   for c,x in zip(cs,controls):actual.append(electrical.anchored_polygon_loading(c,x))
  new=time.perf_counter()-started
  assert all(np.array_equal(a,b) for a,b in zip(actual,expected))
  returned=fn(cs[0]);returned[0][:]=123
  assert all(np.array_equal(a,b) for a,b in zip(fn(cs[0]),original(cs[0]))),'CACHE_ARRAY_ALIAS'
  for c in cs:
   x=c.anchor.copy();x[12:]=np.linspace(-100,100,48)
   electrical.anchored_polygon_parameters=original;before=electrical.anchored_polygon_loading(c,x)
   electrical.anchored_polygon_parameters=fn;after=electrical.anchored_polygon_loading(c,x)
   assert np.array_equal(before,after)
 finally:electrical.anchored_polygon_parameters=original
 result=dict(status='PASS',slots=[0,74],all_branch_values_bitwise_equal=True,independent_returned_arrays=True,unchanged_original_calculation=True,calls=24,original_wall_seconds=old,cached_wall_seconds=new,stats=stats,sources=[record(P/'mess_anchor_cache.py'),record(electrical.__file__)],scope='MESS child only; fixed immutable coefficient tuple; no running AIDC mutation')
 save(P/'performance_verification/ANCHOR_CACHE.json',result);print(json.dumps(result),flush=True)
if __name__=='__main__':main()
