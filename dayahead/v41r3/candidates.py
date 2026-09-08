"""Load the certified 4,772,575 options; never invoke the domain generator."""
import gzip,hashlib,json
from dataclasses import asdict
from functools import lru_cache
from dayahead.paper_analysis.storage import read,write_json,digest
from dayahead.v41.preflight import ROOT,record
from dayahead.v40g.domain import Option
from .authority import OLD,OLD_RUN,OUT,DAY

SOURCE=OLD_RUN/DAY/'B1/dayahead/A0/V41R1_FULL_CANDIDATE_MANIFEST.json'

def verify():
    from dayahead.v41r2.authority import CAP
    cert=read(OLD/'dayahead/artifacts/v41r2_780gpu_capacity_rebase/V41R2_FULL_CANDIDATE_REENUMERATION.json')
    manifest=read(SOURCE)
    assert cert['status']==manifest['status']=='PASS'
    assert cert['count']==manifest['final_authoritative_candidates']==4772575
    assert cert['candidate_set_SHA']==manifest['candidate_set_SHA']
    assert record(CAP)['sha256']==cert['capacity_authority']['sha256']
    refs=[]
    for rel in ('dayahead/v40g/domain.py','dayahead/v41r1/migration.py','dayahead/v41r1/migration_admission.py','dayahead/v40a/feedback.py','dayahead/v38/authority.py','dayahead/v38/wan.py'):
        a,b=record(OLD/rel),record(ROOT/rel);assert a['sha256']==b['sha256'],rel
        refs.append(dict(original=a,current=b))
    assert record(manifest['candidate_artifact']['path'])['sha256']==manifest['candidate_artifact']['sha256']
    assert refs[0]['current']['sha256']==manifest['authoritative_domain_source']['sha256']
    assert refs[1]['current']['sha256']==manifest['migration_authority_source']['sha256']
    value=dict(status='PASS',certification=record(OLD/'dayahead/artifacts/v41r2_780gpu_capacity_rebase/V41R2_FULL_CANDIDATE_REENUMERATION.json'),source=record(SOURCE),candidate_set_SHA=manifest['candidate_set_SHA'],candidates=4772575,source_checks=refs,independent_reenumeration_calls=0,top_K_pruning=0,sensitivity_pruning=0)
    write_json(OUT/'V41R3_CANDIDATE_UNIVERSE_REUSE.json',value)
    return manifest

class Store:
    def __init__(self):
        self.manifest=verify();self.meta={r['job_id']:r for r in self.manifest['jobs']}
        self.refs={r['job_uid']:r for r in read(OLD_RUN/'inputs'/DAY/'common_q90_v3/COMMON_B0_REFERENCE_JOBS.json')}
        self.stream=gzip.open(self.manifest['candidate_artifact']['path'],'rb')
        self.digest=hashlib.sha256();self.offsets={};self.count=0;self.complete=False;self.checked_binding=False
    def options(self,row,capacity,wan,elapsed,temporal_only):
        assert not temporal_only,'FROZEN_DOMAIN_HAS_NO_TEMPORAL_VARIANT'
        uid=row['job_uid'];assert row==self.refs[uid],'FROZEN_DOMAIN_JOB_INPUT_DRIFT'
        if not self.checked_binding:
            from dayahead.v41r2.authority import VECTOR,SITES,CAP
            from dayahead.v38.authority import load_wan_authority
            assert tuple(capacity.site_capacity[s] for s in SITES)==VECTOR
            assert capacity.source_sha256==record(CAP)['sha256']
            assert asdict(wan.authority)==asdict(load_wan_authority(OLD)),'FROZEN_WAN_DOMAIN_DRIFT'
            self.checked_binding=True
        # Checkpoint and reference-start scalars are embedded in the frozen job.
        if uid in self.offsets:
            with gzip.open(self.manifest['candidate_artifact']['path'],'rb') as stream:
                stream.seek(self.offsets[uid]);data=stream.readline()
        else:
            assert not self.complete
            self.offsets[uid]=self.stream.tell();data=self.stream.readline()
            self.digest.update(data)
        assert hashlib.sha256(data).hexdigest()==self.meta[uid]['candidate_row_SHA']
        payload=json.loads(data);assert payload['job_id']==uid
        assert len(payload['options'])==self.meta[uid]['candidate_count']
        return tuple(Option(*o) for o in payload['options'])
    def finish(self):
        assert not self.stream.readline(),'CERTIFIED_DOMAIN_ROWS_NOT_ALL_LOADED'
        self.stream.close();self.complete=True
        assert self.digest.hexdigest()==self.manifest['candidate_set_SHA'],'CANDIDATE_DOMAIN_HASH_DRIFT'
        assert set(self.offsets)==set(self.meta)

_store=None
def options(row,capacity,wan,elapsed,temporal_only=False):
    global _store
    if _store is None:_store=Store()
    return _store.options(row,capacity,wan,elapsed,temporal_only)

class CandidateManifest:
    def __init__(self,output,day,policy):
        assert day==DAY and policy=='B1'
        self.output=output;self.rows=[]
    def add(self,row,opts):
        metadata=_store.meta[row['job_uid']]
        assert len(opts)==metadata['candidate_count'];self.rows.append(metadata)
        return metadata
    def finish(self):
        _store.finish();assert self.rows==_store.manifest['jobs']
        value=dict(_store.manifest,reused_frozen_universe=True,independent_reenumeration_calls=0,reuse_gate=record(OUT/'V41R3_CANDIDATE_UNIVERSE_REUSE.json'))
        write_json(self.output/'V41R1_FULL_CANDIDATE_MANIFEST.json',value)
        return value
