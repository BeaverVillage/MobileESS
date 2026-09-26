"""Existing campaign report with the validated B2 Actual result authority."""
from pathlib import Path
import hashlib
BASE=Path(__file__).absolute().parent
F=BASE.parent/'IEEE8500_QSAFE_V2_LEGACY_SHELL_20260913'
import finalize_campaign as original
if __name__=='__main__':
 done=original.read(F/'B2_ACTUAL_COMPLETE.json')
 assert done['status']=='PASS' and original.sha(done['result']['path'])==done['result']['sha256']
 old_read=original.read
 def read(p):
  if Path(p)==BASE/'actual_B2/B2/COMPLETE.json':p=F/'B2/COMPLETE.json'
  return old_read(p)
 original.read=read
 original.main()
