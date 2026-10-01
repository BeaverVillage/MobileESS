"""Two scientific groups; exact ordered components without arbitrary weights."""
from dataclasses import dataclass
import gurobipy as gp

P1_NAME='MAX_LINE_LOADING'
P2_NAME='MIN_INTERVENTION'
P1_EPS=1e-7
COMPONENT_EPS=1e-8

@dataclass(frozen=True)
class Group:
    name: str
    components: tuple


def aidc_groups(legacy,units,data):
    if [n for n,_ in legacy] != ['rho','reserve_shortfall','CC4_reference_deviation','migration_count','shift_slots','prestart_changes']:
        raise ValueError('UNRECOGNIZED_OR_SUPERSEDING_AIDC_AUTHORITY')
    jobs=data[1]
    magnitude=gp.quicksum(abs(s-jobs[unit['uid']].reference_start)*x
        for unit in units for (site,s),x in unit['v']['y'].items())
    return (Group(P1_NAME,(('rho',legacy[0][1]),)),
            Group(P2_NAME,(('migration_count',legacy[3][1]),
                          ('shift_magnitude',magnitude),
                          ('prestart_relocation',legacy[5][1]))))


def mess_groups(legacy):
    if [n for n,_ in legacy] != ['rho','reserve_shortfall','movement_kwh','movement_count','tie']:
        raise ValueError('UNRECOGNIZED_OR_SUPERSEDING_MESS_AUTHORITY')
    return (Group(P1_NAME,(('rho',legacy[0][1]),)),
            Group(P2_NAME,(('movement_energy',legacy[2][1]),('movement_count',legacy[3][1]))))


def passes(groups):
    if tuple(g.name for g in groups)!=(P1_NAME,P2_NAME):raise ValueError('EXACTLY_TWO_SCIENTIFIC_GROUPS')
    return [(g.name,name,expr) for g in groups for name,expr in g.components]


def relative_gap(incumbent,bound):
    if incumbent is None or bound is None:return None
    if abs(incumbent)<1e-10:return None
    return abs(incumbent-bound)/abs(incumbent)


def integer_certificate(incumbent,bound):
    import math
    if incumbent is None or bound is None:return False
    return abs(incumbent-round(incumbent))<=1e-5 and math.ceil(bound-1e-6)>=round(incumbent)
