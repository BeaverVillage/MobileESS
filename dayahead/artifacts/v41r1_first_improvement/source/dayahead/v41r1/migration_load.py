"""Exact interval incidence, either dense in time or as its first difference.

For each chosen interval [a,b), delta[lo] += weight and delta[hi] -= weight,
with lo=max(a,D00), hi=min(b,D24). Then G[t]=G[t-1]+delta[t], G[-1]=0.
Summing the recurrence gives exactly the original interval occupancy rows.
Subtracting consecutive original rows gives the recurrence. Thus this is an
invertible row transformation even in the LP relaxation, not candidate pruning.
No grid row, objective, service amount or decision variable is removed.

Callers supply canonical compute segments separately: the source END event
is checkpoint departure, destination START is restart. The pause/WAN interval
has no compute segment and therefore no GPU occupancy. Never pass a migrated
job's overall start/end envelope here.
"""
from .migration import BEGIN


def add_interval(load,site,start,end,weight,slots,*,event_form):
    lo=max(BEGIN,start);hi=min(BEGIN+slots,end)
    if lo>=hi:return
    if event_form:
        load[lo-BEGIN,site]+=weight
        if hi<BEGIN+slots:load[hi-BEGIN,site]-=weight
    else:
        for t in range(lo,hi):load[t-BEGIN,site]+=weight
