"""User-authorized V42.2 M implementation pins; independent Native0 remains mandatory."""
EXPECTED_SOURCES = {'v42_integration/m_engine.py': {'sha256': '92c74ca95c9907c9ad2ac25b2836956bdbed1c3a9459a12055aaa436e61ee8d6', 'bytes': 38860}, 'v42_integration/m_candidates.py': {'sha256': 'b22dea1711f15ae4018c905d7d192374ee64bb6b16c0ad6c6bafa3ee78e900d4', 'bytes': 33065}}


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
