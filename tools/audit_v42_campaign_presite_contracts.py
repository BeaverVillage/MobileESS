"""Independently verify R1 contracts against compiled public date WAN inputs."""
from pathlib import Path
import gzip
import json
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import file_record,_write
from v42_integration.policy import digest
from v42_integration.research_presite_contract import ResearchPresiteProvider

BASE=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015'


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    folder=BASE/'RC03/CAMPAIGN_R1_CONTRACTS';target=folder/'INDEPENDENT_SOURCE_DATE_WAN_AUDIT.json'
    if target.exists():raise FileExistsError('INDEPENDENT_DATE_CONTRACT_AUDIT_MUST_NOT_OVERWRITE')
    preparation=read(folder/'MAY31_R1_CONTRACT_PREPARATION.json');rows=[]
    for day,policy in preparation['actual_policy_by_day'].items():
        case=BASE/'RC02/DATE_CASES/COMPILE01'/day/'CASE'
        manifest=read(case/'D0_CASE_MANIFEST.json')
        public_native=case/'D0_NATIVE_PUBLIC_INPUT.json.gz'
        if public_native.exists():
            native=json.loads(gzip.decompress(public_native.read_bytes()))
            public_record=file_record(public_native)
        else:
            # May01 deliberately delegates the exact saved original compiler;
            # it does not create a second serialized public Native bundle.
            assert day=='2025-05-01'
            from v42_integration.release_date_case import load_date_case
            native=load_date_case(day,case)['data'][0]
            public_record=file_record(case/'D0_PLANNING_INPUT_AUDIT.json')
        record=policy['research_contract'];assert file_record(record['path'])==record
        spec=read(record['path']);provider=ResearchPresiteProvider(spec,native_wan=native['WAN'])
        assert policy['mode']=='R1' and policy['variant']=='C1' and spec['scenario']=='R1'
        assert spec['shared_sites']==sorted(native['capacities']) and spec['ready_delay_slots']==0
        assert spec['date_contract']==dict(day=day,planning_identity=manifest['identity'],
            planning_source_sha=manifest['source_sha'],future_UID_roster_in_contract=False)
        assert any(Path(r['path']).name=='ACTUAL_INPUT_BUNDLE.json' and Path(r['path']).parent.name==day
            for r in spec['source_records'])
        rows.append(dict(day=day,status='PASS_DATE_SOURCE_AND_COMPILED_WAN',spec=record,
            planning_identity=manifest['identity'],compiled_public_input=public_record,
            compiled_WAN_sha=digest(native['WAN']),research_spec_sha=provider.science_sha))
    assert len(rows)==31
    _write(target,dict(status='PASS_31_DATE_RESEARCH_CONTRACT_BINDINGS_ONLY',days=rows,
        Native_calls=0,Actual_runs=0,AC_solves=0,private_Truth_reads=0,future_UID_decisions=0,
        actual_movement_or_physical_PASS_certified=False,tool=file_record(__file__)))
    print(json.dumps(dict(status='PASS',days=len(rows),Native_calls=0,Actual_runs=0,AC_solves=0)))


if __name__=='__main__':main()
