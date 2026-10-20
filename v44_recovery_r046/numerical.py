"""Same certified fixed-integer continuation, scoped to the diagnosed May12 A2."""
from contextlib import contextmanager
from types import FunctionType
from unittest.mock import patch
from v44_recovery_r044 import numerical as original


def relocated(function):
    # The immutable helper's relative parent imports now resolve to this
    # revision's independently verified May12 checkpoint and ledger.
    ns=dict(function.__globals__,__package__=__package__)
    return FunctionType(function.__code__,ns,function.__name__,function.__defaults__,function.__closure__)


@contextmanager
def scope():
    from v44 import a2
    from v44.frozen.v43_a2 import adapter
    previous=a2.scope;source_tree=adapter.source_tree
    def tree(module,name):
        value=source_tree(module,name)
        return original.adapt_tree(value) if module.__name__=='v42_may_campaign_native90.a_stage' and name=='run' else value
    @contextmanager
    def continued(request,m1):
        with patch.object(adapter,'source_tree',tree),previous(request,m1) as run:
            ns=dict(run.__globals__,_r044_load_state=relocated(original.load_state),
                _r044_priced=relocated(original.priced),_r044_repair=relocated(original.repair))
            yield FunctionType(run.__code__,ns,run.__name__,run.__defaults__,run.__closure__)
    with patch.object(a2,'scope',continued):yield
