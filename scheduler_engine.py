"""
CPU Scheduling engine.

Pure-Python (no GUI dependency).  Every algorithm is run through one common
simulation loop which records, for every CPU slice, a detailed `Step`
(time, ready queue, remaining times, events, reason for the decision).
"""
from __future__ import annotations

import colorsys
import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

EPS = 1e-9
INF = float("inf")


# --------------------------------------------------------------------------- #
#  Data classes
# --------------------------------------------------------------------------- #
@dataclass
class ProcessInput:
    pid: str
    at: float
    bt: float
    priority: int = 0
    queue_level: int = 0               # for Multilevel Queue (0 = highest)
    deadline: Optional[float] = None   # absolute deadline (EDF)


@dataclass
class SchedOptions:
    quantum: float = 2.0
    cs_time: float = 0.0
    high_is_priority: bool = False     # False -> lower number = higher priority
    aging: float = 0.0                 # 0 = off; else priority improves by 1 / interval
    seed: int = 1                      # lottery
    # Multilevel Queue: one (algorithm, quantum) per queue. algo in FCFS/RR/SJF/PRIORITY
    mlq_levels: List[Tuple[str, float]] = field(
        default_factory=lambda: [("RR", 2.0), ("SJF", 0.0), ("FCFS", 0.0)])
    # Multilevel Feedback Queue: quantum of each level, last level is FCFS
    mlfq_quanta: List[float] = field(default_factory=lambda: [2.0, 4.0])


@dataclass
class GanttSegment:
    pid: str                 # process id, 'IDLE' or 'CS'
    start: float
    end: float
    kind: str = "run"        # run | idle | cs
    queue_level: Optional[int] = None

    @property
    def is_idle(self) -> bool:
        return self.kind == "idle"

    @property
    def is_cs(self) -> bool:
        return self.kind == "cs"


@dataclass
class Step:
    no: int
    kind: str                       # run | idle | cs
    start: float
    end: float
    pid: str
    ready: List[str]                # waiting processes, in queue order
    remaining: Dict[str, float]     # remaining time of all unfinished arrived processes (before the slice)
    events: List[str]
    reason: str
    outcome: str
    level: Optional[int] = None


@dataclass
class ProcessResult:
    pid: str
    at: float
    bt: float
    priority: int
    final_priority: int
    queue_level: int
    ct: float
    tat: float
    wt: float
    rt: float
    first_start: float
    preemptions: int
    deadline: Optional[float] = None

    @property
    def deadline_met(self) -> Optional[bool]:
        return None if self.deadline is None else self.ct <= self.deadline + EPS


@dataclass
class ScheduleOutput:
    key: str
    algorithm: str
    mode: str
    gantt: List[GanttSegment]
    raw_gantt: List[GanttSegment]
    steps: List[Step]
    results: List[ProcessResult]
    end_time: float
    idle_time: float
    cs_count: int
    cs_overhead: float
    avg_wt: float
    avg_tat: float
    avg_rt: float
    avg_ct: float
    throughput: float
    cpu_utilization: float
    summary: List[str] = field(default_factory=list)
    options_text: str = ""

    @property
    def iteration_logs(self) -> List[str]:
        return [format_step(s) for s in self.steps]


def _fmt(v: float) -> str:
    r = round(float(v), 2)
    if r == int(r):
        return str(int(r))
    return f"{r:g}"


def format_step(s: Step) -> str:
    base = f"#{s.no} [{_fmt(s.start)} → {_fmt(s.end)}] {s.pid}: {s.reason}"
    if s.events:
        base += " | " + "; ".join(s.events)
    return base


# --------------------------------------------------------------------------- #
#  Algorithm registry
# --------------------------------------------------------------------------- #
@dataclass
class AlgoInfo:
    key: str
    name: str
    mode: str
    hue: float          # base colour family (0..1)
    desc: str
    uses: str           # which inputs matter


ALGOS: List[AlgoInfo] = [
    AlgoInfo("FCFS", "First Come First Serve (FCFS)", "Non-preemptive", 0.60,
             "Processes run strictly in order of arrival.", "Arrival, Burst"),
    AlgoInfo("SJF", "Shortest Job First (SJF)", "Non-preemptive", 0.08,
             "Among arrived processes the one with the smallest burst runs to completion.", "Arrival, Burst"),
    AlgoInfo("SRTF", "Shortest Remaining Time First (SRTF)", "Preemptive", 0.00,
             "Preemptive SJF: the process with the least remaining time always runs.", "Arrival, Burst"),
    AlgoInfo("LJF", "Longest Job First (LJF)", "Non-preemptive", 0.76,
             "Among arrived processes the one with the largest burst runs to completion.", "Arrival, Burst"),
    AlgoInfo("LRTF", "Longest Remaining Time First (LRTF)", "Preemptive", 0.90,
             "Preemptive LJF: the process with the most remaining time runs (re-checked every 1 unit).", "Arrival, Burst"),
    AlgoInfo("RR", "Round Robin (RR)", "Preemptive", 0.35,
             "Each process gets a fixed time quantum in circular order.", "Arrival, Burst, Quantum"),
    AlgoInfo("PRIO_NP", "Priority Scheduling (Non-preemptive)", "Non-preemptive", 0.50,
             "Highest-priority arrived process runs to completion. Optional aging.", "Arrival, Burst, Priority"),
    AlgoInfo("PRIO_P", "Priority Scheduling (Preemptive)", "Preemptive", 0.68,
             "A higher-priority arrival immediately preempts the running process. Optional aging.", "Arrival, Burst, Priority"),
    AlgoInfo("PRIO_RR", "Priority + Round Robin", "Preemptive", 0.42,
             "Highest priority first; equal priorities share the CPU in Round Robin.", "Arrival, Burst, Priority, Quantum"),
    AlgoInfo("HRRN", "Highest Response Ratio Next (HRRN)", "Non-preemptive", 0.14,
             "Picks the process with the highest (wait + burst) / burst ratio.", "Arrival, Burst"),
    AlgoInfo("MLQ", "Multilevel Queue (MLQ)", "Preemptive (between queues)", 0.55,
             "Fixed queues with strict priority between them; every queue has its own algorithm.",
             "Arrival, Burst, Queue, Priority"),
    AlgoInfo("MLFQ", "Multilevel Feedback Queue (MLFQ)", "Preemptive", 0.28,
             "Processes start in the top queue and are demoted when they use up their quantum.",
             "Arrival, Burst, Quanta"),
    AlgoInfo("EDF", "Earliest Deadline First (EDF)", "Preemptive", 0.97,
             "The process with the nearest deadline runs first.", "Arrival, Burst, Deadline"),
    AlgoInfo("LOTTERY", "Lottery Scheduling", "Preemptive", 0.17,
             "Each quantum a random ticket is drawn; tickets depend on priority.", "Arrival, Burst, Priority, Quantum, Seed"),
    AlgoInfo("STRIDE", "Stride Scheduling", "Preemptive", 0.45,
             "Deterministic proportional share: smallest 'pass' value runs next.", "Arrival, Burst, Priority, Quantum"),
]
ALGO_BY_KEY: Dict[str, AlgoInfo] = {a.key: a for a in ALGOS}


# --------------------------------------------------------------------------- #
#  Colours: each algorithm has a colour family, each process a shade of it
# --------------------------------------------------------------------------- #
def algo_color(key: str, lightness: float = 0.45, sat: float = 0.70) -> str:
    h = ALGO_BY_KEY[key].hue
    r, g, b = colorsys.hls_to_rgb(h, lightness, sat)
    return "#%02X%02X%02X" % (int(r * 255), int(g * 255), int(b * 255))


def process_colors(key: str, pids: List[str]) -> Dict[str, str]:
    n = len(pids)
    out = {}
    for i, pid in enumerate(pids):
        frac = i / (n - 1) if n > 1 else 0.5
        out[pid] = algo_color(key, 0.28 + 0.46 * frac, 0.72)
    return out


def text_color_for(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "#FFFFFF" if (0.299 * r + 0.587 * g + 0.114 * b) < 150 else "#111827"


# --------------------------------------------------------------------------- #
#  Simulation state
# --------------------------------------------------------------------------- #
class _Sim:
    def __init__(self, procs: List[ProcessInput], opts: SchedOptions):
        self.procs = procs
        self.opts = opts
        self.byid = {p.pid: p for p in procs}
        self.n = len(procs)
        self.rem: Dict[str, float] = {p.pid: float(p.bt) for p in procs}
        self.pending = sorted(procs, key=lambda p: (p.at, procs.index(p)))
        self.admitted: List[str] = []
        self.seq: Dict[str, int] = {}
        self._seq = 0
        self.t = 0.0
        self.segs: List[GanttSegment] = []
        self.steps: List[Step] = []
        self.first: Dict[str, float] = {}
        self.completion: Dict[str, float] = {}
        self.final_prio: Dict[str, int] = {}
        self.preempt = {p.pid: 0 for p in procs}
        self.wait_since: Dict[str, float] = {}
        self.level: Dict[str, int] = {}
        self.qleft: Dict[str, float] = {}
        self.extra: dict = {}
        self.last: Optional[str] = None
        self.events: List[str] = []
        self.done = 0
        self.cs_count = 0

    # queue helpers
    def new_seq(self) -> int:
        self._seq += 1
        return self._seq

    def admit(self, t: float):
        while self.pending and self.pending[0].at <= t + EPS:
            p = self.pending.pop(0)
            self.admitted.append(p.pid)
            self.seq[p.pid] = self.new_seq()
            self.wait_since[p.pid] = p.at
            self.events.append(f"{p.pid} arrived (t={_fmt(p.at)})")

    def ready(self) -> List[str]:
        return [p for p in self.admitted if self.rem[p] > EPS]

    def ready_ordered(self) -> List[str]:
        return sorted(self.ready(), key=lambda p: self.seq[p])

    def next_arrival(self, flt: Optional[Callable[[ProcessInput], bool]] = None) -> Optional[float]:
        for p in self.pending:
            if flt is None or flt(p):
                return p.at
        return None

    def prio(self, pid: str) -> float:
        base = self.byid[pid].priority
        if self.opts.aging > 0:
            gain = int((self.t - self.wait_since[pid] + EPS) // self.opts.aging)
            base = base + gain if self.opts.high_is_priority else base - gain
        return base

    def pkey(self, pid: str) -> float:
        """Sort key where smaller = more urgent."""
        p = self.prio(pid)
        return -p if self.opts.high_is_priority else p

    def tickets(self, pid: str) -> int:
        ps = [q.priority for q in self.procs]
        if self.opts.high_is_priority:
            return max(1, int(self.byid[pid].priority) + 1 - min(0, min(ps)))
        return max(1, int(max(ps) - self.byid[pid].priority + 1))

    # recording
    def snapshot(self) -> Dict[str, float]:
        return {p: self.rem[p] for p in self.ready_ordered()}

    def flush_events(self) -> List[str]:
        ev, self.events = self.events, []
        return ev

    def add_idle(self, until: float):
        self.admit(self.t)
        self.segs.append(GanttSegment("IDLE", self.t, until, "idle"))
        self.steps.append(Step(len(self.steps) + 1, "idle", self.t, until, "IDLE", [], {},
                               self.flush_events(),
                               "No process is ready, CPU stays idle until the next arrival.",
                               f"CPU idle for {_fmt(until - self.t)} units"))
        self.t = until
        self.last = None

    def add_cs(self, cs: float, frm: str, to: str):
        self.admit(self.t)
        self.segs.append(GanttSegment("CS", self.t, self.t + cs, "cs"))
        self.steps.append(Step(len(self.steps) + 1, "cs", self.t, self.t + cs, "CS",
                               [p for p in self.ready_ordered() if p != to], self.snapshot(),
                               self.flush_events(),
                               f"Context switch {frm} → {to} costs {_fmt(cs)} units.",
                               "Overhead"))
        self.t += cs
        self.cs_count += 1
        self.admit(self.t)

    def run(self, pid: str, L: float, reason: str):
        self.admit(self.t)
        snap = self.snapshot()
        waiting = [p for p in self.ready_ordered() if p != pid]
        start = self.t
        end = round(start + L, 6)
        self.first.setdefault(pid, start)
        self.rem[pid] = round(self.rem[pid] - L, 6)
        if self.rem[pid] <= EPS:
            self.rem[pid] = 0.0
        self.t = end
        self.segs.append(GanttSegment(pid, start, end, "run", self.level.get(pid)))
        fin = self.rem[pid] <= EPS
        events = self.flush_events()
        if fin:
            self.completion[pid] = end
            self.final_prio[pid] = int(self.prio(pid))
            self.done += 1
            outcome = f"{pid} completed at t={_fmt(end)}"
            self.events.append(f"{pid} completed at t={_fmt(end)}")
        else:
            self.wait_since[pid] = end
            outcome = f"{pid} ran {_fmt(L)}, remaining {_fmt(self.rem[pid])}"
        self.steps.append(Step(len(self.steps) + 1, "run", start, end, pid, waiting, snap,
                               events, reason, outcome, self.level.get(pid)))
        self.last = pid


# --------------------------------------------------------------------------- #
#  Policies
# --------------------------------------------------------------------------- #
class Policy:
    def init(self, s: _Sim):
        pass

    def pick(self, s: _Sim, ready: List[str]) -> Tuple[str, str]:
        raise NotImplementedError

    def slice(self, s: _Sim, pid: str) -> float:
        return s.rem[pid]

    def after(self, s: _Sim, pid: str, L: float, fin: bool):
        pass


def _why(desc: str, best: str, ready: List[str], val: Callable[[str], str]) -> str:
    if len(ready) == 1:
        return f"{best} is the only ready process."
    others = ", ".join(f"{p}({val(p)})" for p in ready if p != best)
    return f"{desc}: {best}({val(best)}) beats {others}."


class KeyPolicy(Policy):
    """Pick min(key). Optionally preemptive (re-evaluated at arrivals / unit steps)."""

    def __init__(self, keyf, valf, desc, preemptive=False, unit=None, sticky=False):
        self.keyf, self.valf, self.desc = keyf, valf, desc
        self.preemptive, self.unit, self.sticky = preemptive, unit, sticky

    def pick(self, s, ready):
        order = sorted(ready, key=lambda p: s.seq[p])
        best = min(order, key=lambda p: (self.keyf(s, p), 0 if (self.sticky and p == s.last) else 1, s.seq[p]))
        return best, _why(self.desc, best, order, lambda p: self.valf(s, p))

    def slice(self, s, pid):
        L = s.rem[pid]
        if self.preemptive:
            na = s.next_arrival()
            if na is not None:
                L = min(L, na - s.t)
        if self.unit:
            L = min(L, self.unit)
        return L


class QuantumPolicy(Policy):
    def __init__(self, q, pickf, arrival_cap=False):
        self.q, self.pickf, self.arrival_cap = max(q, 0.01), pickf, arrival_cap

    def pick(self, s, ready):
        return self.pickf(s, ready)

    def slice(self, s, pid):
        if s.last != pid or s.qleft.get(pid, 0) <= EPS:
            s.qleft[pid] = self.q
        L = min(s.qleft[pid], s.rem[pid])
        if self.arrival_cap:
            na = s.next_arrival()
            if na is not None:
                L = min(L, na - s.t)
        return L

    def after(self, s, pid, L, fin):
        s.admit(s.t)  # arrivals enter the queue before the preempted process re-joins
        s.qleft[pid] = s.qleft.get(pid, 0) - L
        if not fin and s.qleft[pid] <= EPS:
            s.seq[pid] = s.new_seq()
            s.events.append(f"{pid} used its full quantum and goes to the back of the queue")
        self.post(s, pid, L, fin)

    def post(self, s, pid, L, fin):
        pass


class StridePolicy(QuantumPolicy):
    def init(self, s):
        s.extra["pass"] = {p.pid: 0.0 for p in s.procs}

    def post(self, s, pid, L, fin):
        s.extra["pass"][pid] += (1000.0 / s.tickets(pid)) * (L / self.q)


class MultiLevel(Policy):
    def __init__(self, levels, feedback, opts):
        self.levels, self.feedback, self.opts = levels, feedback, opts

    def init(self, s):
        top = len(self.levels) - 1
        for p in s.procs:
            s.level[p.pid] = 0 if self.feedback else min(max(int(p.queue_level), 0), top)

    def pick(self, s, ready):
        lv = min(s.level[p] for p in ready)
        cand = sorted([p for p in ready if s.level[p] == lv], key=lambda p: s.seq[p])
        algo = self.levels[lv][0]
        if algo == "SJF":
            best = min(cand, key=lambda p: (s.rem[p], s.seq[p]))
            how = f"shortest job in Q{lv}"
        elif algo == "PRIORITY":
            best = min(cand, key=lambda p: (s.pkey(p), s.seq[p]))
            how = f"highest priority in Q{lv}"
        else:
            best = cand[0]
            how = f"head of Q{lv} ({algo})"
        return best, f"Q{lv} is the highest non-empty queue; {best} is the {how}."

    def slice(self, s, pid):
        lv = s.level[pid]
        algo, q = self.levels[lv]
        L = s.rem[pid]
        if algo == "RR" and q > 0:
            if s.last != pid or s.qleft.get(pid, 0) <= EPS:
                s.qleft[pid] = q
            L = min(L, s.qleft[pid])
        top = len(self.levels) - 1
        if self.feedback:
            na = s.next_arrival() if lv > 0 else None
        else:
            na = s.next_arrival(lambda p: min(max(int(p.queue_level), 0), top) < lv)
        if na is not None:
            L = min(L, na - s.t)
        return L

    def after(self, s, pid, L, fin):
        s.admit(s.t)
        lv = s.level[pid]
        algo, q = self.levels[lv]
        if algo == "RR" and q > 0:
            s.qleft[pid] = s.qleft.get(pid, 0) - L
            if not fin and s.qleft[pid] <= EPS:
                if self.feedback and lv < len(self.levels) - 1:
                    s.level[pid] = lv + 1
                    s.events.append(f"{pid} used its quantum and is demoted to Q{lv + 1}")
                else:
                    s.events.append(f"{pid} used its quantum and goes to the back of Q{lv}")
                s.seq[pid] = s.new_seq()


# --------------------------------------------------------------------------- #
#  Main loop
# --------------------------------------------------------------------------- #
def _simulate(procs: List[ProcessInput], opts: SchedOptions, policy: Policy, key: str) -> ScheduleOutput:
    s = _Sim(procs, opts)
    policy.init(s)
    cs = max(0.0, float(opts.cs_time))
    guard = 0
    while s.done < s.n:
        guard += 1
        if guard > 100000:
            raise RuntimeError("Simulation did not terminate (too many steps).")
        s.admit(s.t)
        ready = s.ready()
        if not ready:
            nxt = s.next_arrival()
            s.add_idle(nxt)
            continue
        pid, reason = policy.pick(s, ready)
        if s.last is not None and s.last != pid and s.rem[s.last] > EPS:
            s.preempt[s.last] += 1
            s.events.append(f"{s.last} was preempted with {_fmt(s.rem[s.last])} left")
        if cs > 0 and s.last is not None and s.last != pid:
            s.add_cs(cs, s.last, pid)
        L = min(policy.slice(s, pid), s.rem[pid])
        s.run(pid, L, reason)
        policy.after(s, pid, L, s.rem[pid] <= EPS)
    return _build_output(s, key, opts)


def _merge(raw: List[GanttSegment]) -> List[GanttSegment]:
    out: List[GanttSegment] = []
    for g in raw:
        if out and out[-1].pid == g.pid and out[-1].kind == g.kind and abs(out[-1].end - g.start) < EPS \
                and g.kind != "cs":
            out[-1] = GanttSegment(g.pid, out[-1].start, g.end, g.kind, g.queue_level)
        else:
            out.append(GanttSegment(g.pid, g.start, g.end, g.kind, g.queue_level))
    return out


def _build_output(s: _Sim, key: str, opts: SchedOptions) -> ScheduleOutput:
    info = ALGO_BY_KEY[key]
    results = []
    for p in s.procs:
        ct = round(s.completion[p.pid], 2)
        tat = round(ct - p.at, 2)
        wt = round(tat - p.bt, 2)
        rt = round(s.first[p.pid] - p.at, 2)
        results.append(ProcessResult(p.pid, p.at, p.bt, p.priority, s.final_prio.get(p.pid, p.priority),
                                     p.queue_level, ct, tat, wt, rt, s.first[p.pid],
                                     s.preempt[p.pid], p.deadline))
    n = len(results)
    end = max((g.end for g in s.segs), default=0.0)
    total_bt = sum(p.bt for p in s.procs)
    idle = sum(g.end - g.start for g in s.segs if g.kind == "idle")
    cs_over = sum(g.end - g.start for g in s.segs if g.kind == "cs")
    avg = lambda f: round(sum(f(r) for r in results) / n, 2) if n else 0.0
    out = ScheduleOutput(
        key=key, algorithm=info.name, mode=info.mode, gantt=_merge(s.segs), raw_gantt=s.segs,
        steps=s.steps, results=results, end_time=round(end, 2), idle_time=round(idle, 2),
        cs_count=s.cs_count, cs_overhead=round(cs_over, 2),
        avg_wt=avg(lambda r: r.wt), avg_tat=avg(lambda r: r.tat), avg_rt=avg(lambda r: r.rt),
        avg_ct=avg(lambda r: r.ct),
        throughput=round(n / end, 4) if end > 0 else 0.0,
        cpu_utilization=round(total_bt / end * 100, 2) if end > 0 else 0.0,
        options_text=_options_text(key, opts),
    )
    out.summary = build_summary(out)
    return out


def _options_text(key: str, o: SchedOptions) -> str:
    parts = []
    if key in ("RR", "PRIO_RR", "LOTTERY", "STRIDE"):
        parts.append(f"Time quantum = {_fmt(o.quantum)}")
    if key in ("PRIO_NP", "PRIO_P", "PRIO_RR", "LOTTERY", "STRIDE", "MLQ"):
        parts.append("Higher number = higher priority" if o.high_is_priority
                     else "Lower number = higher priority")
    if key in ("PRIO_NP", "PRIO_P", "PRIO_RR") and o.aging > 0:
        parts.append(f"Aging every {_fmt(o.aging)} units")
    if key == "MLQ":
        parts.append("Queues: " + ", ".join(
            f"Q{i}={a}" + (f"(q={_fmt(q)})" if a == "RR" else "") for i, (a, q) in enumerate(o.mlq_levels)))
    if key == "MLFQ":
        parts.append("Quanta: " + ", ".join(_fmt(q) for q in o.mlfq_quanta) + ", last queue FCFS")
    if key == "LOTTERY":
        parts.append(f"Seed = {o.seed}")
    parts.append(f"Context switch = {_fmt(o.cs_time)}")
    return " · ".join(parts)


# --------------------------------------------------------------------------- #
#  Narrative summary
# --------------------------------------------------------------------------- #
def build_summary(o: ScheduleOutput) -> List[str]:
    L = []
    order = [g.pid for g in o.gantt if g.kind == "run"]
    L.append(f"{o.algorithm} ({o.mode}) scheduled {len(o.results)} processes and finished everything at t={_fmt(o.end_time)}.")
    L.append("Execution order: " + " → ".join(order))
    for r in o.results:
        txt = (f"{r.pid}: arrived at {_fmt(r.at)}, first got the CPU at {_fmt(r.first_start)} "
               f"(response time {_fmt(r.rt)}), needed {_fmt(r.bt)} units, finished at {_fmt(r.ct)}. "
               f"It waited {_fmt(r.wt)} units in total and its turnaround time was {_fmt(r.tat)}.")
        if r.preemptions:
            txt += f" It was preempted {r.preemptions} time(s)."
        if r.deadline is not None:
            txt += " Deadline " + (f"met ({_fmt(r.deadline)})." if r.deadline_met else f"MISSED ({_fmt(r.deadline)}).")
        L.append(txt)
    if o.results:
        w = max(o.results, key=lambda r: r.wt)
        b = min(o.results, key=lambda r: r.wt)
        L.append(f"Longest waiting process: {w.pid} ({_fmt(w.wt)}). Shortest waiting process: {b.pid} ({_fmt(b.wt)}).")
    L.append(f"Average waiting time {_fmt(o.avg_wt)}, average turnaround time {_fmt(o.avg_tat)}, "
             f"average response time {_fmt(o.avg_rt)}.")
    L.append(f"CPU utilization {_fmt(o.cpu_utilization)}%, throughput {o.throughput:g} processes/unit, "
             f"idle time {_fmt(o.idle_time)}, context switches {o.cs_count} (overhead {_fmt(o.cs_overhead)}).")
    return L


# --------------------------------------------------------------------------- #
#  Public API
# --------------------------------------------------------------------------- #
def run_algorithm(key: str, procs: List[ProcessInput], opts: Optional[SchedOptions] = None) -> ScheduleOutput:
    opts = opts or SchedOptions()
    if not procs:
        raise ValueError("Add at least one process.")
    q = opts.quantum
    last_pref = lambda s, p: p
    if key == "FCFS":
        pol = KeyPolicy(lambda s, p: s.seq[p], lambda s, p: f"arrived {_fmt(s.byid[p].at)}", "Earliest arrival")
    elif key == "SJF":
        pol = KeyPolicy(lambda s, p: s.byid[p].bt, lambda s, p: _fmt(s.byid[p].bt), "Smallest burst")
    elif key == "SRTF":
        pol = KeyPolicy(lambda s, p: s.rem[p], lambda s, p: _fmt(s.rem[p]), "Least remaining time",
                        preemptive=True, sticky=True)
    elif key == "LJF":
        pol = KeyPolicy(lambda s, p: -s.byid[p].bt, lambda s, p: _fmt(s.byid[p].bt), "Largest burst")
    elif key == "LRTF":
        pol = KeyPolicy(lambda s, p: -s.rem[p], lambda s, p: _fmt(s.rem[p]), "Most remaining time",
                        preemptive=True, unit=1.0, sticky=True)
    elif key == "RR":
        pol = QuantumPolicy(q, lambda s, r: (min(r, key=lambda p: s.seq[p]),
                                             "Head of the circular ready queue."))
    elif key == "PRIO_NP":
        pol = KeyPolicy(lambda s, p: s.pkey(p), lambda s, p: _fmt(s.prio(p)), "Best priority")
    elif key == "PRIO_P":
        pol = KeyPolicy(lambda s, p: s.pkey(p), lambda s, p: _fmt(s.prio(p)), "Best priority",
                        preemptive=True, unit=1.0 if opts.aging > 0 else None, sticky=True)
    elif key == "PRIO_RR":
        def pick(s, r):
            best_key = min(s.pkey(p) for p in r)
            grp = [p for p in r if s.pkey(p) == best_key]
            b = min(grp, key=lambda p: s.seq[p])
            return b, f"Priority {_fmt(s.prio(b))} is the best level; {b} is first in the Round Robin of that level."
        pol = QuantumPolicy(q, pick, arrival_cap=True)
    elif key == "HRRN":
        ratio = lambda s, p: (s.t - s.byid[p].at + s.byid[p].bt) / s.byid[p].bt
        pol = KeyPolicy(lambda s, p: -ratio(s, p), lambda s, p: f"{ratio(s, p):.2f}", "Highest response ratio")
    elif key == "MLQ":
        pol = MultiLevel([(a, qq) for a, qq in opts.mlq_levels], False, opts)
    elif key == "MLFQ":
        lv = [("RR", qq) for qq in opts.mlfq_quanta] + [("FCFS", 0.0)]
        pol = MultiLevel(lv, True, opts)
    elif key == "EDF":
        dl = lambda s, p: s.byid[p].deadline if s.byid[p].deadline is not None else INF
        pol = KeyPolicy(dl, lambda s, p: "-" if dl(s, p) == INF else _fmt(dl(s, p)), "Nearest deadline",
                        preemptive=True, sticky=True)
    elif key == "LOTTERY":
        rng = random.Random(opts.seed)

        def pick(s, r):
            r = sorted(r, key=lambda p: s.seq[p])
            tot = sum(s.tickets(p) for p in r)
            draw = rng.randint(1, tot)
            acc = 0
            for p in r:
                acc += s.tickets(p)
                if draw <= acc:
                    return p, f"Lottery: ticket #{draw} of {tot} drawn → {p} (holds {s.tickets(p)} tickets)."
        pol = QuantumPolicy(q, pick)
    elif key == "STRIDE":
        def pick(s, r):
            b = min(r, key=lambda p: (s.extra["pass"][p], s.seq[p]))
            return b, (f"Smallest pass value: {b}({s.extra['pass'][b]:.0f}), "
                       f"stride {1000 / s.tickets(b):.0f} ({s.tickets(b)} tickets).")
        pol = StridePolicy(q, pick)
    else:
        raise ValueError(f"Unknown algorithm: {key}")
    return _simulate(procs, opts, pol, key)


def run_all(procs: List[ProcessInput], opts: Optional[SchedOptions] = None) -> Dict[str, ScheduleOutput]:
    return {a.key: run_algorithm(a.key, procs, opts) for a in ALGOS}


def comparison_rows(outs: Dict[str, ScheduleOutput]) -> List[dict]:
    rows = []
    for k, o in outs.items():
        rows.append(dict(key=k, name=o.algorithm, mode=o.mode, avg_wt=o.avg_wt, avg_tat=o.avg_tat,
                         avg_rt=o.avg_rt, util=o.cpu_utilization, throughput=o.throughput,
                         cs=o.cs_count, end=o.end_time))
    return sorted(rows, key=lambda r: (r["avg_wt"], r["avg_tat"]))


def comparison_text(rows: List[dict]) -> List[str]:
    if not rows:
        return []
    bw = min(rows, key=lambda r: r["avg_wt"])
    bt = min(rows, key=lambda r: r["avg_tat"])
    br = min(rows, key=lambda r: r["avg_rt"])
    ww = max(rows, key=lambda r: r["avg_wt"])
    return [f"Best average waiting time: {bw['name']} ({_fmt(bw['avg_wt'])}).",
            f"Best average turnaround time: {bt['name']} ({_fmt(bt['avg_tat'])}).",
            f"Best average response time: {br['name']} ({_fmt(br['avg_rt'])}).",
            f"Worst average waiting time: {ww['name']} ({_fmt(ww['avg_wt'])})."]
