"""Pure checks for signed pairwise order on unchanged axes."""
import itertools

def sign(d,tol):return 0 if abs(d)<=tol else (1 if d>0 else -1)

def verify(rows):
    result=[]
    for a,b in itertools.combinations(rows,2):
        for axis in ['x','y']:
            ts=sign(float(a[axis])-float(b[axis]),.01)
            es=sign(float(a['e_'+axis])-float(b['e_'+axis]),.01)
            result.append(dict(service_i=a['service_id'],service_j=b['service_id'],axis=axis,
                traffic_delta=float(a[axis])-float(b[axis]),electrical_delta=float(a['e_'+axis])-float(b['e_'+axis]),
                traffic_sign=ts,electrical_sign=es,applicable=ts!=0,PASS=ts==0 or ts==es,
                both_AIDC=a['type']==b['type']=='IDC',
                authority='UNMODIFIED_EPRI_DRAWING_COORDINATES; geographic CRS unverified'))
    return result
