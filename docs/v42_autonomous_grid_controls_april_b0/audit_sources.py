"""Read-only PR125 control-authority audit; never runs an April/May campaign.

Only static compilation (including source CalcVoltageBases) is performed.
No demand, PV, workload, Actual input loader, or voltage-result tuning is used.
"""
from pathlib import Path
import ast
import hashlib
import json
import os
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PRIOR = ROOT / 'docs/v42_april_b0_capacity_queue_voltage_calibration'
EXTERNAL = Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance')
BASE = '043298363fe51edde0bddaa073a553e526ffef2c'


def record(path):
    path = Path(path)
    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def graph(roots):
    files = {}
    edges = []
    commands = []

    def visit(path):
        path = path.resolve()
        if str(path).lower() in files:
            return
        files[str(path).lower()] = record(path)
        for number, raw in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
            line = raw.split('!', 1)[0].strip()
            if not line:
                continue
            if re.search(r'\b(regcontrol|capcontrol|capacitor)\.', line, re.I):
                commands.append(dict(path=str(path), line=number, command=line))
            match = re.match(r'^(redirect|compile)\s+(?:"([^"]+)"|([^\s]+))\s*$', line, re.I)
            if match:
                child = Path(match[2] or match[3])
                if not child.is_absolute():
                    child = path.parent / child
                edges.append(dict(parent=str(path), line=number, child=str(child.resolve())))
                visit(child)
    for root in roots:
        visit(root)
    return dict(files=list(files.values()), redirect_edges=edges, equipment_commands=commands)


def inventory(odd):
    regs = []
    for name in odd.RegControls.AllNames():
        if name.lower() == 'none':
            continue
        odd.RegControls.Name(name)
        tx = str(odd.RegControls.Transformer())
        winding = int(odd.RegControls.Winding())
        odd.Circuit.SetActiveElement('RegControl.' + name)
        props = {p: str(odd.Properties.Value(p)) for p in odd.CktElement.AllPropertyNames()}
        enabled = bool(odd.CktElement.Enabled())
        odd.Transformers.Name(tx)
        odd.Transformers.Wdg(winding)
        low, high, count = float(odd.Transformers.MinTap()), float(odd.Transformers.MaxTap()), int(odd.Transformers.NumTaps())
        regs.append(dict(name=name, transformer=tx, winding=winding, enabled=enabled,
            resolved_properties=props, min_tap=low, max_tap=high, num_taps=count,
            tap_step=(high-low)/count, initial_tap=float(odd.Transformers.Tap())))
    caps = []
    for name in odd.Capacitors.AllNames():
        if name.lower() == 'none':
            continue
        odd.Capacitors.Name(name)
        odd.Circuit.SetActiveElement('Capacitor.' + name)
        caps.append(dict(name=name, enabled=bool(odd.CktElement.Enabled()),
            buses=list(odd.CktElement.BusNames()), phases=int(odd.CktElement.NumPhases()),
            kvar=float(odd.Capacitors.kvar()), kv=float(odd.Capacitors.kV()),
            num_steps=int(odd.Capacitors.NumSteps()), states=list(map(int, odd.Capacitors.States()))))
    names = [str(n) for n in odd.CapControls.AllNames() if str(n).lower() != 'none']
    capcontrols = []
    for name in names:
        odd.CapControls.Name(name)
        odd.Circuit.SetActiveElement('CapControl.' + name)
        capcontrols.append(dict(name=name, enabled=bool(odd.CktElement.Enabled()),
            resolved_properties={p: str(odd.Properties.Value(p)) for p in odd.CktElement.AllPropertyNames()}))
    return dict(regulator_transformers=len(regs), RegControl_count=int(odd.RegControls.Count()),
        capacitor_banks=int(odd.Capacitors.Count()), CapControl_count=int(odd.CapControls.Count()),
        CapControl_AllNames_raw=list(odd.CapControls.AllNames()), regulators=regs,
        capacitors=caps, capcontrols=capcontrols, engine_version=odd.Basic.Version(),
        control_mode=int(odd.Solution.ControlMode()), solution_mode=int(odd.Solution.Mode()),
        max_control_iterations=int(odd.Solution.MaxControlIterations()))


def main():
    source = json.loads((PRIOR / 'ELECTRICAL_SOURCE_AUTHORITY.json').read_text(encoding='utf-8'))
    for item in source['static_sources'][:6] + source['code_sources']:
        actual = record(item['path'])
        if actual['sha256'] != item['sha256']:
            raise ValueError('PR125_SOURCE_HASH_DRIFT:' + item['path'])
    sources = [Path(r['path']) for r in source['static_sources'][:6]]
    master, ratings, pv, adapter, mapping, pcc = sources
    static = graph([master, pcc, ratings, pv])
    code_paths = [ROOT / n for n in ('v42_capacity/electrical.py', 'v42_capacity/planning.py',
        'v42_capacity/replay.py', 'v42_capacity/actual.py', 'v42_native/actual.py',
        'v42_native/grid.py', 'v42_native/voltage.py')]
    code_paths += [Path(r['path']) for r in source['code_sources']]
    code_paths += [EXTERNAL / 'dayahead/run_planning_ac_voltage_forensic_v1.py']
    functions = []
    for path in code_paths:
        text = path.read_text(encoding='utf-8-sig')
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in (
                'compile_clean_engine', 'apply_frozen_native_state', '_native_state',
                '_anchor_and_sensitivity_day', '_enable_native_controls', '_fix_controls',
                '_compile', '_native_capacitor_q', 'generate', 'run_fresh_opendss', 'add_grid'):
                functions.append(dict(path=str(path), function=node.name, line=node.lineno,
                    end_line=node.end_lineno, source='\n'.join(text.splitlines()[node.lineno-1:node.end_lineno])))
    # Audit both exact compilers, not a replacement feeder or a hypothetical control.
    sys.path.insert(0, str(EXTERNAL))
    from dayahead.v28r2.opendss_mapping import FeederAssets, compile_clean_engine
    from dayahead.run_planning_ac_voltage_forensic_v1 import _compile
    previous = Path.cwd()
    try:
        odd, _ = compile_clean_engine(FeederAssets(*sources))
        actual_inventory = inventory(odd)
        odd.Basic.ClearAll()
        plan_odd, _ = _compile(master.parents[1], pcc.parents[3], 'NATIVE')
        planning_inventory = inventory(plan_odd)
        plan_odd.Basic.ClearAll()
    finally:
        os.chdir(previous)
    same = actual_inventory == planning_inventory
    if not same:
        raise ValueError('STATIC_PLAN_ACTUAL_EQUIPMENT_MISMATCH')
    write('REGCONTROL_CAPCONTROL_SOURCE_AUDIT.json', dict(exact_base=BASE,
        status='STOP_SOURCE_CAPCONTROL_ABSENT', static_source_graph=static,
        raw_external_files_copied=False, code_read=[record(p) for p in code_paths],
        relevant_function_evidence=functions, PR125_source_hashes_match=True,
        actual_static_compile=actual_inventory, planning_static_compile=planning_inventory,
        static_compilers_same_inventory=same,
        regulator_parameter_origins=dict(explicit_DSS=['VReg', 'Band', 'PTRatio', 'CTPrim', 'R', 'X'],
            like_inheritance_resolved=True, compiled_engine_defaults=['Delay', 'TapDelay', 'MaxTapChange',
            'transformer MinTap/MaxTap/NumTaps'], defaults_are_observed_not_new_tuning=True),
        cap_switching_target=None, cap_switching_deadband=None, cap_switching_delay=None,
        capacitor_autonomy_provable=False, control_parameter_tuning_count=0,
        static_compilations=2, scientific_day_slot_solves=0, May_input_outcome_reads=0,
        source_zero_load_CalcVoltageBases_allowed=True,
        stop_conditions=['Actual autonomous CapControl requires adding source equipment/settings',
                         'CapControl target/threshold/delay authority missing']))
    daily = []
    for d in range(1, 31):
        folder = PRIOR / 'BUNDLE' / f'DAY_202504{d:02d}'
        paths = [folder / n for n in ('PLANNING_FREEZE.json', 'FRESH_ACTUAL_AC_RECEIPT.json')]
        freeze, receipt = [json.loads(p.read_text(encoding='utf-8')) for p in paths]
        daily.append(dict(day=f'2025-04-{d:02d}', planning_freeze=freeze, actual_receipt=receipt,
                          source_records=[record(p) for p in paths]))
    write('PR125_DAILY_FREEZE_RECEIPT_AUDIT.json', dict(exact_base=BASE, days=daily,
        days_read=30, planning_freezes_read=30, actual_receipts_read=30,
        old_actual_converged_slots=sum(r['actual_receipt']['converged_slots'] for r in daily),
        old_actual_voltage_violations=sum(r['actual_receipt']['voltage_violations'] for r in daily),
        new_scientific_execution='NOT_RUN'))
    print(json.dumps(dict(status='STOP_SOURCE_CAPCONTROL_ABSENT', static_files=len(static['files']),
        RegControl_count=actual_inventory['RegControl_count'], capacitor_banks=actual_inventory['capacitor_banks'],
        CapControl_count=actual_inventory['CapControl_count'], compilers_same=same, daily_receipts_read=30,
        regulator_settings=[dict(name=r['name'], vreg=r['resolved_properties']['VReg'],
            band=r['resolved_properties']['Band'], delay=r['resolved_properties']['Delay'],
            tap_delay=r['resolved_properties']['TapDelay'], tap_step=r['tap_step']) for r in actual_inventory['regulators']]),
        ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
