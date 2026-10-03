"""Exact terminal current and apparent-power reads, with NormalAmps current only."""
import math
from .authority import checked_normal,current_authority

def branch_measurement(odd,branch):
    odd.Circuit.SetActiveElement(branch.branch_id)
    if odd.CktElement.Name().lower()!=branch.branch_id.lower():raise ValueError('COMPILED_BRANCH_NOT_FOUND')
    n=int(odd.CktElement.NumConductors());buses=[s.split('.')[0].lower() for s in odd.CktElement.BusNames()]
    terminal=buses.index(branch.parent_bus.lower());nodes=list(map(int,odd.CktElement.NodeOrder()))
    currents=list(map(float,odd.CktElement.CurrentsMagAng()));powers=list(map(float,odd.CktElement.Powers()))
    phase='ABC'.index(branch.phase)+1
    local=next(i for i in range(n) if nodes[terminal*n+i]==phase);i=terminal*n+local;amps=currents[2*i]
    if branch.branch_id.startswith('line.'):
        odd.Lines.Name(branch.branch_id.split('.',1)[1]);limit=float(odd.Lines.NormAmps());loading=math.nan
    else:
        if terminal!=0:raise ValueError('NORMALAMPS_FIRST_WINDING_AUTHORITY_REQUIRED')
        limit=checked_normal(odd.Properties.Value('NormAmps'),branch.branch_id)
        authority=current_authority();key=f'{branch.branch_id}::{branch.phase}'
        expected=next(r['NormalAmps'] for r in authority['rows'] if r['branch_phase']==key)
        if limit!=expected:raise ValueError('LIVE_NORMALAMPS_AUTHORITY_DRIFT')
        odd.Transformers.Name(branch.branch_id.split('.',1)[1]);odd.Transformers.Wdg(terminal+1)
        kva=float(odd.Transformers.kVA());positions=[terminal*n+j for j in range(n) if nodes[terminal*n+j] in (1,2,3)]
        loading=math.hypot(sum(powers[2*j] for j in positions),sum(powers[2*j+1] for j in positions))/kva
    if limit<=0:raise ValueError('INVALID_CURRENT_LIMIT')
    return amps,amps/limit,loading
