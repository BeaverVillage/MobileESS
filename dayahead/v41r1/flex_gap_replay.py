"""One diagnostic replay of production's 3% local gap on the coupled set."""
from dayahead.paper_analysis.storage import read,write_json
from dayahead.v41.preflight import record
from .flex_diagnostic import OUT
from .flex_model import Data,ProbeModel


def run():
    d=Data();p=ProbeModel(d)
    try:
        plan=read(OUT/'COUPLED_NEIGHBORHOOD_PLAN.json')
        p.m.reset();p.m.Params.MIPGap=.03
        r=p.solve('PRODUCTION_GAP_REPLAY',plan['groups'],seconds=60,start=p.seed)
        strong=read(OUT/'COUPLED_ESCAPE_TEST.json')
        r.update(production_local_MIPGap=.03,diagnostic_strong_MIPGap=0,
            strong_reference=record(OUT/'COUPLED_ESCAPE_TEST.json'),
            same_opened_groups=r['opened_groups']==strong['opened_groups'],
            production_FO_not_run=True,starting_incumbent='B0',strong_started_from='INDEPENDENTLY_VERIFIED_PAIR_WITNESS')
        write_json(OUT/'PRODUCTION_GAP_REPLAY.json',r)
    finally:p.close();d.close()


if __name__=='__main__':run()
