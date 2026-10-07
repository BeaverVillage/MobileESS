"""Read-only causal control: remove mode-coordinate separator without P/Q edit.

This is not a new solve, UB, LB or full trajectory-hull membership certificate.
"""
from common import *
from common_mode_separator import supports
from fractions import Fraction as F

def main():
    a=Authority();A,d,_=load()
    with np.load(HISTORY/'PURE_LP_POINT.npz') as z:x=z['x'].copy()
    new=x.copy();items=[]
    for t in range(69,73):
        required={0:F(0),1:F(0)}
        for sid,site in enumerate(a.sites):
            if f'Q[MESS04,{site},{t}]' not in a.names:continue
            physical={k:a.value(n,x) for k,n in {'y':f'arc[MESS04,{sid*96+t}]','C':f'Pch[MESS04,{site},{t}]','D':f'Pdis[MESS04,{site},{t}]','Q':f'Q[MESS04,{site},{t}]'}.items()}
            for target in (0,1):
                values=dict(physical)
                if target==1:values['C'],values['D']=physical['D'],physical['C']
                _,candidates=supports(a,'MESS04',site,t,targetmode=target)
                required[target]+=max(sum(terms.get(k,F(0))*v for k,v in values.items()) for _,terms in candidates)
        lo=required[1];hi=1-required[0];old=a.value(f'charge_mode[MESS04,{t}]',x)
        assert lo<=hi,'EXACT_LOCAL_MODE_INTERVAL_EMPTY'
        value=old if lo<=old<=hi else (lo+hi)/2
        expr,constant=a.expression(f'charge_mode[MESS04,{t}]');assert len(expr)==1 and constant==0
        j,w=next(iter(expr.items()));assert w==1;new[j]=float(value)
        items.append(dict(slot=t,old_mode=float(old),minimum_compatible_mode_exact=str(lo),maximum_compatible_mode_exact=str(hi),minimum_compatible_mode=float(lo),maximum_compatible_mode=float(hi),chosen_mode=float(value),changed=old!=value,exact_common_mode_separator_after_relabel=float(required[0]+F.from_float(float(value))-1)))
    mask=np.char.startswith(d['names'],'charge_mode[')
    assert np.array_equal(x[~mask],new[~mask])
    np.savez_compressed(OUT/'MODE_RELABELED_PROXY_POINT.npz',x=new)
    write('MODE_COORDINATE_CAUSAL_CONTROL.json',dict(rows=items,optimize_calls=0,all_non_mode_coordinates_bit_identical=True,objective_before=float(d['objective']@x),objective_after=float(d['objective']@new),strict_C3A_raw_before=replay(A,d,x),strict_C3A_raw_after=replay(A,d,new),not_a_new_valid_UB_or_LB=True,full_four_slot_hull_membership_not_claimed=True,causal_interpretation='The proved t71 mode/location/PQ separator can be removed by changing an objective-zero mode coordinate alone. It does not require changing critical P/Q, routes or SOC. This prevents attributing objective gap to that separator or to temporal SOC solely because stored full coordinates were outside the hull. Whole four-slot/global effects are tested separately.'))
    print('MODE_ONLY_CONTROL',items,flush=True)

if __name__=='__main__':main()
