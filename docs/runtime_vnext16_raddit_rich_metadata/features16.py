"""Label-free, TRAIN-fitted native diagnostic representation. No suffix arithmetic."""
import hashlib
import numpy as np
import pandas as pd
from scipy import sparse

RESOURCE=['nodes_req','processors_req','memory_req_raw','wallclock_req_sec']
IDENTITY=['user','account','partition','qos','job_type','name','script','submit_line']
STACK=['modules','conda_envs']
ALLOWED=set(RESOURCE+IDENTITY+STACK+['submit_time'])
FORBIDDEN={'start_time','end_time','wallclock_used_sec','avg_power_per_node','job_id','runtime','actual_runtime','future_queue','queue_wait'}

def validate_payload(payload):
    extra=set(payload)-ALLOWED
    if extra:raise ValueError('Unapproved predictor keys: '+','.join(sorted(extra)))

def strings(s):return s.fillna('<MISSING>').astype(str)

class NativeAdapter:
    def fit(self,d):
        validate_payload(d.columns)
        self.maps={};self.vocab={};self.freq={};self.pairs={}
        for c in IDENTITY+STACK:
            s=strings(d[c]);self.maps[c]={v:i+1 for i,v in enumerate(pd.unique(s))}
            self.freq[c]=s.value_counts().to_dict()
        for c in STACK:
            # Opaque token spelling is used only for exact equality, never numeric/linguistic similarity.
            self.vocab[c]={v:i for i,v in enumerate(dict.fromkeys(v for s in strings(d[c]) for v in s.split('|') if v and v!='<MISSING>'))}
        for a,b in [('user','script'),('account','script'),('user','submit_line')]:
            self.pairs[(a,b)]=(strings(d[a])+'\x1f'+strings(d[b])).value_counts().to_dict()
        r=np.log1p(np.maximum(d[RESOURCE].to_numpy(dtype=float),0))
        self.center=np.nanmedian(r,axis=0);self.scale=np.maximum(np.nanquantile(r,.75,axis=0)-np.nanquantile(r,.25,axis=0),1)
        return self

    def codes(self,d):
        return np.column_stack([strings(d[c]).map(self.maps[c]).fillna(-1).to_numpy(np.int32) for c in IDENTITY+STACK])

    def resources(self,d):
        r=np.log1p(np.maximum(d[RESOURCE].to_numpy(dtype=float),0))
        return np.nan_to_num((r-self.center)/self.scale,nan=0,posinf=0,neginf=0).astype(np.float32)

    def transform(self,d,arm,neighbors=None):
        validate_payload(d.columns)
        if arm not in ['D0','D1','D2','D3','D4','SOFTWARE_STACK','IDENTITY_ONLY','NEG_SHUFFLE','EMB_D0','EMB_D2']:
            raise ValueError(arm)
        pieces=[sparse.csr_matrix(d[RESOURCE].to_numpy(np.float32))];names=RESOURCE.copy();cats=[]
        # D0 is strictly resource/request-only: no calendar or IDs.
        ids=IDENTITY if arm in ['D1','D2','D3','D4','NEG_SHUFFLE','EMB_D2'] else ['user','account','name','script'] if arm=='IDENTITY_ONLY' else []
        stacks=STACK if arm in ['D2','D3','D4','SOFTWARE_STACK','NEG_SHUFFLE','EMB_D2'] else []
        for c in ids+stacks:
            a=strings(d[c]).map(self.maps[c]).fillna(-1).to_numpy(np.float32)
            cats.append(len(names));names.append(c);pieces.append(sparse.csr_matrix(a[:,None]))
        for c in stacks:
            vocab=self.vocab[c];rr=[];cc=[];unknown=np.zeros(len(d),np.float32)
            # Iterate unique bundles once, then expand sparse binary membership by bundle code.
            vals,inv=np.unique(strings(d[c]).to_numpy(),return_inverse=True)
            for i,s in enumerate(vals):
                for v in s.split('|'):
                    if v in vocab:rr.append(i);cc.append(vocab[v])
            small=sparse.csr_matrix((np.ones(len(rr),np.float32),(rr,cc)),shape=(len(vals),len(vocab)))
            pieces.append(small[inv]);names += [c+'_token_'+str(i) for i in range(len(vocab))]
            counts=np.array([sum(v not in vocab for v in s.split('|') if v and v!='<MISSING>') for s in vals],np.float32)
            pieces.append(sparse.csr_matrix(counts[inv,None]));names.append(c+'_unseen_count')
        if arm=='D3':
            for c in IDENTITY+STACK:
                a=np.log1p(strings(d[c]).map(self.freq[c]).fillna(0).to_numpy(float))
                pieces.append(sparse.csr_matrix(a[:,None]));names.append(c+'_train_frequency')
            for (a,b),counts in self.pairs.items():
                x=np.log1p((strings(d[a])+'\x1f'+strings(d[b])).map(counts).fillna(0).to_numpy(float))
                pieces.append(sparse.csr_matrix(x[:,None]));names.append(a+'_'+b+'_train_cooccurrence')
        if arm=='D4':
            assert neighbors is not None and len(neighbors)==len(d)
            pieces.append(sparse.csr_matrix(neighbors));names += ['neighbor_'+str(i) for i in range(neighbors.shape[1])]
        return sparse.hstack(pieces,format='csr',dtype=np.float32),names,cats

def shuffle_identity_within_days(d,seed=1601):
    out=d.copy();rng=np.random.default_rng(seed)
    day=pd.to_datetime(d.submit_time,utc=True).dt.floor('D')
    for indices in pd.Series(np.arange(len(d))).groupby(day.to_numpy(),sort=True).groups.values():
        ix=np.asarray(indices);perm=rng.permutation(ix)
        out.iloc[ix,out.columns.get_indexer(IDENTITY+STACK)]=d.iloc[perm][IDENTITY+STACK].to_numpy()
    return out

def stable_random_rename(d,seed=1601):
    out=d.copy()
    for c in ['user','account','script']:
        out[c]=strings(d[c]).map(lambda s:hashlib.sha256((str(seed)+'|'+c+'|'+s).encode()).hexdigest())
    return out
