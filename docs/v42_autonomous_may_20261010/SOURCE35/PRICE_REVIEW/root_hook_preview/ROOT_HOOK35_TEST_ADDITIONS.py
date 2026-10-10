"""Proposed tests to append to tests/test_v42_autonomous_b2.py.

These use that module's proof_request, Path, and pytest imports. Run only in
the protected-preload / real-Model-denied selected suite after porting. The
fake factory tests worker routing and lifetime; it supplies no scientific
admission or certificate evidence.
"""


def _hook35_frozen_proof_request(tmp_path, worker):
    from v42_b2_seed_recovery_v19.common import atomic
    request = proof_request(tmp_path)
    folder = tmp_path / 'inputs'
    folder.mkdir()
    for name in ('B2_FIXED_AIDC.json', 'PLANNING_PHYSICAL.npz', 'LINKED.json'):
        (folder / name).write_text('{}', encoding='utf8')
    linked = worker.record(folder / 'LINKED.json')
    atomic(folder / 'NATIVE_INPUT.json', dict(route_table=linked, electrical_certificate=linked))
    manifest_path = tmp_path / 'MANIFEST.json'
    manifest_path.write_text('{}', encoding='utf8')
    request.update(input_folder=str(folder), manifest=str(manifest_path), run_id='hook35_only')
    return request, dict(execution_SHA='test_lazy35_only')


@pytest.mark.parametrize('failure', (None, 'factory', 'delegate'))
def test_current_f1_price_hook_is_lazy_once_and_restores_all_aliases(tmp_path, monkeypatch, failure):
    import gurobipy as gp
    from v42_autonomous_b2 import worker, f1_price_seed, f1_basis, f1_state
    from v42_autonomous_b2 import pricing_cache, rmp_presolve, dw_native
    from v42_may_campaign_native90 import m_stage
    from v42_m1_anytime import algorithms
    from v42_m1_hybrid import pricing, dw
    from v42_b2_seed_recovery_v19 import initialization

    # All protected modules above must freeze originals before constructor and
    # Native descriptors are replaced. The outer selected-suite harness also
    # denies these entry points; retaining its denied class here remains safe.
    attempts = []
    retained_model = rmp_presolve._RAW_MODEL_TYPE
    class NativeModelDenied(AssertionError):
        pass
    def denied(*args, **kwargs):
        attempts.append((len(args), sorted(kwargs)))
        raise NativeModelDenied('REAL_NATIVE_MODEL_FORBIDDEN')
    monkeypatch.setattr(retained_model, '__init__', denied)
    monkeypatch.setattr(retained_model, 'optimize', denied)
    monkeypatch.setattr(gp, 'Model', denied)

    request, manifest = _hook35_frozen_proof_request(tmp_path, worker)
    inputs = {str(p): worker.record(p) for p in Path(request['input_folder']).rglob('*') if p.is_file()}
    before = (initialization.validated_start, m_stage._fresh_lp_dual,
              pricing.run_pricing, dw.run, algorithms.lp_round)
    events = []
    sentinels = (object(), object(), object())
    context = {'unchanged': object()}
    case, decomp, dual, budget, frontier = (object() for _ in range(5))

    class FakeCurrentF1Scope:
        def __init__(self, actual_request, code_root):
            assert actual_request is request and code_root == worker.ROOT
            events.append(('scope', self))
        def capture(self, original, actual_case, actual_budget, progress=None):
            assert original is before[0] and actual_case is case and actual_budget is budget
            events.append(('capture', progress))
            return 'captured'
        def full_lp_adapter(self, original, actual_case, actual_budget, progress=None):
            assert original is before[1] and actual_case is case and actual_budget is budget
            events.append(('full_lp', progress))
            return 'full_lp_receipt'

    def forbidden_cache_or_master(*args, **kwargs):
        pytest.fail('PRICE_HOOK_MUST_NOT_EAGERLY_CREATE_CACHE_OR_RMP')

    def factory(original, actual_request, code_root, getter, owned_output, writer):
        assert original is before[4] and actual_request is request and code_root == worker.ROOT
        # The price adapter must capture the installed routing aliases, not an
        # alias from before the worker's pricing and proof-write scopes.
        assert pricing.run_pricing is not before[2]
        assert pricing.run_pricing.original_pricing is before[2]
        assert algorithms.lp_round.original_lp_round is original
        assert writer is algorithms.write
        events.append(('factory', getter, owned_output, writer))
        if failure == 'factory':
            raise RuntimeError('hook35 factory failure')
        def routed(actual_case, actual_decomp, actual_dual, actual_budget,
                   actual_frontier, actual_path, method, kind, *, context=None):
            assert (actual_case is case and actual_decomp is decomp and actual_dual is dual
                    and actual_budget is budget and actual_frontier is frontier)
            scope = getter()
            assert scope is [event[1] for event in events if event[0] == 'scope'][0]
            events.append(('round', scope, actual_path, method, kind, context))
            if failure == 'delegate':
                raise RuntimeError('hook35 delegate failure')
            return sentinels
        return routed

    monkeypatch.setattr(f1_basis, 'Scope', FakeCurrentF1Scope)
    monkeypatch.setattr(f1_price_seed, 'scoped_lp_round', factory)
    monkeypatch.setattr(pricing_cache, 'create_scope', forbidden_cache_or_master)
    monkeypatch.setattr(rmp_presolve, 'scoped_runner', forbidden_cache_or_master)

    def body():
        with worker.proof_scope(request, manifest) as routes:
            assert events == []
            assert algorithms.lp_round.original_lp_round is before[4]
            path = routes['output'] / 'L1_PRICING'
            assert algorithms.lp_round(case, decomp, dual, budget, frontier, path,
                                       'L1', context=context) is sentinels
            assert len([e for e in events if e[0] == 'factory']) == 1
            assert len([e for e in events if e[0] == 'scope']) == 1
            # Initialization and FULL LP must address the same current slot
            # that the already-created lazy price wrapper consults.
            assert initialization.validated_start(case, budget, progress='same_slot') == 'captured'
            assert m_stage._fresh_lp_dual(case, budget, progress='same_slot') == 'full_lp_receipt'
            assert algorithms.lp_round(case, decomp, dual, budget, frontier,
                                       routes['output'] / 'L4_PRICING', 'L4',
                                       'MILP_AND_LP', context=context) is sentinels
    if failure is None:
        body()
        rounds = [e for e in events if e[0] == 'round']
        assert len(rounds) == 2 and all(e[5] is context for e in rounds)
        assert [(e[3], e[4]) for e in rounds] == [('L1', 'LP_ONLY'), ('L4', 'MILP_AND_LP')]
        assert len([e for e in events if e[0] == 'scope']) == 1
    else:
        with pytest.raises(RuntimeError, match='hook35 ' + failure + ' failure'):
            body()
    assert len([e for e in events if e[0] == 'factory']) == 1
    assert (initialization.validated_start, m_stage._fresh_lp_dual,
            pricing.run_pricing, dw.run, algorithms.lp_round) == before
    assert all(worker.record(path) == rec for path, rec in inputs.items())
    assert attempts == []


def test_current_f1_price_hook_no_scheduled_round_creates_no_factory_or_scope(tmp_path, monkeypatch):
    from v42_autonomous_b2 import worker, f1_price_seed, f1_basis, pricing_cache, rmp_presolve
    from v42_m1_anytime import algorithms
    from v42_m1_hybrid import pricing
    request, manifest = _hook35_frozen_proof_request(tmp_path, worker)
    before = (algorithms.lp_round, pricing.run_pricing)
    def forbidden(*args, **kwargs):
        pytest.fail('NO_SCHEDULED_ROUND_MUST_CREATE_NO_SCIENTIFIC_POLICY')
    monkeypatch.setattr(f1_price_seed, 'scoped_lp_round', forbidden)
    monkeypatch.setattr(f1_basis, 'Scope', forbidden)
    monkeypatch.setattr(pricing_cache, 'create_scope', forbidden)
    monkeypatch.setattr(rmp_presolve, 'scoped_runner', forbidden)
    with worker.proof_scope(request, manifest):
        assert algorithms.lp_round is not before[0]
        assert algorithms.lp_round.original_lp_round is before[0]
        assert pricing.run_pricing.original_pricing is before[1]
    assert (algorithms.lp_round, pricing.run_pricing) == before
