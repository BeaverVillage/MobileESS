"""Eliminate only the auxiliary z analytically in the saved hull audit."""
from .base import *

def run():
    _,_,_,_,_,_,battery=inputs()
    rows=list(csv.DictReader((OUT/'MODE_HULL_ROOT_VIOLATIONS.csv').open(encoding='utf8')))
    residual=[float(r['Pch_sum'])+float(r['Pdis_sum'])-battery.p_limit*float(r['stay_mass']) for r in rows]
    positive=[x for x in residual if x>TOL]
    dump('MODE_HULL_PHYSICAL_PROJECTION_WITNESS.json',dict(
        diagnostic_only=True,new_constraint_family=False,
        inequality='sum Pch + sum Pdis <= Pmax*y, implied by adding H2 and H3',
        violation_count=len(positive),maximum_violation_kW=max(0.,max(residual)),
        total_positive_violation_kW=sum(positive),tolerance=TOL,
        baseline_physical_LP_point_cannot_be_restored_by_only_changing_z=bool(positive),
        interpretation='The S1 point violation includes physical dispatch projection, not merely unused auxiliary assignments. No bound gain follows from this witness alone.'))

if __name__=='__main__':run()
