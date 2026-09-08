"""Each spawned MESS process inherits the same day and final 1.15 physics."""
import os,sys,traceback
if os.environ.get('V41R4_MAY_DATE'):
    try:
        from v41r4_electrical import configure
        configure(os.environ['V41R4_MAY_DATE'])
    except BaseException:
        traceback.print_exc(file=sys.stderr);os._exit(78)
