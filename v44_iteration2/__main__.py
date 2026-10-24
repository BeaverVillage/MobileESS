from pathlib import Path
import argparse

def main():
 p=argparse.ArgumentParser();mode=p.add_mutually_exclusive_group(required=True)
 mode.add_argument('--prepare',action='store_true');mode.add_argument('--run',action='store_true');mode.add_argument('--worker',type=Path)
 mode.add_argument('--monitor',action='store_true');mode.add_argument('--authorize');mode.add_argument('--preflight',action='store_true')
 p.add_argument('--port',type=int,default=8795);a=p.parse_args()
 if a.prepare:
  from .catalog import prepare
  prepare()
 elif a.authorize:
  from .authority import authorize
  authorize(a.authorize)
 elif a.preflight:
  from .preflight import check
  check()
 elif a.worker:
  from .worker import run
  run(a.worker)
 elif a.monitor:
  from .monitor import serve
  serve(a.port)
 else:
  from .supervisor import run
  run()

if __name__=='__main__':main()
