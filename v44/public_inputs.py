"""Prepare the same six public descriptor columns, separately for each date."""
from pathlib import Path
from .common import DOC,read,record,atomic
from .config import DAYS
from .daily import clone
from .inputs import BUNDLE_ROOT


def prepare_descriptors():
    from v43_corrective import public_metadata as original
    path=DOC/'DAILY_AUTHORITY_BINDINGS.json';bindings=read(path) if path.exists() else {}
    for day in DAYS:
        destination=DOC/'input_metadata'/day/'PUBLIC_REQUEST_DESCRIPTORS.json'
        bundle=BUNDLE_ROOT/('DAY_'+day.replace('-',''))
        doc=clone(original.build,BUNDLE=bundle)(destination)
        if set(doc['descriptors'])!={r['job_uid'] for r in read(bundle/'ACTUAL_INPUT_BUNDLE.json')['post_issue_arrivals']}:
            raise ValueError('DATED_PUBLIC_DESCRIPTOR_UID_JOIN')
        bindings.setdefault(day,{})['request_descriptors']=record(destination)
    atomic(path,bindings)


if __name__=='__main__':prepare_descriptors()
