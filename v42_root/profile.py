"""Actual complete PR102 matrix census, before successor reformulation."""
import sys,linecache,gc
from collections import defaultdict,Counter
import numpy as np,gurobipy as gp,psutil
from .common import *
from .data import prepare
from v42_exact.native import build

def category(frame):
    filename=frame.f_code.co_filename.replace('\\','/');fn=frame.f_code.co_name;line=frame.f_lineno
    code=linecache.getline(filename,line)
    if filename.endswith('/factor.py'):
        if fn=='tie_expression':return 'tie'
        if 'active.get' in code:return frame.f_locals.get('n','state')+'_balance'
        if 'depart' in code:return 'depart_linking'
        if 'arrive' in code:return 'arrive_linking'
        if 'remaining' in code or 69<=line<=83:return 'WAN_payload_dynamics'
        if 'u<=' in code or 'member==' in code:return 'link_bytes_linking'
        return 'factor_event_logic'
    if filename.endswith('/formulation.py'):
        if 'lhs==' in code:return frame.f_locals.get('state','state')+'_balance'
        return 'compact_event_service'
    if filename.endswith('/v42_exact/native.py'):
        if 'riskrows' in code:return 'Runtime_completion_risk'
        if 'gpurows' in code:return 'resource_GPU'
        if 'wanrows' in code:return 'resource_WAN'
        if 'active=' in code:return 'resource_active_transfers'
        return 'native_binding'
    if '/service.py' in filename or 'CC4' in code:return 'CC4'
    if '/reserve.py' in filename:return 'Runtime_CC4_reserve_headroom'
    if '/grid.py' in filename:return 'native_grid'
    if '/model.py' in filename:return 'grid_CC4_allocation'
    return filename.split('/')[-2]+'/'+filename.split('/')[-1]+':'+fn

class Census:
    def __init__(self):self.tags=[];self.codes={};self.labels=[];self.original=gp.Model.addConstr
    def __enter__(self):
        def trace(model,*args,**kw):
            frame=sys._getframe(1);label=category(frame)
            if label not in self.codes:self.codes[label]=len(self.labels);self.labels.append(label)
            self.tags.append(self.codes[label]);return self.original(model,*args,**kw)
        gp.Model.addConstr=trace;return self
    def __exit__(self,*args):gp.Model.addConstr=self.original
    def rows(self,m):
        A=m.getA();nz=np.diff(A.indptr);tags=np.asarray(self.tags,dtype=np.int16)
        if len(tags)!=m.NumConstrs:raise ValueError('INCOMPLETE_CENSUS')
        rows=[]
        for i,label in enumerate(self.labels):
            selected=nz[tags==i];rows.append(dict(family=label,rows=len(selected),nonzeros=int(selected.sum()),average_nonzeros_per_row=float(selected.mean()),maximum_nonzeros_per_row=int(selected.max())))
        return rows,int(nz.max())

def column_profile(m,v):
    counts=Counter();labelled=set()
    for vv in v.values():
        for family,items in vv.items():
            for x in items.values():
                if not isinstance(x,gp.Var):continue
                counts[family,x.VType]+=1;labelled.add(x.index)
    for x in m.getVars():
        if x.index not in labelled:
            name=x.VarName
            family='CC4' if name.startswith('CC4') else 'Runtime' if name.startswith(('RT_', 'risk[')) else 'known_GPU' if name.startswith('known[') else 'grid_and_global'
            counts[family,x.VType]+=1
    return [dict(family=n,type={'B':'binary','I':'integer','C':'continuous'}[typ],variables=c,percentage_total_columns=100*c/m.NumVars) for (n,typ),c in sorted(counts.items())]

def main():
    frozen();data=prepare();print('baseline full matrix build',flush=True)
    with Census() as census:m,v,o,c,b=build(Context(),data,'F2')
    print('baseline matrix census',flush=True);rows,maxdensity=census.rows(m);cols=column_profile(m,v)
    table('ROOT_LP_FAMILY_PROFILE.csv',cols);table('ROOT_LP_NONZERO_PROFILE.csv',rows)
    stats=read(LOCAL/'F2_MODEL_COMPLETE.json');stats.update(columns=m.NumVars,max_row_density=maxdensity,profiled=True)
    dump('F2_MODEL_STATS.json',stats)
    assert sum(x['variables'] for x in cols)==m.NumVars and sum(x['rows'] for x in rows)==m.NumConstrs and sum(x['nonzeros'] for x in rows)==m.NumNZs
    print('baseline profile PASS',stats,flush=True)
    (OUT/'ROOT_LP_SIZE_DIAGNOSIS.md').write_text('# Actual PR102 root matrix census\n\nComplete 1499-job model, original tie rows included. Counts and nonzeros are measured from the native sparse matrix, not inferred from column counts. See family CSVs for sparse recurrence, routing, payload, tie, Runtime, CC4 and grid contributions. The PR102 single root node and zero incumbent do not demonstrate branch-tree explosion.\n\n'+json.dumps(rows,indent=2)+'\n',encoding='utf8')
    m.dispose();del m,v,o,c,b;gc.collect();frozen()
if __name__=='__main__':main()
