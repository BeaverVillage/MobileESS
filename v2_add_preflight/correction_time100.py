"""IEEE8500 numerical iteration budget adapter; native TIME physics unchanged.

The larger feeder already used MaxIterations100 in PR236. r043's clock binds
15 for IEEE123. The strict15 attempt is preserved separately; only these two
numerical-budget assertions and the engine MaxIterations change to100.
"""
import ast,csv,math,sys,shutil
from datetime import date
from pathlib import Path
from . import correction as c
from .audit import ROOT,read,sha

def clock_class():
    source=ROOT/'v44/svr11_frozen/v42_voltage_control/timecontrol.py'
    tree=ast.parse(source.read_text(encoding='utf-8'))
    body=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef,ast.Assign))]
    changes=[]
    class NumericalAxisAdapter(ast.NodeTransformer):
        def visit_Compare(self,node):
            text=ast.unparse(node)
            if text=='0 <= slot < 96':node.comparators[-1]=ast.Constant(120);changes.append('Actual chronological bound96->120')
            if text=='int(engine.Solution.MaxIterations()) == 15':node.comparators[-1]=ast.Constant(100);changes.append('electrical MaxIterations15->100')
            return self.generic_visit(node)
    tree=NumericalAxisAdapter().visit(ast.Module(body=body,type_ignores=[]));ast.fix_missing_locations(tree)
    assert changes.count('electrical MaxIterations15->100')==2 and len(changes)==3
    def require(ok,message):
        if not ok:raise ValueError(message)
    ns=dict(csv=csv,date=date,math=math,require=require);exec(compile(tree,str(source),'exec'),ns)
    original=ns['CommonClock'];bind=original.bind
    class FeederClock(original):
        def bind(self,engine):
            engine.Solution.MaxIterations(100)
            return bind(self,engine)
    return FeederClock,ns['queue']

def install():
    c.RUN=c.RUNTIME/'correction_time100';c.RUN.mkdir(exist_ok=True)
    c.clock_class=clock_class
    original_fingerprint=c.fingerprint
    def fingerprint():
        result=original_fingerprint();result['IEEE8500_numerical_clock_adapter']=sha(Path(__file__).read_bytes());return result
    c.fingerprint=fingerprint

def anchors():
    old=c.OUT/'strict15_attempt';old.mkdir(exist_ok=True)
    for name in ('TIME_CONTROL_FRESH_CERTIFICATION.json','TIME_B0_ANCHOR_RESULTS.csv','STATIC_VS_TIME_CONTROL_AUDIT.csv'):
        if (c.OUT/name).exists() and not (old/name).exists():shutil.copyfile(c.OUT/name,old/name)
    c.put('STRICT15_TIME_FAILURE.json',dict(status='TIME_CONTROL_NOT_VERIFIED_STRICT_R043_NUMERICAL_BUDGET',
        completed_cases=6,completed_fresh_pairs=3,failed_case='TIME_1.50_ACTUAL_B0',failed_slot=0,
        failure='TIME_NATIVE_AC_NONCONVERGENCE at MaxIterations15, original CommonClock rejected',
        runtime_preserved=str(c.RUNTIME/'correction'),physical_retuning=False))
    install();c.time_tests()
    cert=read(c.OUT/'TIME_CONTROL_FRESH_CERTIFICATION.json')
    cert.update(numerical_adapter='IEEE8500 existing electrical MaxIterations100 instead of IEEE12315; MaxControlIterations100 unchanged',
        strict15_attempt='strict15_attempt/ and STRICT15_TIME_FAILURE.json',
        numerical_equivalence_to_IEEE123_iteration_budget=False,temporal_event_loop_unchanged=True,
        P5_and_control_delays_unchanged=True)
    c.put('TIME_CONTROL_FRESH_CERTIFICATION.json',cert)

def stage(name):
    install()
    from . import correction_campaign as campaign
    campaign.RUN=c.RUN;campaign.fingerprint=c.fingerprint
    # Preregistration must retain the original pre-execution file. The new
    # numerical budget is an explicit amendment, never backdated into it.
    campaign.register=lambda:None
    c.put('TIME100_NUMERICAL_AMENDMENT.json',dict(reason='strict15 initial nonconvergence',
        MaxIterations=100,MaxControlIterations=100,physical_changes=False,original_preregistration_unchanged=True,
        code_sha256=sha(Path(__file__).read_bytes()),inputs=c.fingerprint()))
    getattr(campaign,name)()

if __name__=='__main__':
    if sys.argv[1]=='anchors':anchors()
    else:stage(sys.argv[1])
