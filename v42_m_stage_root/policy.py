"""The existing 1e-8 numerical authority; no engineering RC relaxation."""
EPS=1e-8

def convergence_certificate(certificate,prices,true_key):
    if not certificate.get('certified') or certificate.get('dual_SHA')!=true_key:return False
    if len(prices)!=4 or {p['unit'] for p in prices}!={0,1,2,3}:return False
    return all(p['type']=='FINAL_CERTIFICATION' and p['native_status']==2 and p['valid_bound']
        and p['valid_point'] and p['full_original_domain'] and not p.get('stabilized_discovery',False)
        and p['dual_SHA']==p['true_dual_SHA']==true_key and p['ObjBound']>=-EPS
        and p['rc_inc']>=-EPS and abs(p['rc_inc']-p['ObjBound'])<=EPS for p in prices)
