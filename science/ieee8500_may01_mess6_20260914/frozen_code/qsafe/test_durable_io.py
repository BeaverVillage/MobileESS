import json, unittest
from unittest.mock import patch
import durable_io as io

class AtomicRetry(unittest.TestCase):
    def test_sharing_violation_then_success(self):
        target = io.H/'IO_RETRY_TEST.json'
        real = io.os.replace
        calls = []
        def replace(a,b):
            calls.append(1)
            if len(calls) <= 3:
                raise PermissionError('simulated Windows reader lock')
            return real(a,b)
        with patch.object(io.os,'replace',side_effect=replace),patch.object(io.time,'sleep'):
            io.save(target,dict(status='PASS',failures_retried=3))
        self.assertEqual(json.loads(target.read_text())['status'],'PASS')
        self.assertEqual(len(calls),4)
        self.assertEqual(list(io.H.glob('IO_RETRY_TEST.json.*.tmp')),[])

if __name__ == '__main__': unittest.main()
