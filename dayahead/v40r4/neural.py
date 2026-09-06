import os
os.environ['CUBLAS_WORKSPACE_CONFIG']=':4096:8'
import torch
from torch import nn
import torch.nn.functional as F
from .common import SEED

def deterministic():
    torch.manual_seed(SEED);torch.set_num_threads(4);torch.use_deterministic_algorithms(True,warn_only=True)
    torch.backends.cudnn.deterministic=True;torch.backends.cudnn.benchmark=False
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False

class CCAF(nn.Module):
    def __init__(self,initial):
        super().__init__();self.u=float(initial['u']);self.register_buffer('initial',torch.tensor(initial['bias'],dtype=torch.float32))
        self.encoder=nn.Sequential(nn.Conv1d(8,32,3,padding=2,dilation=1),nn.GELU(),
            nn.Conv1d(32,32,3,padding=4,dilation=2),nn.GELU(),nn.AdaptiveAvgPool1d(1))
        self.shared=nn.Sequential(nn.Linear(47,64),nn.GELU(),nn.Linear(64,32),nn.GELU())
        self.count=nn.Linear(32,2);self.severity=nn.Sequential(nn.Linear(33,32),nn.GELU(),nn.Linear(32,5))
        nn.init.zeros_(self.count.weight);nn.init.zeros_(self.count.bias)
        nn.init.zeros_(self.severity[-1].weight);nn.init.zeros_(self.severity[-1].bias)
    def forward(self,past,future):
        # Both endpoints are historical and already <= origin; convolutions never access future labels.
        h=self.encoder(past.transpose(1,2)).squeeze(-1);h=h[:,None,:].expand(-1,48,-1)
        context=self.shared(torch.cat([h,future],-1));ct=self.count(context)+self.initial[:2]
        mu=torch.exp(ct[...,0].clamp(-9,9));r=torch.exp(ct[...,1].clamp(-7,7))
        sv=self.severity(torch.cat([context,torch.log1p(mu)[...,None]],-1))+self.initial[2:]
        # Opposite-side medians avoid near-zero normalizing constants in the truncated laws.
        logu=torch.log(torch.tensor(self.u,device=mu.device))
        loc=logu-12*torch.sigmoid(sv[...,0]);sigma=.1+3.9*torch.sigmoid(sv[...,1])
        pt=torch.sigmoid(sv[...,2]).clamp(1e-6,1-1e-6)
        tl=logu+10*torch.sigmoid(sv[...,3]);ts=.1+3.9*torch.sigmoid(sv[...,4])
        return dict(mu=mu,r=r,loc=loc,sigma=sigma,ptail=pt,tail_loc=tl,tail_sigma=ts)

def joint_loss(params,n,suff,mean_train_count,u):
    mu=params['mu'];r=params['r'];n=n.to(mu.dtype)
    count=-(torch.lgamma(n+r)-torch.lgamma(r)-torch.lgamma(n+1)+r*(torch.log(r)-torch.log(r+mu))+n*(torch.log(mu)-torch.log(r+mu)))
    logu=torch.log(torch.tensor(u,device=n.device));suff=suff.to(mu.dtype)
    def component(offset,loc,sigma,tail=False):
        nj,sm,ssq=[suff[...,offset+k] for k in range(3)]
        t=(logu-loc)/sigma
        norm=torch.special.log_ndtr(-t if tail else t)
        normal=sm+nj*(torch.log(sigma)+.5*torch.log(torch.tensor(2*3.141592653589793,device=n.device)))
        normal=normal+.5*(ssq-2*loc*sm+nj*loc**2)/sigma**2+nj*norm
        return normal
    severity=component(0,params['loc'],params['sigma'])+component(3,params['tail_loc'],params['tail_sigma'],True)
    severity-=suff[...,0]*torch.log1p(-params['ptail'])+suff[...,3]*torch.log(params['ptail'])
    return count.mean()+severity.mean()/mean_train_count
