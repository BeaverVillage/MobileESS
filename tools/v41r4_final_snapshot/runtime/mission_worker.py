"""Dispatch unchanged B3 A0 -> M1 -> A1 -> MF after user clarification."""
import sys
from fast_prepare import ROOT,read,record
import v41r4_search_runtime as runtime
import v41r4_search_worker as worker
from dayahead.v40h.identity import verify_manifest
def configure(day,policy):
    assert policy=='B3'
    return runtime.configure(day,policy)
if __name__=='__main__':
    assert sys.argv[2] in ('B3_DA','B3_AC')
    worker.configure=configure
    worker.main(sys.argv[1],sys.argv[2])
