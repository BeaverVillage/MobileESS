"""One train-only categorical transformer for historical replay and future arrivals."""
from dataclasses import dataclass, field, fields
from collections import Counter
from datetime import datetime
import hashlib, json, unicodedata
from pathlib import Path
import numpy as np
from sklearn.feature_extraction import FeatureHasher
from sklearn.decomposition import TruncatedSVD
from threadpoolctl import threadpool_limits

VERSION = 'SEM_COOCCUR32_V1'
ENABLE_SUBMISSION_SEMANTICS = False
DEFAULT_FIELDS = ('user', 'submit_line')
INTERFACE_FIELDS = ('user','account','partition','qos','job_type','name','submit_line','script','modules','conda_envs')

def instant(value):
    d = datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if d.tzinfo is None: raise ValueError('TIMEZONE_REQUIRED')
    return d

@dataclass(frozen=True, repr=False)
class SubmissionSemanticPayload:
    user: str | None = None
    account: str | None = None
    partition: str | None = None
    qos: str | None = None
    job_type: str | None = None
    name: str | None = None
    submit_line: str | None = None
    script: str | None = None
    modules: tuple[str,...] | None = None
    conda_envs: tuple[str,...] | None = None
    identity_namespace: str = 'future-site-v1'

    def __repr__(self): return 'SubmissionSemanticPayload(<redacted>)'

@dataclass(frozen=True)
class SubmissionSemanticRecord:
    job_uid: str
    submit_time: str
    observed_at: str
    payload: SubmissionSemanticPayload = field(repr=False)

    def validate(self, issue_time):
        submit, observed, issue = map(instant, [self.submit_time,self.observed_at,issue_time])
        if submit > issue: raise ValueError('NOT_SUBMITTED')
        if observed > submit: raise ValueError('NOT_ORIGINAL_SUBMISSION_PAYLOAD')
        if not self.payload.identity_namespace: raise ValueError('IDENTITY_NAMESPACE_REQUIRED')

@dataclass(frozen=True)
class NumericSemanticFeatures:
    sem: tuple[float,...]
    recurrence: tuple[float,...]
    feature_version: str
    bundle_sha256: str
    support_level: str

    def __post_init__(self):
        if len(self.sem) != 32 or not np.isfinite(self.sem+self.recurrence).all():
            raise ValueError('INVALID_NUMERIC_SEMANTICS')

def _value_token(payload, name):
    value = getattr(payload, name)
    if value is None: return name+'=<FIELD_MISSING>'
    values = value if isinstance(value,(list,tuple)) else [value]
    if not all(isinstance(x,str) for x in values): raise ValueError('SEMANTIC_STRING_REQUIRED')
    values = sorted(set(unicodedata.normalize('NFC',x).strip() for x in values if x.strip()))
    if not values: return name+'=<FIELD_MISSING>'
    encoded = json.dumps([payload.identity_namespace,name,values],ensure_ascii=False,separators=(',',':')).encode()
    return name+'='+hashlib.sha256(encoded).hexdigest()

class SemanticFeatureAdapter:
    """fit() is offline only; transform() never updates SVD, vocabulary or counts."""
    def __init__(self, whitelist=DEFAULT_FIELDS, combinations=(('user','submit_line'),)):
        if not whitelist or set(whitelist)-set(INTERFACE_FIELDS): raise ValueError('INVALID_WHITELIST')
        if any(set(pair)-set(whitelist) for pair in combinations): raise ValueError('INVALID_COMBINATION')
        self.whitelist=tuple(whitelist);self.combinations=tuple(tuple(x) for x in combinations)
        self.hasher=FeatureHasher(n_features=262144,input_type='string',alternate_sign=False,dtype=np.float64)
        self.svd=None;self.counts=None;self.bundle_sha256=None

    def canonical(self,payload):
        if payload is None: payload=SubmissionSemanticPayload()
        return tuple(sorted({_value_token(payload,f) for f in self.whitelist}))

    def _identities(self,tokens):
        byfield={t.split('=',1)[0]:t for t in tokens}
        # Missing is not a recurrent observed identity.
        single=[None if '<FIELD_MISSING>' in byfield[f] else byfield[f] for f in self.whitelist]
        pair=[None if any('<FIELD_MISSING>' in byfield[f] for f in fs) else '\x1f'.join(byfield[f] for f in fs) for fs in self.combinations]
        return single+pair

    @property
    def recurrence_names(self):
        names=list(self.whitelist)+['_'.join(p) for p in self.combinations]
        return [f'rec_{n}_{kind}' for n in names for kind in ['frequency','log1p_frequency','seen']]

    def fit(self,payloads,*,training_receipt):
        if self.svd is not None: raise ValueError('ALREADY_FITTED_NO_ONLINE_REFIT')
        if not training_receipt.get('TRAIN_ONLY') or not training_receipt.get('membership_sha256'):
            raise ValueError('TRAIN_MEMBERSHIP_RECEIPT_REQUIRED')
        tokens=[self.canonical(p) for p in payloads]
        if len(tokens)<32: raise ValueError('SVD32_INSUFFICIENT_TRAIN_ROWS')
        self.counts=[Counter() for _ in range(len(self.whitelist)+len(self.combinations))]
        for row in tokens:
            for counter,value in zip(self.counts,self._identities(row)):
                if value is not None: counter[value]+=1
        x=self.hasher.transform(tokens)
        self.svd=TruncatedSVD(n_components=32,random_state=1401,algorithm='randomized',n_iter=5,n_oversamples=10)
        with threadpool_limits(limits=4): self.svd.fit(x)
        self.training_receipt=dict(training_receipt)
        self._seal()
        return self

    def _seal(self):
        meta=json.dumps(dict(version=VERSION,whitelist=self.whitelist,combinations=self.combinations,
                             counts=[dict(sorted(c.items())) for c in self.counts],receipt=self.training_receipt),sort_keys=True).encode()
        self.bundle_sha256=hashlib.sha256(meta+self.svd.components_.tobytes()).hexdigest()

    def transform(self,payloads):
        if self.svd is None: raise ValueError('UNFITTED_ADAPTER')
        tokens=[self.canonical(p) for p in payloads]
        if not tokens:return np.empty((0,32),np.float32),np.empty((0,len(self.recurrence_names)),np.float32)
        with threadpool_limits(limits=4): sem=self.svd.transform(self.hasher.transform(tokens)).astype(np.float32)
        rec=[]
        for row in tokens:
            values=[]
            for counter,identity in zip(self.counts,self._identities(row)):
                n=counter.get(identity,0) if identity is not None else 0
                values.extend([n,np.log1p(n),float(n>0)])
            rec.append(values)
        rec=np.asarray(rec,np.float32)
        if not np.isfinite(sem).all() or not np.isfinite(rec).all(): raise ValueError('NONFINITE_SEMANTICS')
        return sem,rec

    def transform_record(self,record,issue_time):
        record.validate(issue_time)
        s,r=self.transform([record.payload])
        n=sum('<FIELD_MISSING>' not in t for t in self.canonical(record.payload))
        level='MINIMAL' if n==0 else 'FULL' if n==len(self.whitelist) else 'PARTIAL'
        return NumericSemanticFeatures(tuple(map(float,s[0])),tuple(map(float,r[0])),VERSION,self.bundle_sha256,level)

    def save(self,directory):
        p=Path(directory);p.mkdir(parents=True,exist_ok=True)
        np.save(p/'svd_components.npy',self.svd.components_,allow_pickle=False)
        meta=dict(version=VERSION,whitelist=self.whitelist,combinations=self.combinations,
                  counts=[dict(c) for c in self.counts],training_receipt=self.training_receipt,
                  bundle_sha256=self.bundle_sha256,components_sha256=hashlib.sha256((p/'svd_components.npy').read_bytes()).hexdigest(),
                  hasher=dict(n_features=262144,input_type='string',alternate_sign=False),dtype='float32')
        (p/'adapter.json').write_text(json.dumps(meta,sort_keys=True,ensure_ascii=False),encoding='utf-8')

    @classmethod
    def load(cls,directory):
        p=Path(directory);m=json.loads((p/'adapter.json').read_text(encoding='utf-8'))
        if m['version']!=VERSION: raise ValueError('SEMANTIC_VERSION_MISMATCH')
        if hashlib.sha256((p/'svd_components.npy').read_bytes()).hexdigest()!=m['components_sha256']:
            raise ValueError('BUNDLE_INTEGRITY_FAILURE')
        a=cls(m['whitelist'],m['combinations']);a.counts=[Counter(c) for c in m['counts']]
        a.svd=TruncatedSVD(n_components=32,random_state=1401);a.svd.components_=np.load(p/'svd_components.npy',allow_pickle=False)
        a.svd.n_features_in_=262144;a.training_receipt=m['training_receipt'];a._seal()
        if a.bundle_sha256!=m['bundle_sha256']: raise ValueError('BUNDLE_INTEGRITY_FAILURE')
        return a

def historical_payload(row):
    """Strict projection. Labels, mutable final attributes and custom derived fields are ignored."""
    return SubmissionSemanticPayload(user=row.get('user_hash') if isinstance(row.get('user_hash'),str) else None,
                                     submit_line=row.get('submit_line_hash') if isinstance(row.get('submit_line_hash'),str) else None,
                                     identity_namespace='kestrel-job-anon-v1')

class SubmissionSemanticCache:
    """Keep only submission-time numeric vectors, including while a job is running."""
    def __init__(self,adapter,enabled=ENABLE_SUBMISSION_SEMANTICS):
        self.adapter=adapter;self.enabled=enabled;self._values={}
    def on_submit(self,record,event_time):
        record.validate(event_time)
        if not self.enabled:return None
        if record.job_uid in self._values:raise ValueError('SUBMISSION_ALREADY_FROZEN')
        out=self.adapter.transform_record(record,event_time);self._values[record.job_uid]=out
        return out
    def running(self,job_uid):return self._values.get(job_uid)
