from runtime import *
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context

def initialize():
 global DATA,Q,PREFIX_V,PREFIX_TAPS
 DATA=data();Q=DATA['Q_EXEC'].copy();Q[:43]=read(H/'LEGACY_Q_ACCEPTED_CHECKPOINT.json')['Q']
 with np.load(BASE/'actual_B2/B2/ETA95_ACTUAL/OPENDSS_PHASE_ARRAYS.npz') as z:
  PREFIX_V=z['voltage_pu'].copy();PREFIX_TAPS=z['regulator_taps'].copy()

def replay(task):
 trial,t,q=task;check_stop();start=time.perf_counter()
 engine=Electrical(H/f'slot_{t:02}/legacy_trials/{trial:06}',DATA)
 try:
  for s in range(t+1):
   r=engine.apply(s,q if s==t else Q[s])
   if s<t:
    assert r['taps']==PREFIX_TAPS[s].tolist() and np.array_equal(r['v'],PREFIX_V[s]),('ACCEPTED_PREFIX_DRIFT',s)
  return r,time.perf_counter()-start
 finally:engine.close()

class LegacyBatch:
 def __init__(self,t,workers=4):
  self.t=t;self.count=0;self.ledger=[];self.started=time.perf_counter()
  self.pool=ProcessPoolExecutor(max_workers=workers,mp_context=get_context('spawn'),initializer=initialize)
 def many(self,qs):
  check_stop();tasks=[(self.count+i,self.t,np.asarray(q).copy()) for i,q in enumerate(qs)]
  results=list(self.pool.map(replay,tasks));self.count+=len(tasks)
  for task,(r,seconds) in zip(tasks,results):
   self.ledger.append(dict(trial=task[0],slot=self.t,Q=task[2],full_replay_solves=self.t+1,seconds=seconds,feasible=feasible(r),Vmin=float(r['v'].min()),Vmax=float(r['v'].max()),line_max=float(r['line'].max()),transformer_current_max=float(r['tx'].max()),transformer_kVA_max=float(r['kva'].max()),taps=r['taps'],caps=r['caps']))
  save(H/'EXACT_TRIALS.json',self.ledger)
  return [r for r,_ in results]
 def one(self,q):return self.many([q])[0]
 def close(self):self.pool.shutdown(wait=True,cancel_futures=True)
