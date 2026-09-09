"""Independent report and dependency audit, never performs optimization/replay."""
from pathlib import Path
import sys,json,math
import numpy as np
import restoration_revision_v1 as r

def main(final=False):
    r.seal_check();r.verify(r.read(r.OUT/'READER_R1_BINDING.json')['adapter'])
    cache={}
    def checked(path,expected):
        key=str(path)
        if key not in cache:cache[key]=r.sha(path)
        assert cache[key]==expected,('DEPENDENCY_HASH_DRIFT',key)
    def references(value):
        if isinstance(value,dict):
            if 'path' in value and 'sha256' in value and value.get('exists',True):checked(value['path'],value['sha256'])
            for v in value.values():references(v)
        elif isinstance(value,list):
            for v in value:references(v)
    def grid(folder):
        s=r.read(folder/'OPENDSS_SUMMARY.json');manifest=r.read(folder/'OPENDSS_OUTPUT_MANIFEST.json')
        for name,rec in manifest['files'].items():checked(folder/name,rec['sha256'])
        with np.load(folder/'OPENDSS_PHASE_ARRAYS.npz',allow_pickle=False) as a:
            v=a['voltage_pu'];loading=a['phase_current_loading_pu'];tx=a['branch_kinds']=='transformer';kva=a['transformer_total_kva_loading_pu'][:,tx]
            assert v.shape[0]==96 and a['convergence'].all() and np.isfinite(v).all() and np.isfinite(loading).all() and np.isfinite(kva).all()
            exact=dict(Vmin_pu=float(v.min()),Vmax_pu=float(v.max()),rho_max_AC=float(loading[:,~tx].max()),transformer_phase_current_loading_max=float(loading[:,tx].max()),transformer_total_kva_loading_max=float(kva.max()))
            assert all(abs(s[k]-val)<1e-12 for k,val in exact.items())
            assert v.min()>=.95-1e-9 and v.max()<=1.05+1e-9 and loading.max()<=1+1e-9 and kva.max()<=1+1e-9
            assert not s['physical_violation']
        return s
    rows=[];pending=[]
    for n in range(1,32):
        day=f'2025-05-{n:02d}'
        for policy in ('B0','B1','B2','B3'):
            folder=r.OUT/day/policy;path=folder/'ACCEPTANCE.json'
            if not path.exists():pending.append([day,policy,'FRESH_NOT_ACCEPTED']);continue
            u=r.read(path);assert u['status']=='PASS'
            references(u['new_joint']);references(u['source_snapshot'])
            for p,h in r.read(u['source_snapshot']['path']).items():checked(p,h)
            d=r.read(u['new_joint']['path'])['decision'];assert r.identities(d)==u['new_identity']
            references(d)
            for k in ('AIDC','route','physical_inputs'):assert u['old_identity'][k]==u['new_identity'][k]
            fpath=folder/'accepted_fresh' if u['old_primary_fresh']=='FAIL' else r.RUN/day/policy/'dayahead/fresh'
            fresh=grid(fpath)
            for k in ('Vmin_pu','Vmax_pu','rho_max_AC','transformer_phase_current_loading_max','transformer_total_kva_loading_max'):assert fresh[k]==u['final'][k]
            acroot=r.OLDAC if u['actual_disposition']=='REUSE_ACTUAL' else r.NEWAC
            ac=acroot/'replays'/day/policy;receipt=ac/'CANDIDATE_RECEIPT.json'
            disposition='REUSED' if acroot==r.OLDAC else 'NEW' if u['actual_disposition']=='NEW_ACTUAL_REQUIRED' else 'RERUN'
            if not receipt.exists():pending.append([day,policy,'ACTUAL_V2_RERUN_REQUIRED']);disposition='PENDING'
            else:
                ar=r.read(receipt);assert ar['status']=='COMPLETE'
                for name,h in ar['files'].items():checked(ac/name,h)
                checked(acroot/'METHOD_FREEZE.json',ar['method_SHA']);checked(acroot/'EXECUTION_BINDING.json',ar['execution_binding_SHA'])
                for name,h in r.read(acroot/'EXECUTION_BINDING.json')['files'].items():checked(acroot/name,h)
                references(r.read(acroot/'METHOD_FREEZE.json')['numerical_method_files'])
                ci=acroot/'common_inputs'/day/policy
                for p,h in r.read(ci/'DA_FRESH_INPUT_SNAPSHOT.json').items():checked(p,h)
                done=r.read(ac/'COMPLETE.json');b=done['binding']
                assert b['AIDC_schedule_SHA']==u['new_identity']['AIDC']
                checked(ci/'ACTUAL_AIDC_POWER.npz',b['Actual_AIDC_power_file_SHA'])
                checked(acroot/'BATTERY_EFFICIENCY_AUTHORITY.json',b['eta_authority_SHA'])
                references(r.read(ci/'ACTUAL_EXOGENOUS_AUTHORITY.json'))
                mess=r.read(ci/'ACTUAL_MESS_AUDIT.json');references(mess)
                assert mess['frozen_commands_SHA']==b['frozen_command_SHA']
                routefields=('mess_id','slot','service_id','departure_slot','origin_service_id','destination_service_id','route_link_ids','connection_ready_slot','mode')
                assert r.digest([{k:x.get(k) for k in routefields} for x in d['MESS_trajectory']])==b['MESS_decision_SHA']
                by={(x['mess_id'],x['slot']):x for x in d['MESS_trajectory']}
                for x in mess['frozen_commands']:
                    y=by[x['mess_id'],x['slot']]
                    assert x['p_kw']==y['p_kw'] and x['q_kvar']==y['q_kvar']
                if disposition=='REUSED':assert u['old_identity']==u['new_identity']
                stage='CONTROL_COMMON_BINDING' if policy in ('B0','B1') else 'ETA95_QSAFE_ACTUAL'
                actual=grid(ac/stage)
                audit=dict(status='PASS',disposition=disposition,accepted_trajectory_SHA=u['new_identity']['trajectory'],Actual_receipt=r.record(receipt),method=r.record(acroot/'METHOD_FREEZE.json'),Actual_summary=actual)
                r.save(folder/'FINAL_EXECUTION_AUDIT.json',audit)
            rows.append(dict(day=day,policy=policy,DA_disposition='NEW_REQUIRED_DA_EXECUTION' if (day,policy)==('2025-05-31','B3') else 'EXISTING_DA_REUSE',
                previous_accepted_trajectory_existed=u['previous_Actual'] is not None,
                old_primary_fresh=u['old_primary_fresh'],new_primary_fresh=u['new_primary_fresh'],local_restoration=u['local_restoration'],full_PQ_fallback=u['full_PQ_fallback'],
                final_Vmin=fresh['Vmin_pu'],final_Vmax=fresh['Vmax_pu'],max_line=fresh['rho_max_AC'],max_transformer_current=fresh['transformer_phase_current_loading_max'],max_transformer_kva=fresh['transformer_total_kva_loading_max'],
                old_trajectory_SHA=u['old_identity']['trajectory'],new_trajectory_SHA=u['new_identity']['trajectory'],Actual_disposition=disposition,changed=u['changed'],reason=u['reason']))
    counts=dict(total_accepted=len(rows),existing_DA_reused=sum(x['DA_disposition']=='EXISTING_DA_REUSE' for x in rows),new_required_DA=sum(x['DA_disposition']=='NEW_REQUIRED_DA_EXECUTION' for x in rows),
        primary_PASS_no_op=sum(x['old_primary_fresh']=='PASS' for x in rows),existing_final_unchanged=sum(not x['changed'] and x['DA_disposition']=='EXISTING_DA_REUSE' for x in rows),
        changed_by_new_restoration=sum(x['changed'] for x in rows),Actual_REUSED=sum(x['Actual_disposition']=='REUSED' for x in rows),Actual_RERUN=sum(x['Actual_disposition']=='RERUN' for x in rows),Actual_NEW=sum(x['Actual_disposition']=='NEW' for x in rows),
        existing_DA_reoptimization_calls=0,existing_route_search_reruns=0,hashes_verified=len(cache))
    status='COMPLETE' if len(rows)==124 and not pending else 'IN_PROGRESS'
    if final:assert status=='COMPLETE',(len(rows),pending)
    report=dict(status=status,counts=counts,pending=pending,rows=rows,restoration_rule=r.record(r.OUT/'RULE_FREEZE.json'),forensic_witness_not_production_input=True,
        assumptions='Minimum normalized squared PQ deviation among exact-validated deterministic candidates; no global AC minimum claim.',
        incident='First NEW May31 B3 bootstrap attempt failed before optimization because child environment omitted date binding; preserved, then relaunched with original dispatcher environment. No completed DA reoptimized.')
    r.save(r.OUT/'FINAL_AUDIT.json',report)
    headers=['day / policy','old/new Primary Fresh','local restoration','full-PQ','Vmin / Vmax','line %','Tx current %','Tx kVA %','old → new trajectory SHA','Actual','reason']
    def table(items):
        lines=['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']
        for x in items:
            new_da=x['DA_disposition']=='NEW_REQUIRED_DA_EXECUTION'
            lines.append('| '+' | '.join([x['day']+' / '+x['policy'],('N/A' if new_da else x['old_primary_fresh'])+'/'+x['new_primary_fresh'],x['local_restoration'],str(x['full_PQ_fallback']),f"{x['final_Vmin']:.9f} / {x['final_Vmax']:.9f}",f"{100*x['max_line']:.6f}",f"{100*x['max_transformer_current']:.6f}",f"{100*x['max_transformer_kva']:.6f}",('N/A' if new_da else x['old_trajectory_SHA'][:12])+' → '+x['new_trajectory_SHA'][:12],x['Actual_disposition'],x['reason']])+' |')
        return '\n'.join(lines)
    affected=[x for x in rows if x['old_primary_fresh']=='FAIL' or x['DA_disposition']=='NEW_REQUIRED_DA_EXECUTION']
    text='# V41R4 revised post-DA closure and selective Actual audit\n\nStatus: '+status+'\n\n'+json.dumps(counts,indent=2)+'\n\nPrimary Fresh is the unmodified pre-restoration check. A retained Primary FAIL can have final Fresh PASS after closure. All accepted rows below have final Fresh PASS. For May31 B2 the old SHA describes the failed original trajectory, not a previously accepted result.\n\n'+table(affected)+'\n\nFull SHA values and all 124 policy-day rows are in FINAL_AUDIT.json.\n\n'+report['assumptions']+'\n\n'+report['incident']+'\n'
    (r.OUT/'FINAL_AUDIT.md').write_text(text,encoding='utf-8')
    (r.OUT/'ALL_POLICY_DAYS.md').write_text(table(rows)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=status,counts=counts,pending=pending),indent=2),flush=True)
if __name__=='__main__':main('--final' in sys.argv)
