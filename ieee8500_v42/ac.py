"""Independent original IEEE8500 AC authority; never invokes a Native solver.

PCC powers are demand-positive kW/kvar. LV injection uses one constant-power
delta element across the two 120 V hot nodes, NOT two independent 120 V loads.
Original triplex neutrals are Kron reduced and have no separate rated current.
"""
from __future__ import annotations

import hashlib
import math
import re
import time
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import opendssdirect as odd


ORIGINAL_CONTROL_POLICY = {
    "name": "original_master_unbal_independent_static_controls",
    "source_pu": 1.05,
    "feeder_vreg_V": 126.5,
    "downstream_vreg_V": 125.0,
    "capacitors": "original enabled states and all nine original CapControls",
    "actual": "restore original initial states then independently settle controls",
    "linear_sensitivity": "restore settled base taps/caps; controlmode=off",
    "solver_only": {"maxiterations": 100, "maxcontroliter": 100, "tolerance": 1e-9},
    "voltage_base_note": "Preserve original Master voltagebases including 0.208kV; LV Bus base is 0.208/sqrt(3), while original Load/Transformer nameplate is 0.120kV",
}


def _complex(values):
    a = np.asarray(values, dtype=float)
    return a[0::2] + 1j * a[1::2]


def _base(bus):
    return bus.split(".", 1)[0].lower()


class IEEE8500AC:
    """Compile the unchanged Master-unbal and retain every original object.

    Each instance has a separate DSS context. Outputs are routed outside source.
    Numerical iteration budgets do not alter physical controls or ratings.
    """
    def __init__(self, source_dir=None, output_dir=None):
        self.source_dir = Path(source_dir or Path(__file__).parent / "data" / "feeder").resolve()
        self.output_dir = Path(output_dir or Path(__file__).parent / "outputs" / "dss").resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.source_hashes = self._hash_source()
        self.d = odd.NewContext()
        self.d.Basic.AllowChangeDir(False)
        self.d.Basic.AllowForms(False)
        self.d.Basic.AllowEditor(False)
        self.d.Basic.AllowDOScmd(False)
        self.d.Text.Command(f'compile "{self.source_dir / "Master-unbal.dss"}"')
        self.d.Text.Command(f'set datapath="{self.output_dir}"')
        self.d.Text.Command('set maxiterations=100 maxcontroliter=100 tolerance=1e-9 mode=snapshot controlmode=static')
        # Initialize node references without changing any original tap/cap state.
        self.d.Text.Command('set controlmode=off')
        self.d.Solution.Solve()
        self.d.Text.Command('set controlmode=static')
        self.pccs = {}
        self._last_background_scale = None
        self._last_pcc_demand = {}
        self.original_loads = {}
        for name in self.d.Loads.AllNames():
            self.d.Loads.Name(name)
            self.original_loads[name] = (self.d.Loads.kW(), self.d.Loads.kvar())
        self.inventory = self._inventory()
        self._orient_original_lines()
        self._controlled_transformers = {r["transformer"] for r in self.inventory["regcontrols"]}
        self._prepare_array_axes()
        self.initial_state = self.control_state()
        self._assert_policy()

    def _orient_original_lines(self):
        """Source-rooted topology orientation matching V42 parent-bus currents.

        Reactor.HVMV_Sub_HSB connects SourceBus to the HV transformer terminal.
        A source-rooted BFS orients radial lines. Equal-depth non-tree edges use
        declared bus1, explicitly disclosed rather than dropped from objective.
        Disabled original switches remain inventoried, outside the objective.
        """
        adjacency = defaultdict(list)
        def edge(a, b, element):
            a, b = _base(a), _base(b)
            if a != b:
                adjacency[a].append((b, element))
                adjacency[b].append((a, element))
        for meta in self.inventory["lines"] + self.inventory["transformers"]:
            if not meta["enabled"]:
                continue
            for b in meta["buses"][1:]:
                edge(meta["buses"][0], b, meta["element"])
        for name in self.d.Reactors.AllNames():
            self.d.Reactors.Name(name)
            buses = self.d.CktElement.BusNames()
            if self.d.CktElement.Enabled() and len(buses) == 2:
                edge(buses[0], buses[1], "Reactor." + name)
        depths = {"sourcebus": 0}
        queue = deque(["sourcebus"])
        while queue:
            parent = queue.popleft()
            for child, _ in adjacency[parent]:
                if child not in depths:
                    depths[child] = depths[parent] + 1
                    queue.append(child)
        for meta in self.inventory["lines"]:
            a, b = [_base(v) for v in meta["buses"]]
            da, db = depths.get(a), depths.get(b)
            terminal = 2 if da is not None and db is not None and db < da else 1
            meta["parent_terminal"] = terminal
            meta["parent_bus"] = [a, b][terminal - 1]
            meta["objective_orientation"] = "source_rooted_bfs" if da != db else "equal_depth_declared_bus1"
            meta["source_connected"] = da is not None and db is not None
        self.inventory["objective_contract"] = {
            "definition": "max original Line current at source-rooted parent terminal / original NormalAmps",
            "node_mask": "positive explicit nodes 1/2/3; triplex 1/2 are local hot labels",
            "all_terminals": "separate conservative thermal audit, not canonical V42 objective",
            "orientation": "BFS from sourcebus including original Reactor, transformers, enabled lines",
            "unreachable_enabled_lines": [r["element"] for r in self.inventory["lines"] if r["enabled"] and not r["source_connected"]]}

    def _hash_source(self):
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(self.source_dir.iterdir()) if p.is_file()}

    def verify_source_unchanged(self):
        current = self._hash_source()
        if current != self.source_hashes:
            raise RuntimeError("Canonical feeder bytes changed during AC audit")
        return True

    def _prepare_array_axes(self):
        """Map bulk PDE arrays to stable original terminal/conductor axes."""
        names = self.d.PDElements.AllNames()
        nc = self.d.PDElements.AllNumConductors()
        nt = self.d.PDElements.AllNumTerminals()
        offsets, cursor = {}, 0
        for name, c, t in zip(names, nc, nt):
            offsets[name.lower()] = cursor
            cursor += c * t
        self.line_axes, line_indices, line_ratings = [], [], []
        for meta in self.inventory["lines"]:
            start = offsets[meta["element"].lower()]
            for i, node in enumerate(meta["node_order"]):
                self.line_axes.append({"element": meta["element"], "group": meta["group"],
                    "terminal": i // meta["ncond"] + 1, "conductor": i % meta["ncond"] + 1,
                    "node": node, "normal_amps": meta["normal_amps"], "enabled": meta["enabled"]})
                line_indices.append(start + i)
                line_ratings.append(meta["normal_amps"])
        self._line_indices = np.array(line_indices, dtype=int)
        self._line_ratings = np.array(line_ratings, dtype=float)
        parent_terminals = {r["element"]: r["parent_terminal"] for r in self.inventory["lines"]}
        self.objective_line_mask = np.array([r["enabled"] and r["node"] > 0 and
            r["terminal"] == parent_terminals[r["element"]] for r in self.line_axes], dtype=bool)
        for row, included in zip(self.line_axes, self.objective_line_mask):
            row["objective_included"] = bool(included)
        self.triplex_terminal_axes, triplex_pairs = [], []
        for meta in self.inventory["lines"]:
            if meta["group"] != "Triplex":
                continue
            for t in range(meta["nterm"]):
                start = offsets[meta["element"].lower()] + t * meta["ncond"]
                triplex_pairs.append([start, start + 1])
                self.triplex_terminal_axes.append({"element": meta["element"], "terminal": t + 1,
                    "rating_A": None, "semantics": "inferred -(I_hot1+I_hot2); original Kron-reduced neutral has no independent ampacity"})
        self._triplex_pairs = np.array(triplex_pairs, dtype=int)
        self.node_axes = self.d.Circuit.AllNodeNames()
        self.transformer_axes, ti, tr, power_indices, starts, kr, nr = [], [], [], [], [], [], []
        self.transformer_winding_axes = []
        for meta in self.inventory["transformers"]:
            offset = offsets[meta["element"].lower()]
            for w in meta["windings"]:
                self.transformer_winding_axes.append({"element": meta["element"], "winding": w["winding"],
                    "normal_kva": w["normal_kva"], "nameplate_kva": w["kva_nameplate"]})
                starts.append(len(power_indices))
                kr.append(w["normal_kva"])
                nr.append(w["kva_nameplate"])
                for ci in range(meta["ncond"]):
                    i = (w["winding"] - 1) * meta["ncond"] + ci
                    self.transformer_axes.append({"element": meta["element"], "winding": w["winding"],
                        "conductor": ci + 1, "node": meta["node_order"][i], "normal_amps": w["normal_line_amps"]})
                    ti.append(offset + i)
                    tr.append(w["normal_line_amps"])
                    power_indices.append(offset + i)
        self._tx_indices, self._tx_ratings = np.array(ti), np.array(tr)
        self._tx_power_indices, self._tx_winding_starts = np.array(power_indices), np.array(starts)
        self._tx_kva_ratings = np.array(kr)
        self._tx_nameplate_ratings = np.array(nr)

    def measurement_arrays(self):
        """Full electrical arrays without thousands of individual object calls.

        Axis metadata: line_axes, node_axes, transformer_axes,
        transformer_winding_axes. All originals are retained, including both ends.
        """
        current = _complex(self.d.PDElements.AllCurrents())
        powers = _complex(self.d.PDElements.AllPowers())
        line_amps = np.abs(current[self._line_indices])
        tx_amps = np.abs(current[self._tx_indices])
        tx_power = np.add.reduceat(powers[self._tx_power_indices], self._tx_winding_starts)
        implied_neutral = -current[self._triplex_pairs].sum(axis=1)
        regs = []
        for name in self.d.RegControls.AllNames():
            self.d.RegControls.Name(name)
            regs.append({"name": name, "tap_number": self.d.RegControls.TapNumber()})
        return {"line_amps": line_amps, "line_rho": line_amps / self._line_ratings,
            "node_voltage_pu": np.array(self.d.Circuit.AllBusMagPu()),
            "transformer_amps": tx_amps, "transformer_current_rho": tx_amps / self._tx_ratings,
            "transformer_winding_complex_kva": tx_power, "transformer_winding_kva_rho": np.abs(tx_power) / self._tx_kva_ratings,
            "transformer_winding_nameplate_kva_rho": np.abs(tx_power) / self._tx_nameplate_ratings,
            "triplex_implied_neutral_complex_A": implied_neutral,
            "triplex_implied_neutral_amps": np.abs(implied_neutral),
            "converged": bool(self.d.Solution.Converged()), "control_actions_done": bool(self.d.Solution.ControlActionsDone()),
            "control_queue_size": self.d.CtrlQueue.QueueSize(), "regcontrols": regs,
            "source_kw_kvar": -np.array(self.d.Circuit.TotalPower()), "loss_kw_kvar": np.array(self.d.Circuit.Losses()) / 1000}

    def _property(self, name):
        return self.d.Properties.Value(name)

    def _node_order(self):
        if self.d.CktElement.Enabled():
            return self.d.CktElement.NodeOrder()
        # Disabled original switches have no initialized NodeRef in DSS. Keep
        # their declared terminal wiring in inventory and zero solved currents.
        nc = self.d.CktElement.NumConductors()
        result = []
        for bus in self.d.CktElement.BusNames():
            declared = [int(v) for v in bus.split(".")[1:]]
            result.extend((declared or list(range(1, nc + 1)))[:nc])
        return result

    def _assert_policy(self):
        self.d.Vsources.Name("source")
        if abs(self.d.Vsources.PU() - 1.05) > 1e-12:
            raise ValueError("Source policy differs from original 1.05 pu")
        for name in self.d.RegControls.AllNames():
            self.d.RegControls.Name(name)
            expected = 126.5 if name.startswith("feeder_reg") else 125.0
            if abs(self.d.RegControls.ForwardVreg() - expected) > 1e-12:
                raise ValueError("RegControl policy differs from original source")

    def _inventory(self):
        d = self.d
        inv = {"engine": d.Basic.Version(), "control_policy": ORIGINAL_CONTROL_POLICY,
               "source_sha256": self.source_hashes, "buses": [], "lines": [],
               "transformers": [], "regcontrols": [], "capacitors": [], "capcontrols": [],
               "loads": [], "other_elements": d.Circuit.AllElementNames()}
        line_files = {}
        for filename in ["Lines.dss", "Triplex_Lines.DSS"]:
            text = (self.source_dir / filename).read_text(errors="replace")
            for name in re.findall(r"(?im)^\s*new\s+line\.([^\s]+)", text):
                line_files[name.lower()] = filename
        for name in d.Circuit.AllBusNames():
            d.Circuit.SetActiveBus(name)
            inv["buses"].append({"bus": name, "nodes": d.Bus.Nodes(), "kv_base_ln": d.Bus.kVBase(),
                                  "x": d.Bus.X(), "y": d.Bus.Y(), "coord_defined": bool(d.Bus.Coorddefined())})
        for name in d.Lines.AllNames():
            d.Lines.Name(name)
            buses = d.CktElement.BusNames()
            d.Circuit.SetActiveBus(_base(buses[0]))
            kvbase = d.Bus.kVBase()
            group = "Triplex" if line_files.get(name) == "Triplex_Lines.DSS" else ("Secondary" if kvbase < 1 else "Primary")
            inv["lines"].append({"element": "Line." + name, "group": group, "buses": buses,
                                 "node_order": self._node_order(), "ncond": d.CktElement.NumConductors(),
                                 "nphase": d.CktElement.NumPhases(), "nterm": d.CktElement.NumTerminals(),
                                 "normal_amps": d.CktElement.NormalAmps(), "emergency_amps": d.CktElement.EmergAmps(),
                                 "enabled": bool(d.CktElement.Enabled()), "linecode": d.Lines.LineCode(),
                                 "length": d.Lines.Length(), "units": int(d.Lines.Units()),
                                 "source_file": line_files.get(name, "unknown")})
        for name in d.Transformers.AllNames():
            d.Transformers.Name(name)
            rec = {"element": "Transformer." + name, "buses": d.CktElement.BusNames(),
                   "node_order": self._node_order(), "ncond": d.CktElement.NumConductors(),
                   "nphase": d.CktElement.NumPhases(), "nterm": d.CktElement.NumTerminals(),
                   "enabled": bool(d.CktElement.Enabled()), "xfmrcode": d.Transformers.XfmrCode(),
                   "normal_amps_primary": d.CktElement.NormalAmps(),
                   "normal_hkva": float(self._property("normhkva")),
                   "emergency_hkva": float(self._property("emerghkva")), "windings": []}
            for winding in range(1, d.Transformers.NumWindings() + 1):
                d.Transformers.Wdg(winding)
                rec["windings"].append({"winding": winding, "kv": d.Transformers.kV(),
                    "kva_nameplate": d.Transformers.kVA(), "delta": bool(d.Transformers.IsDelta()),
                    "tap": d.Transformers.Tap(), "mintap": d.Transformers.MinTap(),
                    "maxtap": d.Transformers.MaxTap(), "numtaps": d.Transformers.NumTaps()})
            kva1 = rec["windings"][0]["kva_nameplate"]
            kv1 = rec["windings"][0]["kv"]
            for w in rec["windings"]:
                # NormAmps is on winding 1, not a common denominator for all windings.
                # Preserve the original normhkva/kva1 factor and winding kVA ratios.
                w["normal_kva"] = rec["normal_hkva"] * w["kva_nameplate"] / kva1
                w["normal_line_amps"] = rec["normal_amps_primary"] * kv1 / w["kv"] * w["kva_nameplate"] / kva1
                phase_voltage_kv = w["kv"] / math.sqrt(3) if rec["nphase"] > 1 and not w["delta"] else w["kv"]
                w["nameplate_coil_amps"] = w["kva_nameplate"] / rec["nphase"] / phase_voltage_kv
            inv["transformers"].append(rec)
        for name in d.RegControls.AllNames():
            d.RegControls.Name(name)
            inv["regcontrols"].append({"name": name, "transformer": d.RegControls.Transformer(),
                "properties": {p: self._property(p) for p in d.CktElement.AllPropertyNames()}})
        for name in d.Capacitors.AllNames():
            d.Capacitors.Name(name)
            inv["capacitors"].append({"name": name, "buses": d.CktElement.BusNames(),
                "kvar": d.Capacitors.kvar(), "kv": d.Capacitors.kV(), "states": d.Capacitors.States(),
                "properties": {p: self._property(p) for p in d.CktElement.AllPropertyNames()}})
        for name in d.CapControls.AllNames():
            d.CapControls.Name(name)
            inv["capcontrols"].append({"name": name,
                "properties": {p: self._property(p) for p in d.CktElement.AllPropertyNames()}})
        for name in d.Loads.AllNames():
            d.Loads.Name(name)
            inv["loads"].append({"name": name, "buses": d.CktElement.BusNames(), "node_order": d.CktElement.NodeOrder(),
                "phases": d.CktElement.NumPhases(), "kv": d.Loads.kV(), "kw": d.Loads.kW(), "kvar": d.Loads.kvar(),
                "model": d.Loads.Model(), "delta": bool(d.Loads.IsDelta()),
                "vminpu_load_characteristic": d.Loads.Vminpu(), "vmaxpu_load_characteristic": d.Loads.Vmaxpu(),
                "pf": d.Loads.PF()})
        inv["counts"] = {"buses": d.Circuit.NumBuses(), "nodes": d.Circuit.NumNodes(),
            "lines": d.Lines.Count(), "transformers": d.Transformers.Count(), "loads": d.Loads.Count(),
            "regcontrols": d.RegControls.Count(), "capacitors": d.Capacitors.Count(), "capcontrols": d.CapControls.Count()}
        return inv

    def add_pcc(self, pcc_id, bus, mode="MV_3PH"):
        if not re.fullmatch(r"[A-Za-z0-9_]+", pcc_id):
            raise ValueError("PCC id must contain only letters/digits/underscore")
        if pcc_id in self.pccs:
            raise ValueError("Duplicate PCC id")
        bus = _base(bus)
        if self.d.Circuit.SetActiveBus(bus) < 0:
            raise ValueError("PCC bus missing from original circuit")
        nodes, kvbase = self.d.Bus.Nodes(), self.d.Bus.kVBase()
        if mode == "MV_3PH":
            if not set([1, 2, 3]).issubset(nodes) or kvbase < 1:
                raise ValueError("MV_3PH requires an original three phase MV bus")
            busconn, phases, conn, kv = bus + ".1.2.3", 3, "wye", kvbase * math.sqrt(3)
        elif mode == "LV_SPLIT_240":
            if not set([1, 2]).issubset(nodes) or abs(kvbase - 0.12) > .001:
                raise ValueError("LV_SPLIT_240 requires original 120/240 V hot nodes 1 and 2")
            busconn, phases, conn, kv = bus + ".1.2", 1, "delta", .24
        elif mode in ("LV_LEG1_120", "LV_LEG2_120"):
            hot = 1 if mode == "LV_LEG1_120" else 2
            if hot not in nodes or abs(kvbase - .12) > .001:
                raise ValueError("LV leg mode requires an original 120 V hot node")
            busconn, phases, conn, kv = bus + f".{hot}.0", 1, "wye", .12
        else:
            raise ValueError("Unknown PCC electrical mode")
        name = "v42pcc_" + pcc_id.lower()
        self.d.Text.Command(f'new Load.{name} phases={phases} bus1={busconn} conn={conn} kv={kv:.12g} kw=0 kvar=0 model=1 vminpu=0.01 vmaxpu=2')
        self.pccs[pcc_id] = {"element": "Load." + name, "bus": bus, "mode": mode, "kv": kv,
            "port_qualification": "hypothetical AC electrical model; field connection hardware/protection is not proven"}
        return self.pccs[pcc_id]

    def control_state(self):
        d = self.d
        state = {"taps": {}, "capacitors": {}}
        for name in sorted(self._controlled_transformers):
            d.Transformers.Name(name)
            taps = []
            for winding in range(1, d.Transformers.NumWindings() + 1):
                d.Transformers.Wdg(winding)
                taps.append(d.Transformers.Tap())
            state["taps"][name] = taps
        for name in d.Capacitors.AllNames():
            d.Capacitors.Name(name)
            state["capacitors"][name] = d.Capacitors.States()
        return state

    def restore_control_state(self, state):
        for name, taps in state["taps"].items():
            self.d.Transformers.Name(name)
            for winding, tap in enumerate(taps, 1):
                self.d.Transformers.Wdg(winding)
                self.d.Transformers.Tap(tap)
        for name, states in state["capacitors"].items():
            self.d.Capacitors.Name(name)
            self.d.Capacitors.States(states)
        self.d.CtrlQueue.ClearQueue()
        self.d.CtrlQueue.ClearActions()

    def solve(self, background_scale=1.0, pcc_demand=None, control_mode="auto", fixed_state=None,
              reset_controls=True, snapshot=True):
        if background_scale < 0 or not math.isfinite(background_scale):
            raise ValueError("Invalid background scale")
        if control_mode not in ("auto", "fixed"):
            raise ValueError("control_mode must be auto or fixed")
        demand = pcc_demand or {}
        unknown = set(demand) - self.pccs.keys()
        if unknown:
            raise ValueError(f"Unknown PCCs: {unknown}")
        d = self.d
        # Only original background loads are scaled; overlays have independent P/Q.
        if background_scale != self._last_background_scale:
            for name, (kw, kvar) in self.original_loads.items():
                d.Loads.Name(name)
                d.Loads.kW(kw * background_scale)
                d.Loads.kvar(kvar * background_scale)
            self._last_background_scale = background_scale
        for name, pcc in self.pccs.items():
            kw, kvar = demand.get(name, (0.0, 0.0))
            if not math.isfinite(kw) or not math.isfinite(kvar):
                raise ValueError("Non-finite PCC power")
            if self._last_pcc_demand.get(name) != (kw, kvar):
                d.Text.Command(f'edit {pcc["element"]} kw={float(kw):.12g} kvar={float(kvar):.12g}')
                self._last_pcc_demand[name] = (kw, kvar)
        if control_mode == "fixed":
            if fixed_state is None:
                raise ValueError("Fixed sensitivity requires a settled base control state")
            self.restore_control_state(fixed_state)
            d.Text.Command('set controlmode=off')
        else:
            if reset_controls:
                self.restore_control_state(self.initial_state)
            d.Text.Command('set controlmode=static')
        d.Text.Command('set mode=snapshot loadmult=1')
        started = time.perf_counter()
        d.Solution.Solve()
        elapsed = time.perf_counter() - started
        result = self.snapshot() if snapshot else {}
        result["settings"] = {"background_scale": background_scale, "pcc_demand": demand,
                              "control_mode": control_mode, "independent_initial_states": reset_controls}
        if snapshot:
            result["summary"]["solve_seconds"] = elapsed
        return result

    def snapshot(self):
        d = self.d
        lines, transformers, buses, regs, caps = [], [], [], [], []
        for meta in self.inventory["lines"]:
            d.Circuit.SetActiveElement(meta["element"])
            current = _complex(d.CktElement.Currents())
            power = _complex(d.CktElement.Powers())
            for index, amps in enumerate(current):
                n = meta["ncond"]
                node = meta["node_order"][index]
                rating = meta["normal_amps"]
                neutral = -sum(current[(index // n) * n:(index // n + 1) * n]) if meta["group"] == "Triplex" else None
                lines.append({"element": meta["element"], "group": meta["group"],
                    "terminal": index // n + 1, "conductor": index % n + 1, "node": node,
                    "bus": _base(meta["buses"][index // n]), "i_real_A": float(amps.real),
                    "i_imag_A": float(amps.imag), "amps": float(abs(amps)), "normal_amps": rating,
                    "rho": float(abs(amps) / rating) if rating > 0 else None,
                    "p_kw": float(power[index].real), "q_kvar": float(power[index].imag),
                    "enabled": meta["enabled"], "explicit_conductor": True,
                    "objective_included": bool(meta["enabled"] and node > 0 and index // n + 1 == meta["parent_terminal"]),
                    "implied_neutral_amps": float(abs(neutral)) if neutral is not None else None,
                    "implied_neutral_real_A": float(neutral.real) if neutral is not None else None,
                    "implied_neutral_imag_A": float(neutral.imag) if neutral is not None else None,
                    "implied_neutral_rating_A": None,
                    "neutral_note": "Kron reduced; neutral not separately represented" if meta["group"] == "Triplex" else ""})
        for meta in self.inventory["transformers"]:
            d.Transformers.Name(meta["element"].split(".", 1)[1])
            current, power = _complex(d.CktElement.Currents()), _complex(d.CktElement.Powers())
            for w in meta["windings"]:
                wi, nc = w["winding"] - 1, meta["ncond"]
                powers = power[wi * nc:(wi + 1) * nc]
                kva_complex = sum(powers)
                d.Transformers.Wdg(wi + 1)
                for ci in range(nc):
                    idx = wi * nc + ci
                    node = meta["node_order"][idx]
                    transformers.append({"element": meta["element"], "xfmrcode": meta["xfmrcode"],
                        "winding": wi + 1, "conductor": ci + 1, "node": node,
                        "bus": _base(meta["buses"][wi]), "amps": float(abs(current[idx])),
                        "i_real_A": float(current[idx].real), "i_imag_A": float(current[idx].imag),
                        "normal_amps": w["normal_line_amps"], "current_rho": float(abs(current[idx]) / w["normal_line_amps"]),
                        "ground_return_without_separate_rating": node == 0,
                        "p_kw": float(powers[ci].real), "q_kvar": float(powers[ci].imag),
                        "winding_p_kw": float(kva_complex.real), "winding_q_kvar": float(kva_complex.imag),
                        "winding_kva": float(abs(kva_complex)), "normal_kva": w["normal_kva"],
                        "nameplate_kva": w["kva_nameplate"], "kva_rho": float(abs(kva_complex) / w["normal_kva"]),
                        "nameplate_kva_rho": float(abs(kva_complex) / w["kva_nameplate"]),
                        "tap": d.Transformers.Tap(), "enabled": meta["enabled"]})
        allpu = np.asarray(d.Circuit.AllBusMagPu())
        nodenames = d.Circuit.AllNodeNames()
        for name in d.Circuit.AllBusNames():
            d.Circuit.SetActiveBus(name)
            nodes, volts, kvbase = d.Bus.Nodes(), _complex(d.Bus.Voltages()), d.Bus.kVBase()
            for node, volt in zip(nodes, volts):
                buses.append({"bus": name, "node": node, "v_real_V": float(volt.real),
                    "v_imag_V": float(volt.imag), "voltage_V": float(abs(volt)),
                    "voltage_pu": float(abs(volt) / (kvbase * 1000)) if kvbase > 0 else None,
                    "split_hot_nominal_120_pu": float(abs(volt) / 120) if abs(kvbase-.12)<.001 else None,
                    "kv_base_ln": kvbase})
        # Bus.Nodes() sorts local node labels; Circuit.AllNodeNames() follows
        # original insertion order, e.g. m1009763.2 precedes m1009763.1. Align
        # full snapshots with the bulk arrays by explicit node identity.
        by_node = {r["bus"] + "." + str(r["node"]): r for r in buses}
        buses = [by_node[name] for name in nodenames]
        for name in d.RegControls.AllNames():
            d.RegControls.Name(name)
            transformer, winding = d.RegControls.Transformer(), d.RegControls.TapWinding()
            tap_number, enabled = d.RegControls.TapNumber(), bool(d.CktElement.Enabled())
            d.Transformers.Name(transformer)
            d.Transformers.Wdg(winding)
            regs.append({"name": name, "transformer": transformer, "winding": winding,
                "tap_number": tap_number, "tap_pu": d.Transformers.Tap(), "enabled": enabled})
        for name in d.Capacitors.AllNames():
            d.Capacitors.Name(name)
            caps.append({"name": name, "states": d.Capacitors.States(), "enabled": bool(d.CktElement.Enabled()),
                         "total_kvar": d.Capacitors.kvar()})
        source = -np.asarray(d.Circuit.TotalPower())
        losses = np.asarray(d.Circuit.Losses()) / 1000
        categories = {"loads": 0j, "capacitors": 0j, "generators": 0j, "pvsystems": 0j, "storages": 0j}
        classes = [("loads", d.Loads), ("capacitors", d.Capacitors), ("generators", d.Generators),
                   ("pvsystems", d.PVsystems), ("storages", d.Storages)]
        pcc_actual = {}
        for category, obj in classes:
            names = obj.AllNames()
            if obj.Count() == 0:
                continue
            for name in names:
                obj.Name(name)
                p = sum(_complex(d.CktElement.Powers()))
                categories[category] += p
        # Capacitor reactive demand belongs outside Circuit.Losses; check exact convention.
        balance = complex(*source) - complex(*losses) - sum(categories.values())
        for name, pcc in self.pccs.items():
            d.Circuit.SetActiveElement(pcc["element"])
            p = sum(_complex(d.CktElement.Powers()))
            v, i = _complex(d.CktElement.Voltages()), _complex(d.CktElement.Currents())
            pcc_actual[name] = {"p_kw": float(p.real), "q_kvar": float(p.imag),
                "node_order": d.CktElement.NodeOrder(), "currents_A": [float(abs(x)) for x in i],
                "v_ll_V": float(abs(v[0] - v[1])) if pcc["mode"] == "LV_SPLIT_240" else None,
                "connection_voltage_V": float(abs(v[0] - v[1])) if pcc["mode"].startswith("LV_") else None,
                "connection_voltage_pu_nameplate": float(abs(v[0]-v[1])/(pcc["kv"]*1000)) if pcc["mode"].startswith("LV_") else None,
                "mode": pcc["mode"], "bus": pcc["bus"]}
        rated = [r for r in lines if r["enabled"] and r["rho"] is not None]
        binding = max(rated, key=lambda r: r["rho"])
        objective_binding = max((r for r in rated if r["objective_included"]), key=lambda r: r["rho"])
        tx = [r for r in transformers if r["enabled"]]
        low, high = int(np.argmin(allpu)), int(np.argmax(allpu))
        summary = {"converged": bool(d.Solution.Converged()), "control_actions_done": bool(d.Solution.ControlActionsDone()),
            "control_queue_size": d.CtrlQueue.QueueSize(), "iterations": d.Solution.Iterations(),
            "control_iterations": d.Solution.ControlIterations(), "rho_max": objective_binding["rho"],
            "binding_line": objective_binding["element"], "binding_terminal": objective_binding["terminal"], "binding_node": objective_binding["node"],
            "rho_max_all_terminals": binding["rho"], "all_terminal_binding_line": binding["element"],
            "all_terminal_binding_terminal": binding["terminal"], "all_terminal_binding_node": binding["node"],
            "vmin_pu": float(allpu[low]), "vmax_pu": float(allpu[high]),
            "vmin_node": nodenames[low], "vmax_node": nodenames[high],
            "transformer_current_rho_max": max(r["current_rho"] for r in tx),
            "transformer_kva_rho_max": max(r["kva_rho"] for r in tx),
            "transformer_nameplate_kva_rho_max": max(r["nameplate_kva_rho"] for r in tx),
            "source_kw": float(source[0]), "source_kvar": float(source[1]),
            "loss_kw": float(losses[0]), "loss_kvar": float(losses[1]),
            "load_kw": float(categories["loads"].real), "load_kvar": float(categories["loads"].imag),
            "capacitor_kw": float(categories["capacitors"].real), "capacitor_kvar": float(categories["capacitors"].imag),
            "balance_residual_kw": float(balance.real), "balance_residual_kvar": float(balance.imag),
            "unrated_line_conductors": sum(r["rho"] is None for r in lines),
            "node_voltage_violations_095_105": int(np.sum((allpu < .95 - 1e-8) | (allpu > 1.05 + 1e-8))),
            "line_conductor_overloads": sum(r["rho"] > 1 + 1e-8 for r in rated),
            "transformer_conductor_overloads": sum(r["current_rho"] > 1 + 1e-8 for r in tx),
            "transformer_winding_overloads": len({(r["element"],r["winding"]) for r in tx if r["kva_rho"] > 1 + 1e-8})}
        summary["transformer_nameplate_winding_overloads"] = len({(r["element"],r["winding"]) for r in tx if r["nameplate_kva_rho"] > 1 + 1e-8})
        neutral_binding = max((r for r in lines if r["implied_neutral_amps"] is not None), key=lambda r:r["implied_neutral_amps"])
        summary["triplex_implied_neutral_amps_max"] = neutral_binding["implied_neutral_amps"]
        summary["triplex_implied_neutral_binding_line"] = neutral_binding["element"]
        summary["triplex_neutral_ampacity_known"] = False
        return {"summary": summary, "lines": lines, "transformers": transformers, "buses": buses,
                "regcontrols": regs, "capacitors": caps, "pcc_actual": pcc_actual,
                "control_state": self.control_state()}

    def finite_difference(self, pcc_id, background_scale, pcc_demand, delta_kw=0.25, delta_kvar=0.25,
                          mode="fixed"):
        """Central differences per positive injection, not increased demand.

        Local fixed controls use exactly the same settled base state for ±P/±Q.
        Automatic variants each restore original states and independently settle.
        Full axes retain both line terminals and every node voltage.
        """
        base = self.solve(background_scale, pcc_demand, control_mode="auto")
        answer = {"base": base, "pcc_id": pcc_id, "mode": mode, "perturbations": {}}
        kwargs = {"control_mode": mode, "fixed_state": base["control_state"] if mode == "fixed" else None}
        for axis, delta in [("P", delta_kw), ("Q", delta_kvar)]:
            if delta <= 0:
                raise ValueError("Finite difference step must be positive")
            pair = []
            for sign in [-1, 1]:
                changed = dict(pcc_demand)
                values = list(changed.get(pcc_id, (0., 0.)))
                values[0 if axis == "P" else 1] -= sign * delta
                changed[pcc_id] = tuple(values)
                pair.append(self.solve(background_scale, changed, **kwargs))
            minus, plus = pair
            answer["perturbations"][axis] = {"delta": delta, "minus": minus, "plus": plus,
                "line_dI_A_per_kW_or_kvar": ((np.array([r["amps"] for r in plus["lines"]]) -
                                               np.array([r["amps"] for r in minus["lines"]])) / (2 * delta)).tolist(),
                "node_dV_pu_per_kW_or_kvar": ((np.array([r["voltage_pu"] for r in plus["buses"]]) -
                                               np.array([r["voltage_pu"] for r in minus["buses"]])) / (2 * delta)).tolist()}
        return answer

    def local_injection_sensitivity(self, pcc_id, background_scale=1., pcc_demand=None,
                                    delta_kw=.25, delta_kvar=.25, mode='fixed', base_snapshot=None):
        """Lightweight central differences on every original current/voltage axis.

        These are hypothetical electrical response scores, not certified port
        flexibility bounds. Positive derivative direction means injected P/Q.
        Automatic endpoints independently restore original controls; fixed ones
        restore the same base state. The caller supplies physically authorized
        steps and applies GPU/jobs/QoS, vehicle, aggregate PCC and site bounds.
        """
        if pcc_id not in self.pccs:
            raise ValueError('PCC must be registered before sensitivity')
        if mode not in ('fixed','auto'):
            raise ValueError('Sensitivity mode must be fixed or auto')
        demand=dict(pcc_demand or {})
        if base_snapshot is None:
            base_snapshot=self.solve(background_scale,demand,control_mode='auto')
        kwargs={'control_mode':mode,'fixed_state':base_snapshot['control_state'] if mode=='fixed' else None}
        response={'pcc_id':pcc_id,'mode':mode,'base_summary':base_snapshot['summary'],
                  'base_control_state':base_snapshot['control_state'],'derivatives':{},'endpoints':{},
                  'port_qualification':self.pccs[pcc_id]['port_qualification']}
        for axis,delta in [('P',delta_kw),('Q',delta_kvar)]:
            if delta<=0:
                raise ValueError('Sensitivity step must be positive')
            endpoints=[]
            for sign in [-1,1]:
                changed=dict(demand);values=list(changed.get(pcc_id,(0.,0.)))
                values[0 if axis=='P' else 1]-=sign*delta
                changed[pcc_id]=tuple(values)
                self.solve(background_scale,changed,snapshot=False,**kwargs)
                arrays=self.measurement_arrays()
                arrays['control_state']=self.control_state()
                endpoints.append(arrays)
            minus,plus=endpoints
            response['endpoints'][axis]={'minus_injection':minus,'plus_injection':plus,'step':delta}
            response['derivatives'][axis]={key:(plus[key]-minus[key])/(2*delta) for key in
                ('line_amps','line_rho','node_voltage_pu','transformer_amps','transformer_current_rho',
                 'transformer_winding_nameplate_kva_rho','triplex_implied_neutral_amps')}
        return response
