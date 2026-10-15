"""Date-bound Original current AC, changing only two clock-day literals.

Static method bodies preserve the Original candidate/prefix/conditional AC.
No dynamic source execution, global replacement or new physical rule is used.
"""
import ast
from datetime import datetime
import inspect
from pathlib import Path
import textwrap

from .current_ac_admission import CurrentACAdmission, AEST
from .rc02_prefix_cache import PrefixCachedCurrentAC
from .research_presite_actual import ResearchCurrentAC
from .m_engine import file_record
from .policy import digest

ORIGINAL_SHA={
    'current_ac_admission.py':'45b54c6c7832444dd773b742d1bd39b7f7f69ab5264f3ae84abca949960a88f9',
    'rc02_prefix_cache.py':'9f8045a8376a6720b443ae173403dcd142451b5d8b14298a78c4b9fb0e1b3448',
    'research_presite_actual.py':'662a589f63e0dd65d5000ff17290b6d69ffa7a365923657487893a4e63b68661'}


def original_date_ac_sources():
    records=[file_record(Path(__file__).with_name(name)) for name in ORIGINAL_SHA]
    if any(r['sha256']!=ORIGINAL_SHA[Path(r['path']).name] for r in records):
        raise ValueError('DATE_AC_ORIGINAL_FROZEN_SOURCE_BYTES_DRIFT')
    return records


def date_ac_static_equivalence():
    """Compare static ASTs only; normalize precisely one CommonClock argument."""
    sources=original_date_ac_sources();proofs=[]
    for original,adapter in ((CurrentACAdmission._probe,DateCurrentAC._probe),
                             (PrefixCachedCurrentAC._replay_current,DatePrefixCachedCurrentAC._replay_current)):
        before=ast.parse(textwrap.dedent(inspect.getsource(original)))
        after=ast.parse(textwrap.dedent(inspect.getsource(adapter)))
        def clock(tree):
            nodes=[n for n in ast.walk(tree) if isinstance(n,ast.Call)
                and isinstance(n.func,ast.Name) and n.func.id=='CommonClock']
            if len(nodes)!=1 or len(nodes[0].args)!=2 or ast.literal_eval(nodes[0].args[0])!='ACTUAL':
                raise ValueError('DATE_AC_SINGLE_ORIGINAL_ACTUAL_CLOCK_REQUIRED')
            return nodes[0]
        left,right=clock(before),clock(after)
        if (ast.literal_eval(left.args[1])!='2025-05-01'
                or ast.unparse(right.args[1])!='datetime.fromtimestamp(self.begin, AEST).date().isoformat()'):
            raise ValueError('DATE_AC_ONLY_APPROVED_BEGIN_AEST_DATE_EXPRESSION_REQUIRED')
        left.args[1]=right.args[1]=ast.Constant(value='APPROVED_DATE_EXPRESSION_ONLY')
        old,new=ast.dump(before,include_attributes=False),ast.dump(after,include_attributes=False)
        if old!=new:
            raise ValueError('DATE_AC_ORIGINAL_METHOD_BEHAVIOR_DRIFT')
        proofs.append(dict(original=original.__qualname__,adapter=adapter.__qualname__,
            normalized_static_AST_sha=digest(old),changed_expressions=1))
    return dict(status='PASS_STATIC_CLOCK_DAY_ONLY',methods=proofs,original_sources=sources,
        additive_source=file_record(__file__),runtime_source_execution=False,
        global_or_original_method_patch=False,Native_calls=0,AC_calls=0)


class DateCurrentAC(CurrentACAdmission):
    def __init__(self,*args,**kwargs):
        date_ac_static_equivalence()
        super().__init__(*args,**kwargs)

    def _probe(self,history,current,future_rows=None):
        from .actual_validation import _validated_hardware_context,mess_service_bindings
        from v42_regcontrol import authority
        from v42_regcontrol.runner import background
        from v42_voltage_control.timecontrol import CommonClock,queue,seconds
        from v42_voltage_control.svr import install
        from v42_voltage_control.integration import _equipment,measure_full_network,assert_control_inventory
        steps=[];all_rows=[*history,*(future_rows or [current])]
        # The shape-only suffix is held current data, never future Actual.
        stamps=[datetime.fromtimestamp(self.begin+(t+1)*900,AEST).isoformat() for t in range(96)]
        demand=[];pv=[]
        for t in range(96):
            r=all_rows[t] if t<len(all_rows) else current
            demand.append(r['observations']['demand']['values']['demand_mw'])
            pv.append(r['observations']['pv']['values']['pv_mw'])
        with self._hardware_context() as scenario:
            source=authority.source();bg_key=digest(dict(stamps=stamps,demand=demand,pv=pv))
            if bg_key not in self._background_cache:
                self._background_cache[bg_key]=background(stamps,demand,pv)
                while len(self._background_cache)>2:self._background_cache.popitem(last=False)
            bg=self._background_cache[bg_key]
            from dayahead.v28r2.opendss_mapping import _set_generator,_set_load,mess_injection_mapping
            engine,adapter,initial=authority.compile_verified()
            try:
                equipment=_equipment(engine);nodes={n.lower() for n in engine.Circuit.AllNodeNames() if n.rsplit('.',1)[-1] in {'1','2','3'}}
                native=source['NativeAllocation'].from_adapter(adapter);native.validate_native_engine(engine)
                svrs=install(engine,scenario['svr']);clock=CommonClock('ACTUAL',datetime.fromtimestamp(self.begin,AEST).date().isoformat());clock.bind(engine)
                assert_control_inventory(source['inventory'](engine),scenario,initial=True)
                aliases,_=mess_service_bindings(source,self.mess['P_by_site'])
                def apply(r):
                    t=r['slot'];native.apply(engine,bg,t)
                    for item in adapter['pv_generators']:
                        loc=(str(item['bus']).lower(),'ABC'[int(item['phase'])-1])
                        _set_generator(engine,item['generator_name'],bg.pv_generation_kw_96[t].get(loc,0),0)
                    for j in range(len(self.sites)):_set_load(engine,f'IDC_IDC{j+1:02d}',r['P'][j],r['Q'][j])
                    for site,names in aliases.items():
                        inj=mess_injection_mapping(self.mess['P_by_site'][site][t],self.mess['Q_by_site'][site][t])
                        _set_generator(engine,names['generator'],inj['generator_p_kw'],inj['generator_q_kvar'])
                        _set_load(engine,names['load'],inj['charging_load_p_kw'],inj['charging_load_q_kvar'])
                def measure(kind):
                    physical=measure_full_network(engine,nodes,equipment);hardware=svrs.measure()
                    ok=bool(physical['PASS'] and hardware['hardware_PASS'] and hardware['added_nodes_voltage_PASS'])
                    lines=[r for r in physical['currents'] if r['element'].lower().startswith('line.')]
                    steps.append(dict(native_seconds=seconds(engine),kind=kind,PASS=ok,
                        voltage_min_pu=physical['voltage_min_pu'],voltage_max_pu=physical['voltage_max_pu'],
                        maximum_phase_line_loading=max((r['loading_pu'] for r in lines),default=0.),
                        physical_sha=digest(physical),SVR_sha=digest(hardware),
                        SVR_hardware_PASS=hardware['hardware_PASS'],SVR_voltage_PASS=hardware['added_nodes_voltage_PASS'],
                        checked_nodes=len(physical['nodes']),checked_current_rows=len(physical['currents']),
                        violations={k:v for k,v in physical.items() if 'violation' in k},
                        worst_line=max(lines,key=lambda r:r['loading_pu'],default=None)))
                for row in history:
                    apply(row);clock.settle_slot(engine,row['slot'],observer=lambda event:measure(event['kind']))
                apply(current)
                expected=current['slot']*900
                if seconds(engine)!=expected:raise ValueError('CURRENT_AC_NATIVE_CLOCK_DRIFT')
                engine.Solution.SolveSnap()
                pending=queue(engine)
                if (not engine.Solution.Converged() or not engine.Solution.ControlActionsDone()
                        or any(item['absolute_seconds']<=expected for item in pending)):
                    raise ValueError('CURRENT_AC_DUE_ACTION_OR_CONVERGENCE_FAILURE')
                measure('CURRENT_CANDIDATE_ONLY_NO_FUTURE_TAP_EXECUTION')
                assert_control_inventory(source['inventory'](engine),scenario)
                current_ok=steps[-1]['PASS'];prefix_ok=all(r['PASS'] for r in steps[:-1])
                if future_rows:
                    for row in future_rows:
                        apply(row);clock.settle_slot(engine,row['slot'],
                            observer=lambda event:measure('CONDITIONAL_PUBLIC_'+event['kind']))
                return dict(PASS=current_ok,status='PASS' if current_ok else 'PHYSICAL_FAIL',
                    historical_prefix_physical_PASS=prefix_ok,physical_steps=steps,
                    current_native_seconds=expected,future_queue_not_executed=pending,
                    original_RegControl=7,SVR_count=11,
                    future_native_Tap_actions_executed=0 if not future_rows else None,
                    conditional_predicted_AUTO_substeps=sum(s['kind'].startswith('CONDITIONAL_PUBLIC_') for s in steps),
                    prediction_is_not_Actual_Tap_observation=bool(future_rows))
            finally:engine.Basic.ClearAll()


class DatePrefixCachedCurrentAC(PrefixCachedCurrentAC,DateCurrentAC):
    def __init__(self,*args,proof_records,**kwargs):
        super().__init__(*args,proof_records=[*proof_records,file_record(__file__)],**kwargs)

    def _replay_current(self,history,current):
        from .actual_validation import mess_service_bindings
        from v42_regcontrol import authority
        from v42_regcontrol.runner import background
        from v42_voltage_control.timecontrol import CommonClock,queue,seconds
        from v42_voltage_control.svr import install
        from v42_voltage_control.integration import _equipment,measure_full_network,assert_control_inventory
        rows=[*history,current]
        stamps=[datetime.fromtimestamp(self.begin+(t+1)*900,AEST).isoformat() for t in range(96)]
        demand=[rows[t]['observations']['demand']['values']['demand_mw'] if t<len(rows) else
                current['observations']['demand']['values']['demand_mw'] for t in range(96)]
        pv=[rows[t]['observations']['pv']['values']['pv_mw'] if t<len(rows) else
            current['observations']['pv']['values']['pv_mw'] for t in range(96)]
        with self._hardware_context() as scenario:
            source=authority.source();bg_key=digest(dict(stamps=stamps,demand=demand,pv=pv))
            if bg_key not in self._background_cache:
                self._background_cache[bg_key]=background(stamps,demand,pv)
                while len(self._background_cache)>2:self._background_cache.popitem(last=False)
            bg=self._background_cache[bg_key]
            from dayahead.v28r2.opendss_mapping import _set_generator,_set_load,mess_injection_mapping
            engine,adapter,_=authority.compile_verified()
            try:
                equipment=_equipment(engine)
                nodes={n.lower() for n in engine.Circuit.AllNodeNames() if n.rsplit('.',1)[-1] in {'1','2','3'}}
                native=source['NativeAllocation'].from_adapter(adapter);native.validate_native_engine(engine)
                svrs=install(engine,scenario['svr']);clock=CommonClock('ACTUAL',datetime.fromtimestamp(self.begin,AEST).date().isoformat());clock.bind(engine)
                assert_control_inventory(source['inventory'](engine),scenario,initial=True)
                aliases,_=mess_service_bindings(source,self.mess['P_by_site'])
                def apply(row):
                    t=row['slot'];native.apply(engine,bg,t)
                    for item in adapter['pv_generators']:
                        loc=(str(item['bus']).lower(),'ABC'[int(item['phase'])-1])
                        _set_generator(engine,item['generator_name'],bg.pv_generation_kw_96[t].get(loc,0),0)
                    for j in range(len(self.sites)):_set_load(engine,f'IDC_IDC{j+1:02d}',row['P'][j],row['Q'][j])
                    for site,names in aliases.items():
                        inj=mess_injection_mapping(self.mess['P_by_site'][site][t],self.mess['Q_by_site'][site][t])
                        _set_generator(engine,names['generator'],inj['generator_p_kw'],inj['generator_q_kvar'])
                        _set_load(engine,names['load'],inj['charging_load_p_kw'],inj['charging_load_q_kvar'])
                for row in history:
                    apply(row)
                    clock.settle_slot(engine,row['slot'],capture_events=False)
                apply(current)
                expected=current['slot']*900
                if seconds(engine)!=expected:raise ValueError('PREFIX_CACHE_CURRENT_NATIVE_CLOCK_DRIFT')
                engine.Solution.SolveSnap();pending=queue(engine)
                if (not engine.Solution.Converged() or not engine.Solution.ControlActionsDone()
                        or any(r['absolute_seconds']<=expected for r in pending)):
                    raise ValueError('PREFIX_CACHE_DUE_QUEUE_OR_CONVERGENCE_FAILURE')
                physical=measure_full_network(engine,nodes,equipment);hardware=svrs.measure()
                assert_control_inventory(source['inventory'](engine),scenario)
                ok=bool(physical['PASS'] and hardware['hardware_PASS'] and hardware['added_nodes_voltage_PASS'])
                lines=[r for r in physical['currents'] if r['element'].lower().startswith('line.')]
                step=dict(native_seconds=seconds(engine),kind='CURRENT_CANDIDATE_ONLY_NO_FUTURE_TAP_EXECUTION',
                    PASS=ok,voltage_min_pu=physical['voltage_min_pu'],voltage_max_pu=physical['voltage_max_pu'],
                    maximum_phase_line_loading=max((r['loading_pu'] for r in lines),default=0.),
                    physical_sha=digest(physical),SVR_sha=digest(hardware),
                    SVR_hardware_PASS=hardware['hardware_PASS'],SVR_voltage_PASS=hardware['added_nodes_voltage_PASS'],
                    checked_nodes=len(physical['nodes']),checked_current_rows=len(physical['currents']),
                    violations={k:v for k,v in physical.items() if 'violation' in k},
                    worst_line=max(lines,key=lambda r:r['loading_pu'],default=None))
                return dict(PASS=ok,status='PASS' if ok else 'PHYSICAL_FAIL',physical_steps=[step],
                    current_native_seconds=expected,future_queue_not_executed=pending,
                    original_RegControl=7,SVR_count=11,future_native_Tap_actions_executed=0,
                    conditional_predicted_AUTO_substeps=0,prediction_is_not_Actual_Tap_observation=False,
                    executed_prefix_physical_solves=clock.total_physical_solve_count)
            finally:engine.Basic.ClearAll()


class DateResearchCurrentAC(ResearchCurrentAC,DatePrefixCachedCurrentAC):
    """Original research scoring plus the two exact date-bound AC methods."""
