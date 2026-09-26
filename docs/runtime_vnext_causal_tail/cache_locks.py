"""Process locks for independent cache producers and the single GPU allocation."""
from common import ROOT
from contextlib import contextmanager
import time,msvcrt

@contextmanager
def file_lock(name):
 directory=ROOT/'locks';directory.mkdir(exist_ok=True);path=directory/(name+'.lock')
 with path.open('a+b') as stream:
  stream.seek(0,2)
  if stream.tell()==0:stream.write(b'0');stream.flush()
  while True:
   try:stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1);break
   except OSError:time.sleep(.5)
  try:yield
  finally:stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
