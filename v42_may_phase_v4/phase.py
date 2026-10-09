"""Keep the first Phase I normalization across row promotion and activation."""
from v42_a_stage_phase1.core import elastic_master as original_elastic
from v42_a_stage_compact_rowgen.rowgen import restricted as original_restricted
from v42_may_campaign_native90.a_routing import group

VERSION = 'FROZEN_PHASE_WEIGHTS_V4'


class FrozenWeights:
    def __init__(self, snapshot, global_rows):
        initial = original_elastic(snapshot, global_rows)
        self.rows = initial.global_rows
        self.weights = dict(zip(initial.artificial_rows, initial.weights))
        self.senses = {i: snapshot.senses[i] for i in self.rows}
        self.rhs = {i: snapshot.rhs[i] for i in self.rows}
        self.restricted_snapshot = None
        self.restricted_rows = ()

    def restricted(self, snapshot, included):
        rows = tuple(sorted(set(included)))
        result = original_restricted(snapshot, rows)
        self.restricted_snapshot, self.restricted_rows = result, rows
        return result

    def elastic_master(self, snapshot, global_rows):
        global_rows = tuple(global_rows)
        weights = {}
        for row in global_rows:
            source = self.restricted_rows[row] if snapshot is self.restricted_snapshot else row
            if (source not in self.weights or snapshot.senses[row] != self.senses[source]
                    or snapshot.rhs[row] != self.rhs[source]):
                raise ValueError('FROZEN_PHASE_GLOBAL_ROW_IDENTITY_DRIFT')
            weights[row] = self.weights[source]
        return original_elastic(snapshot, global_rows, weights_by_row=weights)


def routed_group(module, names, **routing):
    namespace = group(module, names, **routing)
    inherited_run = namespace['run']

    def run(native, state, day, certified_zero_point=None):
        frozen = FrozenWeights(state['compact'], state['grows'])
        # These globals belong only to this separately routed call. The legacy
        # module, its code objects and all current Worker imports stay intact.
        namespace.update(elastic_master=frozen.elastic_master, restricted=frozen.restricted)
        return inherited_run(native, state, day, certified_zero_point)

    namespace['run'] = run
    return namespace
