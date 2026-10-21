"""Accept existing IEEE8500 hyphenated bus identifiers without rewiring them."""
import re,sys
from pathlib import Path
from .audit import sha,read
from . import correction_svr_implicit as implicit
from .correction_svr import SV,save

def main(config):
    original=implicit.source_svr
    def source_svr():
        m=original();m._BUS=re.compile(r'^[a-zA-Z0-9_\-]+(?:\.[0-3])*$');return m
    implicit.source_svr=source_svr
    value=dict(status='BEFORE_FIRST_S1_06_OR_S1_12_OPERATING_AC',
        reason='Original IEEE8500 bus IDs221-311609/221-311905/221-308718 contain hyphens; IEEE123 identifier regex rejected them',
        physical_parameter_changes=0,exact_existing_bus_match_and_live_phase_kV_checks_retained=True,
        adapter_sha256=sha(Path(__file__).read_bytes()),retained_failure='FAILURE_S1_06_1.00.json')
    p=SV/'IEEE8500_BUS_NAME_SYNTAX_AMENDMENT.json'
    if p.exists():assert read(p)==value
    else:save(p.name,value)
    base=implicit.runner.install
    def install(config):
        base(config);prior=implicit.runner.c.fingerprint
        def fingerprint():
            r=prior();r['hyphenated_bus_adapter']=value['adapter_sha256'];return r
        implicit.runner.c.fingerprint=fingerprint
    implicit.runner.install=install
    implicit.main(config)

if __name__=='__main__':main(sys.argv[1])
