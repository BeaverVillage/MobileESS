"""Trusted LP-only process entrypoint for the inherited external supervisor."""
def worker(context,payload):
    from v42_dw.execute import worker as run
    return run(context,payload)

def validator(candidate,payload):
    return {'PASS':False,'reason':'DANTZIG_WOLFE_LP_IS_NOT_INTEGER_A1'}
