"""Native-zero exact validation comparisons over every frozen May input."""
import argparse, subprocess, sys, json
from pathlib import Path
from dataclasses import replace
from v42_pr134_b1.common import ROOT,read,atomic,record,now
from v42_may_campaign_native90.preflight import native_zero
from v42_job_capability import validate,Option
from v42_may_build_v6.efficient_validation import ConstructionChecks,routed_validate
from .preflight import RUN,DOC


def outcome(function,*args):
    try:return {'value':function(*args)}
    except ValueError as error:return {'error':type(error).__name__+':'+str(error)}


def main(day=None):
    if day is None:
        for i in range(1,32):
            subprocess.run([sys.executable,'-B','-X','utf8','-m',__spec__.name,'--day','2025-05-%02d'%i],
                           check=True,cwd=ROOT,stdout=subprocess.DEVNULL)
        rows=[read(DOC/'input_checks'/('2025-05-%02d.json'%i)) for i in range(1,32)]
        atomic(DOC/'MAY31_INPUT_VALIDATION.json',dict(PASS=all(r['PASS'] for r in rows),
            Native_calls=0,P2_calls=0,UTC=now(),dates=rows,
            scope='All original frozen Job/Boundary/Resources inputs; original vs interval validator outcomes',
            full_model_reconstruction_all31='NOT_TESTED',full_model_reconstruction_May23='SEPARATE_GATE'))
        print('31-day original input and exact validation comparison PASS',flush=True)
        return
    manifest=read(RUN/'CAMPAIGN_MANIFEST.json');folder=Path(manifest['input_folders']['B1/'+day])
    destination=RUN/'preflight_v6/input_checks'/day/'DATA';destination.mkdir(parents=True,exist_ok=False)
    bundle=read(folder/'NATIVE_INPUT.json');before=record(folder/'NATIVE_INPUT.json')
    from v42_pr134_b1.native import bind
    with native_zero() as calls:
        module,*_=bind(bundle,folder,destination)
        _,jobs,bounds,_,resources,_=module.load_native()
        checks=ConstructionChecks();fast=routed_validate(checks);comparisons=0
        for uid,job in jobs.items():
            option=Option(job.reference_start,job.reference_site,
                          ((job.reference_site,job.reference_start,job.reference_start+job.service_slots),))
            for candidate in (option,replace(option,start=-1),
                              replace(option,wan=(('__MISSING__',0,resources.bytes_per_gpu*job.gpu),))):
                assert outcome(fast,job,candidate,bounds[uid],resources)==outcome(validate,job,candidate,bounds[uid],resources)
                comparisons+=1
        checks.verify_resources()
    assert not calls and before==record(folder/'NATIVE_INPUT.json')
    atomic(DOC/'input_checks'/(day+'.json'),dict(PASS=True,day=day,Native_calls=0,P2_calls=0,
        jobs=len(jobs),comparisons=comparisons,input_SHA=before['sha256'],input=before,
        windows=record(folder/'WINDOWS.json'),all_original_dates_and_input_values_preserved=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--day');main(parser.parse_args().day)
