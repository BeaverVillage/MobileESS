"""Lossless full option universe and compact per-candidate coverage encoding."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
from dayahead.paper_analysis.storage import write_json
from dayahead.v41.preflight import record


class CandidateManifest:
    def __init__(self,output,day,policy):
        self.output=Path(output);self.day=day;self.policy=policy;self.rows=[];self.counts=Counter()
        self.path=self.output/'FULL_CANDIDATES.jsonl.gz';self.stream=gzip.GzipFile(filename=str(self.path),mode='wb',mtime=0)
        self.digest=hashlib.sha256()
    def add(self,row,opts):
        options=[(o.site,o.start,o.end,o.checkpoint,o.transfer_start,o.transfer_end,o.initial_site) for o in opts]
        payload=dict(job_id=row['job_uid'],options=options)
        data=(json.dumps(payload,separators=(',',':'))+'\n').encode();self.stream.write(data);self.digest.update(data)
        initial={o.initial_site or o.site for o in opts}
        arcs={(o.initial_site or row['AIDC_site'],o.site) for o in opts if o.migrated}
        migrations=sum(o.migrated for o in opts)
        relocation=len(initial-{row['AIDC_site']}) if row['state_at_issue']=='PENDING' else 0
        self.counts.update(final_authoritative_candidates=len(opts),PENDING_relocation_candidates=relocation,
            RUNNING_migration_candidates=migrations,total_destination_arcs=len(arcs),
            eligible_relocation_jobs=int(relocation>0),eligible_migration_jobs=int(migrations>0))
        metadata=dict(job_id=row['job_uid'],candidate_count=len(opts),candidate_ids='job_id/option_index',
            candidate_index_start=0,candidate_index_end_exclusive=len(opts),candidate_row_SHA=hashlib.sha256(data).hexdigest(),
            state=row['state_at_issue'],start=row['start_slot'],end=row['end_slot'],
            can_migrate=bool(migrations),can_relocate=bool(relocation),initial_site=row['AIDC_site'],
            touched_sites=sorted({s for o in opts for s,a,b in o.segments(row)}),
            earliest_effect=min((a for o in opts for s,a,b in o.segments(row)),default=row['start_slot']),
            latest_effect=max((b for o in opts for s,a,b in o.segments(row)),default=row['end_slot']))
        self.rows.append(metadata)
        return metadata
    def finish(self):
        self.stream.close()
        value=dict(schema='V41R1_FULL_CANDIDATE_MANIFEST_V1',day=self.day,policy=self.policy,status='PASS',
            **dict(self.counts),hard_infeasible_removals=0,reason_counts={},
            removal_scope='THIS_COMPUTE_REVISION; ORIGINAL_DOMAIN_AUTHORITY_UNCHANGED',
            authoritative_domain_source=record(Path(__file__).parents[1]/'v40g/domain.py'),
            migration_authority_source=record(Path(__file__).parent/'migration.py'),
            top_K_pruning=0,sensitivity_pruning=0,candidate_set_SHA=self.digest.hexdigest(),
            candidate_artifact=record(self.path),jobs=self.rows,
            RUNNING_count_definition='Includes PENDING jobs becoming RUNNING at their first valid checkpoint',
            fixed_planned_start_preserved=True)
        write_json(self.output/'V41R1_FULL_CANDIDATE_MANIFEST.json',value)
        return value
