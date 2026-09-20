import json,time,pathlib,psutil
D=pathlib.Path(__file__).absolute().parent
H=D.parent.parent
psutil.cpu_percent(percpu=True)
with (D/'resource_samples.jsonl').open('w',encoding='utf-8') as out:
 for i in range(96):
  row={'unix':time.time(),'cpu_per_core_percent':psutil.cpu_percent(percpu=True),'memory':psutil.virtual_memory()._asdict(),'swap':psutil.swap_memory()._asdict(),'disk':psutil.disk_io_counters()._asdict(),'processes':[]}
  for p in psutil.process_iter(['pid','name']):
   if 'python' not in (p.info['name'] or '').lower() and p.pid!=45528:continue
   try:row['processes'].append({'pid':p.pid,'cmdline':p.cmdline(),'cpu':p.cpu_times()._asdict(),'memory':p.memory_info()._asdict(),'io':p.io_counters()._asdict(),'threads':p.num_threads()})
   except (psutil.NoSuchProcess,psutil.AccessDenied):pass
  try:row['live']=json.loads((H/'STATUS.json').read_text())
  except Exception as e:row['read_error']=repr(e)
  out.write(json.dumps(row)+'\n');out.flush();time.sleep(5)
