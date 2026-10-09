"""Persist evidence-backed triage without touching date results or budgets."""
import argparse,json,csv
from pathlib import Path
from v42_may_campaign.common import atomic,read,record,now,d_path,table
from .session import check_lock


def resolve(storage,token,key,evidence):
    storage=d_path(storage);evidence=d_path(evidence)
    with check_lock(storage,token):
        proof=read(evidence)
        if not proof.get('root_cause') or proof.get('original_results_preserved') is not True or not proof.get('source_evidence'):
            raise PermissionError('ROOT_CAUSE_AND_ORIGINAL_EVIDENCE_REQUIRED')
        from v42_may_campaign.common import sha
        for item in proof['source_evidence']:
            if sha(item['path'])!=item['sha256']:raise PermissionError('TRIAGE_EVIDENCE_SHA_DRIFT')
        state=read(storage/'MAINTENANCE_STATE.json');item=state['pending_issues'][key]
        item.update(status='RESOLVED_CLASSIFIED',resolved_UTC=now(),resolution=record(evidence))
        causes_path=storage/'FAILURE_ROOT_CAUSE.csv'
        causes=list(csv.DictReader(causes_path.open(encoding='utf-8'))) if causes_path.is_file() else []
        original=item.get('issue',{})
        for cause in causes:
            if (cause.get('arm'),cause.get('day'),cause.get('result_SHA'))==(original.get('arm'),original.get('day'),original.get('result_SHA')):
                cause.update(diagnosis=proof['root_cause'],resolved_UTC=item['resolved_UTC'],resolution_SHA=item['resolution']['sha256'])
        table(causes_path,causes,['UTC','arm','day','status','category','error','result_SHA','diagnosis','retries','resolved_UTC','resolution_SHA'])
        atomic(storage/'MAINTENANCE_STATE.json',state)
        return dict(status=item['status'],issue_id=key,evidence=record(evidence))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage',required=True);p.add_argument('--session-token',required=True)
    p.add_argument('--issue-id',required=True);p.add_argument('--evidence',required=True);a=p.parse_args()
    print(json.dumps(resolve(a.storage,a.session_token,a.issue_id,a.evidence),ensure_ascii=False))
