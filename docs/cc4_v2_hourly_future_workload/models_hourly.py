import os
for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
os.environ['CUBLAS_WORKSPACE_CONFIG']=':4096:8'
import copy,time,random,json,hashlib
from pathlib import Path
import numpy as np,torch
from torch import nn
from torch.nn import functional as F
torch.set_num_threads(1);torch.set_num_interop_threads(1)
torch.backends.cudnn.benchmark=False;torch.backends.cudnn.deterministic=True
torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
torch.use_deterministic_algorithms(True)
DEVICE='cuda:0' if torch.cuda.is_available() else 'cpu'
def seed_all(s):
 random.seed(s);np.random.seed(s);torch.manual_seed(s)
 if torch.cuda.is_available():torch.cuda.manual_seed_all(s)
def pinball(y,q,t=.9):
 e=y-q;return np.maximum(t*e,(t-1)*e).mean()
class GRN(nn.Module):
 def __init__(self,n):
  super().__init__();self.a=nn.Linear(n,n);self.b=nn.Linear(n,2*n);self.norm=nn.LayerNorm(n)
 def forward(self,x):return self.norm(x+F.glu(self.b(F.elu(self.a(x))),-1))
class VSN(nn.Module):
 def __init__(self,n,h):
  super().__init__();self.w=nn.Parameter(torch.randn(n,h)*.05);self.b=nn.Parameter(torch.zeros(n,h));self.gate=nn.Linear(n,n);self.grn=GRN(h)
 def forward(self,x):
  weights=torch.softmax(self.gate(x),-1)
  z=F.elu(x[...,None]*self.w+self.b)
  return self.grn((z*weights[...,None]).sum(-2))
class SmallTFT(nn.Module):
 def __init__(self,init):
  super().__init__();h=16;self.p=VSN(8,h);self.f=VSN(71,h);self.enc=nn.LSTM(h,h,batch_first=True);self.dec=nn.LSTM(h,h,batch_first=True);self.att=nn.MultiheadAttention(h,2,dropout=.1,batch_first=True);self.grn=GRN(h);self.drop=nn.Dropout(.1);self.head=nn.Linear(h,2)
  nn.init.zeros_(self.head.weight)
  v=np.maximum([init[0],init[1]-init[0]],.05)
  self.head.bias.data.copy_(torch.tensor(np.log(np.expm1(v)),dtype=torch.float32))
 def forward(self,p,f):
  enc,state=self.enc(self.p(p));dec,_=self.dec(self.f(f),state);allx=torch.cat([enc,dec],1)
  n=dec.shape[1];m=enc.shape[1];mask=torch.cat([torch.zeros(n,m,device=p.device,dtype=torch.bool),torch.triu(torch.ones(n,n,device=p.device,dtype=torch.bool),1)],1)
  a,_=self.att(dec,allx,allx,attn_mask=mask,need_weights=False)
  z=F.softplus(self.head(self.drop(self.grn(dec+a))));return torch.stack([z[...,0],z.sum(-1)],-1)
class SmallDeepAR(nn.Module):
 def __init__(self):
  super().__init__();h=16;self.enc=nn.LSTM(8,h,batch_first=True);self.dec=nn.LSTM(73,h,batch_first=True);self.head=nn.Linear(h,3);self.drop=nn.Dropout(.1)
 def params(self,z):
  a=self.head(z);return a[...,0],a[...,1],F.softplus(a[...,2])+.05
 def train_params(self,p,f,y):
  _,st=self.enc(p);prev=torch.cat([torch.zeros_like(y[:,:1]),y[:,:-1]],1)
  z,_=self.dec(torch.cat([f,prev],-1),st);return self.params(self.drop(z))
 @torch.no_grad()
 def sample(self,p,f,center,scale,n_samples=128):
  b,k,_=f.shape;_,st=self.enc(p);st=tuple(s.repeat_interleave(n_samples,dim=1) for s in st)
  prev=p.new_zeros((b*n_samples,1,2));paths=[]
  for j in range(k):
   cov=f[:,j:j+1].repeat_interleave(n_samples,dim=0);z,st=self.dec(torch.cat([cov,prev],-1),st);logit,mu,sd=self.params(z)
   occ=torch.rand_like(mu)<torch.sigmoid(logit);val=mu+sd*torch.randn_like(mu)
   gpu=torch.where(occ,torch.exp(val*scale+center),0)
   if not torch.isfinite(gpu).all():raise ValueError('NONFINITE_DEEPAR_PATH')
   paths.append(gpu.reshape(b,n_samples));prev=torch.stack([torch.where(occ,val,0),occ.float()],-1)
  paths=torch.stack(paths,1);return torch.quantile(paths,torch.tensor([.5,.9],device=p.device),dim=-1).permute(1,2,0)
def normalizer(p,x,train):
 pp=p.copy();xx=x.copy()
 for j in [0,1,3]:pp[:,:,j]=np.log1p(np.maximum(pp[:,:,j],0))
 # Continuous GPUh, counts, ages and calendar treated with training-fitted log signed scaling.
 xx=np.sign(xx)*np.log1p(np.abs(xx))
 pm=pp[train].mean((0,1));ps=np.maximum(pp[train].std((0,1)),.1);xm=xx[train].mean((0,1));xs=np.maximum(xx[train].std((0,1)),.1)
 return {'pm':pm,'ps':ps,'xm':xm,'xs':xs}
def apply_norm(p,x,n):
 pp=p.copy()
 for j in [0,1,3]:pp[:,:,j]=np.log1p(np.maximum(pp[:,:,j],0))
 xx=np.sign(x)*np.log1p(np.abs(x));return ((pp-n['pm'])/n['ps']).astype('float32'),((xx-n['xm'])/n['xs']).astype('float32')
def fit_predict(family,p,x,y,train,dev,ids,seed,lr,directory,frozen=None,epochs=None):
 directory=Path(directory);directory.mkdir(parents=True,exist_ok=True);seed_all(seed)
 if DEVICE.startswith('cuda'):torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats()
 norm=normalizer(p,x,train) if frozen is None else frozen['normalizer']
 pp,xx=apply_norm(p,x,norm);positive=y[train][y[train]>0]
 center=float(np.log(positive).mean()) if frozen is None else frozen['center'];scale=max(float(np.log(positive).std()),1.) if frozen is None else frozen['scale']
 init=np.log1p(np.quantile(y[train],[.5,.9])) if frozen is None else frozen['init'];yscale=max(float(np.quantile(positive,.95)),1.) if frozen is None else frozen['yscale']
 config={'normalizer':norm,'center':center,'scale':scale,'init':init,'yscale':yscale}
 model=(SmallTFT(init) if family=='TFT' else SmallDeepAR()).to(DEVICE);opt=torch.optim.AdamW(model.parameters(),lr=lr,weight_decay=1e-4)
 P=torch.tensor(pp,device=DEVICE);X=torch.tensor(xx,device=DEVICE);Y=torch.tensor(y,dtype=torch.float32,device=DEVICE)
 yz=np.stack([np.where(y>0,(np.log(np.maximum(y,1e-30))-center)/scale,0),(y>0).astype(float)],-1);YZ=torch.tensor(yz,dtype=torch.float32,device=DEVICE)
 rng=np.random.default_rng(seed);best=np.inf;beststate=None;bestepoch=0;history=[];start=time.perf_counter()
 def predict(ix):
  model.eval();out=[]
  with torch.no_grad(),torch.random.fork_rng(devices=[0] if DEVICE.startswith('cuda') else []):
   torch.manual_seed(seed+1000)
   for k in range(0,len(ix),16):
    ii=ix[k:k+16];q=torch.expm1(model(P[ii],X[ii])) if family=='TFT' else model.sample(P[ii],X[ii],center,scale)
    out.append(q.cpu().numpy())
  q=np.concatenate(out).astype(float);q=np.maximum(q,0);q[:,:,1]=np.maximum(q[:,:,0],q[:,:,1]);assert np.isfinite(q).all();return q
 for epoch in range(1,(epochs or 40)+1):
  model.train();losses=[];grads=[]
  order=rng.permutation(train)
  for k in range(0,len(order),16):
   ii=order[k:k+16];opt.zero_grad(set_to_none=True)
   if family=='TFT':
    q=torch.expm1(model(P[ii],X[ii]));e=(Y[ii,:,None]-q)/yscale;tau=q.new_tensor([.5,.9]);weights=q.new_tensor([.2,.8]);loss=(torch.maximum(tau*e,(tau-1)*e)*weights).sum(-1).mean()
   else:
    logit,mu,sd=model.train_params(P[ii],X[ii],YZ[ii]);pos=Y[ii]>0;nll=.5*((YZ[ii,:,0]-mu)/sd)**2+torch.log(sd)+.5*np.log(2*np.pi)
    loss=F.binary_cross_entropy_with_logits(logit,pos.float())+(nll*pos).mean()
   if not torch.isfinite(loss):raise ValueError('NONFINITE_LOSS')
   loss.backward();gn=torch.nn.utils.clip_grad_norm_(model.parameters(),1.,error_if_nonfinite=True);opt.step();losses.append(float(loss.detach()));grads.append(float(gn))
  score=float(pinball(y[dev],predict(dev)[:,:,1])) if epochs is None else None
  history.append({'epoch':epoch,'train_loss':float(np.mean(losses)),'dev_Q90_pinball_GPUh':score,'gradient_norm_mean':float(np.mean(grads)),'gradient_norm_max':max(grads),'finite_gradients':True})
  if epochs is not None or score<best-1e-6:
   if score is not None:best=score
   bestepoch=epoch;beststate=copy.deepcopy({k:v.detach().cpu() for k,v in model.state_dict().items()})
  if epochs is None and epoch-bestepoch>=7:break
 train_s=time.perf_counter()-start;model.load_state_dict(beststate);start=time.perf_counter();pred=predict(ids);infer_s=time.perf_counter()-start
 torch.save({'weights':beststate,'config':config,'family':family,'seed':seed,'lr':lr},directory/'model.pt')
 meta={'family':family,'seed':seed,'learning_rate':lr,'selected_epoch':bestepoch,'epochs_run':len(history),'training_seconds':train_s,'inference_seconds':infer_s,'N_training_days':len(train),'N_inference_days':len(ids),'parameter_count':sum(v.numel() for v in model.parameters()),'gpu_peak_memory_bytes':torch.cuda.max_memory_allocated() if DEVICE.startswith('cuda') else 0,'device':DEVICE,'torch':torch.__version__,'cuda':torch.version.cuda,'cpu_threads':1,'dataloader_workers':0,'history':history,'model_sha256':hashlib.sha256((directory/'model.pt').read_bytes()).hexdigest()}
 (directory/'receipt.json').write_text(json.dumps(meta,indent=2),encoding='utf-8');np.save(directory/'prediction.npy',pred)
 print(f'{family} seed={seed} lr={lr} n={len(train)} epoch={bestepoch}/{len(history)} train={train_s:.1f}s',flush=True)
 del model,opt,P,X,Y,YZ
 if DEVICE.startswith('cuda'):torch.cuda.empty_cache()
 return pred,meta,config

def predict_saved(directory,p,x,ids):
 start=time.perf_counter();c=torch.load(Path(directory)/'model.pt',map_location='cpu',weights_only=False);config=c['config'];seed_all(c['seed']+1000)
 model=(SmallTFT(config['init']) if c['family']=='TFT' else SmallDeepAR()).to(DEVICE);model.load_state_dict(c['weights']);model.eval();pp,xx=apply_norm(p,x,config['normalizer']);out=[]
 if DEVICE.startswith('cuda'):torch.cuda.reset_peak_memory_stats()
 with torch.no_grad():
  for k in range(0,len(ids),16):
   ix=ids[k:k+16];P=torch.tensor(pp[ix],device=DEVICE);X=torch.tensor(xx[ix],device=DEVICE)
   q=torch.expm1(model(P,X)) if c['family']=='TFT' else model.sample(P,X,config['center'],config['scale']);out.append(q.cpu().numpy())
 q=np.maximum(np.concatenate(out).astype(float),0);q[:,:,1]=np.maximum(q[:,:,0],q[:,:,1]);assert np.isfinite(q).all()
 meta={'inference_seconds':time.perf_counter()-start,'inference_days':len(ids),'gpu_peak_memory_bytes':torch.cuda.max_memory_allocated() if DEVICE.startswith('cuda') else 0}
 del model
 if DEVICE.startswith('cuda'):torch.cuda.empty_cache()
 return q,meta
