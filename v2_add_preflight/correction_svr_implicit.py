"""IEEE8500 implicit bus phase syntax adapter, electrically identical wiring."""
import json,sys,types,re
from pathlib import Path
from .audit import ROOT,read,sha
from . import correction_svr_run as runner
from .correction_svr import SV,save

def source_svr():
    p=ROOT/'v44/svr11_frozen/v42_voltage_control/svr.py';text=p.read_text(encoding='utf-8')
    old='nodes = [int(x) for x in u["original_bus_spec"].split(".")[1:]]'
    new='nodes = [int(x) for x in u["original_bus_spec"].split(".")[1:]] or list(engine.CktElement.NodeOrder()[(u["cut_terminal"]-1)*engine.CktElement.NumConductors(): (u["cut_terminal"]-1)*engine.CktElement.NumConductors()+3])'
    assert text.count(old)==1
    m=types.ModuleType('v2_add_ieee8500_explicit_phase_equivalence')
    exec(compile(text.replace(old,new),str(p),'exec'),m.__dict__)
    m.ORIGINAL_REGCONTROLS=tuple(r['regcontrol'] for r in read(SV/'EXISTING_REGULATOR_FULL_STATIC_AUDIT.json')['initial_readbacks'])
    m._NAME=re.compile(r'^[a-zA-Z][a-zA-Z0-9_\-]*$')
    return m

def main(config):
    # The first installer rejected IEEE8500 implicit `bus` (no .1.2.3 suffix)
    # before any S1 operating AC. Its failure receipt is retained. Infer phases
    # only from the compiled existing terminal NodeOrder; require exact123.
    amendment=SV/'IEEE8500_PHASE_SYNTAX_AMENDMENT.json'
    value=dict(status='BEFORE_FIRST_S1_OPERATING_AC',reason='IEEE123 source installer requires explicit bus.1.2.3; IEEE8500 declares implicit three-phase buses',
        checks='Existing terminal live NodeOrder exactly1,2,3 and NumPhases3; all original bus strings and feeder bytes retained',
        original_failure='FAILURE_S1_03_1.00.json',physical_parameter_changes=0,adapter_sha256=sha(Path(__file__).read_bytes()))
    if amendment.exists():assert read(amendment)==value
    else:save(amendment.name,value)
    runner.source_svr=source_svr
    original_install=runner.install
    def install(config):
        original_install(config);original=runner.c.fingerprint
        def fingerprint():
            v=original();v['implicit_phase_adapter']=value['adapter_sha256'];return v
        runner.c.fingerprint=fingerprint
    runner.install=install
    runner.main(config)

if __name__=='__main__':main(sys.argv[1])
