"""Check completed historical stages against their exact preserved source bytes."""
from pathlib import Path
from unittest.mock import patch
from . import config as c
from .io import read,verify


def verify_historical(rows):
 snapshots={}
 authority=c.OPS/'AUTHORIZATION.json'
 manifests=read(authority).get('historical_source_manifests',[]) if authority.exists() else []
 for receipt in manifests:verify([receipt])
 for manifest in [Path(r['path']) for r in manifests]:
  for item in read(manifest)['files']:
   original=item['original']
   snapshots[(str(Path(original['path']).resolve()),original['bytes'],original['sha256'])]=item['snapshot']
 for receipt in rows:
  try:verify([receipt])
  except (OSError,ValueError):
   saved=snapshots.get((str(Path(receipt['path']).resolve()),receipt['bytes'],receipt['sha256']))
   if saved is None:raise
   verify([saved])
   if (saved['bytes'],saved['sha256'])!=(receipt['bytes'],receipt['sha256']):raise ValueError('HISTORICAL_SOURCE_BYTES_DRIFT')


def checked_completed(path,request):
 from .bootstrap import equipment
 from v44 import checkpoints
 # A completed immutable checkpoint may cite an older controller version.
 # Only sealed exact historical bytes resolve those receipts. Hardware, key,
 # checkpoint SHA, result files and all other scientific checks stay original.
 with equipment.scope(),patch.object(checkpoints,'verify',verify_historical):
  return checkpoints.checked(path,request,'COMPLETED')
