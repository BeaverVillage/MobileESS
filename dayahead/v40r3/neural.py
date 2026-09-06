"""Independent CMABF and pinned upstream TFT/DeepAR/NHiTS adapters.

This module defines models; importing or shape-testing it performs no fitting.
"""
import os
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
import random
import warnings
warnings.filterwarnings('ignore',message="Attribute .* is an instance of `nn.Module`.*")
from .causal_snapshot import *
import torch
from torch import nn
from torch.nn import functional as F
from pytorch_forecasting import TemporalFusionTransformer, DeepAR, NHiTS
from pytorch_forecasting.metrics import QuantileLoss, NormalDistributionLoss
from pytorch_forecasting.data import TorchNormalizer

POS_LEVELS=[.01,.05,.1,.25,.5,.75,.9,.95,.99]
UNION=list(dict.fromkeys(PAST_NAMES+FUTURE_NAMES))

def seed_everything(seed=SEED):
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
    if torch.cuda.is_available():torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.deterministic=True;torch.backends.cudnn.benchmark=False
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    torch.set_num_threads(4)

def pinball_tensor(y,q,tau):
    e=y-q
    return torch.maximum(tau*e,(tau-1)*e)

def mix_quantile(p,positive,tau,levels=POS_LEVELS):
    """Exact atom-at-zero mixture, piecewise-linear positive quantile grid."""
    level=torch.as_tensor([0.]+list(levels),device=p.device,dtype=p.dtype)
    values=torch.cat([torch.zeros_like(positive[...,:1]),positive],dim=-1)
    u=((tau-(1-p))/p.clamp_min(1e-8)).clamp(0,levels[-1])
    hi=torch.searchsorted(level,u.contiguous(),right=True).clamp(1,len(level)-1)
    lo=hi-1
    low=torch.gather(values,-1,lo.unsqueeze(-1)).squeeze(-1)
    high=torch.gather(values,-1,hi.unsqueeze(-1)).squeeze(-1)
    frac=(u-level[lo])/(level[hi]-level[lo])
    return torch.where(tau<=1-p,torch.zeros_like(p),low+frac*(high-low))

class CausalBlock(nn.Module):
    def __init__(self,hidden,dilation):
        super().__init__();self.left=2*dilation
        self.conv=nn.Conv1d(hidden,hidden,3,dilation=dilation)
        self.norm=nn.LayerNorm(hidden)
    def forward(self,x):
        z=self.conv(F.pad(x,(self.left,0)))
        return self.norm((x+F.gelu(z)).transpose(1,2)).transpose(1,2)

class TemporalEncoder(nn.Module):
    def __init__(self,channels,hidden=32):
        super().__init__();self.input=nn.Conv1d(channels,hidden,1)
        self.blocks=nn.Sequential(*(CausalBlock(hidden,d) for d in [1,2,4,8]))
        self.pool=nn.Linear(hidden*2,hidden)
    def forward(self,x):
        z=self.blocks(self.input(x.transpose(1,2)))
        return F.gelu(self.pool(torch.cat([z[:,:,-1],z.mean(-1)],dim=-1)))

class CMABF(nn.Module):
    def __init__(self,ablation='FULL',hidden=32):
        super().__init__();self.ablation=ablation
        self.activity=TemporalEncoder(5,hidden);self.mature=TemporalEncoder(3,hidden)
        self.single=TemporalEncoder(8,hidden) if ablation=='NO_MATURITY' else None
        self.gate=nn.Linear(hidden*2,hidden)
        self.decode=nn.Sequential(nn.Linear(hidden+len(FUTURE_NAMES),64),nn.GELU(),nn.Linear(64,32),nn.GELU())
        self.trajectory=nn.Conv1d(32,32,3,padding=1)
        self.occurrence=nn.Linear(32,1)
        self.magnitude=nn.Linear(32,len(POS_LEVELS))
    def forward(self,past,future):
        # Sanitize by mask again at the boundary, including ablations.
        p=past.clone();p[:,:,1]=torch.where(p[:,:,2]>0,p[:,:,1],0.)
        if self.single is not None:
            p[:,:,2:4]=0.;context=self.single(p)
        else:
            a=self.activity(p[:,:,[0,4,5,6,7]])
            b=self.mature(p[:,:,[1,2,3]])
            gate=torch.sigmoid(self.gate(torch.cat([a,b],-1)))
            context=gate*a+(1-gate)*b
        z=self.decode(torch.cat([context[:,None,:].expand(-1,K,-1),future],-1))
        z=F.gelu(z+self.trajectory(z.transpose(1,2)).transpose(1,2))
        logits=self.occurrence(z).squeeze(-1)
        prob=torch.ones_like(logits) if self.ablation=='NO_HURDLE' else torch.sigmoid(logits)
        positive=torch.cumsum(F.softplus(self.magnitude(z)),dim=-1)/len(POS_LEVELS)
        return {'p':prob,'logits':logits,'positive_quantiles':positive,
                'q50':mix_quantile(prob,positive,.5),'q90':mix_quantile(prob,positive,.9)}

def cmabf_loss(output,y,ablation='FULL'):
    pos=y>0
    occ=F.binary_cross_entropy_with_logits(output['logits'],pos.float()) if ablation!='NO_HURDLE' else y.new_tensor(0.)
    q=.5*(pinball_tensor(y,output['q50'],.5).mean()+pinball_tensor(y,output['q90'],.9).mean())
    mask=torch.ones_like(pos) if ablation=='NO_HURDLE' else pos
    levels=torch.as_tensor(POS_LEVELS,device=y.device,dtype=y.dtype)
    grid=pinball_tensor(y[...,None],output['positive_quantiles'],levels)
    positive=grid[mask].mean() if mask.any() else y.new_tensor(0.)
    # y is scaled by training positive Q95, so y == 1 is the frozen burst threshold.
    weighted=(1.+torch.minimum(y,y.new_tensor(3.)))*pinball_tensor(y,output['q90'],.9)
    burst=weighted.mean() if ablation!='NO_BURST' else y.new_tensor(0.)
    return occ+q+.2*positive+.25*burst

def library_batch(past,future,y=None,deepar_training=False):
    b=past.shape[0];enc=past.new_zeros((b,HISTORY,len(UNION)));dec=past.new_zeros((b,K,len(UNION)))
    for i,name in enumerate(PAST_NAMES):enc[:,:,UNION.index(name)]=past[:,:,i]
    for i,name in enumerate(FUTURE_NAMES):dec[:,:,UNION.index(name)]=future[:,:,i]
    enc[:,:,UNION.index('mature_GPUh')]=torch.where(past[:,:,2]>0,past[:,:,1],0.)
    # Only generative likelihood training uses shifted decoder targets.
    # Forecasting passes no y and always samples autoregressively with n_samples.
    if deepar_training:
        if y is None:raise ValueError('DEEPar_LIKELIHOOD_REQUIRES_LABELS')
        dec[:,:,UNION.index('mature_GPUh')]=y
    empty_cat=torch.empty((b,HISTORY,0),device=past.device,dtype=torch.long)
    return {'encoder_cont':enc,'decoder_cont':dec,'encoder_cat':empty_cat,
      'decoder_cat':torch.empty((b,K,0),device=past.device,dtype=torch.long),
      'encoder_lengths':torch.full((b,),HISTORY,device=past.device,dtype=torch.long),
      'decoder_lengths':torch.full((b,),K,device=past.device,dtype=torch.long),
      'target_scale':torch.tensor([0.,1.],device=past.device).repeat(b,1),
      'encoder_target':enc[:,:,UNION.index('mature_GPUh')],
      'decoder_target':torch.zeros((b,K),device=past.device) if y is None else y}

def build_model(name):
    if name.startswith('CMABF'):
        ablation={'CMABF':'FULL','CMABF_A0':'NO_MATURITY','CMABF_A1':'NO_HURDLE','CMABF_A2':'NO_BURST'}[name]
        return CMABF(ablation)
    kwargs={'x_reals':UNION,'x_categoricals':[],'static_categoricals':[],'static_reals':[],
      'time_varying_reals_encoder':PAST_NAMES,'time_varying_reals_decoder':FUTURE_NAMES,
      'time_varying_categoricals_encoder':[],'time_varying_categoricals_decoder':[],
      'output_transformer':TorchNormalizer(method='identity')}
    if name=='TFT':
        return TemporalFusionTransformer(hidden_size=32,lstm_layers=1,dropout=.1,output_size=2,
         attention_head_size=2,max_encoder_length=HISTORY,hidden_continuous_size=8,
         loss=QuantileLoss(quantiles=[.5,.9]),causal_attention=True,**kwargs)
    if name=='DEEPAR':
        # Same union covariates, with unavailable future observed inputs set to 0.
        # Their phase is unambiguous from lead/calendar context. No future actuals.
        kwargs['time_varying_reals_encoder']=UNION
        kwargs['time_varying_reals_decoder']=[v for v in UNION if v!='mature_GPUh']
        return DeepAR(hidden_size=32,rnn_layers=2,dropout=.1,target='mature_GPUh',
         loss=NormalDistributionLoss(),**kwargs)
    if name=='NHITS':
        return NHiTS(context_length=HISTORY,prediction_length=K,hidden_size=128,n_blocks=[1,1,1],
         n_layers=2,pooling_sizes=[8,4,1],downsample_frequencies=[8,4,1],dropout=.1,
         naive_level=False,backcast_loss_ratio=0.,output_size=2,loss=QuantileLoss(quantiles=[.5,.9]),
         dataset_parameters={'target':'mature_GPUh'},**kwargs)
    raise ValueError(name)

def neural_loss(model,name,past,future,y):
    if name.startswith('CMABF'):return cmabf_loss(model(past,future),y,model.ablation)
    out=model(library_batch(past,future,y,deepar_training=name=='DEEPAR'))['prediction']
    if name=='DEEPAR':return model.loss.loss(out,y).mean()
    quant=F.softplus(out)
    return .5*(pinball_tensor(y,quant[:,:,0],.5).mean()+pinball_tensor(y,quant[:,:,1],.9).mean())

@torch.no_grad()
def predict_neural(model,name,past,future,n_samples=256):
    model.eval()
    if name.startswith('CMABF'):
        output=model(past,future)
        return torch.stack([output['q50'],output['q90']],-1)
    x=library_batch(past,future)
    if name=='DEEPAR':
        sample=model(x,n_samples=n_samples)['prediction'].clamp_min(0)
        return torch.quantile(sample,torch.tensor([.5,.9],device=sample.device),dim=-1).permute(1,2,0)
    return F.softplus(model(x)['prediction'])

if __name__=='__main__':
    seed_everything();device='cuda:0' if torch.cuda.is_available() else 'cpu'
    p=torch.zeros((2,HISTORY,len(PAST_NAMES)),device=device);p[:,:,2]=1
    f=torch.zeros((2,K,len(FUTURE_NAMES)),device=device);y=torch.ones((2,K),device=device)
    for name in ['TFT','DEEPAR','NHITS','CMABF','CMABF_A0','CMABF_A1','CMABF_A2']:
        model=build_model(name).to(device);model.train()
        loss=neural_loss(model,name,p,f,y)
        out=predict_neural(model,name,p,f,16)
        assert out.shape==(2,K,2) and torch.isfinite(out).all() and torch.isfinite(loss)
        print(name,tuple(out.shape),'finite untrained forward/loss',float(loss.detach()),flush=True)
    print('No optimizer created; no backward pass; no fitting or actual-data predictions.')
