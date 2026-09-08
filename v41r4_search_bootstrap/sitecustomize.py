"""Propagate unchanged 1.15 physics and safe artifact I/O to MESS children."""
import os,sys,traceback
if os.environ.get('V41R4_MAY_DATE'):
    try:
        from v41r4_electrical import configure
        configure(os.environ['V41R4_MAY_DATE'])
        from v41r4_search_io import install
        install()
    except BaseException:
        traceback.print_exc(file=sys.stderr);os._exit(78)
