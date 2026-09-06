from .common import *
def main():
    a,i,j,m=data();labels=np.load(OUT/'compound_labels.npz');n=labels['count'];z=labels['severity'];ix=labels['job_interval']
    p=a['past'].copy().astype(np.float32);f=a['future'].copy().astype(np.float32)
    scale=read('V40R4_PHASE0_PLAN.json')['burst_threshold_GPUh'];cs=max(1.,np.quantile(np.log1p(p[m['TRAIN'],:,0]),.95))
    p[:,:,0]=np.log1p(p[:,:,0])/cs;p[:,:,1]=np.where(p[:,:,2]>0,p[:,:,1]/scale,0);p[:,:,3]=np.log1p(p[:,:,3])/np.log1p(672)
    for k in [7,9,11,13]:f[:,:,k]=np.where(f[:,:,k+1]>0,f[:,:,k]/scale,0)
    u=read('V40R4_BURST_CLASSIFICATION_RULE.json')['job_severity_Q95'];logz=np.log(z)
    suff=[]
    for flag in [z<=u,z>u]:
        for weights in [np.ones(len(z)),logz,logz**2]:suff.append(np.bincount(ix,weights=weights*flag,minlength=n.size).reshape(n.shape))
    suff=np.stack(suff,-1)
    compact=np.concatenate([np.repeat(p.mean(1)[:,None,:],48,1),np.repeat(p[:,-1,:][:,None,:],48,1),f],-1).reshape(-1,31)
    tr=np.repeat(m['TRAIN'],48);mean=compact[tr].mean(0);sd=np.maximum(compact[tr].std(0),.05)
    compact=(compact-mean)/sd;compact=np.column_stack([np.ones(len(compact)),compact])
    np.savez_compressed(OUT/'prepared.npz',past=p,future=f,compact=compact,count=n,target=labels['target'],sufficient=suff,
       days=a['days'],tail_u=u,job_interval=ix,severity=z)
    dump('V40R4_NORMALIZATION.json',{'count_scale':cs,'GPUh_scale':scale,'compact_mean':mean,'compact_sd':sd,
       'training_only':True,'compact_representation':'Mean/last of the same causal history tensor plus identical future context; internal parametric projection, no added raw information',
       'source_input_hashes':read('V40R4_INPUT_IDENTITY.json'),'prepared_SHA256':sha(OUT/'prepared.npz'),
       'sufficient_stats':'Exact per-interval body/tail N,sum(log Z),sum(log Z squared), labels only; no realized count/severity included as predictor'})
    print('Prepared exact causal tensors and job-level likelihood sufficient statistics; no forecast fit.')
if __name__=='__main__':main()
