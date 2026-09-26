"""Same Q search and acceptance, with exact-input memoization and slot resume."""
import ast,hashlib,json,time
from pathlib import Path
import numpy as np
import actual_electrical_speed as speed


class PhysicalMemo:
    def __init__(self,evaluate,data,t,folder,q,save,rule_sha):
        self.evaluate=evaluate;self.data=data;self.t=t;self.save=save
        self.cache={};self.hits=0;self.misses=0;self.calls=0;self.final_revalidations=0
        self.started=time.perf_counter()
        token=hashlib.sha256(rule_sha.encode()+q[:t].tobytes())
        token.update(hashlib.sha256(Path(__file__).read_bytes()).digest())
        token.update(hashlib.sha256(Path(speed.__file__).read_bytes()).digest())
        for k in sorted(data):token.update(k.encode());token.update(np.asarray(data[k]).tobytes())
        self.prefix_sha=token.hexdigest();self.folder=folder/'EXACT_STATE_CACHE'/f'slot_{t:02d}'/self.prefix_sha[:16]
        self.folder.mkdir(parents=True,exist_ok=True)
        self.progress=folder/'Q_EVALUATION_PROGRESS.json'

    def report(self):
        self.save(self.progress,dict(status='RUNNING',slot=self.t,logical_Q_evaluations=self.calls,
            cache_hits=self.hits,physical_cache_misses=self.misses,final_clean_revalidations=self.final_revalidations,
            elapsed_s=time.perf_counter()-self.started,prefix_sha=self.prefix_sha,updated_unix=time.time(),
            metadata_builds=dict(speed.COUNTS)))

    def __call__(self,qtrial,allow_state_cache=False):
        self.calls+=1
        # The frozen search's selected-Q revalidation never uses this cache.
        if not allow_state_cache:
            self.final_revalidations+=1;result=self.evaluate(qtrial);self.report();return result
        key=hashlib.sha256(speed.electrical_key(self.data,self.t,qtrial)).hexdigest()
        file_key=key[:24]
        if key in self.cache:
            self.hits+=1;result=self.cache[key]
        elif (self.folder/(file_key+'.json')).exists():
            meta=json.loads((self.folder/(file_key+'.json')).read_text(encoding='utf-8'))
            assert meta['full_key']==key and meta['prefix_sha']==self.prefix_sha
            p=self.folder/(file_key+'.npz')
            assert hashlib.sha256(p.read_bytes()).hexdigest()==meta['arrays_sha256']
            with np.load(p) as a:result={k:a[k].copy() for k in a.files}
            result.update(meta['nonarrays']);self.cache[key]=result;self.hits+=1
        else:
            result=self.evaluate(qtrial);self.cache[key]=result;self.misses+=1
            arrays={k:v for k,v in result.items() if isinstance(v,np.ndarray)}
            rest={k:v for k,v in result.items() if k not in arrays}
            p=self.folder/(file_key+'.npz');np.savez_compressed(p,**arrays)
            self.save(self.folder/(file_key+'.json'),dict(full_key=key,prefix_sha=self.prefix_sha,arrays_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),nonarrays=rest))
        if self.calls%10==0 or self.misses<3:self.report()
        return result


def bind(worker,ns):
    method=worker.METHOD/'robust_search.py'
    text=method.read_text(encoding='utf-8');tree=ast.parse(text)
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='correct_slot')
    original=ast.get_source_segment(text,node)
    assert original.count('r=evaluate(q);cache[key]')==1
    modified=original.replace('r=evaluate(q);cache[key]','r=evaluate(q,allow_state_cache=True);cache[key]')
    bound=dict(ns['correct_slot'].__globals__)
    exec(compile(modified,str(method)+'::exact_state_cache','exec'),bound)
    ns['correct_slot']=bound['correct_slot']
    # Candidate generation, order, cap, objectives, and final uncached call are
    # text-identical. Only eligibility for exact electrical-state caching changes.
    assert modified.replace('evaluate(q,allow_state_cache=True)','evaluate(q)')==original
    tree=ast.parse(worker.source_text)
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_policy')
    runner=ast.get_source_segment(worker.source_text,node)
    runner=runner.replace('2025-05-21','2025-05-01').replace("W/'IEEE8500_numerical_preflight_20260911/AXES.json'","BASE/'AXES.json'")
    patches=[
        ("accepted=[];events=[];trials=[];engine_count=0;solve_count=0", "accepted=[];events=[];trials=[];engine_count=0;solve_count=0;resume_slots=0\n if (folder/'Q_ACCEPTED_CHECKPOINT.json').exists():\n  checkpoint=read(folder/'Q_ACCEPTED_CHECKPOINT.json');assert checkpoint['rule_sha']==sha(H/'RULE_FREEZE.json')\n  resume_slots=int(checkpoint['slots']);events=read(folder/'Q_CONTROL_EVENTS.json');assert len(events)==resume_slots\n  q[:resume_slots]=checkpoint['Q']\n  if np.array_equal(q[:resume_slots],data['Q_EXEC'][:resume_slots]):accepted=baseline[:resume_slots]\n  else:\n   prefix_engine=Electrical(folder/'resume_prefix_runtime',data)\n   try:accepted=[prefix_engine.apply(s,q[s]) for s in range(resume_slots)]\n   finally:prefix_engine.close()\n  save(folder/'SLOT_RESUME_VERIFIED.json',dict(status='PASS',slots=resume_slots,rule_sha=checkpoint['rule_sha'],no_accepted_Q_changed=True))"),
        ('for t in range(96):','for t in range(resume_slots,96):'),
        ("qt,r,event=ns['correct_slot'](evaluate,q[t],lo,hi,q_da=data['Q_DA'][t]);", "memo=PhysicalMemo(evaluate,data,t,folder,q,save,sha(H/'RULE_FREEZE.json'))\n   qt,r,event=ns['correct_slot'](memo,q[t],lo,hi,q_da=data['Q_DA'][t]);memo.report();"),
        ("independent=continuous(folder/'CONTINUOUS_VERIFICATION',data,q)","independent=original_continuous(continuous,folder/'CONTINUOUS_VERIFICATION',data,q)"),
    ]
    for before,after in patches:
        assert runner.count(before)==1,('RUNNER_SOURCE_DRIFT',before)
        runner=runner.replace(before,after)
    globals_=dict(worker.__dict__,PhysicalMemo=PhysicalMemo,original_continuous=speed.original_continuous)
    exec(compile(runner,str(Path(__file__))+'::run_policy','exec'),globals_)
    worker.save(worker.H/'SPEED_RUNTIME_BINDING.json',dict(status='BOUND_AFTER_PREFLIGHT',
        method=worker.rec(method),speed=worker.rec(Path(speed.__file__)),runner=worker.rec(Path(__file__)),
        controller_change='Only cache eligibility for identical physical electrical input; final selected Q forced fresh',
        controller_candidate_sequence_objective_cap_unchanged=True,original_final_independent_engine=True,
        runner_replacements=patches))
    return globals_['run_policy']
