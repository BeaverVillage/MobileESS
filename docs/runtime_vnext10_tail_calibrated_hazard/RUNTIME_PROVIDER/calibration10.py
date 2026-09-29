"""Strict, endpoint-preserving probability maps and stable exact interval scores."""
import numpy as np
from scipy.special import expit
from scipy.optimize import minimize
from sklearn.isotonic import IsotonicRegression
EPS=.01
CENTERS=expit(np.arange(-30.,30.0001,.1))
LOGITS=np.arange(-30.,30.0001,.1)
def probability_bins(logsf):
    logsf=np.asarray(logsf,float);logp=np.log(-np.expm1(logsf))
    z=np.clip(logp-logsf,-30,30)
    return np.clip(np.rint((z+30)*10).astype(int),0,len(CENTERS)-1)
class ProbabilityMap:
    def __init__(self,state=None):self.state=state or {'family':'NONE'}
    @classmethod
    def fit(cls,total,positive,family):
        total=np.asarray(total,float);positive=np.asarray(positive,float);mask=total>0
        if not mask.any():return cls()
        x=CENTERS[mask];w=total[mask];y=positive[mask]/w
        if family=='ISOTONIC':
            iso=IsotonicRegression(y_min=0,y_max=1,increasing=True,out_of_bounds='clip').fit(x,y,sample_weight=w)
            xx=iso.X_thresholds_;yy=iso.y_thresholds_;keep=(xx>=1e-10)&(xx<=1-1e-10);xx=xx[keep];yy=yy[keep]
            xx=np.r_[0,xx,1];yy=np.r_[0,yy,1]
            xx,ix=np.unique(xx,return_index=True);yy=yy[ix];yy[0]=0;yy[-1]=1
            sx=1-xx[::-1];hy=EPS*sx+(1-EPS)*(1-yy[::-1])
            # Store increasing survival knots h(s)=1-g(1-s).
            return cls(dict(family=family,s=sx.tolist(),h=hy.tolist(),epsilon=EPS))
        z=LOGITS[mask]
        def loss(theta):
            a,b=theta;score=a*z+b
            value=np.sum(w*(np.logaddexp(0,score)-y*score))/w.sum()
            residual=w*(expit(score)-y)/w.sum()
            return value,np.array([np.dot(residual,z),residual.sum()])
        fit=minimize(loss,[1.,0.],jac=True,bounds=[(.05,20.),(-20.,20.)],method='L-BFGS-B',options={'maxiter':200,'ftol':1e-11})
        if not fit.success and np.linalg.norm(fit.jac)>1e-4:raise RuntimeError('CALIBRATION_OPTIMIZER_FAILED '+fit.message)
        return cls(dict(family=family,a=float(fit.x[0]),b=float(fit.x[1]),epsilon=EPS,optimizer_success=bool(fit.success)))
    def logsf(self,logs):
        logs=np.asarray(logs,float);kind=self.state['family']
        if kind=='NONE':return logs
        if kind=='LOGISTIC':
            with np.errstate(divide='ignore',invalid='ignore'):
                logp=np.log(-np.expm1(logs));z=self.state['a']*(logp-logs)+self.state['b']
            logistic=-np.logaddexp(0,z)
            ls=np.logaddexp(np.log(EPS)+logs,np.log1p(-EPS)+logistic)
            lf=np.logaddexp(np.log(EPS)+logp,np.log1p(-EPS)-np.logaddexp(0,-z))
            return np.where(lf<np.log(.5),np.log1p(-np.exp(lf)),ls)
        sx=np.array(self.state['s']);hy=np.array(self.state['h']);s=np.exp(logs)
        idx=np.clip(np.searchsorted(sx,s,side='right')-1,0,len(sx)-2);slopes=np.diff(hy)/np.diff(sx)
        value=hy[idx]+slopes[idx]*(s-sx[idx])
        with np.errstate(divide='ignore'):result=np.log(value)
        # Exact positive first segment remains representable in log space beyond underflow.
        result=np.where(idx==len(slopes)-1,np.log1p(slopes[-1]*np.expm1(logs)),result)
        return np.where(idx==0,logs+np.log(slopes[0]),result)
    def inverse_logsf(self,target):
        target=np.asarray(target,float);kind=self.state['family']
        if kind=='NONE':return target
        if kind=='ISOTONIC':
            sx=np.array(self.state['s']);hy=np.array(self.state['h']);u=np.exp(target);raw=np.interp(u,hy,sx)
            with np.errstate(divide='ignore'):out=np.log(raw)
            slope=(hy[1]-hy[0])/(sx[1]-sx[0])
            last=(hy[-1]-hy[-2])/(sx[-1]-sx[-2]);out=np.where(u>=hy[-2],np.log1p(np.expm1(target)/last),out)
            return np.where(u<=hy[1],target-np.log(slope),out)
        hi=np.zeros_like(target);lo=np.minimum(target-100.,-100.)
        while np.any(self.logsf(lo)>target):lo=np.where(self.logsf(lo)>target,2*lo,lo)
        for _ in range(65):
            mid=(lo+hi)/2;below=self.logsf(mid)<target;lo=np.where(below,mid,lo);hi=np.where(below,hi,mid)
        return (lo+hi)/2
    def log_interval(self,raw_logleft,delta_h):
        """log[h(S_left)-h(S_right)], no probability or log-score floor."""
        ls=np.asarray(raw_logleft,float);dh=np.asarray(delta_h,float)
        if np.any(dh<=0):raise ValueError('NONPOSITIVE_INTERVAL_HAZARD')
        raw=ls+np.log(-np.expm1(-dh));kind=self.state['family']
        if kind=='NONE':return raw
        if kind=='LOGISTIC':
            a=self.state['a'];b=self.state['b']
            with np.errstate(divide='ignore',invalid='ignore'):
                logfl=np.log(-np.expm1(ls));logfr=np.log(-np.expm1(ls-dh))
                zl=a*(logfl-ls)+b;zr=a*(logfr-ls+dh)+b
                dz=a*(np.logaddexp(0,raw-logfl)+dh)
                component=-np.logaddexp(0,-zr)-np.logaddexp(0,zl)+np.log(-np.expm1(-dz))
            # F_left=0 gives g(F_left)=0, hence interval probability g(F_right).
            component=np.where(np.isneginf(logfl),-np.logaddexp(0,-zr),component)
            return np.logaddexp(np.log(EPS)+raw,np.log1p(-EPS)+component)
        sx=np.array(self.state['s']);hy=np.array(self.state['h']);slopes=np.diff(hy)/np.diff(sx)
        left=np.exp(ls);right=left*np.exp(-dh)
        il=np.clip(np.searchsorted(sx,left,side='left')-1,0,len(slopes)-1);ir=np.clip(np.searchsorted(sx,right,side='right')-1,0,len(slopes)-1)
        out=raw+np.log(slopes[il])
        for n in np.flatnonzero(il!=ir):
            points=np.r_[right[n],sx[ir[n]+1:il[n]+1],left[n]]
            prob=np.sum(np.diff(points)*slopes[ir[n]:il[n]+1])
            if prob<=0:raise FloatingPointError('CALIBRATED_INTERVAL_LOST')
            out[n]=np.log(prob)
        return out
    def audit(self):
        grid=-np.geomspace(1e-12,1e6,1000);values=self.logsf(grid)
        return bool(np.all(np.isfinite(values)) and np.all(np.diff(values)<0) and np.all(values<0))
def maps_quantiles(model,par,mapobj,continuation,quantiles=(.5,.7,.8,.9,.95)):
    return np.column_stack([model.inverse_logsf(par,mapobj.inverse_logsf(np.array(np.log1p(-q))),continuation) for q in quantiles])
def maps_remaining(model,par,elapsed,mapobj,continuation):
    logs=mapobj.logsf(model.logsf(par,elapsed,continuation))
    q=np.column_stack([np.maximum(model.inverse_logsf(par,mapobj.inverse_logsf(logs+np.log1p(-tau)),continuation)-elapsed,0) for tau in [.5,.9]])
    return q,logs
