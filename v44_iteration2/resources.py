"""Disk admission and Actual max7; RAM telemetry never blocks dispatch."""
import shutil,psutil
G=2**30

def admission(root,*,phase,running=0,peak=0,pilot_complete=False):
 mem=psutil.virtual_memory();disk=shutil.disk_usage(root)
 # Keep existing RAM estimates as telemetry, per the user's no-RAM-gate policy.
 estimate=max(2*G,2*peak+G) if pilot_complete else 6*G
 needed=8*G if phase=='PLANNING' else estimate
 reserve=6*G
 allowed=disk.free>=(16*G if phase=='PLANNING' else 4*G)
 if phase=='ACTUAL':allowed=running<7 and disk.free>=4*G
 return dict(admit=bool(allowed),phase=phase,available_RAM_bytes=mem.available,total_RAM_bytes=mem.total,
  reserve_RAM_bytes=reserve,additional_worker_RAM_estimate_bytes=needed,observed_Actual_process_tree_peak_bytes=peak,
  pilot_complete=pilot_complete,running=running,max_workers=7,free_disk_bytes=disk.free,
  throttle='MAX7_AND_DISK_GUARD' if phase=='ACTUAL' else 'DISK_GUARD',
  planning_RAM_admission_enabled=False,actual_RAM_admission_enabled=False,seven_at_once_memory_validated=False)

def rss(identity):
 try:
  p=psutil.Process(identity['pid'])
  if abs(p.create_time()-identity['process_created'])>.001:return 0
  return sum(q.memory_info().rss for q in [p]+p.children(recursive=True) if q.is_running())
 except psutil.Error:return 0
