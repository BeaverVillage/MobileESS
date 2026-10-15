"""Reviewed PR230 M revision; predecessor eleven physical/AIDC pins remain exact."""
EXPECTED_SOURCES = {'v42_integration/m_engine.py': {'sha256': '9272043b4cc922e46c0f11b29c2829ad40fb24e5290796052593af8d25ea7047', 'bytes': 38144}, 'v42_integration/m_candidates.py': {'sha256': '9f6d01542c2910b744f46cf1f067d6e7394ecddb26b11cc3623512484466d6d8', 'bytes': 31823}}


EXPECTED_PREPARATION_SOURCES = {'v42_supercompact/presolve.py': {'sha256': 'a0cd3c2006da1ea51d8e394c461bb4e06594e30c047e93acd92ddc4286271527', 'bytes': 16071}, 'v42_may_campaign_native90/m_model.py': {'sha256': '8ea4aaeab59506e59953e8f79b56f913c50a42d07c766fef4ece7dc507ec5554', 'bytes': 54073}}

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
