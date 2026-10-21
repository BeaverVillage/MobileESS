"""Independent saved-evidence verification for physical S0/S1 hardware."""
import csv,json,unittest
from pathlib import Path
import numpy as np
from .audit import read,sha
from .correction import OUT,RUNTIME,priority
from .correction_svr import SV,RUN

class SVRChecks(unittest.TestCase):
    def test_pre_svr_seal_and_fixed_candidates(self):
        seal=read(SV/'S0_DIAGNOSIS_SEAL.json')
        for p,h in seal['files'].items():self.assertEqual(sha(Path(p).read_bytes()),h)
        self.assertEqual(seal['SVR_operating_solves_before_seal'],0)
        reg=read(SV/'SVR_CANDIDATE_PREREGISTRATION.json')
        self.assertEqual(reg['betas'],[1.,1.5,2.,2.05,2.1])
        allunits=reg['contracts']['S1_12']['units']
        for n in (3,6,12):self.assertEqual(reg['contracts'][f'S1_{n:02d}']['units'],allunits[:n])

    def test_series_snapshot_impedance_path_and_reindexed_currents(self):
        cert=read(SV/'INDEPENDENT_S1_12_MODEL_CERTIFICATION.json');p=Path(cert['snapshot']['path'])
        self.assertEqual(sha(p.read_bytes()),cert['snapshot']['sha256']);raw=read(p)
        self.assertEqual(raw['before_line_properties'],raw['after_line_properties'])
        self.assertEqual(len(raw['before_line_properties']),3703)
        cuts={u['cut_element'].split('.',1)[1]:u for u in raw['contract']['units']}
        self.assertEqual(len(cuts),12)
        for name,old in raw['original_bus_connections'].items():
            expected=old.copy()
            if name in cuts:expected[0]=cuts[name]['upstream_new_bus']+'.1.2.3'
            self.assertEqual(raw['installed_bus_connections'][name],expected)
        tx=raw['installation']['added_transformer_static'];self.assertEqual(len(tx),36)
        live={r['element'].lower():r for r in raw['transformer_inventory']}
        for u in raw['contract']['units']:
            for ph in (1,2,3):
                name='svr_'+u['id'].lower()+'_p'+str(ph);row=tx[name]
                wiring=live['transformer.'+name]
                self.assertEqual(wiring['nphase'],1)
                self.assertEqual(wiring['buses'],[u['original_bus_spec'].split('.')[0]+'.'+str(ph)+'.0',u['upstream_new_bus']+'.'+str(ph)+'.0'])
                self.assertEqual(float(row['properties']['XHL']),1.)
                self.assertEqual(float(row['properties']['%NoLoadLoss']),.05)
                for w in row['windings']:
                    self.assertAlmostEqual(w['kva'],u['phase_kva'],delta=1e-8)
                    self.assertAlmostEqual(w['kv'],u['nominal_kv_ln'],delta=1e-8)
        self.assertLess(cert['new_PDE_reindex_scalar_vs_bulk_max_abs_error'],1e-12)
        self.assertEqual(len(raw['PV_roster']),2354)

    def test_all_event_tap_readbacks_and_frozen_original_controls(self):
        base={r['regcontrol']:r for r in read(SV/'EXISTING_REGULATOR_FULL_STATIC_AUDIT.json')['initial_readbacks']}
        dynamic={'TapNum','Reset'};cases=0
        for p in sorted(RUN.glob('*/TAP_QUEUE_EVENT_READBACK.json')):
            if not (p.parent/'RECEIPT.json').exists():continue
            raw=read(p);rec=read(p.parent/'RECEIPT.json');config=rec['scientific_inputs']['schedule']['name']
            expected=12+(0 if config=='S0' else int(config.split('_')[1])*3)
            self.assertEqual(len(raw['initial']),expected)
            for event in raw['events']:
                for r in event['controls']:
                    self.assertEqual(r['winding'],2);self.assertEqual(r['tap_winding'],2)
                    step=(r['max_tap']-r['min_tap'])/r['num_taps']
                    self.assertAlmostEqual((r['tap']-1)/step,r['tap_number'],delta=1e-7)
                    self.assertGreaterEqual(r['tap'],r['min_tap']-1e-9);self.assertLessEqual(r['tap'],r['max_tap']+1e-9)
                    if r['regcontrol'] in base:
                        a={k:v for k,v in r['properties'].items() if k not in dynamic}
                        b={k:v for k,v in base[r['regcontrol']]['properties'].items() if k not in dynamic}
                        self.assertEqual(a,b)
                    else:
                        self.assertEqual(float(r['properties']['VReg']),120.)
                        self.assertEqual(float(r['properties']['Delay']),30.)
                    self.assertTrue(all(q['absolute_seconds']>event['physical_seconds'] for q in event['queue']))
            cases+=1
        self.assertEqual(cases,40)

    def test_s0_instrumentation_does_not_change_physics(self):
        for beta in (1.,1.5,2.,2.05,2.1):
            old=RUNTIME/'correction_time100'/f'TIME_{beta:.2f}_ACTUAL_B0'
            new=RUN/f'TIME_{beta:.2f}_ACTUAL_S0'
            with np.load(old/'AC_FULL.npz') as a,np.load(new/'AC_FULL.npz') as b:
                for key in a.files:self.assertTrue(np.array_equal(a[key],b[key]),(beta,key))
            self.assertEqual(read(old/'STATES.json'),read(new/'STATES.json'))
            self.assertEqual(read(old/'EVENTS.json'),read(new/'EVENTS.json'))

    def test_independent_fresh_all_arrays_and_raw_sha(self):
        pairs=0
        for p in RUN.glob('*/RECEIPT.json'):
            r=read(p)
            for name,h in r['files'].items():self.assertEqual(sha((p.parent/name).read_bytes()),h)
            if p.parent.name.endswith('_FRESH'):continue
            peer=p.parent.with_name(p.parent.name+'_FRESH')
            with np.load(p.parent/'AC_FULL.npz') as a,np.load(peer/'AC_FULL.npz') as b:
                for key in a.files:self.assertTrue(np.array_equal(a[key],b[key]),(p,key))
            self.assertEqual(read(p.parent/'STATES.json'),read(peer/'STATES.json'));pairs+=1
        self.assertEqual(pairs,20)

    def test_settled_and_event_safety_not_conflated(self):
        with (SV/'S0_S1_ACTUAL_TIME_RESULTS.csv').open(encoding='utf-8') as f:rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),40)
        for row in rows:
            p=Path(row['receipt']).parent
            with np.load(p/'AC_FULL.npz') as z:rho=z['line_rho'];v=z['node_voltage_pu'];s=z['event_slot']
            axes=read(p/'AXES.json');parents={r['element']:r['parent_terminal'] for r in axes['orientation']}
            cols=[j for j,r in enumerate(axes['line']) if r['enabled'] and r['node']>0 and r['terminal']==parents[r['element']]]
            last={}
            for j,t in enumerate(s):last[int(t)]=j
            selected=[last[t] for t in range(24,120)]
            self.assertAlmostEqual(float(rho[selected][:,cols].max()),float(row['rho_objective']),delta=1e-12)
            self.assertAlmostEqual(float(v[selected].min()),float(row['Vmin']),delta=1e-12)
            self.assertAlmostEqual(float(v[s>=24].max()),float(row['evaluation_all_event_Vmax']),delta=1e-12)

if __name__=='__main__':
    priority();result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SVRChecks))
    (SV/'INDEPENDENT_SVR_TESTS.json').write_text(json.dumps(dict(tests=result.testsRun,PASS=result.wasSuccessful(),failures=[str(x) for x in result.failures],errors=[str(x) for x in result.errors]),indent=2),encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())
