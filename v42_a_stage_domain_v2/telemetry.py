"""Passive later-run instrumentation; no optimize, relax, or method probes."""
from math import isfinite
from time import perf_counter
import re
import threading
import psutil


NATIVE_SETTINGS = ('Method', 'Crossover', 'NumericFocus', 'ScaleFlag',
    'BarHomogeneous', 'Presolve', 'Threads', 'Seed', 'FeasibilityTol',
    'OptimalityTol', 'IntFeasTol')
RANGE_ATTRIBUTES = ('NumVars', 'NumConstrs', 'NumNZs', 'NumBinVars', 'NumIntVars',
    'MaxCoeff', 'MinCoeff', 'MaxBound', 'MinBound', 'MaxRHS', 'MinRHS',
    'MaxObjCoeff', 'MinObjCoeff')
POST_ATTRIBUTES = ('Runtime', 'Work', 'IterCount', 'BarIterCount', 'NodeCount',
    'Kappa', 'ConstrVio', 'BoundVio', 'IntVio', 'DualVio', 'ComplVio')


def native_scalar(obj, name):
    try:
        value = float(getattr(obj, name))
        return value if isfinite(value) and abs(value) < 1e99 else None
    except Exception:
        # Unsupported/unavailable solver attributes remain unavailable.
        return None


class FutureRunTelemetry:
    def __init__(self, model, *, day=None, sample_interval=1., max_samples=1024):
        self.day = day
        self.started = perf_counter()
        self.samples = []
        self.passes = []
        self.max_samples = max_samples
        self.sample_interval = sample_interval
        self.last_sample = -1.
        self.dropped_samples = 0
        self.active = None
        self.before = dict(matrix_geometry={k: native_scalar(model, k) for k in RANGE_ATTRIBUTES},
            solver_settings={k: native_scalar(model.Params, k) for k in NATIVE_SETTINGS})

    def begin_objective(self, name, *, group=None, remaining_seconds=None):
        self.active = dict(objective=name, group=group,
            begin_wall_seconds=perf_counter()-self.started,
            cumulative_native_seconds=sum(p.get('native_seconds') or 0. for p in self.passes),
            available_seconds=remaining_seconds)
        self.objective_started = perf_counter()
        self.last_sample = -1.

    def callback(self, model, where, GRB):
        if self.active is None:
            return
        names = {
            GRB.Callback.SIMPLEX: ('SIMPLEX', ('SPX_ITRCNT', 'SPX_OBJVAL', 'SPX_PRIMINF', 'SPX_DUALINF')),
            GRB.Callback.BARRIER: ('BARRIER', ('BARRIER_ITRCNT', 'BARRIER_PRIMINF', 'BARRIER_DUALINF', 'BARRIER_COMPL')),
            GRB.Callback.MIPNODE: ('MIPNODE', ('MIPNODE_NODCNT', 'MIPNODE_STATUS', 'MIPNODE_OBJBND')),
        }
        if where not in names:
            return
        elapsed = perf_counter()-self.objective_started
        if elapsed-self.last_sample < self.sample_interval:
            return
        label, attributes = names[where]
        row = dict(objective=self.active['objective'], group=self.active['group'],
            callback_kind=label, objective_wall_seconds=elapsed,
            total_wall_seconds=perf_counter()-self.started)
        for name in attributes:
            try:
                value = float(model.cbGet(getattr(GRB.Callback, name)))
                row[name] = value if isfinite(value) and abs(value) < 1e99 else None
            except Exception:
                row[name] = None
        row['root_node_confirmed'] = label == 'MIPNODE' and row.get('MIPNODE_NODCNT') == 0
        self.last_sample = elapsed
        if len(self.samples) < self.max_samples:
            self.samples.append(row)
        else:
            self.dropped_samples += 1

    def finish_objective(self, model):
        row = dict(self.active, wall_seconds=perf_counter()-self.objective_started,
            native_seconds=native_scalar(model, 'Runtime'),
            numerical_quality={k: native_scalar(model, k) for k in POST_ATTRIBUTES})
        self.passes.append(row)
        self.active = None
        return row

    def receipt(self):
        return dict(day=self.day, prepared_for_future_runs=True,
            matrix_geometry=self.before['matrix_geometry'], solver_settings=self.before['solver_settings'],
            objective_stage_timings=self.passes, root_and_solver_observations=self.samples,
            dropped_samples=self.dropped_samples, synthetic_root_duration_claimed=False,
            exact_condition_number_computed=False, solver_methods_changed=False,
            extra_relaxations_or_optimization_calls=0,
            note='Simplex/barrier callback observations do not isolate root LP time; Kappa is null without an available basis. KappaExact is not computed.')


class ResourceObservation:
    """Observe build resources too; never gate, terminate, or change a model."""
    def __init__(self,*,day,objective,phase,interval=.5):
        self.day=day;self.objective=objective;self.phase=phase;self.interval=interval
        self.started=perf_counter();self.resources=[];self.errors=[];self.peak_rss=0
        self.stop=threading.Event();self.thread=None

    def sample(self):
        try:
            rss=psutil.Process().memory_info().rss
            self.peak_rss=max(self.peak_rss,rss)
            self.resources.append(dict(day=self.day,objective=self.objective,phase=self.phase,
                wall_seconds=perf_counter()-self.started,RSS_bytes=rss,
                available_RAM_bytes=psutil.virtual_memory().available,
                peak_RSS_bytes=self.peak_rss,observational_only=True))
        except psutil.Error as error:self.errors.append(str(error))

    def start_resources(self):
        self.sample()
        def observe():
            while not self.stop.wait(self.interval):self.sample()
        self.thread=threading.Thread(target=observe,daemon=True);self.thread.start()

    def stop_resources(self):
        self.stop.set()
        if self.thread is not None:self.thread.join(timeout=2.)
        self.sample()

    def receipt(self):
        return dict(day=self.day,objective=self.objective,phase=self.phase,
            resource_samples=self.resources,observed_peak_RSS_bytes=self.peak_rss,
            sampling_interval_seconds=self.interval,observation_errors=self.errors,
            observational_only=True,peak_is_sampled_not_exact=True)


class StressTelemetry(FutureRunTelemetry):
    """Observational telemetry for a single authorized native objective pass."""
    def __init__(self,model,*,day,objective,group=None,remaining_seconds=None,resource_interval=.5):
        super().__init__(model,day=day,sample_interval=1.,max_samples=10000)
        self.begin_objective(objective,group=group,remaining_seconds=remaining_seconds)
        self.messages=[];self.history=[];self.resources=[];self.events={}
        self.callback_errors=[];self.resource_interval=resource_interval
        self.stop=threading.Event();self.thread=None;self.peak_rss=0

    def start_resources(self):
        process=psutil.Process()
        def observe():
            while not self.stop.is_set():
                try:
                    rss=process.memory_info().rss;available=psutil.virtual_memory().available
                    self.peak_rss=max(self.peak_rss,rss)
                    self.resources.append(dict(day=self.day,objective=self.active['objective'] if self.active else None,
                        phase='NATIVE_OPTIMIZE',wall_seconds=perf_counter()-self.started,RSS_bytes=rss,available_RAM_bytes=available,
                        peak_RSS_bytes=self.peak_rss,observational_only=True))
                except psutil.Error as error:
                    self.callback_errors.append('RESOURCE_OBSERVATION:'+str(error))
                self.stop.wait(self.resource_interval)
        self.thread=threading.Thread(target=observe,daemon=True);self.thread.start()

    def stop_resources(self):
        self.stop.set()
        if self.thread is not None:self.thread.join(timeout=2.)

    def callback(self,model,where,GRB):
        super().callback(model,where,GRB)
        def cb(name):
            try:
                value=float(model.cbGet(getattr(GRB.Callback,name)))
                return value if isfinite(value) and abs(value)<1e99 else None
            except Exception:return None
        runtime=cb('RUNTIME');work=cb('WORK')
        if where==GRB.Callback.MESSAGE:
            try:message=model.cbGet(GRB.Callback.MSG_STRING).strip()
            except Exception:return
            self.messages.append(message)
            if 'Crossover log' in message:
                self.events.setdefault('crossover_first_observed_native_seconds',runtime)
        elif where==GRB.Callback.BARRIER:
            self.events.setdefault('barrier_first_observed_native_seconds',runtime)
            self.events['barrier_last_observed_native_seconds']=runtime
            self.events['barrier_iterations_last_observed']=cb('BARRIER_ITRCNT')
        elif where==GRB.Callback.PRESOLVE:
            self.events['presolve_rows_removed']=cb('PRE_ROWDEL')
            self.events['presolve_columns_removed']=cb('PRE_COLDEL')
        elif where==GRB.Callback.MIPNODE:
            nodes=cb('MIPNODE_NODCNT');status=cb('MIPNODE_STATUS')
            if nodes==0 and status==GRB.OPTIMAL:
                self.events.setdefault('root_completion_observed_native_seconds',runtime)
                self.events.setdefault('root_completion_observed_Work',work)
                self.events.setdefault('root_objective_observed',cb('MIPNODE_OBJBND'))
        if where in (GRB.Callback.MIP,GRB.Callback.MIPSOL):
            solution=where==GRB.Callback.MIPSOL
            if solution:self.events.setdefault('first_incumbent_native_seconds',runtime)
            incumbent=cb('MIPSOL_OBJ' if solution else 'MIP_OBJBST')
            bound=cb('MIPSOL_OBJBND' if solution else 'MIP_OBJBND')
            nodes=cb('MIPSOL_NODCNT' if solution else 'MIP_NODCNT')
            if len(self.history)<10000 and (solution or not self.history or runtime is None or
                    runtime-(self.history[-1].get('native_seconds') or 0.)>=1.):
                gap=abs(incumbent-bound)/max(abs(incumbent),1e-10) if incumbent is not None and bound is not None else None
                self.history.append(dict(day=self.day,objective=self.active['objective'],native_seconds=runtime,
                    Work=work,incumbent=incumbent,active_domain_global_bound=bound,gap=gap,node_count=nodes,
                    event='INCUMBENT' if solution else 'BOUND_OBSERVATION',RSS_bytes=self.peak_rss))

    def receipt(self):
        result=super().receipt();log='\n'.join(self.messages)
        def parsed(pattern,groups):
            match=re.search(pattern,log,re.MULTILINE)
            if match is None:return None
            try:return {name:converter(match[index+1]) for index,(name,converter) in enumerate(groups)}
            except ValueError:return None
        result.update(events=dict(self.events),incumbent_and_bound_history=self.history,
            resource_samples=self.resources,peak_RSS_bytes=self.peak_rss,
            presolve=parsed(r'Presolve time: ([\d.]+)s',(('seconds',float),)),
            presolved_matrix=parsed(r'Presolved: (\d+) rows, (\d+) columns, (\d+) nonzeros',
                (('rows',int),('columns',int),('nnz',int))),
            root_relaxation=parsed(r'Root relaxation: objective ([\deE+.-]+), (\d+) iterations, ([\d.]+) seconds',
                (('objective',float),('iterations',int),('seconds',float))),
            barrier=parsed(r'Barrier solved model in (\d+) iterations and ([\d.]+) seconds',
                (('iterations',int),('seconds',float))),
            crossover=parsed(r'Crossover time: ([\d.]+) seconds',(('seconds',float),)),
            numerical_warnings=[line for line in self.messages if any(word in line.lower() for word in
                ('warning','numerical','refactor','quad precision'))],
            root_algorithm='frozen Method=2 barrier policy; actual observations and unavailable phases remain explicit',
            callback_errors=self.callback_errors)
        return result

