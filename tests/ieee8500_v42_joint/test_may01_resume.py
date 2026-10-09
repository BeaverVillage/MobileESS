import tempfile
import json
import numpy as np
import unittest
from pathlib import Path
from unittest.mock import patch
from ieee8500_v42_joint import run_ac
from ieee8500_v42_high.screen import run_day


class May01ScopeTests(unittest.TestCase):
    def test_source_date_rejected_before_read(self):
        with self.assertRaisesRegex(ValueError,'MAY01_ONLY'):
            run_ac.source_input('ACTUAL','2025-05-02')

    def test_resume_date_rejected_before_engine(self):
        with patch.object(run_ac,'run_day') as execute:
            with self.assertRaisesRegex(ValueError,'MAY01_ONLY'):
                run_ac.run_or_reuse('forbidden',.85,day='2025-05-02')
            execute.assert_not_called()

    def test_nested_report_date_rejected_before_engine(self):
        with patch('ieee8500_v42_high.screen.HighEngine') as engine:
            with self.assertRaisesRegex(ValueError,'MAY01_ONLY'):
                run_day('forbidden',.85,day='2025-05-02',report_dir=Path('ieee8500_v42_joint_pcc_reselection/nested'))
            engine.assert_not_called()

    def test_completed_producer_record_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=Path(tmp)/'ieee8500_v42_joint_pcc_reselection'
            proof=report/'ac/existing/RECEIPT.json';proof.parent.mkdir(parents=True);proof.write_text('{}')
            with patch('ieee8500_v42_high.screen.HighEngine') as engine:
                with self.assertRaisesRegex(RuntimeError,'MUST_BE_REUSED'):
                    run_day('existing',.85,report_dir=report)
                engine.assert_not_called()

    def test_existing_wrong_date_is_not_recalculated(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=Path(tmp);proof=report/'ac/existing/RECEIPT.json';proof.parent.mkdir(parents=True)
            proof.write_text(json.dumps(dict(day='2025-05-02',source='PLANNING',bg=.85,layout='M3',slots=96)))
            with patch.object(run_ac,'REPORT',report),patch.object(run_ac,'run_day') as execute:
                with self.assertRaisesRegex(AssertionError,'REUSE_METADATA_MISMATCH'):
                    run_ac.run_or_reuse('existing',.85,layout='M3')
                execute.assert_not_called()

    def test_completed_reuse_preserves_new_solve_accounting(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=Path(tmp);folder=report/'ac/completed';folder.mkdir(parents=True)
            mapping=report/'mapping.csv';mapping.write_text('mapping')
            inputs=report/'input.npz';inputs.write_bytes(b'original input')
            r=dict(tag='completed',day='2025-05-01',source='PLANNING',bg=.85,layout='M3',slots=96,
                AIDC_input={'sha256':run_ac.sha(inputs)},mapping={'sha256':run_ac.sha(mapping)})
            (folder/'RECEIPT.json').write_text(json.dumps(r))
            (folder/'PARAMETER_SNAPSHOT.json').write_text(json.dumps(dict(source_pu=1.04,
                P5_overlay_sha256=run_ac.sha(run_ac.HIGH/'overlays/P5.dss'))))
            (folder/'SLOTS.csv').write_text('slot\n'+'\n'.join(str(t) for t in range(96))+'\n')
            np.savez(folder/'AC_96.npz',node_voltage_pu=np.ones((96,1)))
            for name in ('CUSTOMER_PV_PCC_96.npz','CONTROL_STATES.json','PORT_96.json'):(folder/name).write_text('[]')
            ledger=report/'EXECUTION_REUSE_LEDGER.json'
            ledger.write_text(json.dumps({'completed':dict(status='COMPLETED',new_operating_point_solves=96)}))
            save=lambda path,value:Path(path).write_text(json.dumps(value))
            with patch.object(run_ac,'REPORT',report),patch.object(run_ac,'write',side_effect=save),patch.object(run_ac,'run_day') as execute:
                run_ac.run_or_reuse('completed',.85,layout='M3',input_path=inputs,mapping_path=mapping)
                execute.assert_not_called()
            accounting=json.loads(ledger.read_text())['completed']
            self.assertEqual(accounting['status'],'COMPLETED')
            self.assertEqual(accounting['new_operating_point_solves'],96)
            self.assertEqual(accounting['subsequent_reuse_reads'],1)

if __name__=='__main__':unittest.main()
