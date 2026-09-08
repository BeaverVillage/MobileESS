"""Audit every retained single-move witness against cached actual MPS rows."""
import gzip
import json
import math
import time
import numpy as np
from gurobipy import GRB
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import record
from .flex_model import Data,ProbeModel
from .flex_diagnostic import OUT,WORK
from .feasible_seed import job_audit
from dayahead.v40g.domain import audit


class CachedRows:
    def __init__(self,p):
        m=p.m;cs=m.getConstrs();self.A=m.getA()
        self.rhs=np.array(m.getAttr('RHS',cs));self.sense=np.array(m.getAttr('Sense',cs))
        self.lb=p.lb;self.ub=p.ub;self.integer=np.array(m.getAttr('VType',p.vs))!=GRB.CONTINUOUS
        self.general=[]
        for c in m.getGenConstrs():
            kind=c.GenConstrType
            if kind==GRB.GENCONSTR_PWL:
                a,b,xx,yy=m.getGenConstrPWL(c);self.general.append(('pwl',a.index,b.index,np.array(xx),np.array(yy)))
            elif kind==GRB.GENCONSTR_MAX:
                r,vs,k=m.getGenConstrMax(c);self.general.append(('max',r.index,[v.index for v in vs],k))
            elif kind==GRB.GENCONSTR_INDICATOR:
                v,flag,e,s,b=m.getGenConstrIndicator(c)
                self.general.append(('indicator',v.index,flag,np.array([e.getVar(i).index for i in range(e.size())]),
                    np.array([e.getCoeff(i) for i in range(e.size())]),e.getConstant(),s,b))
            else:raise ValueError('UNSUPPORTED_ORIGINAL_GENERAL_CONSTRAINT')
        assert not m.NumQConstrs and not m.NumSOS

    def check(self,x):
        lhs=self.A@x
        residual=np.where(self.sense=='=',abs(lhs-self.rhs),np.where(self.sense=='<',np.maximum(lhs-self.rhs,0),np.maximum(self.rhs-lhs,0)))
        linear=float(residual.max(initial=0));bounds=float(np.maximum(np.maximum(self.lb-x,x-self.ub),0).max(initial=0))
        integer=float(abs(x[self.integer]-np.rint(x[self.integer])).max(initial=0));general=0.
        for c in self.general:
            if c[0]=='pwl':
                _,a,b,xx,yy=c
                err=abs(x[b]-np.interp(x[a],xx,yy)) if xx[0]<=x[a]<=xx[-1] else math.inf
            elif c[0]=='max':
                _,r,vs,k=c;err=abs(x[r]-max([k]+[x[v] for v in vs]))
            else:
                _,v,f,ids,co,const,s,b=c
                if round(x[v])!=f:continue
                lhs=float(co@x[ids]+const);err=abs(lhs-b) if s=='=' else max(0,lhs-b if s=='<' else b-lhs)
            general=max(general,float(err))
        return dict(status='PASS' if max(linear,bounds,integer,general)<=1e-9 else 'FAIL',
            linear=linear,bounds=bounds,integrality=integer,general=general)


class Assignments:
    def __init__(self,p):
        self.p=p;d=p.d;self.blocks={}
        grid=d.grid
        for prefix,shape in [('GPU',(96,12)),('PCC',(96,12)),('v_squared',grid.vc.shape),
            ('line_p',grid.pc.shape),('line_q',grid.pc.shape),('line_delta',grid.pc.shape),('tx_p',grid.pc.shape),('tx_q',grid.pc.shape)]:
            idx=np.array([[p.ni.get(f'{prefix}[{t},{d.sites[k] if prefix in ("GPU","PCC") else k}]',-1) for k in range(shape[1])] for t in range(shape[0])])
            self.blocks[prefix]=(idx,idx>=0)
        self.wan=[(u,p.ni['WAN_ready_'+u],p.ni['WAN_selected_'+u],p.ni['WAN_cursor_'+u],d.byuid[u]['r1_first_valid_checkpoint'])
            for u in sorted(d.byuid) if 'WAN_ready_'+u in p.ni]
        self.xi=np.array([p.ni[f'V41_H4_shortfall_GPUh[{i}]'] for i in range(81)])

    def make(self,uid,k):
        p=self.p;d=p.d;cache=d.grid;x=p.seed.copy();g=d.uidgroup[uid];o=d.option(uid,k);ref=d.reference_index[uid]
        if g in p.choices:
            x[p.choices[g][str(ref)]]-=1;x[p.choices[g][str(k)]]+=1
        else:
            x[p.placement[g][str(ref)]]=0
            if not o.migrated:x[p.placement[g][str(k)]]=1
            else:
                source=o.initial_site or d.byuid[uid]['AIDC_site']
                x[p.routes[g][source+','+o.site]]=1;x[p.arrivals[g][o.site+','+str(o.transfer_end+1)]]=1
                x[p.ni[f'migration_source[{g},{source}]']]=1
        q,why=d.quick({uid:k});assert q is not None,why
        power=q['pcc']
        vals={'GPU':q['gpu'],'PCC':power,
            'v_squared':cache.vc+np.einsum('tnk,tk->tn',cache.vm,power),
            'line_p':cache.pc+np.einsum('tbk,tk->tb',cache.pm,power),
            'line_q':cache.qc+np.einsum('tbk,tk->tb',cache.qm,power),
            'line_delta':cache.cc+np.einsum('tbk,tk->tb',cache.cm,power)}
        vals['tx_p']=vals['line_p'];vals['tx_q']=vals['line_q']
        for prefix,(idx,mask) in self.blocks.items():x[idx[mask]]=vals[prefix][mask]
        x[p.ni['rho_max']]=q['vector'][0];x[self.xi]=q['reserve']['xi_GPUh']
        cursor=26
        for u,ready,flag,after,cp in self.wan:
            x[ready]=max(cursor,cp);x[flag]=int(u==uid and o.migrated)
            if u==uid and o.migrated:
                assert o.transfer_start==max(cursor,cp);cursor=o.transfer_end
            x[after]=cursor
        return x,q


def run():
    d=Data();p=ProbeModel(d);started=time.perf_counter()
    try:
        rows=CachedRows(p);assign=Assignments(p);assert rows.check(p.seed)['status']=='PASS'
        moves=read(WORK/'FEASIBLE_SINGLE_MOVES.json');certs=[]
        for i,item in enumerate(moves):
            u=item['uid'];k=item['option_index'];x,q=assign.make(u,k);ra=rows.check(x)
            # Recompute actual job materialization and all site/rack/WAN
            # resources separately from the fast enumeration's delta arrays.
            selected=d.rows({u:k});service=audit(d.refs,selected,d.ctx.capacity,d.ctx.wan)
            physical,power=job_audit(selected,d.ctx)
            equal=np.array_equal(power['gpu'],q['gpu']) and np.array_equal(power['pcc'],q['pcc'])
            status='PASS' if ra['status']==service['status']==physical['status']=='PASS' and equal else 'FAIL'
            assert status=='PASS',(u,k,ra,physical.get('residual_extrema'))
            changed=np.flatnonzero((x!=p.seed)&np.isin(np.arange(len(x)),p.ids))
            certs.append(dict(uid=u,option_index=k,status=status,vector=q['vector'],rows=ra,
                changed_decision_variables=[p.names[j] for j in changed],
                original_B0_and_alternative_both_feasible=True,independent_materialization_equal=equal))
            if i%100==0:print('ALL_SINGLE_WITNESSES',i,len(moves),'seconds',round(time.perf_counter()-started,1),flush=True)
        path=WORK/'SINGLE_MOVE_FULL_ROW_CERTIFICATES.json.gz'
        with gzip.open(path,'wt',encoding='utf-8') as f:json.dump(certs,f,separators=(',',':'))
        result=dict(status='PASS',verified_single_moves=len(certs),seconds=time.perf_counter()-started,
            all_original_linear_rows=len(rows.rhs),all_original_general_rows=len(rows.general),
            full_certificates=record(path),individual_job_materialization=True,
            bounds_and_integrality_tolerance=1e-9,Actual_reads=0)
        write_json(OUT/'SINGLE_MOVE_FULL_MODEL_VERIFICATION.json',result)
        print('ALL_SINGLE_WITNESSES_PASS',len(certs),flush=True)
    finally:p.close();d.close()


if __name__=='__main__':run()
