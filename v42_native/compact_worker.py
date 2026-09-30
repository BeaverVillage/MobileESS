"""Canonical supervised compact build/solve entrypoint."""
def worker(context,payload):
    from v42_compact.execute import worker as run
    return run(context,payload)
def validator(candidate,payload):
    from v42_compact.execute import validator as check
    return check(candidate,payload)
