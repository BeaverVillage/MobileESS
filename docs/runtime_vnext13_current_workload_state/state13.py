"""Event-sourced state. This module has no archive, label, or model dependency.

The dispatcher owns event scheduling. The engine receives only observed events.
Pickle checkpoints are trusted local research artifacts, never untrusted input.
"""
import bisect, math, pickle
from collections import Counter, deque
from pathlib import Path

FIELDS=('num_gpus_req','num_nodes_req','num_cores_req','requested_memory_mib',
        'requested_seconds','array_index','qos','partition','account')
WINDOWS=(300,900,3600,21600,86400)
SCALE=1000000
def category(x): return '__MISSING__' if x is None or str(x) in ('nan','<NA>','None') else str(x)
def number(x):
    try:
        v=float(x)
        return v if math.isfinite(v) and v>=0 else None
    except (ValueError,TypeError): return None
def descriptor(raw):
    extra=set(raw)-set(FIELDS)
    if extra: raise ValueError('Forbidden descriptor keys: '+str(sorted(extra)))
    d={c:category(raw.get(c)) for c in ('qos','partition','account')}
    for c in FIELDS[:6]:d[c]=number(raw.get(c))
    d['gpu_bucket']=str(bisect.bisect_left([1,4,8,16],d['num_gpus_req'])) if d['num_gpus_req'] is not None else 'MISSING'
    d['wall_bucket']=str(bisect.bisect_left([3600,14400,43200,86400],d['requested_seconds'])) if d['requested_seconds'] is not None else 'MISSING'
    return d
def quantile(a,p):
    if not a:return float('nan')
    k=(len(a)-1)*p;i=int(k);r=k-i
    return a[i]*(1-r)+a[min(i+1,len(a)-1)]*r

class Bag:
    def __init__(self):
        self.n=0;self.sums=Counter();self.valid=Counter()
        self.gpu=[];self.wall=[];self.times=[]
        self.counts={c:Counter() for c in ('account','qos','partition','gpu_bucket','wall_bucket')}
    def update(self,d,t,sign):
        self.n+=sign
        for c in FIELDS[:5]:
            v=d[c]
            if v is not None:
                self.sums[c]+=sign*round(v*SCALE);self.valid[c]+=sign
        g=d['num_gpus_req'];w=d['requested_seconds']
        if g is not None and w is not None and w>0:
            self.sums['gpu_time']+=sign*round(g*w*SCALE)
        for key,flag in [('high_gpu',g is not None and g>=16),('long_wall',w is not None and w>14400),('array',d['array_index'] is not None)]:
            self.sums[key]+=sign*int(flag)
        for values,value in [(self.gpu,g),(self.wall,w),(self.times,t)]:
            if value is None:continue
            if sign==1:bisect.insort_right(values,value)
            else:
                i=bisect.bisect_left(values,value)
                assert i<len(values) and values[i]==value
                values.pop(i)
        for c,count in self.counts.items():
            count[d[c]]+=sign
            if count[d[c]]==0:del count[d[c]]
        assert self.n>=0
    def base(self,prefix,t,kind):
        f={prefix+'count':self.n}
        sums=FIELDS[:4] if kind=='running' else FIELDS[:4]+('gpu_time',)
        for c in sums:f[prefix+c+'_sum']=self.sums[c]/SCALE
        if kind=='arrival':
            for c,values in [('num_gpus_req',self.gpu),('requested_seconds',self.wall)]:
                f[prefix+c+'_mean']=self.sums[c]/SCALE/self.valid[c] if self.valid[c] else float('nan')
                f[prefix+c+'_q50']=quantile(values,.5)
            for p in [.75,.9]:f[prefix+'wall_q'+str(int(p*100))]=quantile(self.wall,p)
            for key in ['high_gpu','long_wall','array']:
                f[prefix+key+'_fraction']=self.sums[key]/self.n if self.n else 0.
                f[prefix+key+'_count']=self.sums[key]
        if kind=='pending':
            for name,values in [('wall',self.wall),('gpu',self.gpu)]:
                for p in [.5,.9]:f[prefix+name+'_q'+str(int(p*100))]=quantile(values,p)
            f[prefix+'long_wall_fraction']=self.sums['long_wall']/self.n if self.n else 0.
        if kind!='arrival':
            for p in [.5,.9]:f[prefix+'age_q'+str(int(p*100))]=t-quantile(self.times,1-p)
            f[prefix+'age_max']=t-self.times[0] if self.times else float('nan')
        return f
    def composition(self,prefix,vocab,available):
        f={}
        for c in ['qos','partition','gpu_bucket','wall_bucket']:
            names=vocab[c] if c in vocab else [str(i) for i in range(5)]+['MISSING']
            counts=self.counts[c];n=self.n;selected=0
            for i,name in enumerate(names):
                value=counts[name] if available or c not in vocab else 0
                f[prefix+c+'_share_'+str(i)]=value/n if n else 0.;selected+=value
            values=[f[prefix+c+'_share_'+str(i)] for i in range(len(names))]
            other=(n-selected)/n if n else 0.;values.append(other)
            f[prefix+c+'_OTHER']=other
            f[prefix+c+'_entropy']=-sum(p*math.log(p) for p in values if p>0)
            f[prefix+c+'_HHI']=sum(p*p for p in values)
        return f

class State:
    version='V13_EVENT_STATE_1'
    def __init__(self,vocab,available_after):
        self.vocab=vocab;self.available_after=available_after
        self.pending={};self.running={};self.phase={}
        self.pbag=Bag();self.rbag=Bag();self.arrivals={w:deque() for w in WINDOWS}
        self.abags={w:Bag() for w in WINDOWS};self.latest_event=None;self.latest_query=None
        self.previous_submit=None;self.processed=Counter();self.duplicates=0
        self.cache_time=None;self.cache=None
    def apply(self,event,asof):
        if set(event)-{'time','kind','job_id','request'}:raise ValueError('Forbidden event payload')
        t=event['time'];kind=event['kind'];j=event['job_id']
        if t>=asof:raise ValueError('Future/simultaneous event rejected')
        if self.latest_event is not None and t<self.latest_event:raise ValueError('Event time reversal')
        if self.latest_query is not None and t<self.latest_query:raise ValueError('Late historical event rejected')
        if kind not in ('SUBMIT','START','END'):raise ValueError('Unknown event')
        if kind!='SUBMIT' and 'request' in event:raise ValueError('Unexpected START/END payload')
        d=descriptor(event['request']) if kind=='SUBMIT' else None
        phase=self.phase.get(j,0)
        desired={'SUBMIT':1,'START':2,'END':3}[kind]
        if phase>=desired:
            self.duplicates+=1;self.latest_event=t;return
        if kind=='SUBMIT':
            self.pending[j]=(d,t);self.pbag.update(d,t,1)
            for w in WINDOWS:self.arrivals[w].append((t,d));self.abags[w].update(d,t,1)
            self.previous_submit=t
        elif kind=='START':
            if phase!=1:raise ValueError('START without observed SUBMIT')
            d,submitted=self.pending.pop(j);self.pbag.update(d,submitted,-1)
            self.running[j]=(d,t);self.rbag.update(d,t,1)
        else:
            if phase==1:
                d,submitted=self.pending.pop(j);self.pbag.update(d,submitted,-1)
            elif phase==2:
                d,started=self.running.pop(j);self.rbag.update(d,started,-1)
            else:raise ValueError('END without observed SUBMIT')
        self.phase[j]=desired;self.latest_event=t;self.processed[kind]+=1;self.cache_time=None
    def predict(self,raw,t):
        d=descriptor(raw)
        if self.latest_query is not None and t<self.latest_query:raise ValueError('Query time reversal')
        if self.latest_event is not None and self.latest_event>=t:raise ValueError('State contains non-past event')
        if t!=self.cache_time:
            f={}
            for w in WINDOWS:
                queue=self.arrivals[w];bag=self.abags[w]
                while queue and queue[0][0]<t-w:
                    when,old=queue.popleft();bag.update(old,when,-1)
                if w==300:f['a_300_count']=bag.n
                else:f.update(bag.base('a_'+str(w)+'_',t,'arrival'))
            f.update(self.pbag.base('p_',t,'pending'));f.update(self.rbag.base('r_',t,'running'))
            for prefix,bag in [('c_pending_',self.pbag),('c_running_',self.rbag)]:
                f.update(bag.composition(prefix,self.vocab,t>self.available_after))
            f['a_since_previous_submit']=t-self.previous_submit if self.previous_submit is not None else float('nan')
            # All same-timestamp events are excluded. This is a support marker,
            # not the retrospective size of the current submission burst.
            f['a_observed_same_timestamp_count']=0
            self.cache=f;self.cache_time=t
        f=self.cache.copy()
        for w in [3600,21600]:f['a_same_account_'+str(w)]=self.abags[w].counts['account'][d['account']]
        for c in ['qos','partition']:f['a_same_'+c+'_3600']=self.abags[3600].counts[c][d[c]]
        f['p_same_account']=self.pbag.counts['account'][d['account']]
        f['r_same_account']=self.rbag.counts['account'][d['account']]
        f['x_gpu_arrival_3600']=d['num_gpus_req']*f['a_3600_num_gpus_req_sum'] if d['num_gpus_req'] is not None else float('nan')
        f['x_wall_pending_long']=d['requested_seconds']*f['p_long_wall_fraction'] if d['requested_seconds'] is not None else float('nan')
        f['x_same_partition_pending']=self.pbag.counts['partition'][d['partition']]
        f['x_same_qos_arrival_3600']=f['a_same_qos_3600']
        self.latest_query=t
        return f
    def save(self,path):
        Path(path).write_bytes(pickle.dumps(self,protocol=5))
    @classmethod
    def load(cls,path):
        state=pickle.loads(Path(path).read_bytes())
        if state.version!=cls.version:raise ValueError('State schema mismatch')
        return state
