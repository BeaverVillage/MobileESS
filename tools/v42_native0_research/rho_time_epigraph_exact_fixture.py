"""Exact rational rho-time extension/projection fixture; no solver imports."""
from datetime import datetime,timezone
from fractions import Fraction as F
from itertools import product
from pathlib import Path
import hashlib,json,time

def original_feasible(x,rho):
    return 0<=rho<=1 and 0<=x<=1 and x-F(1,2)*rho<=F(1,4) and F(2)*x-rho<=F(3,4) and -x-F(2)*rho<=F(-1,4) and x+rho>=F(1,4)

def extension_feasible(x,rho,tau):
    return (0<=rho<=1 and 0<=x<=1 and len(tau)==3 and all(0<=v<=1 and v<=rho for v in tau)
        and x-F(1,2)*tau[0]<=F(1,4) and F(2)*x-tau[1]<=F(3,4)
        and -x-F(2)*tau[2]<=F(-1,4) and x+rho>=F(1,4))

def fixture():
    started=time.perf_counter();grid=tuple(F(k,4) for k in range(5));forward=reverse=0
    for x,rho in product(grid,repeat=2):
        if original_feasible(x,rho):
            assert extension_feasible(x,rho,(rho,rho,rho));forward+=1
        for tau in product(grid,repeat=3):
            if extension_feasible(x,rho,tau):
                assert original_feasible(x,rho);reverse+=1
    assert forward>0 and reverse>forward
    # Fractional mode/int axes untouched: x may be any real or restricted integer.
    integer_forward=sum(original_feasible(x,rho) for x,rho in product((F(0),F(1)),grid))
    assert all(not original_feasible(x,rho) or extension_feasible(x,rho,(rho,)*3) for x,rho in product((F(0),F(1)),grid))
    # Both failures are explicit feasible points of the incorrectly changed model.
    positive_coefficient_counterexample=dict(rho='1',tau='0',old_row='rho<=1/2',wrong_new_row='tau<=1/2',old_feasible=False,wrong_new_feasible=True)
    assert F(0)<=F(1,2) and F(0)<=F(1) and not F(1)<=F(1,2)
    reversed_link_counterexample=dict(x='1',rho='0',tau='1',old_row='x-rho<=0',wrong_new_rows=['x-tau<=0','rho<=tau'],old_feasible=False,wrong_new_feasible=True)
    assert F(1)-F(1)<=0 and F(0)<=F(1) and not F(1)-F(0)<=0
    inward_helper_bound_counterexample=dict(x='1',rho='1',required_tau='1',wrong_tau_upper='1/2',old_feasible=True,wrong_extension_feasible=False)
    assert F(1)-F(1)<=0 and F(1)>F(1,2)
    packet=dict(schema='EXACT_RHO_TIME_EPIGRAPH_RATIONAL_FIXTURE_V1',PASS=True,UTC=datetime.now(timezone.utc).isoformat(),all_horizon_mathematical_proof=True,
        theorem=dict(original_row='g_i(x)+c_i*rho<=b_i',condition='All replaced normalized stored coefficients c_i<=0. All unchanged rho rows, bounds, type and objective remain exactly original.',extension='g_i(x)+c_i*tau_t<=b_i; tau_t-rho<=0; helper continuous bounds contain the actual global rho interval; helper objective0',forward='For every original feasible real/integer point, set all tau_t=rho. Every replaced row and link holds. No arithmetic or coefficient approximation is needed.',reverse='For every extension feasible point, tau_t<=rho and c_i<=0 imply g_i(x)+c_i*rho<=g_i(x)+c_i*tau_t<=b_i. Drop the helpers; every original row remains feasible.',objective='The objective uses only unchanged original coordinates, so its value and projected integer optimum and LP optimum are exactly preserved.',integer='All original integer types/domains are untouched. New tau coordinates are continuous.',exactness='Every stored coefficient/RHS/bound is copied unchanged; relocation of an original rho coefficient does not compute a new coefficient. Link coefficients +/-1 and RHS0 are exactly binary64-representable.'),
        small_fixture=dict(slots=3,original_points_checked=25,extended_points_checked=3125,original_feasible_points=forward,extended_feasible_points=reverse,original_integer_feasible_points=integer_forward,unchanged_positive_rho_row='x+rho>=1/4 retained exactly',grid='0,1/4,1/2,3/4,1',scope='Finite rational fixture illustrates but does not replace the general real-domain proof'),
        counterexamples=[positive_coefficient_counterexample,reversed_link_counterexample,inward_helper_bound_counterexample],
        Native_calls=0,model_builds=0,production_matrix_mutations=0,rows_inserted=0,columns_inserted=0,wall_seconds=time.perf_counter()-started)
    p=Path(r'D:\v42_multitime_audit_20261011\EXACT_RHO_TIME_EPIGRAPH_FIXTURE.json');p.write_text(json.dumps(packet,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(PASS=True,receipt=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),fixture=packet['small_fixture'],wall_seconds=packet['wall_seconds'])))

if __name__=='__main__':fixture()
