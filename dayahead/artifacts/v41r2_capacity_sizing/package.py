"""Finalize six-candidate report and read-only preservation evidence."""
from compare_allocations import *

def assemble():
 a=read(OUT/'V41R2_AIDC_GPU_CAPACITY_SIZING_REPORT.json');cs=a['candidates'];o=a['offered']
 recommendation=dict(disposition='RECOMMEND_GENERALIZED_ALLOCATION_RULE_B_BUT_NO_TESTED_CAPACITY_APPLICATION',
   allocation_rule=RULE_B,recommended_total=None,recommended_per_site_vector=None,safe_to_apply=False,
   nominal_80_total=2752,nominal_80_vector=cs['B80']['vector'],
   largest_reference_only_review_candidate=dict(option='B75',target=.75,total=2936,vector=cs['B75']['vector']),
   allocation_reason='B preserves the common 32-GPU floor and authoritative relative facility heterogeneity with much lower weight distortion, independent of May geography. A sometimes has better destination headroom; B is not universally superior. B is a new generalized rule, not historical V39C identity.',
   capacity_reason='All six candidates leave 702–840 pending job-day observations unstarted within Day D. None satisfies the requested healthy operating/service region; even B75 leaves 515712 offered GPU-hours unserved. This is demonstrated system burst/backlog inadequacy, not missing preassigned sites.',
   next_review='Resolve peak/backlog-service design intent before selecting installed capacity. Keep WAN/D24 contract issues separate; no additional untested capacity or policy is applied.')
 a['recommendation']=recommendation;a['status']='RECOMMENDED_CAPACITY_AUTHORITY_RULE_B_CAPACITY_HOLD'
 a['current']['resizing_decision']='Compare A common-alpha frozen shape against user-authorized B minimum-plus-weighted-residual; recommend B as generalized allocation philosophy, without promoting a tested capacity.'
 a['current']['exact_allocator']['decision']='Historical one-pass allocator is not scaled. A and newly generalized B are independently specified, deterministic, and compared.'
 a['current']['exact_allocator']['latest_user_preference']='Explicit A/B comparison for each 75/80/85 total; B minimum32 plus Hamilton residual nodes.'
 a['verification']['six_candidates_verified']=True
 write('CURRENT_AIDC_GPU_CAPACITY_AUTHORITY.json',a['current']);write('RECOMMENDED_CAPACITY_AUTHORITY.json',recommendation)
 write('V41R2_AIDC_GPU_CAPACITY_SIZING_REPORT.json',a)
 oldmd=(OUT/'V41R2_AIDC_GPU_CAPACITY_SIZING_REPORT.md').read_text(encoding='utf-8')
 foundation=oldmd.split('## Current authority and historical lineage')[1].split('## Capacity options and integer apportionment')[0]
 start=foundation.index('The historical function has fixed total/expected-vector assertions.')
 end=foundation.index('[GitHub PR #12]',start)
 foundation=foundation[:start]+('The original fixed-total allocator is not forced onto larger totals. Rule A scales its frozen shape; rule B is the user-authorized generalization: 32 GPU/site plus residual 4-GPU nodes apportioned by authoritative V22SR1 weights. B is explicitly **not historically identical** to the original allocator.\n\n')+foundation[end:]
 text='# V41R2 AIDC GPU capacity sizing authority audit\n\n'
 text+='**RECOMMENDED CAPACITY AUTHORITY: generalized allocation rule B; no tested installed capacity is approved. Full May remains HOLD.** This PR contains only audit evidence and reproducibility code. No production capacity, schedule, model, electrical coefficients, B1/B2/B3 or WAN semantics are changed.\n\n'
 text+=f'All-D-day offered mean: **{fmt(o["aggregate"]["mean"])} GPU slots**. Mean-occupancy totals: **75%=2,936; 80%=2,752; 85%=2,592**. A and B are compared at each identical total. All six still leave material D-day service unstarted. The requested 80% mean is an arithmetic design point, not proof of a healthy operating region.\n\n'
 text+='## Current authority and historical lineage'+foundation
 text+='## Two allocation rules at each target\n\nA — **LEGACY_SHAPE_SCALE**: common-alpha scaling of the frozen current vector, Hamilton apportionment in 4-GPU nodes.\n\nB — **GENERALIZED_MINIMUM_PLUS_WEIGHTED_RESIDUAL**: reserve 32 GPU at every site (384 total); distribute the remaining `(C_total-384)/4` nodes with Hamilton largest remainders using repository V22SR1 weights. Numeric AIDC order breaks ties. The floor and residual weights are independent of May workload geography. No MW-to-GPU census claim is made.\n\n'
 text+=table(['Option','Total','Continuous total','AIDC01–12 vector'],[[k,v['total'],fmt(v['continuous_total']),vec(v['vector'])] for k,v in sorted(cs.items())])
 text+='\nThe rounded total is the nearest physically valid multiple of four; allocation conserves this total exactly. Every candidate has minimum >=32 GPU and only complete 4-GPU nodes. Per-site quota errors are in CAPACITY_INTEGER_APPORTIONMENT_AUDIT.json; all 72 site/option rows are in V41R2_AIDC_GPU_CAPACITY_CANDIDATES.csv.\n\n'
 text+='## Aggregate offered-demand occupancy\n\nThese ratios include unknown-site D-day offered work; they are not feasible materialized occupancy. A/B share identical aggregate ratios at a given total.\n\n'
 text+=table(['Target','Mean','P50','P90','P95','P99','Max','>=90%','>=95%','>=100%'],[[k+'%']+[pct(cs['A'+k]['system_offered_occupancy'][f]) for f in ('mean','P50','P90','P95','P99','max','fraction_ge_90','fraction_ge_95','fraction_ge_100')] for k in ('75','80','85')])
 text+='\nNo P95 hard threshold is claimed as an industry law. Severe burstiness is visible directly: the 80% point has offered P95/P99 of 304.469%/368.750%.\n\n'
 text+='## A/B resource-only comparison\n\nFixed D00 RUNNING sources and residuals are preserved. D-day ready PENDING uses service-tier/FIFO, earliest feasible event, whole-gang site/rack capacity, numeric AIDC preference and first logical rack. Current V39D supplies the eligible-site domain/numeric preference; V41R1 supplies event first fit. **This is an explicit resource-only adaptation**, because the production baseline fixes old sites and skips UNASSIGNED; it is not that unchanged routine nor a global-placement-optimality certificate. Newly assigned PENDING sites are generated only after candidate capacity is specified. No policy/grid/temporal-flexibility/migration optimization is run.\n\n'
 text+=table(['Option','Materialized mean','P95','P99','12/12 FULL','>=10 FULL','Unstarted jobs','Unserved offered GPUh','Weight L1'],[[k,pct(v['materialized_headroom']['system']['mean']),pct(v['materialized_headroom']['system']['P95']),pct(v['materialized_headroom']['system']['P99']),pct(v['materialized_headroom']['all12_FULL_fraction']),pct(v['materialized_headroom']['ge10_FULL_fraction']),v['remaining_Dday_UNASSIGNED']['pending_jobs'],fmt(v['remaining_Dday_UNASSIGNED']['pending_offered_GPU_hours']),fmt(v['V22SR1_weight_distortion']['total_capacity_L1'])] for k,v in sorted(cs.items())])
 text+='\nAll six have valid gang/rack envelopes and fit immutable running reservations. The largest pending gang is 256 GPU and has compatible sites under each candidate. An additional 14 ambiguous D00 source observations / 11 GPU-hours remain separate, with no fabricated physical source. Remaining D-day pending counts mean resource starts at/after120; they are capacity-induced unserved demand, not true nominal future arrivals.\n\n'
 text+='## Whole-job destination headroom\n\nEmpirical P50/P90 GPU request sizes are **1/2 GPU**, counted over frozen job-day observations. Additional 4/8/16/32/60/128/256-GPU representative gangs are retained. Instantaneous GPU/rack acceptance only; source exclusion, full-duration reservation, WAN and electrical safety are not claimed.\n\n'
 text+=table(['Option','GPU','>=1 destination','>=2','>=3'],[[k,g,pct(x['fraction_at_least_1']),pct(x['fraction_at_least_2']),pct(x['fraction_at_least_3'])] for k,v in sorted(cs.items()) for g,x in v['materialized_headroom']['whole_job_feasibility'].items()])
 text+='\n## Per-site occupancy and headroom\n\n'
 for k,v in sorted(cs.items()):
  h=v['materialized_headroom'];text+=f'### {k}: {v["allocation_rule"]}\n\n'
  text+=table(['AIDC','Mean','P90','P95','P99','Max','FULL','Spare mean','Spare P10/P50','Headroom GPUh'],[[s]+[pct(x[f]) for f in ('mean','P90','P95','P99','max','FULL_fraction')]+[fmt(x['available_GPU_mean']),fmt(x['available_GPU_P10'])+'/'+fmt(x['available_GPU_P50']),fmt(x['headroom_GPU_hours'])] for s,x in h['sites'].items()])
  text+=f'\nSites with positive headroom at every slot: {h["number_sites_positive_headroom_every_slot"]}. Destination-count distribution (count: slots): `{json.dumps(h["available_destination_count_distribution"])}`.\n\n'
 text+='## May-04 18:00 and reference queue changes\n\n'
 text+=table(['AIDC','Before spare']+list(sorted(cs)),[[s,0]+[cs[k]['materialized_headroom']['May04_1800']['available_GPU'][i] for k in sorted(cs)] for i,s in enumerate(SITES)])
 text+='\nOld May-04 critical-slot demand is624; offered demand is308. Extra capacity permits earlier completion. Critical-slot headroom is useful but does not negate monthly bursts.\n\n'
 keys=['reference_jobs_no_longer_delayed','start_change_jobs','newly_admitted_former_UNASSIGNED','queue_reduction_job_hours','queue_reduction_GPU_hours','same_day_completions_old','same_day_completions_new','D24_running_old','D24_running_new','old_carryout_GPU_hours','new_carryout_GPU_hours']
 text+=table(['Metric']+list(sorted(cs)),[[f]+[fmt(cs[k]['B0_rematerialization']['aggregate'].get(f,0)) for k in sorted(cs)] for f in keys])
 text+='\nFull per-job evidence is compressed in A_B0_RESOURCE_REMATERIALIZATION_JOB_CHANGES.csv.gz and B_B0_RESOURCE_REMATERIALIZATION_JOB_CHANGES.csv.gz. The combined NPZ identifies A75/A80/A85/B75/B80/B85 explicitly. Independent days do not propagate synthetic carry to the next day.\n\n'
 text+='## Allocation recommendation and capacity HOLD\n\nRecommend **B as the generalized relative-capacity allocation rule**. At75%, total-share L1 distortion from V22SR1 falls from0.511796 (A) to0.094902 (B), while the32-GPU minimum remains. B also leaves slightly fewer unstarted jobs at each total. This does not mean B dominates: at75%, A has lower simultaneous saturation and more32-GPU destination availability. B is selected for physical relative-scale fidelity with an explicit service floor, not for favorable policy or realized-site outcomes.\n\n'
 text+='**No tested total/vector is recommended for application.** Even B75, the largest and least-backlogged B comparison, leaves702 pending observations and515,712 offered GPU-hours without a Day-D start. Its offered saturation remains24.160% of slots. B80 leaves762; B85 leaves836. The mean-size/peak-service tradeoff must be resolved before a new installed authority is frozen. No untested larger capacity or changed terminal/WAN contract is silently substituted.\n\n'
 text+='## Power, electrical coefficients, H4 and WAN dependencies\n\nPower CASE2: installed capacity contributes104.1606964512843 W idle/GPU; active swing547.7239090195797 W/GPU. Both A/B totals add idle IT power of240.820/221.654/204.988 kW for75/80/85%. Site allocation changes its geographic distribution. GPU-to-PCC tables use the unchanged C1/weather model and PF0.95; no extra historical PUE1.30 multiplication. No physical rack census is available; four nonadditive logical pools/site stay, but their capacity envelopes must be refrozen.\n\n'
 text+='GPU/rack authority,624-specific aggregate power bounds/conservation, all31-day power tables, H4 physical/actionable capacity fields, B0 materialization and descendant manifests require propagation. Current dedicated PCC ratings are500 kVA/phase and208.179184 A/phase; shared feeder constraints still apply.\n\n'
 text+='Electrical class **A conditional exact numerical equivalence**: existing AC coefficients use an immutable exogenous anchor, not rematerialized B0 or GPU count. No numerical regeneration is required if that anchor and all generation inputs stay identical; capacity-dependent power tables are built afterward. Context provenance/reuse must be recertified. If the anchor is recentered, **full31-day regeneration** is required. No coefficients were regenerated and no expanded-load Fresh safety is claimed here. See GPU_CAPACITY_DEPENDENCY_GRAPH.md and dependency JSONs.\n\n'
 text+='GPU headroom cannot repair UID-serialized WAN waits or D24 service-shift semantics. The resource study already exhibits material backlog with migration/WAN optimization absent. That contract audit remains separate.\n\n'
 text+='## Validation, provenance and scope\n\n31/31 current B0 tables reproduced exactly with the unmodified baseline. Offered total reconciles exactly to known-site plus UNASSIGNED components and independently counted job-interval GPU-hours. All six candidate interval sweeps conserve resources and satisfy gang/rack limits. Critical May04 and heavy May21 repeat exactly for each vector. Source/forecast causality and Q90 duration identities are checked. PR_PACKAGE_VERIFICATION.json provides a portable read-only check of saved results; raw-authority replay still requires the external frozen source/forecast files referenced by manifests.\n\nThe initial A-only audit is superseded by this six-candidate report. The pre-existing Git worktree was separately committed as a6ba216 after audit interruption; source/evidence byte preservation is verified separately from this expected Git metadata change. No claim of unchanged Git HEAD across that external PR work is made.\n'
 (OUT/'V41R2_AIDC_GPU_CAPACITY_SIZING_REPORT.md').write_text(text,encoding='utf-8')
 with np.load(OUT/'A_B0_RESOURCE_REMATERIALIZATION_STUDY.npz') as aa,np.load(OUT/'B_B0_RESOURCE_REMATERIALIZATION_STUDY.npz') as bb:
  payload={'A'+k:aa[k] for k in aa.files};payload.update({k:bb[k] for k in bb.files});np.savez_compressed(OUT/'B0_RESOURCE_REMATERIALIZATION_STUDY.npz',**payload)
 for name in ('UNASSIGNED_AND_DDAY_COHORT_CLASSIFICATION.csv','OFFERED_JOB_REFERENCE_AUDIT.csv'):gzip_file(OUT/name,OUT/(name+'.gz'))

def preservation():
 before=read(OUT/'PROTECTED_BEFORE.json');changed=[];missing=[];count=0
 for r in before['files']:
  p=Path(r['path'])
  if not p.exists():missing.append(r['path']);continue
  if p.stat().st_size!=r['bytes'] or sha(p)!=r['sha256']:changed.append(r['path'])
  count+=1
  if count%1000==0:print('PRESERVATION',count,flush=True)
 result=dict(status='PASS' if not changed and not missing else 'FAIL',files_checked=count,changed=changed,missing=missing,
   prior_git_HEAD=before['git_HEAD'],current_git_HEAD=git('rev-parse','HEAD'),
   git_metadata_note='External PR35 committed already-existing V41R1 changes as a6ba216 between turns; byte preservation is checked independently.',
   production_mutations_by_this_audit=0)
 write('PROTECTED_AFTER_AUDIT.json',result);print('PRESERVATION_DONE',result,flush=True)

if __name__=='__main__':assemble();preservation()
