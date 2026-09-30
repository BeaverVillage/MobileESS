"""Preregistered formulation switches; no solver-specific tuning."""
def settings(kind):
    legacy={'F2A':dict(runtime=True,aux=True),'F2B':dict(aggregate=True),'F2C':dict(runtime=True,aggregate=True,aux=True)}
    variants={
        'F2-BASE':dict(tie=True),
        'F2-T':{},
        'F2-R':dict(tie=True,runtime=True),
        'F2-TR':dict(runtime=True),
        'F2-A':dict(f0=True,state=True),
        'F2-C':dict(aggregate=True),
        'F2-CRA':dict(runtime=True,aggregate=True,f0=True,state=True,sparse_cardinality=True,scale_wan=True),
        'DA0':{},'DA1':dict(depart=True),'DA2':dict(arrive=True),'DA3':dict(depart=True,arrive=True),
        'LINK':dict(link=True),'F0':dict(f0=True),'STATE':dict(f0=True,state=True),
    }
    d=legacy.get(kind,variants.get(kind))
    if d is None:raise ValueError('UNKNOWN_FORMULATION:'+kind)
    return {**dict.fromkeys(('tie','runtime','aggregate','aux','depart','arrive','link','f0','state','sparse_cardinality','scale_wan'),False),**d}

PRIMARY=['F2-BASE','F2-T','F2-R','F2-TR','F2-A','F2-C','F2-CRA']
