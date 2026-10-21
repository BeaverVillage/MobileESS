"""Independent arithmetic checks: do not import the producing mask or reducers."""
import csv,json
from pathlib import Path
import unittest
import numpy as np
from .audit import ROOT,DOC,read,sha
from .correction import OUT,RUNTIME

class CorrectionChecks(unittest.TestCase):
    def test_current_canonical_api_against_live_terminal_readbacks(self):
        from .correction_time100 import install
        from .correction_current import CanonicalTimePhysical
        install();e=CanonicalTimePhysical('PUBLIC_SETTLED_API','ACTUAL');e.apply('ACTUAL',0,2.)
        row,arrays,state,ports=e.measure('ACTUAL',0,2.);values=[]
        for meta in e.inventory['lines']:
            if not meta['enabled']:continue
            e.d.Circuit.SetActiveElement(meta['element']);current=e.d.CktElement.CurrentsMagAng();nodes=e.d.CktElement.NodeOrder()
            start=(meta['parent_terminal']-1)*meta['ncond']
            for j in range(start,start+meta['ncond']):
                if nodes[j]>0:values.append(current[2*j]/e.d.CktElement.NormalAmps())
        self.assertAlmostEqual(max(values),row['rho_global'],delta=1e-12)
        self.assertNotAlmostEqual(row['rho_global'],row['event_envelope_rho'],delta=1e-9)
        self.assertEqual(e.d.Solution.Hour()*3600+e.d.Solution.Seconds(),900)
        self.assertEqual(state,e.control_state());self.assertEqual(len(ports),12)

    def test_solve_vs_original_solve_snap_event_loop(self):
        from .correction_time100 import install
        from .correction import CorrectedPhysical
        install()
        a=CorrectedPhysical('SOLVE_BODY_A','PLANNING');b=CorrectedPhysical('SOLVE_BODY_B','PLANNING')
        differences=[]
        for t in range(3):
            a.apply('PLANNING',t,1.);b.apply('PLANNING',t,1.)
            a.measure('PLANNING',t,1.)
            snapshots=[]
            def observe(event):snapshots.append(b.measurement_arrays())
            rb=b.clock.settle_slot(b.d,t,observer=observe)  # Original default SolveSnap.
            self.assertEqual(len(snapshots),len(a.event_arrays))
            for x,y in zip(a.event_arrays,snapshots):
                for key in ('line_rho','node_voltage_pu','transformer_current_rho','transformer_winding_nameplate_kva_rho'):
                    diff=float(np.max(abs(x[key]-y[key])));differences.append(diff);self.assertLess(diff,1e-12)
            self.assertEqual(a.control_state(),b.control_state())
            self.assertEqual([r['absolute_seconds'] for r in a.last_events['events']],
                [r['absolute_seconds'] for r in rb['events']])
        (OUT/'SOLVE_SNAPSHOT_BODY_EQUIVALENCE.json').write_text(json.dumps(dict(PASS=True,
            slots=3,mode=0,control_mode=2,max_absolute_array_difference=max(differences),
            contract='Callback Solve() in snapshot mode compared with unmodified CommonClock default SolveSnap; all queued instants/control states equal'),indent=2),encoding='utf-8')

    def test_direct_scalar_current_authority(self):
        from .physical import Physical
        e=Physical('CORRECTION_DIRECT_CURRENT_CONTRACT');e.apply('PLANNING',0,1.)
        e.d.Solution.Solve();a=e.measurement_arrays()['line_rho'];error=0.;index=0;cells=0
        for meta in e.inventory['lines']:
            e.d.Circuit.SetActiveElement(meta['element'])
            if meta['enabled']:
                nodes=e.d.CktElement.NodeOrder();curr=e.d.CktElement.CurrentsMagAng()
                for i,node in enumerate(nodes):
                    if node>0:
                        expected=curr[2*i]/e.d.CktElement.NormalAmps();error=max(error,abs(expected-a[index+i]));cells+=1
            else:self.assertEqual(float(np.max(abs(a[index:index+len(meta['node_order'])]))),0)
            index+=len(meta['node_order'])
        e.d.Vsources.Name('source');root=e.d.CktElement.BusNames()
        self.assertEqual(root[0].split('.')[0].lower(),'sourcebus');self.assertLess(error,1e-12)
        (OUT/'DIRECT_TERMINAL_CURRENT_AUTHORITY_CHECK.json').write_text(json.dumps(dict(PASS=True,
            source_buses=root,source_pu=e.d.Vsources.PU(),active_real_terminal_cells=cells,
            max_abs_scalar_vs_bulk_rho_error=error,disabled_currents_zero=True,
            validation_operating_solves=1,saved_array_recalculation_solves=0),indent=2),encoding='utf-8')

    def test_previous_evidence_unchanged(self):
        baseline=read(OUT/'PRESERVATION_BASELINE.json')
        for p,h in baseline['tracked_sha256'].items():self.assertEqual(sha((ROOT/p).read_bytes()),h,p)
        for p,h in baseline['runtime_sha256'].items():self.assertEqual(sha(Path(p).read_bytes()),h,p)

    def test_original_algorithm_byte_unchanged(self):
        import subprocess
        names=subprocess.check_output(['git','diff','--name-only',read(OUT/'PRESERVATION_BASELINE.json')['PR236_HEAD']],cwd=ROOT,text=True).splitlines()
        self.assertTrue(all(p.startswith(('docs/v2_add/correction/','v2_add_preflight/correction')) for p in names),names)

    def test_policy_reclassification(self):
        with (OUT/'AIDC_WINDOW_POLICY_414_REAUDIT.csv').open(encoding='utf-8') as f:a=list(csv.DictReader(f))
        with (OUT/'AIDC_QOS_BUDGET_192_REAUDIT.csv').open(encoding='utf-8') as f:b=list(csv.DictReader(f))
        self.assertEqual(len(a),414);self.assertEqual(len({r['job_uid'] for r in a}),414)
        self.assertEqual(len(b),192);self.assertTrue(all(r['origin_unknown']=='False' for r in b))
        self.assertTrue(all(r['source_customer_QoS_certified']=='False' for r in a+b))
        self.assertTrue(all(r['actual_known_relaxed_window_permitted']=='True' for r in b))
        self.assertFalse(read(OUT/'AIDC_REAL_FEASIBILITY.json')['customer_Source_QoS_certified'])

    def test_control_properties(self):
        v=read(OUT/'CONTROL_PROPERTY_AUDIT.json')
        self.assertEqual(len(v['differences']),12)
        self.assertTrue(all(r[0]=='regcontrols' and r[2]=='VReg' and float(r[4])==123.5 for r in v['differences']))
        for r in v['P5'][:12]:
            self.assertEqual(r['properties']['Delay'],'15');self.assertEqual(r['properties']['TapDelay'],'2')

    def test_saved_canonical_independent(self):
        parents={r['element']:r['parent_terminal'] for r in read(OUT/'INDEPENDENT_PARENT_ORIENTATION.json')}
        with (OUT/'RECALCULATED_B0_AND_PILOT.csv').open(encoding='utf-8') as f:results={r['case']:r for r in csv.DictReader(f)}
        with (OUT/'RECALCULATED_CANONICAL_TOP20.csv').open(encoding='utf-8') as f:
            ranked={}
            for r in csv.DictReader(f):ranked.setdefault(r['case'],[]).append(r)
        baseaxis=read(RUNTIME/'phase2/B0_beta1.50_ACTUAL/AXES.json')['line']
        original_lines={r['name']:r for r in read(DOC/'OFFICIAL_BALANCED_AXES.json')['lines']}
        for rec in read(DOC/'B0_AC_ARCHIVE_RECEIPTS.json')+read(DOC/'CONTROL_PILOT_ARCHIVE_RECEIPTS.json'):
            p=Path(rec['archive_path']).parent;axes=read(p/'AXES.json')['line'] if (p/'AXES.json').exists() else baseaxis
            a=np.load(p/'AC_FULL.npz')['line_rho'];offset=24 if rec['role']=='ACTUAL' else 0
            for r in axes:
                source=original_lines[r['element'].split('.',1)[1]]
                self.assertEqual(r['normal_amps'],source['normal_amps'])
                self.assertEqual(r['group']=='Primary',source['kv_ln']>1)
            # Separate Python scalar reduction, no numpy producer masks.
            line_max=[];mv=[];lv=[];perline={}
            for j,r in enumerate(axes):
                if not (r['enabled'] and r['node']>0 and r['terminal']==parents[r['element']]):continue
                peak=max(map(float,a[offset:,j]));line_max.append(peak)
                perline[r['element']]=max(perline.get(r['element'],-1),peak)
                (mv if r['group']=='Primary' else lv).append(peak)
            row=results[rec['case']]
            self.assertAlmostEqual(max(line_max),float(row['rho_max']),delta=1e-12)
            self.assertAlmostEqual(max(mv),float(row['rho_MV']),delta=1e-12)
            self.assertAlmostEqual(max(lv),float(row['rho_LV']),delta=1e-12)
            expected=sorted(perline,key=lambda n:(-perline[n],n))[:20]
            self.assertEqual(expected,[r['line'] for r in ranked[rec['case']]])
            self.assertTrue(any(not r['enabled'] for r in axes))
            self.assertTrue(any(r['group']=='Triplex' and r['node'] in (1,2) for r in axes))
            self.assertTrue(all('UNKNOWN' not in r['physical_phase'] for r in axes if r['group']=='Triplex' and r['node']>0))

    def test_time_event_arrays_and_prefix(self):
        roots=[RUNTIME/'correction_time100',RUNTIME/'correction_old_pilot_time100',RUNTIME/'correction_charge_spread_time100']
        count=0
        for root in roots:
            for receipt in sorted(root.glob('*/RECEIPT.json')):
                p=receipt.parent;r=read(receipt)
                with np.load(p/'AC_FULL.npz') as z:a={k:z[k] for k in z.files}
                axes=read(p/'AXES.json')['line']
                orientation={v['element']:v['parent_terminal'] for v in read(p/'AXES.json')['orientation']}
                ids=[j for j,v in enumerate(axes) if v['node']>0 and v['enabled'] and v['terminal']==orientation[v['element']]]
                security=[j for j,v in enumerate(axes) if v['node']>0]
                rows=read(p/'ROWS.json');events=read(p/'EVENTS.json');er=read(p/'EVENT_ROWS.json')
                self.assertEqual(len(er),len(a['event_slot']))
                self.assertEqual(len(rows),120 if r['scientific_inputs']['role']=='ACTUAL' else 96)
                for t,row in enumerate(rows):
                    select=np.where(a['event_slot']==t)[0];currents=a['line_rho'][select]
                    self.assertAlmostEqual(float(currents[:,ids].max()),row['rho_global'],delta=1e-12)
                    self.assertAlmostEqual(float(currents[:,security].max()),row['rho_all_terminals'],delta=1e-12)
                    self.assertAlmostEqual(float(a['node_voltage_pu'][select].min()),row['Vmin'],delta=1e-12)
                    self.assertAlmostEqual(float(a['node_voltage_pu'][select].max()),row['Vmax'],delta=1e-12)
                    event=events[t];self.assertEqual(event['start_seconds'],t*900);self.assertEqual(event['end_seconds'],(t+1)*900)
                    for e in event['events']:
                        self.assertGreaterEqual(e['absolute_seconds'],t*900);self.assertLess(e['absolute_seconds'],(t+1)*900)
                        self.assertTrue(all(q['absolute_seconds']>e['absolute_seconds'] for q in e['pending_queue']))
                    self.assertTrue(all(q['absolute_seconds']>=(t+1)*900 for q in event['queue_carried_to_next_slot']))
                for file,h in r['files'].items():self.assertEqual(sha((p/file).read_bytes()),h)
                count+=1
        self.assertEqual(count,140)

    def test_final_slot_measurement_is_not_event_envelope(self):
        with (OUT/'canonical/ALL_TIME_CASES_CANONICAL_RESULTS.csv').open(encoding='utf-8') as f:results=list(csv.DictReader(f))
        self.assertEqual(len(results),140)
        different=0
        for row in results:
            p=Path(row['receipt']).parent
            with np.load(p/'AC_FULL.npz') as z:currents=z['line_rho'];eventslots=z['event_slot']
            axes=read(p/'AXES.json');parent={r['element']:r['parent_terminal'] for r in axes['orientation']}
            cols=[j for j,r in enumerate(axes['line']) if r['enabled'] and r['node']>0 and r['terminal']==parent[r['element']]]
            # Independent ordered overwrite, rather than producer selector.
            last={}
            for j,t in enumerate(eventslots):last[int(t)]=j
            offset=24 if row['role']=='ACTUAL' else 0
            expected=max(float(currents[last[t],cols].max()) for t in range(offset,len(last)))
            self.assertAlmostEqual(expected,float(row['rho_objective']),delta=1e-12)
            different+=abs(expected-float(row['event_envelope_rho']))>1e-9
        self.assertGreater(different,0,'Test must detect the erroneous all-event objective projection')

    def test_temporal_battery_and_routes(self):
        # Independent SOC reconstruction from exported per-unit dispatch.
        p=OUT/'MESS8_TEMPORAL_UNIT_TRAJECTORIES.csv'
        if not p.exists():self.skipTest('Temporal campaign not yet complete')
        with p.open(encoding='utf-8') as f:rows=list(csv.DictReader(f))
        extra=OUT/'MESS8_CHARGE_SPREAD_UNIT_TRAJECTORIES.csv'
        if extra.exists():
            with extra.open(encoding='utf-8') as f:rows.extend(csv.DictReader(f))
        for name in ('PEAK31_DIAGNOSTIC_UNIT_TRAJECTORIES.csv','SVR_PEAK31_DIAGNOSTIC_UNIT_TRAJECTORIES.csv'):
            p=OUT/name
            if p.exists():
                with p.open(encoding='utf-8') as f:rows.extend(csv.DictReader(f))
        groups={}
        for r in rows:groups.setdefault((r['beta_BG'],r['schedule'],r['vehicle']),[]).append(r)
        initial=read(DOC/'MESS8_INITIAL_STATES_AND_PORTS.json')['initial_sites']
        for key,rs in groups.items():
            energy=760.
            for r in sorted(rs,key=lambda r:int(r['slot'])):
                p=float(r['P_demand_kw']);q=float(r['Q_demand_kvar'])
                self.assertEqual(r['STA'],initial[r['vehicle']]);self.assertEqual(float(r['travel_energy_kwh']),0)
                self.assertAlmostEqual(energy,float(r['SOC_start']),delta=1e-8)
                self.assertLessEqual(abs(p),300);self.assertLessEqual(abs(q),250)
                for f in range(16):self.assertLessEqual(np.cos(f*np.pi/8)*p+np.sin(f*np.pi/8)*q,400*np.cos(np.pi/16)+1e-8)
                energy+=.25*(.95*max(p,0)-max(-p,0)/.95)
                self.assertGreaterEqual(energy,440-1e-8);self.assertLessEqual(energy,1080+1e-8)
                self.assertAlmostEqual(energy,float(r['SOC_end']),delta=1e-8)
            self.assertAlmostEqual(energy,760,delta=1e-8)
        self.assertTrue(read(DOC/'MESS8_SOURCE_STAY_ROUTE_AUDIT.json')['PASS'])

if __name__=='__main__':
    from .correction import priority
    priority()
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(CorrectionChecks)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    (OUT/'INDEPENDENT_REGRESSION_TESTS.json').write_text(json.dumps(dict(tests=result.testsRun,
        failures=[str(x) for x in result.failures],errors=[str(x) for x in result.errors],skipped=result.skipped,
        PASS=result.wasSuccessful()),indent=2),encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
