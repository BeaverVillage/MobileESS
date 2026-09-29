"""Deterministic bounded retrieval; exact ranking within causal candidate union."""
import numpy as np

KEY=np.dtype([('group','<i4'),('time','<i8')])

def stack_similarity(mapping):
    sets=[set()]+[set(s.split('|'))-{'','<MISSING>'} for s in mapping]
    out=np.zeros((len(sets),len(sets)),np.float32)
    for i,a in enumerate(sets):
        for j,b in enumerate(sets):
            if a or b:out[i,j]=len(a&b)/len(a|b)
    return out

class CompletedNeighborIndex:
    def __init__(self,ids,end,codes,resources,runtime,stack_tables):
        self.ids=np.asarray(ids,np.int32);self.end=np.asarray(end,np.int64)
        self.codes=np.asarray(codes,np.int32);self.resources=np.asarray(resources,np.float32)
        self.runtime=np.asarray(runtime,float);self.stack_tables=stack_tables
        self.order=np.lexsort((self.ids,self.end));self.indices=[]
        for c in range(codes.shape[1]):
            order=np.lexsort((self.ids,self.end,codes[:,c]))
            key=np.empty(len(ids),KEY);key['group']=codes[order,c];key['time']=end[order]
            self.indices.append((order,key))

    def query(self,submit,codes,resources):
        n=len(submit);parts=[]
        for c,(order,key) in enumerate(self.indices):
            q=np.empty(n,KEY);q['group']=codes[:,c];q['time']=submit
            pos=np.searchsorted(key,q,side='left')[:,None]-1-np.arange(16)
            ix=order[np.clip(pos,0,len(order)-1)]
            valid=(pos>=0)&(self.codes[ix,c]==codes[:,c,None])&(codes[:,c,None]>0)&(self.end[ix]<submit[:,None])
            parts.append(np.where(valid,ix,-1))
        pos=np.searchsorted(self.end[self.order],submit,side='left')[:,None]-1-np.arange(64)
        parts.append(np.where(pos>=0,self.order[np.clip(pos,0,len(self.order)-1)],-1))
        candidate=np.sort(np.concatenate(parts,axis=1),axis=1)
        valid=candidate>=0
        valid[:,1:] &= candidate[:,1:]!=candidate[:,:-1]
        safe=np.maximum(candidate,0)
        assert np.all(self.end[safe][valid]<np.broadcast_to(submit[:,None],safe.shape)[valid])
        similarity=np.zeros(candidate.shape,np.float32)
        for c in range(8):similarity+=(self.codes[safe,c]==codes[:,c,None])&(codes[:,c,None]>0)
        for c,table in zip([8,9],self.stack_tables):
            similarity+=table[np.maximum(codes[:,c,None],0),np.maximum(self.codes[safe,c],0)]
        distance=np.mean(np.abs(self.resources[safe]-resources[:,None,:]),axis=2)
        similarity=(similarity+np.exp(-distance))/11
        similarity[~valid]=-np.inf
        # Candidate order provides deterministic pool-row tie breaks, fixed by historic row order.
        rank=np.argsort(-similarity,axis=1,kind='stable')[:,:64]
        ix=np.take_along_axis(candidate,rank,axis=1);sim=np.take_along_axis(similarity,rank,axis=1)
        ix[~np.isfinite(sim)]=-1
        outputs=[]
        for k in [16,64]:
            use=ix[:,:k];v=use>=0;count=v.sum(axis=1)
            y=np.where(v,self.runtime[np.maximum(use,0)],np.nan)
            ss=np.where(v,sim[:,:k],np.nan)
            with np.errstate(invalid='ignore',divide='ignore'):
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore',RuntimeWarning)
                    quant=np.nanquantile(y,[.5,.75,.9],axis=1).T
                    feat=np.column_stack([quant,np.nanmean(np.log1p(y),axis=1),
                        np.sum((y>14400)&v,axis=1)/count,np.sum((y>43200)&v,axis=1)/count,
                        count,np.nanmax(ss,axis=1),np.nanmean(ss,axis=1)])
            outputs.append(feat)
        ids=np.where(ix>=0,self.ids[np.maximum(ix,0)],-1)
        return np.column_stack(outputs).astype(np.float32),ids
