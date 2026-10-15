"""Native0 candidate: aggregate per-vehicle route/location/charge-mode hull.

This is a separation diagnostic, not an activated cut, pricing routine or LB.
Actual source adoption requires the original single-path/connection/mode rows,
same-case LP separation, independent validity and a certified global LP bound.
"""
from collections import defaultdict
from fractions import Fraction

import numpy as np


INTEGER_PROOF = (
    "For an original integer vehicle route, at most one STAY site is connected "
    "at a slot (a vehicle in transit has none). The original connection rows "
    "force all other nonnegative Pch/Pdis to zero. If binary charge_mode=0, "
    "every Pch is zero; if charge_mode=1, the sole connected Pch is at most "
    "Pmax. Thus sum_site Pch <= Pmax*charge_mode. Interchanging charge and "
    "discharge proves sum_site Pdis <= Pmax*(1-charge_mode). All Original "
    "integer routes, travel/SOC states and P/Q operations are preserved."
)


def aggregate_mode_hull_diagnostic(domain, p_limit, point=None):
    """Return exact sparse candidates and optional raw LP violations, no solve."""
    limit = Fraction(float(p_limit))
    if limit <= 0:
        raise ValueError("MESS_MODE_HULL_ORIGINAL_POSITIVE_POWER_LIMIT_REQUIRED")
    groups, modes = defaultdict(lambda: {"Pch":[], "Pdis":[]}), {}
    for j, name in enumerate(map(str, domain["names"])):
        if "[" not in name:
            continue
        family, text = name.split("[",1)
        fields = text[:-1].split(",")
        if family in ("Pch", "Pdis"):
            unit, site, tick = fields
            if domain["lower"][j] < 0 or domain["upper"][j] > float(p_limit):
                raise ValueError("MESS_MODE_HULL_ORIGINAL_NONNEGATIVE_P_BOX_REQUIRED")
            groups[unit,int(tick)][family].append(j)
        elif family == "charge_mode":
            unit,tick = fields
            if domain["types"][j] != "B" or domain["lower"][j] != 0 or domain["upper"][j] != 1:
                raise ValueError("MESS_MODE_HULL_ORIGINAL_BINARY_MODE_AUTHORITY_REQUIRED")
            modes[unit,int(tick)] = j
    if not groups or not modes:
        raise ValueError("MESS_MODE_HULL_ORIGINAL_POWER_AND_MODE_AXES_REQUIRED")
    x = None if point is None else np.asarray(point, dtype=np.float64)
    if x is not None and (x.shape != (len(domain["names"]),) or not np.isfinite(x).all()):
        raise ValueError("MESS_MODE_HULL_UNMODIFIED_ROOT_POINT_REQUIRED")
    rows = []
    for key in sorted(groups):
        if key not in modes:
            raise ValueError("MESS_MODE_HULL_POWER_SLOT_HAS_NO_ORIGINAL_MODE")
        mode = modes[key]
        for family in ("Pch", "Pdis"):
            cols = groups[key][family]
            coeff = -limit if family == "Pch" else limit
            rhs = Fraction(0) if family == "Pch" else limit
            terms = {j:Fraction(1) for j in cols}; terms[mode] = coeff
            violation = None if x is None else sum((w*Fraction(float(x[j])) for j,w in terms.items()),Fraction(0))-rhs
            rows.append(dict(name=f"aggregate_{family}_mode_hull[{key[0]},{key[1]}]",
                unit=key[0], slot=key[1], family=family,
                terms={str(j):str(w) for j,w in terms.items()}, rhs=str(rhs), sense="<",
                exact_raw_violation=None if violation is None else str(violation),
                raw_violation=None if violation is None else float(violation),
                robustly_violated=None if violation is None else violation>Fraction(1,10**7)))
    return dict(status="DIAGNOSTIC_ONLY", Native_optimize_calls=0, candidate_rows=rows,
        integer_validity_theorem=INTEGER_PROOF, original_single_integer_route_authority_required=True,
        actual_source_row_authority_independently_verified=False, cuts_adopted=0,
        candidate_count=len(rows), root_point_observed=x is not None,
        robustly_violated_count=None if x is None else sum(r["robustly_violated"] for r in rows),
        strengthened_global_LB=None, K48_improvement="NOT_RUN",
        restricted_pool_bound_used_as_Global_LB=False,
        method="AGGREGATE_SITE_POWER_BINARY_MODE_INTEGER_HULL_CANDIDATE")


def continuous_mode_reselection(domain, p_limit, point):
    """Separate LP witness; never alter the saved raw point or an integer UB.

    If C+D<=Pmax, choose Mode in [C/Pmax,1-D/Pmax]. All aggregate
    power-mode rows can then hold without changing route/P/Q/SOC/objective.
    The caller must replay every ORIGINAL row; this function grants no UB/LB.
    """
    separation=aggregate_mode_hull_diagnostic(domain,p_limit,point)
    x=np.asarray(point,dtype=np.float64).copy();before=x.copy()
    groups=defaultdict(dict)
    for row in separation["candidate_rows"]:groups[row["unit"],row["slot"]][row["family"]]=row
    mode_ids=[];gaps=[]
    for key,rows in groups.items():
        ch=rows["Pch"];dis=rows["Pdis"]
        mode=next(int(j) for j,v in ch["terms"].items() if Fraction(v)<0)
        C=sum(Fraction(float(x[int(j)])) for j,v in ch["terms"].items() if int(j)!=mode and Fraction(v)==1)
        D=sum(Fraction(float(x[int(j)])) for j,v in dis["terms"].items() if int(j)!=mode and Fraction(v)==1)
        lower=C/Fraction(float(p_limit));upper=1-D/Fraction(float(p_limit))
        if lower>upper:return None,dict(status="NOT_CERTIFIED",reason="AGGREGATE_TOTAL_POWER_EXCEEDS_ORIGINAL_PMAX",unit=key[0],slot=key[1])
        x[mode]=float((lower+upper)/2);mode_ids.append(mode);gaps.append(float(upper-lower))
    if np.any(domain["objective"][mode_ids]!=0):raise ValueError("MESS_MODE_RESELECTION_ORIGINAL_OBJECTIVE_DEPENDS_ON_MODE")
    changed=np.flatnonzero(x!=before)
    if not set(changed)<=set(mode_ids):raise ValueError("MESS_MODE_RESELECTION_CHANGED_NONMODE_COORDINATE")
    return x,dict(status="DIAGNOSTIC_ONLY",scope="NEW_CONTINUOUS_LP_WITNESS_NOT_RAW_INTEGER_UB",
        changed_mode_columns=len(changed),route_power_Q_SOC_unchanged=True,
        original_objective_bit_unchanged=float(domain["objective"]@x+domain["constant"])==float(domain["objective"]@before+domain["constant"]),
        minimum_mode_interval_width=min(gaps),physical_integer_execution_claimed=False,
        raw_point_edited=False,Native_optimize_calls=0)
