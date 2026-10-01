"""Gate optional extra CPU test on actual MIP root LP, never standalone LP."""
def root_measurement(p):
    root=p.get('root') or {}
    complete=bool(root.get('LP_complete') or root.get('status')=='cutoff' or p['status']==2)
    seconds=root.get('seconds')
    if seconds is None and p['status']==2:seconds=0. # Solved by presolve/start without a root relaxation.
    return complete,seconds
def extra_allowed(p):
    complete,seconds=root_measurement(p)
    return not complete or seconds is None or seconds>300.
def four_is_better(one,four):
    a,x=root_measurement(one);b,y=root_measurement(four)
    if b and not a:return True
    if a and b and y is not None and x is not None and y<x:return True
    return False
