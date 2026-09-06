"""Valid NB counts and positive lognormal/spliced lognormal severity distributions."""
from .common import *
from scipy import stats as ss,special

def nb_logpmf(n,mu,r):return ss.nbinom.logpmf(n,r,r/(r+mu))
def severity_cdf(z,p):
    z=np.asarray(z);body=ss.lognorm.cdf(z,s=p['sigma'],scale=np.exp(p['loc']))
    if p['kind']!='SPLICE':return body
    u=p['u'];fb=ss.lognorm.cdf(u,s=p['sigma'],scale=np.exp(p['loc']))
    ft=ss.lognorm.cdf(u,s=p['tail_sigma'],scale=np.exp(p['tail_loc']))
    tail=ss.lognorm.cdf(z,s=p['tail_sigma'],scale=np.exp(p['tail_loc']))
    return np.where(z<=u,(1-p['ptail'])*body/fb,1-p['ptail']+p['ptail']*(tail-ft)/(1-ft))
def severity_logpdf(z,p):
    body=ss.lognorm.logpdf(z,s=p['sigma'],scale=np.exp(p['loc']))
    if p['kind']!='SPLICE':return body
    u=p['u'];fb=ss.lognorm.cdf(u,s=p['sigma'],scale=np.exp(p['loc']))
    ft=ss.lognorm.cdf(u,s=p['tail_sigma'],scale=np.exp(p['tail_loc']))
    tail=ss.lognorm.logpdf(z,s=p['tail_sigma'],scale=np.exp(p['tail_loc']))
    return np.where(z<=u,np.log1p(-p['ptail'])+body-np.log(fb),np.log(p['ptail'])+tail-np.log1p(-ft))
def severity_ppf(prob,p):
    prob=np.clip(np.asarray(prob),1e-12,1-1e-12)
    if p['kind']!='SPLICE':return np.exp(p['loc']+p['sigma']*special.ndtri(prob))
    u=p['u'];fb=special.ndtr((np.log(u)-p['loc'])/p['sigma']);ft=special.ndtr((np.log(u)-p['tail_loc'])/p['tail_sigma'])
    bp=np.clip(prob/np.maximum(1-p['ptail'],1e-12)*fb,1e-12,1-1e-12)
    tp=np.clip(ft+(prob-(1-p['ptail']))/np.maximum(p['ptail'],1e-12)*(1-ft),1e-12,1-1e-12)
    return np.where(prob<=1-p['ptail'],np.exp(p['loc']+p['sigma']*special.ndtri(bp)),np.exp(p['tail_loc']+p['tail_sigma']*special.ndtri(tp)))
def take(p,idx):return {k:(v[idx] if k!='levels' and isinstance(v,np.ndarray) and v.ndim else v) for k,v in p.items()}

def scenarios(p,indices,M,seed):
    """Exact finite-sample random-sum draws; GPU batching, no count truncation.

    Scenarios are independent across intervals conditional on frozen context.
    Compound-Gamma summation uses its exact reproductive property for Tweedie.
    """
    import torch
    torch.manual_seed(seed);torch.set_num_threads(4)
    device='cuda:0' if torch.cuda.is_available() else 'cpu'
    generator=torch.Generator(device=device).manual_seed(seed)
    indices=np.asarray(indices,int);out=np.empty((len(indices),M),np.float64)
    def tensor(x):return torch.as_tensor(x,dtype=torch.float64,device=device)
    def uniform(shape):return torch.rand(shape,dtype=torch.float64,device=device,generator=generator).clamp_(1e-12,1-1e-12)
    for begin in range(0,len(indices),4):
        ids=indices[begin:begin+4];q=take(p,ids);b=len(ids)
        if p['kind']=='ZERO':draws=torch.zeros((b,M),device=device,dtype=torch.float64)
        elif p['kind']=='SEASONAL':
            vals=tensor(q['values']);valid=torch.as_tensor(q['valid'],device=device,dtype=torch.bool)
            # Compact each interval's eligible profile entries; no unobserved value drawn.
            draws=torch.zeros((b,M),device=device,dtype=torch.float64)
            for row in range(b):
                v=vals[row][valid[row]]
                if len(v):draws[row]=v[(uniform((M,))*len(v)).long()]
        elif p['kind']=='HURDLE':
            occ=tensor(q['occ']);grid=tensor(q['grid']);prob=uniform((b,M))
            u=((prob-(1-occ[:,None]))/occ[:,None].clamp_min(1e-12)).clamp(0,.99)
            knots=tensor(np.r_[0.,p['levels']]);vals=torch.cat([torch.zeros((b,1),device=device,dtype=torch.float64),grid],1)
            hi=torch.searchsorted(knots,u.contiguous(),right=True).clamp(1,len(knots)-1);lo=hi-1
            fraction=(u-knots[lo])/(knots[hi]-knots[lo])
            draws=vals.gather(1,lo)+(vals.gather(1,hi)-vals.gather(1,lo))*fraction
            draws=torch.where(prob<=1-occ[:,None],0.,draws)
        elif p['kind']=='TWEEDIE':
            lam=tensor(q['lam']);alpha=tensor(q['alpha']);theta=tensor(q['theta'])
            n=torch.poisson(lam[:,None].expand(b,M),generator=generator)
            shape=n*alpha[:,None]
            draws=torch._standard_gamma(shape.clamp_min(1e-8),generator=generator)*theta[:,None]
            draws=torch.where(n>0,draws,0.)
        else:
            mu=tensor(q['mu']);r=tensor(q['r'])
            lam=torch._standard_gamma(r[:,None].expand(b,M),generator=generator)*(mu/r)[:,None]
            n=torch.poisson(lam,generator=generator).long()
            # Work in bounded scenario batches if a heavy count draw is large.
            ncpu=n.cpu().numpy();flat=ncpu.ravel();cum=np.cumsum(flat);cuts=[0];cursor=0
            while cursor<len(flat):
                before=0 if cursor==0 else cum[cursor-1]
                end=int(np.searchsorted(cum,before+2_000_000,side='right'))
                end=max(cursor+1,end);cuts.append(end);cursor=end
            sums=torch.zeros(b*M,device=device,dtype=torch.float64)
            for left,right in zip(cuts[:-1],cuts[1:]):
                lengths=n.reshape(-1)[left:right];total=int(lengths.sum().item())
                if total==0:continue
                if total>50_000_000:raise RuntimeError('PREREGISTERED_SINGLE_SCENARIO_RESOURCE_LIMIT_NO_TRUNCATION')
                interval_ids=torch.arange(left,right,device=device)//M
                jid=torch.repeat_interleave(interval_ids,lengths)
                loc=tensor(q['loc'])[jid];sigma=tensor(q['sigma'])[jid]
                if p['kind']=='LOGNORMAL':z=torch.exp(loc+sigma*torch.randn(total,dtype=torch.float64,device=device,generator=generator))
                else:
                    pt=tensor(q['ptail'])[jid];tl=tensor(q['tail_loc'])[jid];ts=tensor(q['tail_sigma'])[jid];u=float(p['u'])
                    is_tail=uniform((total,))<pt;v=uniform((total,))
                    fb=torch.special.ndtr((np.log(u)-loc)/sigma);ft=torch.special.ndtr((np.log(u)-tl)/ts)
                    bp=(v*fb).clamp(1e-12,1-1e-12);tp=(ft+v*(1-ft)).clamp(1e-12,1-1e-12)
                    z=torch.where(is_tail,torch.exp(tl+ts*torch.special.ndtri(tp)),torch.exp(loc+sigma*torch.special.ndtri(bp)))
                sums[left:right]=torch.segment_reduce(z,'sum',lengths=lengths)
            draws=sums.reshape(b,M)
        arr=draws.cpu().numpy();assert np.isfinite(arr).all() and (arr>=0).all()
        out[begin:begin+b]=arr
    return out

def predictive_summary(scenarios_by_interval):
    q=np.quantile(scenarios_by_interval,[.5,.9,.95],axis=1).T
    return q
