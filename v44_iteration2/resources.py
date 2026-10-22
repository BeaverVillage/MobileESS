"""Measured rolling admission; a seven-worker ceiling is never a RAM promise."""
import shutil,psutil
G=2**30

def admission(root,*,phase,running=0,peak=0,pilot_complete=False):
 mem=psutil.virtual_memory();disk=shutil.disk_usage(root)
 # Before the first full Actual/Fresh ends, admit one calibration worker only.
 # Afterwards use twice the observed entire process-tree peak plus 1 GiB.
 estimate=max(2*G,2*peak+G) if pilot_complete else 6*G
 needed=8*G if phase=='PLANNING' else estimate
 reserve=6*G
 allowed=mem.available>=needed+reserve and disk.free>=(16*G if phase=='PLANNING' else 4*G)
 if phase=='ACTUAL' and (running>=7 or not pilot_complete and running>=1):allowed=False
 return dict(admit=bool(allowed),phase=phase,available_RAM_bytes=mem.available,total_RAM_bytes=mem.total,
  reserve_RAM_bytes=reserve,additional_worker_RAM_estimate_bytes=needed,observed_Actual_process_tree_peak_bytes=peak,
  pilot_complete=pilot_complete,running=running,max_workers=7,free_disk_bytes=disk.free,
  throttle='NO_NEW_DISPATCH_UNTIL_RESOURCES_RECOVER',seven_at_once_memory_validated=bool(pilot_complete and mem.available>=max(0,7-running)*estimate+reserve))

def rss(identity):
 try:
  p=psutil.Process(identity['pid'])
  if abs(p.create_time()-identity['process_created'])>.001:return 0
  return sum(q.memory_info().rss for q in [p]+p.children(recursive=True) if q.is_running())
 except psutil.Error:return 0
