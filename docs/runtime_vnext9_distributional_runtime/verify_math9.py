from common9 import *
from distribution9 import Distribution
import numpy as np
def main():
    errors=[]
    models=[(Distribution(dict(kind='D1',edges=[0,900,3600]),[]),np.array([[1/3600,1/3600]]))]
    for noise in ['normal','logistic','extreme']:models.append((Distribution(dict(kind='D2',noise=noise,scale=1.5),[]),np.array([8.])))
    for model,par in models:
        for delta in [-1000,0,1000]:
            for elapsed in [0,900,14400,1000000]:
                q,s,ls=model.remaining(par,elapsed,delta)
                for i,tau in enumerate([.5,.9]):
                    ratio=np.exp(model.logsf(par,elapsed+q[:,i]-delta)-ls)
                    error=float(abs(ratio[0]-(1-tau)));assert error<1e-9,(model.meta,delta,elapsed,error);errors.append(error)
                assert 0<=q[0,0]<=q[0,1] and 0<=s[0]<=1
    m,p=models[0];q,_,_=m.remaining(p,100000)
    assert np.max(abs(q[0]-(-np.log([.5,.1])*3600)))<1e-8
    write('DISTRIBUTION_MATH_TEST.json',dict(PASS=True,cases=len(errors),max_survival_ratio_error=max(errors),exponential_memorylessness=True,extreme_tail_log_survival_tested=True))
    print('MATH_PASS',max(errors))
if __name__=='__main__':main()
