"""Memoize decoded certified tuples across model construction and evaluation."""
from dayahead.v41r3.candidates import options as load_options
from dayahead.v41r1.candidate_manifest import CandidateManifest as BaseManifest
from dayahead.v41.temporal_restore import restored_options,TOTAL_COUNT,RESTORED_COUNT
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import record
from dayahead.v41r3.authority import OUT
_cache={}
_rows={}
def options(row,capacity,wan,elapsed,temporal_only=False):
    uid=row['job_uid']
    if uid not in _cache:
        base=load_options(row,capacity,wan,elapsed,temporal_only)
        restored=restored_options(row,capacity)
        _cache[uid]=tuple(sorted((*base,*restored)))
        assert len(set(_cache[uid]))==len(base)+len(restored)
        _rows[uid]=dict(row)
    assert not temporal_only and row==_rows[uid]
    return _cache[uid]

class CandidateManifest(BaseManifest):
    def finish(self):
        from dayahead.v41r3.candidates import _store
        _store.finish()
        value=super().finish()
        assert value['final_authoritative_candidates']==TOTAL_COUNT
        ranking=read(OUT/'V41R3_FO_PHYSICS_RANKING_AUDIT.json')
        assert value['candidate_set_SHA']==ranking['candidate_set_SHA'],'RESTORED_DOMAIN_HASH_DRIFT'
        value.update(restored_temporal_options=RESTORED_COUNT,base_universe_SHA=_store.manifest['candidate_set_SHA'],base_universe_all_retained=True,restoration_authority=record(OUT/'V41R3_TIMESHIFTING_RESTORATION_AUTHORITY.json'),fixed_planned_start_preserved=False,temporal_semantics='EXACT_RESTORED_PRE_V4_DOMAIN; NO_NEW_MIGRATION_TIME_PRODUCTS')
        write_json(self.output/'V41R1_FULL_CANDIDATE_MANIFEST.json',value)
        write_json(OUT/'V41R3_RESTORED_CANDIDATE_DOMAIN.json',dict(status='PASS',candidate_set_SHA=value['candidate_set_SHA'],total=TOTAL_COUNT,base_count=TOTAL_COUNT-RESTORED_COUNT,restored_count=RESTORED_COUNT,manifest=record(self.output/'V41R1_FULL_CANDIDATE_MANIFEST.json')))
        return value
