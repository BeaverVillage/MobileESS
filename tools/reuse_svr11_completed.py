"""Admit a completed B0 day without executing AC or changing original evidence."""
from pathlib import Path
import sys, copy
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,now,sha,digest
from v42_svr11.authority import verify
from verify_svr11_handoff37 import audit_date,require

# These reviewed changes affect lifetime/dispatch or remove the erroneous
# additional original nominal-current guard. B0 has no model/Native solver.
B0_REVIEWED_CHANGES={'v42_svr11/migration.py','v42_svr11/processes.py',
 'v42_voltage_control/integration.py','v42_svr11/model.py','v42_svr11/prepare.py',
 'v42_svr11/authority.py','v42_svr11/context_lifecycle.py','v42_voltage_control/timecontrol.py',
 'v42_voltage_control/forecast.py'}

def normalized_forecast_receipt_guard(text):
    """Only normalize the final receipt's existing checked() path rule."""
    import ast
    expected=ast.parse("record(r['path']) == dict(r,path=str(Path(r['path']).resolve()))",mode='eval').body
    original=ast.parse("record(r['path']) == r",mode='eval').body
    class Guard(ast.NodeTransformer):
        def visit_Compare(self,node):
            return original if ast.dump(node,include_attributes=False)==ast.dump(expected,include_attributes=False) else self.generic_visit(node)
    return ast.dump(Guard().visit(ast.parse(text)),include_attributes=False)

def normalized_reviewed_model(text):
    """Normalize only explicitly reviewed equivalent caches/owner cleanup."""
    import ast
    helpers=ast.parse('''def _forecast_native_totals(native,background):
    return tuple(native.allocate(background.gross_p_kw_96[t],background.gross_q_kvar_96[t])[0]
        for t in range(96))
def _apply_forecast_native(engine,native,totals,slot):
    from dayahead.v28r2.opendss_mapping import _set_load
    for row in native.loads:
        name=str(row['load_name']);p,q=totals[slot][name.lower()]
        _set_load(engine,name,p,q)
''').body
    helper_axis={n.name:ast.dump(n,include_attributes=False) for n in helpers}
    approved_assignment=ast.parse('totals_by_slot=_forecast_native_totals(native,bg)').body[0]
    approved_apply=ast.parse('_apply_forecast_native(e,native,totals_by_slot,t)',mode='eval').body
    original_apply=ast.parse('native.apply(e,bg,t)',mode='eval').body
    def same(a,b):return ast.dump(a,include_attributes=False)==ast.dump(b,include_attributes=False)
    tree=ast.parse(text)
    helper_names=[n.name for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in helper_axis]
    require(not helper_names or sorted(helper_names)==sorted(helper_axis),'REUSE_INCOMPLETE_FORECAST_CACHE')
    class CacheNames(ast.NodeTransformer):
        def visit_Assign(self,node):
            if any(isinstance(t,ast.Name) and t.id=='cached' for t in node.targets):
                approved=ast.parse("cached={f:z[f] for f in FIELDS+('anchor_control',)}").body[0]
                require(ast.dump(node,include_attributes=False)==ast.dump(approved,include_attributes=False),'REUSE_UNREVIEWED_COEFFICIENT_CACHE')
                return None
            return self.generic_visit(node)
        def visit_Name(self,node):
            return ast.copy_location(ast.Name(id='z',ctx=node.ctx),node) if node.id=='cached' else node
    class Reviewed(ast.NodeTransformer):
        def visit_FunctionDef(self,node):
            if node.name in helper_axis:
                require(ast.dump(node,include_attributes=False)==helper_axis[node.name],'REUSE_UNREVIEWED_FORECAST_CACHE_HELPER')
                return None
            if node.name=='load_coefficients':
                node=CacheNames().visit(node)
            return self.generic_visit(node)
        def visit_Assign(self,node):
            if any(isinstance(t,ast.Name) and t.id=='totals_by_slot' for t in node.targets):
                require(bool(helper_names) and same(node,approved_assignment),'REUSE_UNREVIEWED_FORECAST_CACHE_INPUT')
                return None
            return self.generic_visit(node)
        def visit_Call(self,node):
            if isinstance(node.func,ast.Name) and node.func.id=='_apply_forecast_native':
                require(bool(helper_names) and same(node,approved_apply),'REUSE_UNREVIEWED_FORECAST_CACHE_APPLY')
                return original_apply
            approved=ast.parse("owned.get('generation_source_SHA',contract['generation_source_SHA'])",mode='eval').body
            if ast.dump(node,include_attributes=False)==ast.dump(approved,include_attributes=False):
                return node.args[1]
            return self.generic_visit(node)
        def visit_Import(self,node):
            return None if all(a.name in ('gc','weakref') for a in node.names) else node
        def visit_ImportFrom(self,node):
            return None if node.module=='context_lifecycle' else node
        def visit_Delete(self,node):
            return None if all(isinstance(t,ast.Name) and t.id=='e' for t in node.targets) else node
        def visit_Expr(self,node):
            call=node.value
            if isinstance(call,ast.Call) and ((isinstance(call.func,ast.Name) and call.func.id=='flush_completed_probes')
                or (isinstance(call.func,ast.Attribute) and isinstance(call.func.value,ast.Name)
                    and call.func.value.id=='gc' and call.func.attr=='collect')):return None
            return self.generic_visit(node)
    return ast.dump(Reviewed().visit(tree),include_attributes=False)

def qualify(root,origin,day,arm='B0'):
    root=Path(root).resolve();origin=Path(origin).resolve()
    m=verify(root/'CAMPAIGN_MANIFEST.json');old=read(origin/'CAMPAIGN_MANIFEST.json')
    require(old['execution_SHA']==digest(old['execution_sources']),'REUSE_ORIGIN_SOURCE_DIGEST')
    for name,value in old['execution_sources'].items():
        require(sha(Path(old['code_root'])/name)==value,'REUSE_ORIGIN_SOURCE_DRIFT:'+name)
    receipts=[record(origin/'CAMPAIGN_MANIFEST.json')]
    for key in ('hardware','scenario','thermal'):
        require(record(old[key]['path'])==old[key],'REUSE_ORIGIN_FREEZE_DRIFT')
        receipts.extend([old[key],m[key]])
    h=read(m['hardware']['path']);oh=read(old['hardware']['path'])
    require(h['equipment_SHA']==oh['equipment_SHA'] and h['SVR_count']==oh['SVR_count']==11,
        'REUSE_EQUIPMENT_DIFFERENT')
    require(m['scenario']['sha256']==old['scenario']['sha256'] and
        m['thermal']['sha256']==old['thermal']['sha256'],'REUSE_PHYSICAL_CONTRACT_DIFFERENT')
    changes={k for k in set(old['execution_sources'])|set(m['execution_sources'])
        if old['execution_sources'].get(k)!=m['execution_sources'].get(k)}
    require(changes<=B0_REVIEWED_CHANGES,'REUSE_UNREVIEWED_SCIENTIFIC_CHANGE')
    if 'v42_voltage_control/forecast.py' in changes:
        forecasts=[normalized_forecast_receipt_guard((Path(mm['code_root'])/'v42_voltage_control/forecast.py').read_text()) for mm in (old,m)]
        require(forecasts[0]==forecasts[1],'REUSE_UNREVIEWED_FORECAST_CHANGE')
    require(arm in ('B0','B2'),'REUSE_POLICY_NOT_REVIEWED')
    if arm=='B2':
        require(changes<={'v42_svr11/context_lifecycle.py','v42_svr11/model.py',
            'v42_svr11/prepare.py','v42_svr11/migration.py','v42_voltage_control/forecast.py'},'REUSE_M_POLICY_CHANGE')
        require(all(m[k]==old[k] for k in ('algorithm_version','native_M_limit_seconds',
            'M_acceptance','M_gap_certificate_required','Threads','Actual_reoptimization',
            'Actual_PQ_repair','Planning_taps_copied_to_Actual')),'REUSE_M_CONTRACT_DIFFERENT')
        # Explicitly verify that the only model edits are retirement imports,
        # completed-owner GC statements and deletion of a finished local owner.
        models=[normalized_reviewed_model((Path(mm['code_root'])/'v42_svr11/model.py').read_text()) for mm in (old,m)]
        require(models[0]==models[1],'REUSE_MODEL_MATH_NOT_IDENTICAL')
    # B0 excludes B1/B2 operations and optimization templates. Every actual
    # B0 load/PV/power, forecast, domain and traffic input must be byte equal.
    exclude={'OPERATIONS_TEMPLATE_B1.json','OPERATIONS_TEMPLATE_B2.json',
        'NATIVE_INPUT_TEMPLATE_B1.json','NATIVE_INPUT_TEMPLATE_B2.json'}
    if arm=='B2':exclude.remove('NATIVE_INPUT_TEMPLATE_B2.json')
    axes=[]
    for manifest in (old,m):
        axis={}
        for r in manifest['input_receipts'][day]:
            if Path(r['path']).name in exclude:continue
            require(record(r['path'])==r,'REUSE_RAW_INPUT_DRIFT')
            axis[Path(r['path']).name]=(r['sha256'],r['bytes']);receipts.append(r)
        axes.append(axis)
    require(axes[0]==axes[1] and {'ACTUAL_INPUT_BUNDLE.json','PLANNING_INPUT_BUNDLE.json',
        'POWER_AUTHORITY.json','WINDOWS.json'}<=set(axes[0]),'REUSE_INPUT_DIFFERENT')
    if arm=='B2':
        operations=[]
        for mm in (old,m):
            r=next(r for r in mm['input_receipts'][day] if Path(r['path']).name=='OPERATIONS_TEMPLATE_B2.json')
            require(record(r['path'])==r,'REUSE_OPERATIONS_DRIFT');receipts.append(r)
            op=read(r['path']);folder=op.pop('current_day_folder')
            require(Path(folder).resolve()==Path(mm['root']).resolve()/'raw'/day,'REUSE_OPERATION_FOLDER')
            operations.append(op)
        require(operations[0]==operations[1],'REUSE_OPERATION_DOMAIN_DIFFERENT')
    row=copy.deepcopy(read(origin/'CAMPAIGN_LEDGER.json')['dates'][arm+'/'+day])
    if row['status']=='RUNNING':
        # A intentionally quiesced dispatcher may not have consumed a naturally
        # completed Worker RESULT. Reconcile a copy; never rewrite its ledger.
        from v42_svr11.controller import record_terminal
        result=Path(read(row['request'])['result'])
        require(result.exists(),'REUSE_NOT_COMPLETED');record_terminal(row,result)
    require(row['status']=='PASS','REUSE_ORIGINAL_PASS_REQUIRED')
    validation=audit_date(origin,old,row)
    require(validation['PASS'] is True,'REUSE_FULL_96_SLOT_REQUIRED')
    # Old PASS passed the stricter erroneous guard too; every literal native
    # NormalAmps/kVA/SVR/voltage check is retained in this independent audit.
    receipts.extend(validation['evidence'])
    proof=dict(schema='SVR11_COMPLETED_RESULT_REUSE_V1',PASS=True,arm=arm,day=day,
        origin_root=str(origin),execution_source_SHA=validation.get('execution_source_SHA',old['execution_SHA']),
        validation_source_SHA=m['execution_SHA'],equipment_SHA=h['equipment_SHA'],
        original_result=row['result'],original_result_SHA=row['result_SHA'],
        changed_sources_reviewed=sorted(changes),validation=validation,evidence=receipts,
        validator=record(Path(__file__)),Native_calls=0,AC_calls=0,
        original_result_bytes_changed=False,original_execution_relabelled=False,UTC=now())
    path=root/'reuse'/(day+'_'+arm+'.json');atomic(path,proof)
    return path,proof,copy.deepcopy(row)

def verify_reuse(root,m,row):
    receipt=row['reuse_proof'];p=Path(receipt['path']).resolve()
    require(p.is_relative_to(Path(root).resolve()/'reuse'),'REUSE_PROOF_OWNERSHIP')
    require(record(p)==receipt,'REUSE_PROOF_SHA_DRIFT');v=read(p)
    require(v['PASS'] is True and v['arm']==row['arm'] and v['arm'] in ('B0','B2') and v['day']==row['day']
        and v['validation_source_SHA']==m['execution_SHA'] and
        v['original_result']==row['result'] and v['original_result_SHA']==row['result_SHA'],
        'REUSE_PROOF_IDENTITY')
    require(all(record(r['path'])==r for r in v['evidence']),'REUSE_PROTECTED_BYTE_DRIFT')
    result=dict(v['validation'],source_SHA=m['execution_SHA'],
        execution_source_SHA=v['execution_source_SHA'],validation_source_SHA=m['execution_SHA'],
        reused=True,evidence=v['evidence']+[receipt])
    return result

def admit_before_first_dispatch(root):
    """Scheduled successor gate reuses eligible naturally completed B2 days."""
    from v42_svr11.processes import live
    from v42_common_campaign.authority import singleton
    root=Path(root).resolve();m=verify(root/'CAMPAIGN_MANIFEST.json')
    contract=read(m['predecessor_drain_contract']['path'])
    origin=Path(read(contract['manifest']['path'])['root'])
    sup=root/'SUPERVISOR_PROCESS.json'
    if sup.exists() and live(read(sup)):return
    with singleton(root/'WATCHDOG.lock'):
        if sup.exists() and live(read(sup)):return
        ledger=read(root/'CAMPAIGN_LEDGER.json');source=read(origin/'CAMPAIGN_LEDGER.json');decisions=[]
        failure_admissions=[]
        for key,row in ledger['dates'].items():
            if row['arm']!='B2' or row['status']!='NOT_EXECUTED' or row['attempts']:continue
            oldrow=source['dates'][key]
            path=Path(oldrow['result']) if oldrow.get('result') else (Path(read(oldrow['request'])['result']) if oldrow.get('request') else None)
            if path is None or not path.exists():continue
            result=read(path)
            if result.get('PASS') is not True:
                # Only this diagnosed, byte-identical C/D junction mismatch is
                # a reviewed technical recovery. Keep the original FAIL/Native
                # Runtime; do not promote an unfinished stage to date PASS.
                diagnosis=root/'FORECAST_JUNCTION_RECEIPT_DIAGNOSIS.json'
                expected="ValueError('CAPCONTROL_SVR_FORECAST_SOURCE_OR_DECISION_MUTATED')"
                if result.get('reason')!=expected or not diagnosis.exists() or not read(diagnosis)['PASS']:continue
                model_contract=read(m['model_checkpoint_reuse_contract']['path'])
                require(record(diagnosis)==model_contract['forecast_junction_diagnosis'],'RETRY_DIAGNOSIS_RECEIPT_DRIFT')
                forecast=read(origin/'raw'/row['day']/'SOURCE_PROVENANCE.json')['daily_sources']['aemo_forecast.json']
                require(record(forecast['path'])==dict(forecast,path=str(Path(forecast['path']).resolve())),
                    'RETRY_FORECAST_CONTENT_DIFFERENT')
                from v42_svr11.controller import record_terminal,following_date
                record_terminal(row,path)
                day_after=following_date(row['day']);nextrow=source['dates'].get('B2/'+str(day_after),{})
                # A following date already assigned in the preserved origin
                # satisfies the user's dispatch-first requirement. Otherwise
                # the successor dispatches that next date before this retry.
                already_assigned=bool(nextrow.get('attempts'))
                row.update(retry_pending=True,retry_eligible_after=None if already_assigned else day_after,
                    execution_source_SHA=result['source_SHA'],validation_source_SHA=m['execution_SHA'],
                    previous_epoch_Native_Runtime=result.get('Native_Runtime'),previous_epoch_failure=record(path),
                    previous_epoch_runtime_pending=False,
                    next_date_previous_epoch_assignment=record(nextrow['request']) if already_assigned else None,
                    recovery='Verified canonical Forecast receipt path fix; fresh Native0 attempt; original FAIL/runtime retained')
                history=row.setdefault('previous_epoch_attempts',[])
                for receipt in (record(oldrow['request']),record(path)):
                    if receipt not in history:history.append(receipt)
                failure_admissions.append(record(path));continue
            try:proof_path,proof,admitted=qualify(root,origin,row['day'],'B2')
            except ValueError as error:
                # A rejected date is recalculated, never accepted or used to
                # block unrelated dates/policies. Global active Source errors
                # raised by authority.verify remain distinct exceptions.
                atomic(root/'reuse'/(row['day']+'_B2_REJECTED.json'),dict(PASS=False,
                    original_result=record(path),reason=repr(error),fresh_execution_required=True,UTC=now()))
                continue
            admitted.update(reused=True,reuse_proof=record(proof_path),execution_source_SHA=proof['execution_source_SHA'],
                validation_source_SHA=m['execution_SHA'],retry_pending=False)
            verify_reuse(root,m,admitted);ledger['dates'][key]=admitted
            decisions.append(record(proof_path))
        if decisions or failure_admissions:
            atomic(root/'CAMPAIGN_LEDGER.json',ledger)
            atomic(root/'B2_PRE_DISPATCH_REUSE.json',dict(PASS=True,proofs=decisions,UTC=now(),
                original_result_bytes_changed=False,Native_calls=0,AC_calls=0))
            atomic(root/'TECHNICAL_FAIL_RETRY_ADMISSION.json',dict(PASS=True,failed_original_results=failure_admissions,
                recovery='Only independently diagnosed canonical C/D alias mismatch; fresh Native0 after next date assignment',
                original_FAIL_and_Runtime_preserved=True,failures_promoted_to_PASS=0,UTC=now()))

def admit(root,origin,day):
    import psutil
    from v42_svr11.processes import live,workers
    from v42_svr11.controller import record_terminal
    from v42_common_campaign.authority import singleton
    root=Path(root).resolve();m=verify(root/'CAMPAIGN_MANIFEST.json')
    q=read(root/'REUSE_DISPATCH_QUIESCENCE.json');sup=q['supervisor']
    require(live(sup),'REUSE_QUIESCED_SUPERVISOR_IDENTITY')
    process=psutil.Process(sup['PID'])
    require(process.status()==psutil.STATUS_STOPPED,'REUSE_DISPATCH_MUST_BE_QUIESCED')
    require(not workers(root,m['execution_SHA']),'REUSE_WAIT_HEALTHY_WORKER_DRAIN')
    path,proof,oldrow=qualify(root,origin,day)
    with singleton(root/'WATCHDOG.lock'):
        ledger=read(root/'CAMPAIGN_LEDGER.json');key='B0/'+day
        require(ledger['dates'][key]['status']=='NOT_EXECUTED' and not ledger['dates'][key]['attempts'],
            'REUSE_NEVER_REPLACE_STARTED_ATTEMPT')
        before=root/'reuse'/'PRE_ADMISSION_LEDGER.json';require(not before.exists(),'REUSE_ALREADY_ADMITTED')
        atomic(before,ledger)
        # The last existing Worker completed naturally while dispatch alone
        # was paused; reconcile its real RESULT before changing the controller.
        for row in ledger['dates'].values():
            if row['status']=='RUNNING':
                result=Path(read(row['request'])['result'])
                require(result.exists(),'REUSE_DRAIN_RESULT_REQUIRED');record_terminal(row,result)
        oldrow.update(reused=True,reuse_proof=record(path),
            execution_source_SHA=proof['execution_source_SHA'],validation_source_SHA=m['execution_SHA'],
            admission='USER_VERIFIED_COMPLETED_RESULT_REUSE',retry_pending=False)
        ledger['dates'][key]=oldrow;ledger.update(active_workers=[],UTC=now())
        verify_reuse(root,m,oldrow)
        # Only replace the drained, intentionally suspended control process
        # to load the new ledger; no Worker/Solver is terminated or hot-patched.
        process.terminate();process.wait(timeout=15)
        atomic(root/'CAMPAIGN_LEDGER.json',ledger)
        from v42_svr11.watchdog import launch
        successor=launch('v42_svr11.controller',root)
        atomic(root/'REUSE_ADMISSION.json',dict(PASS=True,day=day,proof=record(path),
            previous_ledger=record(before),successor_PID=successor.pid,
            old_dispatcher_PID=sup['PID'],healthy_workers_terminated=0,Native_calls=0,AC_calls=0,UTC=now()))
    print('REUSED',day,'SUPERVISOR',successor.pid)

if __name__=='__main__':
    mode,root,origin,day=sys.argv[1:5]
    if mode=='qualify':print(qualify(root,origin,day)[1]['PASS'])
    elif mode=='admit':admit(root,origin,day)
    else:raise ValueError(mode)
