"""One scientific domain materialization per new May day; no physical ranking."""
from fast_prepare import *
import gzip,hashlib,time
from dayahead.v40g.domain import Option

MAY_RUN=ROOT/'frozen_artifacts/v41r3_may'
MAY_OUT=ROOT/'frozen_artifacts/v41r4_may/audit'

def generate(day):
    from dayahead.v41r2.authority import capacity,CAP,RACK
    from dayahead.v38.authority import load_wan_authority
    from dayahead.v41r1.migration import FrozenWanView
    from dayahead.v40g.domain import options
    from dayahead.v41.temporal_restore import restored_options
    from dayahead.v41r1.candidate_manifest import CandidateManifest
    from dayahead.paper_analysis.storage import write_json
    out=MAY_OUT/day/'domain';seal=out/'DAILY_DOMAIN_AUTHORITY.json'
    if seal.exists():return read(seal)
    assert not out.exists(),'PRESERVE_INCOMPLETE_DOMAIN_ATTEMPT'
    started=time.perf_counter();out.mkdir(parents=True)
    for name in ('base','combined'):(out/name).mkdir()
    jobpath=(RUN if day==DAY else MAY_RUN)/'inputs'/day/'common_q90_v3/COMMON_B0_REFERENCE_JOBS.json'
    jobs=read(jobpath);cap=capacity()[0];wan=FrozenWanView(load_wan_authority(ROOT))
    elapsed={r['job_uid']:r['r1_elapsed_seconds_at_issue'] for r in jobs if 'r1_elapsed_seconds_at_issue' in r}
    base=CandidateManifest(out/'base',day,'B1');full=CandidateManifest(out/'combined',day,'B1')
    restored=0;eligible=0
    for row in sorted(jobs,key=lambda r:r['job_uid']):
        original=options(row,cap,wan,elapsed);temporal=restored_options(row,cap)
        combined=tuple(sorted((*original,*temporal)))
        assert len(set(combined))==len(original)+len(temporal)
        base.add(row,original);full.add(row,combined)
        restored+=len(temporal);eligible+=bool(temporal)
    a=base.finish();b=full.finish()
    assert b['final_authoritative_candidates']==a['final_authoritative_candidates']+restored
    b.update(fixed_planned_start_preserved=False,restored_temporal_options=restored,base_universe_all_retained=True,new_shifted_start_migration_products=0)
    write_json(out/'combined/V41R1_FULL_CANDIDATE_MANIFEST.json',b)
    value=dict(status='FROZEN',day=day,base_count=a['final_authoritative_candidates'],restored_count=restored,total_count=b['final_authoritative_candidates'],eligible_temporal_jobs=eligible,base_candidate_SHA=a['candidate_set_SHA'],candidate_set_SHA=b['candidate_set_SHA'],base_manifest=record(out/'base/V41R1_FULL_CANDIDATE_MANIFEST.json'),combined_manifest=record(out/'combined/V41R1_FULL_CANDIDATE_MANIFEST.json'),reference=record(jobpath),capacity=record(CAP),rack=record(RACK),sources=[record(ROOT/p) for p in ('dayahead/v40g/domain.py','dayahead/v41r1/migration.py','dayahead/v41r1/terminal.py','dayahead/v41/temporal_restore.py','may_domain.py','v41r4_domain.py')],seconds_to_charge_B1=time.perf_counter()-started,independent_repeat_enumeration=0,domain_membership_depends_on_background=False,OpenDSS_calls=0,optimizer_calls=0)
    save(seal,value)
    print('MAY_DOMAIN_FROZEN',day,value['total_count'],value['seconds_to_charge_B1'],flush=True)
    return value

class Store:
    def __init__(self,day):
        self.authority=read(MAY_OUT/day/'domain/DAILY_DOMAIN_AUTHORITY.json')
        a=self.authority
        for entry in [a['base_manifest'],a['combined_manifest'],a['reference'],a['capacity'],a['rack'],*a['sources']]:assert record(entry['path'])==entry
        self.manifest=read(a['base_manifest']['path']);self.meta={r['job_id']:r for r in self.manifest['jobs']}
        self.refs={r['job_uid']:r for r in read(a['reference']['path'])}
        assert record(self.manifest['candidate_artifact']['path'])==self.manifest['candidate_artifact']
        self.stream=gzip.open(self.manifest['candidate_artifact']['path'],'rb');self.digest=hashlib.sha256();self.offsets={};self.complete=False;self.checked_binding=False
    def options(self,row,capacity,wan,elapsed,temporal_only=False):
        assert not temporal_only and row==self.refs[row['job_uid']]
        if not self.checked_binding:
            from dataclasses import asdict
            from dayahead.v41r2.authority import capacity as frozen_capacity
            from dayahead.v38.authority import load_wan_authority
            assert capacity.site_capacity==frozen_capacity()[0].site_capacity
            assert capacity.rack_pools==frozen_capacity()[0].rack_pools
            assert asdict(wan.authority)==asdict(load_wan_authority(ROOT))
            self.checked_binding=True
        if 'r1_elapsed_seconds_at_issue' in row:assert elapsed[row['job_uid']]==row['r1_elapsed_seconds_at_issue']
        uid=row['job_uid']
        if uid in self.offsets:
            with gzip.open(self.manifest['candidate_artifact']['path'],'rb') as f:f.seek(self.offsets[uid]);data=f.readline()
        else:
            assert not self.complete
            self.offsets[uid]=self.stream.tell();data=self.stream.readline();self.digest.update(data)
        assert hashlib.sha256(data).hexdigest()==self.meta[uid]['candidate_row_SHA']
        value=json.loads(data);assert value['job_id']==uid
        return tuple(Option(*o) for o in value['options'])
    def finish(self):
        if self.complete:return
        assert not self.stream.readline() and set(self.offsets)==set(self.meta)
        self.stream.close();self.complete=True
        assert self.digest.hexdigest()==self.manifest['candidate_set_SHA']
