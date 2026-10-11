"""Approved daily exogenous conversion after B0's own Planning freeze."""
from pathlib import Path
from unittest.mock import patch
from v42_pr134_b1.common import read,record

def run(request,manifest,progress):
    from v42_voltage_control import b0_new
    from v42_may_campaign_native90.operations import actual_sources
    actual_plan={};original_build=b0_new.build_actual;original_fresh=b0_new.fresh_environment
    def build(plan,folder,output,freeze):
        frozen=read(freeze)
        if not frozen['Planning_frozen'] or record(frozen['physical']['path'])!=frozen['physical']:
            raise PermissionError('SVR11_ACTUAL_EXOGENOUS_REQUIRES_OWN_PLANNING_FREEZE')
        daily=actual_sources(request,Path(output).parent/'ACTUAL_SOURCES')
        new=dict(plan,provenance=read(daily/'SOURCE_PROVENANCE.json'))
        actual_plan['value']=new
        return original_build(new,folder,output,freeze)
    def fresh(plan,arrays,folder,output,**kwargs):
        return original_fresh(actual_plan['value'] if kwargs['namespace']=='ACTUAL' else plan,arrays,folder,output,**kwargs)
    with patch.object(b0_new,'build_actual',build),patch.object(b0_new,'fresh_environment',fresh):
        return b0_new.run_day(request['day'],request['input_folder'],request['output'],scenario=read(manifest['scenario']['path']),
            source_SHA=manifest['execution_SHA'],progress=progress,design_receipt=manifest['hardware'])
