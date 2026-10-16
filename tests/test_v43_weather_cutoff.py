from datetime import datetime
import pytest
from v43.weather_repair import require_available

def test_gfs_initialization_is_not_release_authority():
    with pytest.raises(ValueError,match='NOT_AVAILABLE_BY_CUTOFF'):
        require_available({'Last-Modified':'Wed, 30 Apr 2025 09:35:44 GMT','ETag':'old'})

def test_earlier_complete_object_is_admissible():
    assert require_available({'Last-Modified':'Wed, 30 Apr 2025 03:42:45 GMT','ETag':'new'})

def test_missing_release_evidence_fails_closed():
    with pytest.raises(ValueError,match='NOT_AVAILABLE_BY_CUTOFF'):
        require_available({'initialization_utc':'2025-04-30T06:00:00Z','ETag':'old'})
