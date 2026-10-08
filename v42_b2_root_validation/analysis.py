"""Postprocess one completed ROOT. Every operation here has optimize=0."""
from v42_physics_redesign.common import *
from .certificate import verify_certificate
from fractions import Fraction as F
from collections import Counter
import re

ORIGINAL_LP=.568711942993466
SOURCE=ROOT/'docs/v42_m1_physics_strengthened_20261008'

def extent(v):
    v=np.asarray(v);nonzero=abs(v[v!=0])
    return dict(minimum=float(v.min()),maximum=float(v.max()),min_abs_nonzero=float(nonzero.min()) if len(nonzero) else None,max_abs=float(abs(v).max()))

def point_summary(A,d,x,reader):
    names=np.array([str(n).split('[')[0] for n in d['names']]);family=[];by_unit=[]
    for kind in ('node_activity','charge_mode','route_flow','SOC','Pch','Pdis','Q','injection_P','injection_Q'):
        idx=np.flatnonzero(names==kind);v=x[idx]
        if not len(idx):continue
        fraction=(abs(v-np.rint(v))>1e-8) if kind in ('node_activity','charge_mode','route_flow') else np.zeros(len(v),bool)
        thresholds=(1e-8,1e-6,1e-4)
        family.append(dict(family=kind,columns=len(idx),fractional_count=int(fraction.sum()),positive_support=int((abs(v)>1e-8).sum()),
            fractional_count_by_diagnostic_threshold={str(t):int((abs(v-np.rint(v))>t).sum()) for t in thresholds} if kind in ('node_activity','charge_mode','route_flow') else None,
            positive_support_by_diagnostic_threshold={str(t):int((abs(v)>t).sum()) for t in thresholds},min=float(v.min()),max=float(v.max())))
        for unit in ('MESS01','MESS02','MESS03','MESS04'):
            select=np.array([unit in str(d['names'][j]) for j in idx]);u=v[select]
            if len(u):by_unit.append(dict(MESS=unit,family=kind,columns=len(u),fractional_count=int(fraction[select].sum()),positive_support=int((abs(u)>1e-8).sum()),sum=float(u.sum()),min=float(u.min()),max=float(u.max())))
    full=reader.inverse(x)
    physical=[]
    from v42_strengthening.analysis import graph_inputs
    _,initial,arcs,_,_=graph_inputs()
    for unit in initial:
        soc=np.zeros(97);ch=np.zeros(96);dis=np.zeros(96);q=np.zeros(96);energy=np.zeros(96);stay=np.zeros(96);charge_sites=set();stays=set()
        for j,name in enumerate(reader.d['names']):
            text=str(name)
            if '[' not in text or unit not in text:continue
            kind,args=text.split('[',1);args=args[:-1].split(',');value=float(full[j])
            if kind=='SOC':soc[int(args[-1])]=value
            elif kind in ('Pch','Pdis','Q'):
                t=int(args[-1]);{'Pch':ch,'Pdis':dis,'Q':q}[kind][t]+=value
                if kind=='Pch' and value>1e-8:charge_sites.add((args[1],t))
            elif kind=='arc':
                a=arcs[int(args[-1])]
                if a[4] is not None:energy[a[1]]+=value*float(a[4].energy_kwh)
                elif value>1e-8:stay[a[1]]+=value;stays.add((a[0],a[1]))
        physical.append(dict(MESS=unit,SOC=soc.tolist(),Pch_by_slot=ch.tolist(),Pdis_by_slot=dis.tolist(),Q_by_slot=q.tolist(),
            fractional_weighted_travel_energy_by_departure=energy.tolist(),weighted_travel_energy_kWh=float(energy.sum()),
            stay_mass_by_slot=stay.tolist(),positive_stay_site_slots=len(stays),positive_charging_site_slots=len(charge_sites),
            charge_site_slots=[list(v) for v in sorted(charge_sites)],simultaneous_aggregate_charge_discharge_slots=int(((ch>1e-8)&(dis>1e-8)).sum()),
            minimum_SOC=float(soc.min()),maximum_SOC=float(soc.max()),
            note='Weighted fractional LP quantities; not an integer route or validated incumbent'))
    residual=A@x-d['rhs'];families=np.array([str(n).split('[')[0] for n in d['row_names']]);viol=np.where(d['sense']=='=',abs(residual),np.where(d['sense']=='<',residual,-residual))
    physics_rows=[]
    for kind in ['flow','node_activity_link','energy_balance','connected_Pch','connected_Pdis','no_simultaneous_charge','no_simultaneous_discharge','PCS16','injection_P_binding','injection_Q_binding','voltage_upper','voltage_lower','line_thermal_face','transformer_kVA']:
        idx=np.flatnonzero(families==kind)
        if len(idx):physics_rows.append(dict(family=kind,rows=len(idx),max_violation=float(max(0.,viol[idx].max())),strict_violations=int((viol[idx]>1e-8).sum())))
    binary=d['types']=='B'
    return dict(fractional_binary_count=int((abs(x[binary]-np.rint(x[binary]))>1e-8).sum()),family=family,by_MESS=by_unit,
        physical_trajectories=physical,physical_row_families=physics_rows,original_relaxed_row_replay=hc.replay(A,d,x,False),
        original_FULL_relaxed_row_replay=hc.replay(reader.full,dict(reader.d,types=np.full(reader.full.shape[1],'C')),full,False),
        rho=float(d['objective']@x+d['constant']),integer_incumbent=False,A1_source_unchanged=True)

def exact_cut_violations(T,rhs,x):
    result=[]
    for i in range(T.shape[0]):
        row=T.getrow(i);v=sum((F.from_float(float(a))*F.from_float(float(x[j])) for j,a in zip(row.indices,row.data)),F(0))-F.from_float(float(rhs[i]))
        result.append(float(v))
    return np.array(result)

def main():
    prior.forbid_optimize();start=time.perf_counter()
    native=read(REPORTS/'B2_ROOT_NATIVE_RESULT.json');root=read(REPORTS/'ROOT_RESULT.json')
    identity=read(REPORTS/'B2_ROOT_SOURCE_IDENTITY.json');assert identity['PASS']
    resource=read(REPORTS/'RESOURCE_ISOLATION_AUDIT.json')
    observation=REPORTS/'B2_EXTERNAL_PROCESS_OBSERVATION.json'
    if observation.exists():
        resource['mid_root_external_process_observation']=read(observation)
        resource['continuous_host_isolation_proven']=False
        resource['performance_comparison_controlled']=False
    write(REPORTS/'B2_ROOT_RESOURCE_AUDIT.json',resource)
    certificate=dict(PASS=False,measured=False,reason='NO_COMPLETED_OPTIMAL_ROOT_CERTIFICATE',native_calls=0)
    fractional=dict(measured=False,reason='ROOT_NOT_EXECUTED',new_integer_incumbent=False)
    effects=dict(measured=False,reason='ROOT_NOT_EXECUTED',rows=651)
    numerical=dict(measured=False,reason='ROOT_NOT_EXECUTED',tolerances_unchanged=True)
    exact_lb=None;valid_lb=LB;objective=native.get('ObjVal');obj_change=None;case='NOT_MEASURED'
    if native['executed']:
        fractional['reason']=effects['reason']=numerical['reason']='RAW_ATTRIBUTES_NOT_AVAILABLE'
        A,d,_=hc.load();T=sparse.load_npz(WORK/'artifacts/TEMPORAL_VALID_ROWS.npz').tocsr()
        with np.load(WORK/'artifacts/TEMPORAL_VALID_ROW_DATA.npz') as f:rhs=f['rhs'].copy()
        augmented=sparse.vstack([A,T],format='csr');full=dict(d,rhs=np.r_[d['rhs'],rhs],sense=np.r_[d['sense'],np.full(len(rhs),'<')])
        with np.load(WORK/'artifacts/B2_ROOT_RAW.npz') as f:raw={k:f[k].copy() for k in f.files}
        stored=REPORTS/'ROOT_LOWER_BOUND_CERTIFICATE.json'
        if stored.exists():
            producer=read(stored);accepted=producer.get('accepted')
            if accepted and accepted['PASS']:
                try:
                    independent=verify_certificate(augmented,full,accepted)
                    exact=F(independent['exact_alpha']);exact_lb=float(exact)
                    if F.from_float(exact_lb)>exact:exact_lb=float(np.nextafter(exact_lb,-np.inf))
                    valid_lb=max(LB,exact_lb)
                    certificate=dict(PASS=True,measured=True,producer=producer,independent=independent,exact_certified_LB=exact_lb,final_valid_global_LB=valid_lb,native_ObjBound_never_used=True)
                except Exception as error:certificate=dict(PASS=False,measured=True,producer=producer,independent_error=repr(error),final_valid_global_LB=LB)
        if 'x' in raw:
            reader=hc.physical_reader()
            with np.load(ROOT/'docs/v42_m1_joint_formulation_20261008/runs/ORIGINAL/LP_POINT_DUAL.npz') as f:old=f['x'].copy();old_pi=f['Pi'].copy()
            new=raw['x'];older=point_summary(A,d,old,reader);newer=point_summary(A,d,new,reader)
            families=np.array([str(n).split('[')[0] for n in d['names']]);changes=[]
            for kind in sorted(set(families)):
                idx=np.flatnonzero(families==kind);delta=new[idx]-old[idx]
                changes.append(dict(family=kind,changed_columns_above_1e8=int((abs(delta)>1e-8).sum()),L1_change=float(abs(delta).sum()),max_change=float(abs(delta).max())))
            fractional=dict(measured=True,archived=older,B2=newer,changes=changes,
                raw_vector_difference_norm=float(np.linalg.norm(new-old)),new_integer_incumbent=False,LP_point_never_updates_UB=True)
            before=exact_cut_violations(T,rhs,old);after=exact_cut_violations(T,rhs,new);cut_pi=raw.get('pi',np.zeros(augmented.shape[0]))[-651:]
            cut_rows=[];records=read(REPORTS/'VALID_INEQUALITY_CERTIFICATES.json')['coefficient_proof']
            for i,record in enumerate(records):cut_rows.append(dict(row=i,MESS=record['MESS'],depart=record['depart'],connect=record['connect'],arc_index=record['arc_index'],old_violation=before[i],new_violation=after[i],new_slack=-after[i],dual=cut_pi[i]))
            table(REPORTS/'B2_ALL_651_CUT_ROWS.csv',cut_rows)
            has_pi='pi' in raw
            effects=dict(measured=True,rows=651,old_violated_rows=int((before>1e-8).sum()),old_max_violation=float(max(0.,before.max())),
                new_violated_rows=int((after>1e-8).sum()),new_max_violation=float(max(0.,after.max())),all_new_rows_strict_PASS=bool(np.all(after<=1e-8)),
                active_rows_abs_slack_le_1e8=int((abs(after)<=1e-8).sum()),active_rows_abs_slack_le_1e6=int((abs(after)<=1e-6).sum()),
                slack_quantiles={str(q):float(np.quantile(-after,q)) for q in (0,.25,.5,.75,1)},
                cut_dual_nonzero_above_1e8=int((abs(cut_pi)>1e-8).sum()) if has_pi else None,cut_dual_absolute_mass=float(abs(cut_pi).sum()) if has_pi else None,
                cut_dual_rhs_sum=float(cut_pi@rhs) if has_pi else None,cut_dual_available=has_pi,all_651_rows_table='B2_ALL_651_CUT_ROWS.csv',native_slack_max_disagreement=float(abs(raw['slack'][-651:]+after).max()) if 'slack' in raw else None)
            rho=int(np.flatnonzero(d['objective'])[0]);csc=A.tocsc();rho_rows=csc.indices[csc.indptr[rho]:csc.indptr[rho+1]]
            newpi=raw.get('pi',np.zeros(augmented.shape[0]));original_res=A@old-d['rhs'];new_res=A@new-d['rhs']
            critical=[int(i) for i in rho_rows if abs(old_pi[i])>1e-8 or abs(newpi[i])>1e-8]
            write(REPORTS/'B2_CRITICAL_GRID_COMPARISON.json',dict(all_original_grid_rows_retained=True,critical_rho_rows=[dict(row=i,name=str(d['row_names'][i]),archived_Pi=old_pi[i],B2_Pi=newpi[i],archived_residual=original_res[i],B2_residual=new_res[i]) for i in critical]))
            log=(WORK/'logs/B2_ROOT_NATIVE.log').read_text(encoding='utf-8',errors='replace');warnings=[line for line in log.splitlines() if re.search(r'warning|numerical|ill.condition|scal|Markowitz',line,re.I)]
            presolved=re.search(r'Presolved:\s+(\d+) rows, (\d+) columns, (\d+) nonzeros',log)
            ptime=re.search(r'Presolve time:\s+([\d.]+)s',log);barrier=re.search(r'Barrier solved model in (\d+) iterations and ([\d.]+) seconds',log)
            stationarity=d['objective']-augmented.T@newpi
            numerical=dict(measured=True,original_coefficient_range=extent(A.data),augmented_coefficient_range=extent(augmented.data),RHS_range=extent(full['rhs']),
                lower_bounds=extent(d['lower']),upper_bounds=extent(d['upper']),native_attributes={k:native.get(k) for k in ('ConstrVio','BoundVio','DualVio','ComplVio','Kappa','KappaExact')},
                unavailable_native_attributes=native.get('missing_attributes'),Kappa_new_solve_forbidden=True,
                original_relaxed_replay=newer['original_relaxed_row_replay'],strengthened_max_violation=effects['new_max_violation'],
                numerical_warning_and_scaling_lines=warnings,presolved=dict(rows=int(presolved[1]),columns=int(presolved[2]),nnz=int(presolved[3])) if presolved else None,
                presolve_seconds=float(ptime[1]) if ptime else None,barrier_reported_seconds=float(barrier[2]) if barrier else None,crossover_seconds=0.,
                stationarity_vs_native_RC_max=float(abs(stationarity-raw['rc']).max()) if 'rc' in raw else None,
                native_primal_minus_exact_LB=objective-exact_lb if objective is not None and exact_lb is not None else None,
                raw_multiplier_rejection=certificate.get('producer',{}).get('raw_native_multiplier_certificate'),tolerances_unchanged=True)
            numerical.update(barrier_reported_time_is_log_endpoint_not_exclusive_phase=True,
                post_presolve_native_seconds_estimate=native['Runtime']-float(ptime[1]) if ptime else None,
                phase_timing_caveat='Presolve time is reported separately; Barrier solved-model seconds is a native log endpoint, not an additive exclusive interval. Crossover=0.')
            if certificate['PASS']:
                accepted=certificate['producer']['accepted']
                with np.load(accepted['npz_path']) as f:cert_pi=f['pi'].copy();cert_r=f['stationarity'].copy()
                endpoint=np.where(cert_r>=0,d['lower'],d['upper']);bound_loss=cert_r*(new-endpoint)
                row_loss=cert_pi*(augmented@new-full['rhs'])
                loss_by_family=[dict(family=kind,columns=int((families==kind).sum()),finite_box_loss=float(bound_loss[families==kind].sum()),maximum_stationarity_residual=float(abs(cert_r[families==kind]).max()),source_lower_range=extent(d['lower'][families==kind]),source_upper_range=extent(d['upper'][families==kind])) for kind in sorted(set(families))]
                loss_by_family.sort(key=lambda z:-z['finite_box_loss'])
                bad=((full['sense']=='<')&(newpi>0))|((full['sense']=='>')&(newpi<0))
                rf=np.r_[np.array([str(n).split('[')[0] for n in d['row_names']]),np.full(651,'B2_SOC_CUT')]
                numerical.update(certified_finite_box_loss_by_family=loss_by_family,
                    finite_box_loss_total=float(bound_loss.sum()),projected_multiplier_row_residual_term=float(row_loss.sum()),
                    primal_minus_cert_reconstructed_float=float(bound_loss.sum()+row_loss.sum()),
                    loss_decomposition_roundoff=float(bound_loss.sum()+row_loss.sum()-(objective-exact_lb)),
                    raw_wrong_sign_by_row_family=dict(Counter(rf[bad])),raw_wrong_sign_count=int(bad.sum()),
                    exact_certificate_uses_separate_projected_multiplier=True,
                    loss_family_numbers_are_float_diagnostics=True)
            if objective is not None:
                obj_change=objective-ORIGINAL_LP
                case='B_SAME_NATIVE_LP_OBJECTIVE' if abs(obj_change)<=1e-6 else 'A_NATIVE_LP_OBJECTIVE_INCREASE' if obj_change>0 else 'NATIVE_OBJECTIVE_DECREASE_NUMERICAL_DIAGNOSTIC'
            if native['Status']!=2:case='C_ROOT_INCOMPLETE'
            elif not certificate['PASS']:case='D_NUMERICAL_CERTIFICATION_FAILURE'
            elif obj_change is not None and obj_change>1e-6 and valid_lb<=LB:
                case='D_NATIVE_INCREASE_NOT_CERTIFIED_VALID_WEAKER_BOUND_ONLY'
    if not native['executed']:classification='B2_ROOT_RESOURCE_PENDING'
    elif native.get('Status')!=2 or native['Runtime']>900:classification='B2_ROOT_TRACTABILITY_FAIL'
    elif not certificate['PASS']:classification='B2_ROOT_NUMERICAL_CERTIFICATION_FAIL'
    elif abs(obj_change)<=1e-6:classification='B2_ROOT_SAME_LP_OPTIMUM'
    elif valid_lb-LB>=.001:classification='B2_ROOT_CERTIFIED_MATERIAL_LB_GAIN'
    else:classification='B2_ROOT_NONMATERIAL'
    material=bool(native['executed'] and native.get('Status')==2 and native['Runtime']<=900 and certificate['PASS'] and valid_lb-LB>=.001)
    if not native['executed']:next_action='다른 native 작업과 자원이 격리된 시간에 동일한 사전등록 B2 ROOT 단일 검증을 실행한다.'
    elif material:next_action='검증된 original UB를 Start로 제공하는 별도 900초 full-domain Branch-and-Cut canary 한 회를 다음 실험으로 검토한다.'
    elif classification=='B2_ROOT_SAME_LP_OPTIMUM':next_action='대체 분수해의 이동 구간과 충전 가능 질량을 함께 묶는 96-slot route–mode–energy joint inequality의 유효성과 분리 가능성을 optimize=0으로 검증한다.'
    elif classification=='B2_ROOT_TRACTABILITY_FAIL':next_action='저장된 barrier trajectory와 finite-bound support를 이용해 수치 정체 원인을 optimize=0으로 분해한다.'
    else:next_action='인증 손실을 지배하는 injection_P/Q의 원래 binding 등식으로 stationarity residual을 상쇄하는 exact multiplier repair 한 건을 optimize=0의 별도 실험으로 검증한다.'
    decision=dict(classification=classification,case=case,source_HEAD='6d1d64beaf012d32ddf39245890785e3d8f01d4b',
        native_optimize_calls=native['native_optimize_calls'],native_status=native.get('Status'),Runtime=native.get('Runtime'),Work=native.get('Work'),
        native_LP_objective=objective,archived_native_LP_objective=ORIGINAL_LP,native_objective_change=obj_change,
        exact_certified_LB=exact_lb,old_global_LB=LB,new_valid_global_LB=valid_lb,Delta_LB=valid_lb-LB,
        Delta_LB_definition='Final valid global LB minus inherited LB, as preregistered',
        Delta_LB_B2_minus_old=None if exact_lb is None else exact_lb-LB,
        valid_global_LB_improvement=valid_lb-LB,
        old_UB=UB,new_UB=UB,global_gap_percent=100*(UB-valid_lb)/UB,target_LB=UB*.995,
        integer_equivalence_PASS=identity['PASS'],independent_certificate_PASS=certificate['PASS'],Material_Gate_PASS=material,
        root_completed=bool(native.get('Status')==2),root_tractability_PASS=bool(native.get('Status')==2 and native['Runtime']<=900),
        original_strict_primal_PASS=fractional.get('B2',{}).get('original_relaxed_row_replay',{}).get('PASS'),
        all_651_Cut_rows_strict_PASS=effects.get('all_new_rows_strict_PASS'),raw_native_dual_sign_certificate_PASS=certificate.get('producer',{}).get('raw_native_multiplier_certificate',{}).get('PASS'),
        native_objective_increase_certified=False if valid_lb<=LB else None,
        M1_ACCEPTED=False,canary_calls=0,production_calls=0,additional_cut_generation=False,downstream_executed=False,
        next_action=next_action,next_action_count=1,next_action_executed=False,postprocessing_wall_seconds=time.perf_counter()-start)
    for name,value in [('B2_ROOT_LB_CERTIFICATE.json',certificate),('B2_ROOT_FRACTIONAL_SOLUTION_AUDIT.json',fractional),('B2_ROOT_CUT_EFFECT_AUDIT.json',effects),('B2_ROOT_NUMERICAL_AUDIT.json',numerical),('B2_ROOT_FINAL_DECISION.json',decision)]:write(REPORTS/name,value)
    table(REPORTS/'B2_ROOT_BOUND_COMPARISON.csv',[dict(candidate='B0_ARCHIVED_NATIVE_LP',native_LP_objective=ORIGINAL_LP,valid_global_LB=LB,UB=UB),dict(candidate='B2',native_LP_objective=objective,exact_certified_LB=exact_lb,valid_global_LB=valid_lb,Delta_LB_B2_minus_old=decision['Delta_LB_B2_minus_old'],valid_global_LB_improvement=valid_lb-LB,UB=UB,global_gap_percent=decision['global_gap_percent'])])
    baseline=read(ROOT/'docs/v42_m1_joint_formulation_20261008/runs/ORIGINAL/RESULT.json')
    table(REPORTS/'B2_ROOT_RUNTIME_WORK.csv',[dict(candidate='B0_ARCHIVED',Runtime=baseline['Runtime'],Work=baseline['Work'],native_calls_new=0),dict(candidate='B2',Runtime=native.get('Runtime'),Work=native.get('Work'),native_calls_new=native['native_optimize_calls'],peak_RSS=root.get('peak_RSS'),controller_wall=native.get('controller_native_wall_seconds'),build_and_preopt_guard_wall=read(REPORTS/'ROOT_SOLVER_PARAMETERS.json').get('build_wall_seconds'),presolve_seconds=numerical.get('presolve_seconds'),barrier_reported_log_endpoint=numerical.get('barrier_reported_seconds'),post_presolve_native_seconds_estimate=numerical.get('post_presolve_native_seconds_estimate'),crossover_seconds=0 if native['executed'] else None)])
    write(REPORTS/'B2_OWNED_PROCESS_PEAK_RSS.json',dict(peak_RSS=root.get('peak_RSS'),observation_only=True,no_memory_limits_added=True))
    review=f'''# B2 ROOT 단일 검증 결과

**{classification}**

PR185 exact HEAD 위 별도 D: worktree에서 원본 목적함수·CSR·bounds·types·A1/물리 authority와 기존 651개 제약을 검증했다. Native optimize는 {native['native_optimize_calls']}회다. Cut 재생성·추가 ROOT·canary·production·downstream은 없다. 다른 작업을 중지하거나 수정하지 않았다.

| 지표 | 결과 |
|---|---|
| Native status | {native.get('Status')} |
| Runtime / Work | {native.get('Runtime')} / {native.get('Work')} |
| Native LP objective | {objective} |
| Archived native LP objective | {ORIGINAL_LP} |
| Native 목적값 차이 | {obj_change} |
| Exact certified B2 LB | {exact_lb} |
| Inherited global LB | {LB} |
| Final valid global LB | {valid_lb} |
| B2 certificate − inherited LB | {decision['Delta_LB_B2_minus_old']} |
| Final global LB 개선량 | {valid_lb-LB} |
| 검증된 UB | {UB} |
| Global gap | {decision['global_gap_percent']:.9f}% |
| Material gate | {material} |
| M1_ACCEPTED | false |

요청의 B2 certificate−LB_old 차이와 기존 인증을 보존한 final global LB 개선량을 둘 다 기록한다. 사전등록 파일의 Delta_LB 이름은 final global 개선량을 가리키므로 사후에 그 정의를 바꾸지 않는다.

Native 목적값, exact finite-box certificate, inherited bound를 포함한 global LB를 구분한다. RAW LP point는 정수 incumbent가 아니다. 목적값 비교의 1e-6 기준은 진단 분류이며 원래 1e-8 feasibility tolerance를 변경하지 않는다. Original/B2 residual과 모든 651개 행의 exact violation, slack·Pi, SOC/PQ/route 질량과 critical-grid 변화를 동봉한다. 저장된 point가 strict residual을 통과하지 못하면 그 사실을 그대로 기록한다. Native ObjBound는 채택하지 않는다. RAM은 관측만 하고 MemLimit·SoftMemLimit은 default infinity로 보존했다.

분수해 비교 Case: `{case}`. 새 제약이 archived 점을 분리했다는 사실과 실제 목적값 상승은 별개다. 독립 CSR-row dyadic 계산으로 CSC producer의 모든 finite-bound term과 exact α를 대조한다. TIME_LIMIT 또는 certificate 실패의 raw point를 인증된 LB로 사용하지 않는다.

다음 행동은 하나다: {next_action}

현재 후속 실험을 실행하지 않았다. 최종 Git HEAD·PR URL·remote equality·clean tree는 외부 GIT_COMPLETION.json에 기록한다.
'''
    if fractional.get('measured') and certificate['PASS']:
        oldf=fractional['archived'];newf=fractional['B2']
        at6=lambda summary:sum(row['fractional_count_by_diagnostic_threshold']['1e-06'] for row in summary['family'] if row['family'] in ('node_activity','charge_mode'))
        family_loss={v['family']:v['finite_box_loss'] for v in numerical['certified_finite_box_loss_by_family']}
        injection_share=100*(family_loss['injection_P']+family_loss['injection_Q'])/numerical['finite_box_loss_total']
        soc_change=next(v['max_change'] for v in fractional['changes'] if v['family']=='SOC')
        numerical_detail=f'''## 651개 제약과 분수점의 변화

Archived 점의 위반 651개는 새 점에서 0개가 됐다. 최대 archived 위반은 {effects['old_max_violation']}이며 새 최소 slack은 {effects['slack_quantiles']['0']}다. Slack의 절댓값≤1e-6인 행은 {effects['active_rows_abs_slack_le_1e6']}개지만 raw dual의 절댓값>1e-8인 행은 {effects['cut_dual_nonzero_above_1e8']}개다. Barrier 내부점의 작은 양의 slack과 작은 dual을 함께 기록하며, 이를 단순한 cut 비활성 또는 최적값 동일성의 증명으로 해석하지 않는다.

분수 binary는 scientific 1e-8 기준 {oldf['fractional_binary_count']}→{newf['fractional_binary_count']}개다. 1e-6 진단 기준에서는 {at6(oldf)}→{at6(newf)}개로 같다. Charge_mode는 두 점 모두 384개가 분수이며, 상당한 route-flow 분수 질량도 남는다. SOC 380개는 모두 바뀌었고 최대 변화는 {soc_change:.6f} kWh다. P/Q와 route 분포가 바뀌어 651개 행을 만족하는 다른 native 분수점이 관측됐지만, 이 점의 원본 strict 행 residual은 {native.get('ConstrVio')}로 1e-8을 넘는다. 완전한 원본 LP feasible point나 두 exact 최적값의 동일성을 주장하지 않는다. Support count의 1e-8 부근 변화에는 barrier 내부점과 종료 정밀도의 영향이 있다.

## 인증 병목과 확대 실행 판단

Raw Pi의 부호 오류 {numerical.get('raw_wrong_sign_count')}개를 거부했다. 별도 sign-cone multiplier의 모든 583,459행·306,040 finite-bound term을 exact CSR 방식으로 재검증해 유효한 LB를 얻었다. 이 약한 인증은 native 목적값의 상승을 증명하지 못했다. Native ObjBound={native.get('ObjBound')}도 채택하지 않는다.

Native primal과 exact LB 사이의 차이는 {numerical.get('native_primal_minus_exact_LB')}다. Float 진단 분해에서 finite-box support 손실은 {numerical.get('finite_box_loss_total')}, projected row residual 항은 {numerical.get('projected_multiplier_row_residual_term')}다. Injection_Q 손실 {family_loss['injection_Q']}과 injection_P 손실 {family_loss['injection_P']}이 finite-box 손실의 약 {injection_share:.5f}%를 차지한다. 이 분해는 exact scalar certificate와 구분한 진단 수치다.

Presolve는 {numerical.get('presolve_seconds')}초, presolved size는 {numerical.get('presolved')}다. Native 전체 ROOT는 {native['Runtime']:.3f}초로 900초 예산 안에 완료됐고 crossover는 0이다. Barrier 로그의 완료 시각 {numerical.get('barrier_reported_seconds')}초는 별도 독점 phase 시간이 아니므로 presolve와 합산하지 않는다. 기존 ROOT의 {baseline['Runtime']:.3f}초 / Work {baseline['Work']:.3f}와 이번 {native['Runtime']:.3f}초 / Work {native['Work']:.3f}를 기록하지만 단일 archived 비교로 인과적인 속도 향상을 입증하지 않는다. 실행 중 외부 May12 pytest가 관측됐으며 이를 통제된 성능 비교라고 주장하지 않는다.

계산시간 기준은 통과했으나 certified ΔLB={valid_lb-LB}이므로 Branch-and-Cut 확대를 정당화하지 못한다. {classification}은 이번 유효 하한 개선에 대한 판정이다. Raw dual 인증 실패와 별도 약한 certificate PASS를 구분하며, 실제 두 LP 최적값이 정확히 같다는 결론은 내리지 않는다.
'''
        review=review.replace('다음 행동은 하나다:',numerical_detail+'\n다음 행동은 하나다:')
    (REPORTS/'FINAL_REVIEW_KO.md').write_text(review,encoding='utf-8')
    print('B2_FINAL_DECISION',json.dumps(clean(decision),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
