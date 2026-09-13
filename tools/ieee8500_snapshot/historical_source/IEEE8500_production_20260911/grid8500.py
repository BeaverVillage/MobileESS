"""IEEE8500 phasor-affine surrogate with full-axis separation and exact AC gate."""
import time,math
import numpy as np
import gurobipy as gp
import ac8500 as ac
TAN=.3286841051788632

def controls(pcc,mp=None,mq=None):
    x=np.zeros((96,72));x[:,:24:2]=pcc;x[:,1:24:2]=pcc*TAN
    if mp is not None:x[:,24::2]=mp
    if mq is not None:x[:,25::2]=mq
    return x

class Grid:
    def __init__(self):
        started=time.perf_counter();self.base=controls(np.load(ac.s.OLD/'V41R4_B0_AIDC_POWER_UNCHANGED.npz')['pcc']);self.matrix=[];self.anchor=[]
        for t in range(96):
            with np.load(next((ac.H/'coefficients_v2').glob(f'block_*/slot_{t:02d}.npz'))) as z:
                self.matrix.append([z[k].copy() for k in ac.KEYS]);self.anchor.append([z[k+'_anchor'].copy() for k in ac.KEYS])
        self.load_seconds=time.perf_counter()-started
    def fork(self):
        other=object.__new__(Grid);other.base=self.base.copy();other.matrix=self.matrix;other.anchor=[[a.copy() for a in row] for row in self.anchor];other.load_seconds=0.;return other
    def values(self,x):
        return [[a+(x[t]-self.base[t])@m for a,m in zip(self.anchor[t],self.matrix[t])] for t in range(96)]
    def report(self,x,values=None):
        z=self.values(x) if values is None else values
        ex=[(min(np.abs(v[0]).min() for v in z),max(np.abs(v[0]).max() for v in z))]+[max(float(np.abs(v[k]).max()) for v in z) for k in range(1,4)]
        return dict(Vmin=float(ex[0][0]),Vmax=float(ex[0][1]),P1=float(ex[1]),transformer_current=float(ex[2]),transformer_kva=float(ex[3]),feasible=ex[0][0]>=.95-1e-9 and ex[0][1]<=1.05+1e-9 and max(ex[1:])<=1.+1e-9)
    def cost_gradient(self,x):
        z=self.values(x);rho=np.array([np.abs(v[1]).max() for v in z]);ts=np.argsort(-rho,kind='stable')[:24];cost=np.zeros((96,12))
        for t in ts:
            j=int(np.abs(z[t][1]).argmax());angle=np.exp(-1j*np.angle(z[t][1][j]));m=np.real(self.matrix[t][1][:24,j]*angle)
            cost[t]=(m[::2]+TAN*m[1::2])/(1+int(np.where(ts==t)[0][0]))
        return cost,z

class GridRows:
    def __init__(self,grid,model,x,rho,seed,initial_per_slot=3):
        self.grid=grid;self.model=model;self.x=x;self.rho=rho;self.keys=set();self.rows=0;self.seed=seed
        z=grid.values(seed)
        for t,v in enumerate(z):
            for k in range(4):
                for j in np.argsort(-np.abs(v[k]),kind='stable')[:initial_per_slot]:self.add(t,k,int(j),v[k][j],False)
            for j in np.argsort(np.abs(v[0]),kind='stable')[:initial_per_slot]:self.add(t,0,int(j),v[0][j],True)
    def add(self,t,k,j,z,lower=False):
        angle=float(np.angle(z));key=(t,k,j,lower,round(angle,8))
        if key in self.keys:return False
        self.keys.add(key);phase=np.exp(-1j*angle);m=np.real(self.grid.matrix[t][k][:,j]*phase);constant=float(np.real(self.grid.anchor[t][k][j]*phase)-m@self.grid.base[t]);expr=gp.LinExpr(constant)
        for c,xx in zip(m,self.x[t]):
            if abs(c)>1e-15:expr+=float(c)*xx
        if lower:self.model.addConstr(expr>=.95,name=f'vmin_{self.rows}')
        else:self.model.addConstr(expr<=(1.05 if k==0 else self.rho if k==1 else 1.),name=f'upper_{k}_{self.rows}')
        self.rows+=1;return True
    def separate(self,x,rho,maximum_per_slot=8):
        z=self.grid.values(x);added=0
        for t,v in enumerate(z):
            for k in range(4):
                mag=np.abs(v[k]);bound=1.05 if k==0 else rho if k==1 else 1.
                bad=np.flatnonzero(mag>bound+1e-8)
                for j in bad[np.argsort(-mag[bad],kind='stable')[:maximum_per_slot]]:added+=self.add(t,k,int(j),v[k][j])
            bad=np.flatnonzero(np.abs(v[0])<.95-1e-8)
            for j in bad[np.argsort(np.abs(v[0][bad]),kind='stable')[:maximum_per_slot]]:added+=self.add(t,0,int(j),v[0][j],True)
        return added,self.grid.report(x,z)
