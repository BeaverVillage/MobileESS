"""Persist evidence-backed triage without touching date results or budgets."""
import argparse,json
from pathlib import Path
from v42_may_campaign.common import atomic,read,record,now,d_path
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
        atomic(storage/'MAINTENANCE_STATE.json',state)
        return dict(status=item['status'],issue_id=key,evidence=record(evidence))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--storage',required=True);p.add_argument('--session-token',required=True)
    p.add_argument('--issue-id',required=True);p.add_argument('--evidence',required=True);a=p.parse_args()
    print(json.dumps(resolve(a.storage,a.session_token,a.issue_id,a.evidence),ensure_ascii=False))
