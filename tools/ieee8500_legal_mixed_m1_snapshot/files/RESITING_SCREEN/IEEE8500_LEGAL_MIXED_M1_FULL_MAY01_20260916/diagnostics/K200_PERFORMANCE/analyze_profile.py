import pathlib,json,collections,statistics
D=pathlib.Path(__file__).absolute().parent
d=json.loads((D/'live_480s.speedscope.json').read_text());frames=d['shared']['frames'];counts=collections.Counter()
for p in d['profiles']:
 for sample,weight in zip(p['samples'],p['weights']):
  fs=[frames[i] for i in sample];names=[f['name'] for f in fs];leaf=fs[-1] if fs else {}
  if 'evaluate_opportunity_dispatch' in names or '_cached_anchored_polygon_loading' in names:cat='affine_electrical_evaluation'
  elif any(f['name']=='solve_fixed_candidate_certified' and f.get('line')==1102 for f in fs):cat='gurobi_optimize'
  elif any(n in names for n in ['build_fixed_candidate_model','_add_fixed_line','_add_fixed_voltage','_add_fixed_tx_current','_add_fixed_tx_kva','_fixed_expression']) or (leaf.get('name')=='<genexpr>' and 907<=leaf.get('line',0)<=925):cat='electrical_model_materialization'
  elif any('execution_acceleration.py' in f.get('file','') for f in fs):cat='cache_serialization_io'
  elif any(f['name']=='_solve_item' and f.get('line')==252 for f in fs):cat='model_dispose'
  else:cat='other_or_incomplete_stack'
  counts[cat]+=weight
counts['unsampled_or_errors']=480-sum(counts.values())
t=json.loads((D/'timing_cache_summary.json').read_text());median=statistics.median(t['current_runtime_seconds']);residual=statistics.median(t['advance_residual_seconds']);advance=median+residual
rows={k:{'sampled_seconds_480s':v,'window_percent':v/480*100,'estimated_seconds_per_advance':v/480*advance} for k,v in counts.items()}
resources=[json.loads(s) for s in (D/'resource_samples.jsonl').read_text().splitlines()];first,last=resources[0],resources[-1];dt=last['unix']-first['unix'];a={p['pid']:p for p in first['processes']};b={p['pid']:p for p in last['processes']};proc=[]
for pid,p in a.items():
 if pid not in b:continue
 q=b[pid];cpu=lambda r:r['cpu']['user']+r['cpu']['system']
 proc.append({'pid':pid,'cmdline':p['cmdline'],'average_cpu_cores':(cpu(q)-cpu(p))/dt,'rss_end_gib':q['memory']['rss']/2**30,'read_MiB_s':(q['io']['read_bytes']-p['io']['read_bytes'])/dt/2**20,'write_MiB_s':(q['io']['write_bytes']-p['io']['write_bytes'])/dt/2**20})
out={'method':'5Hz nonblocking external sampling; 480s window, 2328 samples, 44 reported sampling errors; approximate wall allocation, NOT exact function timers','categories':rows,'reference_candidate_runtime_median_seconds':median,'reference_advance_overhead_median_seconds':residual,'resource_span_seconds':dt,'system_cpu_mean_percent':statistics.mean(statistics.mean(r['cpu_per_core_percent']) for r in resources[1:]),'available_RAM_GiB_range':[min(r['memory']['available'] for r in resources)/2**30,max(r['memory']['available'] for r in resources)/2**30],'processes':proc,'paging_caveat':'Windows psutil swap sin/sout cannot establish hard-page-fault rate; do not interpret zero as proof of no paging.'}
(D/'profile_analysis.json').write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps(out,indent=2))
