"""Windows native-loader bootstrap; unchanged tests, no production solve.

Load the OpenDSS DLL before mixed native numerical libraries initialize. The
first plain pytest attempt is preserved; this runner neither skips tests nor
changes any model, tolerance, authority or global machine setting.
"""
from .common import *
import sys
import opendssdirect  # import only; no circuit compile or Solve here
import pytest

if __name__=='__main__':
    raise SystemExit(pytest.main(sys.argv[1:] or ['-q']))
