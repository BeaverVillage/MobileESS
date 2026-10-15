"""Reviewed PR230 M revision; predecessor eleven physical/AIDC pins remain exact."""
EXPECTED_SOURCES = {'v42_integration/m_engine.py': {'sha256': '1e59ad25073e52d373acf0fc0ddb58f55f70fa4d6be527299be7d03ab8584aac', 'bytes': 37942}, 'v42_integration/m_candidates.py': {'sha256': '9f6d01542c2910b744f46cf1f067d6e7394ecddb26b11cc3623512484466d6d8', 'bytes': 31823}}


EXPECTED_PREPARATION_SOURCES = {'v42_supercompact/presolve.py': {'sha256': 'a0cd3c2006da1ea51d8e394c461bb4e06594e30c047e93acd92ddc4286271527', 'bytes': 16071}, 'v42_may_campaign_native90/m_model.py': {'sha256': '0e606376285ad0c0b2039421317d59184cbba410961af522b3ef12f95ced9731', 'bytes': 54135}}

def require_preparation_sources():
    """Pin the exact, independently compared sparse preparation implementation."""
    from pathlib import Path
    from .m_engine import file_record
    root=Path(__file__).resolve().parents[1]
    for name,expected in EXPECTED_PREPARATION_SOURCES.items():
        current=file_record(root/name)
        if {key:current[key] for key in ('sha256','bytes')}!=expected:
            raise ValueError('CURRENT_MESS_EXACT_PREPARATION_SOURCE_DRIFT:'+name)
    return dict(PASS=True,sources=EXPECTED_PREPARATION_SOURCES,
        scope='EXACT_DYADIC_NORMALIZATION_AND_PIVOT_CARDINALITY_NO_EQUATION_CHANGE')
