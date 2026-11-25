from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class ProcessInput:
    pid: str
    at: float
    bt: float
    priority: int = 0
    queue_level: int = 0  # 0 = Foreground/High, 1 = Background/Low


@dataclass
class ProcessResult:
    pid: str
    at: float
    bt: float
    initial_priority: int
    final_priority: int
    queue_level: int
    ct: float
    tat: float
    wt: float
    rt: float


@dataclass
class GanttSegment:
    pid: str              # Process ID or 'IDLE'
    start: float
    end: float
    cs_before: bool = False
    is_idle: bool = False
    queue_level: Optional[int] = None


@dataclass
class ScheduleOutput:
    algorithm: str
    mode: str
    gantt: List[GanttSegment]
    context_switch_points: List[float]
    context_switch_count: int
    total_cs_overhead: float
    results: List[ProcessResult]
    avg_wt: float
    avg_tat: float
    avg_rt: float
    avg_bt: float
    throughput: float
    cpu_utilization: float
    iteration_logs: List[str]


def _fmt(val: float) -> str:
    r = round(float(val), 2)
    if r == 0:
        return "0"
    if r == int(r):
        return str(int(r))
    return f"{r:.2f}".rstrip("0").rstrip(".")


def _merge_gantt_segments(raw_segments: List[GanttSegment]) -> List[GanttSegment]:
    if not raw_segments:
        return []
    merged = [
        GanttSegment(
            pid=raw_segments[0].pid,
            start=round(raw_segments[0].start, 4),
            end=round(raw_segments[0].end, 4),
            cs_before=raw_segments[0].cs_before,
            is_idle=(raw_segments[0].pid == "IDLE"),
            queue_level=raw_segments[0].queue_level,
        )
    ]
    for seg in raw_segments[1:]:
        prev = merged[-1]
        if (
            prev.pid == seg.pid
            and prev.queue_level == seg.queue_level
            and not seg.cs_before
            and abs(prev.end - seg.start) < 1e-6
        ):
            prev.end = round(seg.end, 4)
        else:
            merged.append(
                GanttSegment(
                    pid=seg.pid,
                    start=round(seg.start, 4),
                    end=round(seg.end, 4),
                    cs_before=seg.cs_before,
                    is_idle=(seg.pid == "IDLE"),
                    queue_level=seg.queue_level,
                )
            )
    return merged


def _apply_context_switch(
    current_time: float,
    last_pid: Optional[str],
    next_pid: str,
    cs_enabled: bool,
    cs_time: float,
    cs_points: List[float],
    logs: List[str],
) -> Tuple[float, int, bool]:
    if cs_enabled and cs_time > 0 and last_pid is not None and last_pid != next_pid:
        sw_start = round(current_time, 4)
        sw_end = round(current_time + cs_time, 4)
        cs_points.append(sw_start)
        logs.append(
            f"  [Context Switch] {last_pid} -> {next_pid} | "
            f"t={_fmt(sw_start)} -> {_fmt(sw_end)} (+{_fmt(cs_time)})"
        )
        return sw_end, 1, True
    return current_time, 0, False


def _build_output(
    algorithm: str,
    mode: str,
    processes: List[ProcessInput],
    completion: Dict[str, float],
    first_start: Dict[str, float],
    final_prio: Dict[str, int],
    raw_gantt: List[GanttSegment],
    cs_points: List[float],
    cs_count: int,
    cs_time: float,
    logs: List[str],
) -> ScheduleOutput:
    gantt = _merge_gantt_segments(raw_gantt)
    results: List[ProcessResult] = []
    for p in processes:
        ct = round(completion[p.pid], 2)
        tat = round(ct - p.at, 2)
        wt = round(tat - p.bt, 2)
        rt = round(first_start[p.pid] - p.at, 2)
        results.append(
            ProcessResult(
                pid=p.pid,
                at=p.at,
                bt=p.bt,
                initial_priority=p.priority,
                final_priority=final_prio.get(p.pid, p.priority),
                queue_level=p.queue_level,
                ct=ct,
                tat=tat,
                wt=wt,
                rt=rt,
            )
        )

    n = len(results)
    total_bt = sum(p.bt for p in processes)
    end_time = max((seg.end for seg in gantt), default=0.0)
    total_cs_overhead = round(cs_count * cs_time, 2)
    avg_wt = round(sum(r.wt for r in results) / n, 2) if n else 0.0
    avg_tat = round(sum(r.tat for r in results) / n, 2) if n else 0.0
    avg_rt = round(sum(r.rt for r in results) / n, 2) if n else 0.0
    avg_bt = round(total_bt / n, 2) if n else 0.0
    throughput = round(n / end_time, 4) if end_time > 0 else 0.0
    cpu_utilization = round((total_bt / end_time) * 100, 2) if end_time > 0 else 0.0

    return ScheduleOutput(
        algorithm=algorithm,
        mode=mode,
        gantt=gantt,
        context_switch_points=[round(x, 2) for x in cs_points],
        context_switch_count=cs_count,
        total_cs_overhead=total_cs_overhead,
        results=results,
        avg_wt=avg_wt,
        avg_tat=avg_tat,
        avg_rt=avg_rt,
        avg_bt=avg_bt,
        throughput=throughput,
        cpu_utilization=cpu_utilization,
        iteration_logs=logs,
    )


def run_fcfs(
    processes: List[ProcessInput], cs_enabled: bool = False, cs_time: float = 0.0
) -> ScheduleOutput:
    procs = sorted(processes, key=lambda p: (p.at, p.pid))
    t = 0.0
    last_pid: Optional[str] = None
    gantt, cs_points = [], []
    cs_count = 0
    completion, first_start, final_prio = {}, {}, {p.pid: p.priority for p in procs}
    logs = [
        f"=== FCFS (Non-Preemptive{f', CS={_fmt(cs_time)}' if cs_enabled and cs_time > 0 else ''}) ==="
    ]

    for step, p in enumerate(procs, start=1):
        if t < p.at:
            gantt.append(GanttSegment(pid="IDLE", start=t, end=p.at, is_idle=True))
            logs.append(f"Idle | t={_fmt(t)}->{_fmt(p.at)}: CPU IDLE")
            t = p.at
        t, added_cs, had_cs = _apply_context_switch(
            t, last_pid, p.pid, cs_enabled, cs_time, cs_points, logs
        )
        cs_count += added_cs
        start_t, end_t = t, round(t + p.bt, 4)
        first_start[p.pid], completion[p.pid] = start_t, end_t
        gantt.append(GanttSegment(pid=p.pid, start=start_t, end=end_t, cs_before=had_cs))
        tat, wt, rt = end_t - p.at, (end_t - p.at) - p.bt, start_t - p.at
        logs.append(
            f"Step {step} | t={_fmt(start_t)}->{_fmt(end_t)}: {p.pid} "
            f"(AT={_fmt(p.at)}, BT={_fmt(p.bt)}) | "
            f"CT={_fmt(end_t)}, TAT={_fmt(tat)}, WT={_fmt(wt)}, RT={_fmt(rt)}"
        )
        t, last_pid = end_t, p.pid

    return _build_output(
        "FCFS",
        "Non-Preemptive",
        processes,
        completion,
        first_start,
        final_prio,
        gantt,
        cs_points,
        cs_count,
        cs_time if cs_enabled else 0.0,
        logs,
    )


def run_sjf_non_preemptive(
    processes: List[ProcessInput], cs_enabled: bool = False, cs_time: float = 0.0
) -> ScheduleOutput:
    remaining = list(processes)
    t = 0.0
    last_pid: Optional[str] = None
    gantt, cs_points = [], []
    cs_count = 0
    completion, first_start, final_prio = {}, {}, {p.pid: p.priority for p in processes}
    logs = [
        f"=== SJF (Non-Preemptive{f', CS={_fmt(cs_time)}' if cs_enabled and cs_time > 0 else ''}) ==="
    ]
    step = 1

    while remaining:
        ready = [p for p in remaining if p.at <= t + 1e-9]
        if not ready:
            next_at = min(p.at for p in remaining)
            gantt.append(GanttSegment(pid="IDLE", start=t, end=next_at, is_idle=True))
            logs.append(f"Idle | t={_fmt(t)}->{_fmt(next_at)}: CPU IDLE")
            t = next_at
            continue

        chosen = min(ready, key=lambda p: (p.bt, p.at, p.pid))
        remaining.remove(chosen)
        t, added_cs, had_cs = _apply_context_switch(
            t, last_pid, chosen.pid, cs_enabled, cs_time, cs_points, logs
        )
        cs_count += added_cs
        start_t, end_t = t, round(t + chosen.bt, 4)
        first_start[chosen.pid], completion[chosen.pid] = start_t, end_t
        gantt.append(
            GanttSegment(pid=chosen.pid, start=start_t, end=end_t, cs_before=had_cs)
        )
        tat, wt, rt = end_t - chosen.at, (end_t - chosen.at) - chosen.bt, start_t - chosen.at
        logs.append(
            f"Step {step} | t={_fmt(start_t)}->{_fmt(end_t)}: Selected {chosen.pid} "
            f"(BT={_fmt(chosen.bt)}) | CT={_fmt(end_t)}, TAT={_fmt(tat)}, WT={_fmt(wt)}, RT={_fmt(rt)}"
        )
        t, last_pid, step = end_t, chosen.pid, step + 1

    return _build_output(
        "SJF",
        "Non-Preemptive",
        processes,
        completion,
        first_start,
        final_prio,
        gantt,
        cs_points,
        cs_count,
        cs_time if cs_enabled else 0.0,
        logs,
    )


def run_srtf_preemptive(
    processes: List[ProcessInput],
    cs_enabled: bool = False,
    cs_time: float = 0.0,
    tick: float = 1.0,
) -> ScheduleOutput:
    rem_bt = {p.pid: p.bt for p in processes}
    completed = set()
    n = len(processes)
    t = 0.0
    last_pid: Optional[str] = None
    gantt, cs_points = [], []
    cs_count = 0
    completion, first_start, final_prio = {}, {}, {p.pid: p.priority for p in processes}
    logs = [
        f"=== SRTF / Preemptive SJF (tick={_fmt(tick)}{f', CS={_fmt(cs_time)}' if cs_enabled and cs_time > 0 else ''}) ==="
    ]

    while len(completed) < n:
        ready = [
            p for p in processes if p.pid not in completed and p.at <= t + 1e-9
        ]
        if not ready:
            next_at = min(p.at for p in processes if p.pid not in completed)
            gantt.append(GanttSegment(pid="IDLE", start=t, end=next_at, is_idle=True))
            logs.append(f"Idle | t={_fmt(t)}->{_fmt(next_at)}: CPU IDLE")
            t = next_at
            continue

        chosen = min(
            ready,
            key=lambda p: (
                rem_bt[p.pid],
                0 if p.pid == last_pid else 1,
                p.at,
                p.pid,
            ),
        )
        t, added_cs, had_cs = _apply_context_switch(
            t, last_pid, chosen.pid, cs_enabled, cs_time, cs_points, logs
        )
        cs_count += added_cs
        if chosen.pid not in first_start:
            first_start[chosen.pid] = t

        future_arrivals = [
            p.at
            for p in processes
            if p.pid not in completed and p.at > t + 1e-9
        ]
        if future_arrivals:
            next_event = min(future_arrivals)
            run_for = round(min(rem_bt[chosen.pid], next_event - t), 4)
        else:
            run_for = rem_bt[chosen.pid]

        start_t, end_t = t, round(t + run_for, 4)
        rem_bt[chosen.pid] = round(rem_bt[chosen.pid] - run_for, 4)
        gantt.append(
            GanttSegment(pid=chosen.pid, start=start_t, end=end_t, cs_before=had_cs)
        )
        if rem_bt[chosen.pid] <= 1e-6:
            rem_bt[chosen.pid] = 0.0
            completed.add(chosen.pid)
            completion[chosen.pid] = end_t
            tat, wt, rt = (
                end_t - chosen.at,
                (end_t - chosen.at) - chosen.bt,
                first_start[chosen.pid] - chosen.at,
            )
            logs.append(
                f"t={_fmt(start_t)}->{_fmt(end_t)}: {chosen.pid} COMPLETED | "
                f"CT={_fmt(end_t)}, TAT={_fmt(tat)}, WT={_fmt(wt)}, RT={_fmt(rt)}"
            )
        else:
            logs.append(
                f"t={_fmt(start_t)}->{_fmt(end_t)}: {chosen.pid} ran "
                f"(rem BT={_fmt(rem_bt[chosen.pid])})"
            )
        t, last_pid = end_t, chosen.pid

    return _build_output(
        "SRTF",
        "Preemptive",
        processes,
        completion,
        first_start,
        final_prio,
        gantt,
        cs_points,
        cs_count,
        cs_time if cs_enabled else 0.0,
        logs,
    )


def run_priority_non_preemptive(
    processes: List[ProcessInput],
    aging_enabled: bool = False,
    aging_interval: float = 4.0,
    cs_enabled: bool = False,
    cs_time: float = 0.0,
) -> ScheduleOutput:
    remaining = list(processes)
    t = 0.0
    last_pid: Optional[str] = None
    gantt, cs_points = [], []
    cs_count = 0
    completion, first_start = {}, {}
    final_prio = {p.pid: p.priority for p in processes}
    mode_label = (
        f"Non-Preemptive{' + Aging(interval=' + _fmt(aging_interval) + ')' if aging_enabled else ''}"
    )
    logs = [
        f"=== Priority Scheduling ({mode_label}{f', CS={_fmt(cs_time)}' if cs_enabled and cs_time > 0 else ''}) ==="
    ]
    iteration = 1

    while remaining:
        ready = [p for p in remaining if p.at <= t + 1e-9]
        if not ready:
            next_at = min(p.at for p in remaining)
            gantt.append(GanttSegment(pid="IDLE", start=t, end=next_at, is_idle=True))
            logs.append(f"Idle | t={_fmt(t)}->{_fmt(next_at)}: CPU IDLE")
            t = next_at
            continue

        scored, iter_rows = [], []
        for p in ready:
            wt_so_far = max(0.0, t - p.at)
            aging_val = (
                int(wt_so_far // aging_interval)
                if (aging_enabled and aging_interval > 0)
                else 0
            )
            eff_prio = max(0, p.priority - aging_val)
            final_prio[p.pid] = eff_prio
            scored.append((eff_prio, p.at, p.pid, p))
            if aging_enabled:
                iter_rows.append(
                    f"  {p.pid}: IP={p.priority}, WT={_fmt(wt_so_far)}, "
                    f"Aging=floor({_fmt(wt_so_far)}/{_fmt(aging_interval)})={aging_val}, "
                    f"Effective={eff_prio}"
                )
            else:
                iter_rows.append(
                    f"  {p.pid}: Priority={p.priority}, AT={_fmt(p.at)}, BT={_fmt(p.bt)}"
                )

        scored.sort(key=lambda x: (x[0], x[1], x[2]))
        eff_prio, _, _, chosen = scored[0]
        remaining.remove(chosen)
        logs.append(f"Iteration {iteration} (at t={_fmt(t)}):")
        logs.extend(iter_rows)

        t, added_cs, had_cs = _apply_context_switch(
            t, last_pid, chosen.pid, cs_enabled, cs_time, cs_points, logs
        )
        cs_count += added_cs
        start_t, end_t = t, round(t + chosen.bt, 4)
        first_start[chosen.pid], completion[chosen.pid] = start_t, end_t
        gantt.append(
            GanttSegment(pid=chosen.pid, start=start_t, end=end_t, cs_before=had_cs)
        )
        tat, wt, rt = end_t - chosen.at, (end_t - chosen.at) - chosen.bt, start_t - chosen.at
        logs.append(
            f"  -> Selected {chosen.pid} (Effective Priority={eff_prio}) | "
            f"t={_fmt(start_t)}->{_fmt(end_t)} | CT={_fmt(end_t)}, TAT={_fmt(tat)}, "
            f"WT={_fmt(wt)}, RT={_fmt(rt)}"
        )
        t, last_pid, iteration = end_t, chosen.pid, iteration + 1

    return _build_output(
        "Priority",
        mode_label,
        processes,
        completion,
        first_start,
        final_prio,
        gantt,
        cs_points,
        cs_count,
        cs_time if cs_enabled else 0.0,
        logs,
    )


def run_priority_preemptive(
    processes: List[ProcessInput],
    aging_enabled: bool = False,
    aging_interval: float = 3.0,
    cs_enabled: bool = False,
    cs_time: float = 0.0,
) -> ScheduleOutput:
    rem_bt = {p.pid: p.bt for p in processes}
    wait_accum = {p.pid: 0.0 for p in processes}
    eff_prio = {p.pid: p.priority for p in processes}
    completed = set()
    n = len(processes)
    t = 0.0
    last_pid: Optional[str] = None
    gantt, cs_points = [], []
    cs_count = 0
    completion, first_start = {}, {}
    mode_label = (
        f"Preemptive{' + Aging(interval=' + _fmt(aging_interval) + ')' if aging_enabled else ''}"
    )
    logs = [
        f"=== Priority Scheduling ({mode_label}{f', CS={_fmt(cs_time)}' if cs_enabled and cs_time > 0 else ''}) ==="
    ]

    while len(completed) < n:
        ready = [
            p for p in processes if p.pid not in completed and p.at <= t + 1e-9
        ]
        if not ready:
            next_at = min(p.at for p in processes if p.pid not in completed)
            gantt.append(GanttSegment(pid="IDLE", start=t, end=next_at, is_idle=True))
            logs.append(f"Idle | t={_fmt(t)}->{_fmt(next_at)}: CPU IDLE")
            t = next_at
            continue

        for p in ready:
            if aging_enabled and aging_interval > 0:
                eff_prio[p.pid] = max(
                    0, p.priority - int(wait_accum[p.pid] // aging_interval)
                )
            else:
                eff_prio[p.pid] = p.priority

        chosen = min(
            ready,
            key=lambda p: (
                eff_prio[p.pid],
                0 if p.pid == last_pid else 1,
                p.at,
                p.pid,
            ),
        )
        prev_t = t
        t, added_cs, had_cs = _apply_context_switch(
            t, last_pid, chosen.pid, cs_enabled, cs_time, cs_points, logs
        )
        cs_count += added_cs
        cs_dt = round(t - prev_t, 4)
        if cs_dt > 0 and aging_enabled:
            for p in ready:
                if p.pid != chosen.pid:
                    wait_accum[p.pid] = round(wait_accum[p.pid] + cs_dt, 4)

        if chosen.pid not in first_start:
            first_start[chosen.pid] = t

        future_arrivals = [
            p.at
            for p in processes
            if p.pid not in completed and p.at > t + 1e-9
        ]
        step_dt = min(1.0, rem_bt[chosen.pid])
        if future_arrivals:
            step_dt = min(step_dt, round(min(future_arrivals) - t, 4))
        step_dt = max(1e-4, round(step_dt, 4))

        start_t, end_t = t, round(t + step_dt, 4)
        rem_bt[chosen.pid] = round(rem_bt[chosen.pid] - step_dt, 4)
        for p in ready:
            if p.pid != chosen.pid:
                wait_accum[p.pid] = round(wait_accum[p.pid] + step_dt, 4)

        gantt.append(
            GanttSegment(pid=chosen.pid, start=start_t, end=end_t, cs_before=had_cs)
        )
        if rem_bt[chosen.pid] <= 1e-6:
            rem_bt[chosen.pid] = 0.0
            completed.add(chosen.pid)
            completion[chosen.pid] = end_t
            tat, wt, rt = (
                end_t - chosen.at,
                (end_t - chosen.at) - chosen.bt,
                first_start[chosen.pid] - chosen.at,
            )
            logs.append(
                f"t={_fmt(start_t)}->{_fmt(end_t)}: {chosen.pid} "
                f"(Prio={eff_prio[chosen.pid]}) COMPLETED | "
                f"CT={_fmt(end_t)}, TAT={_fmt(tat)}, WT={_fmt(wt)}, RT={_fmt(rt)}"
            )
        else:
            logs.append(
                f"t={_fmt(start_t)}->{_fmt(end_t)}: {chosen.pid} "
                f"(Prio={eff_prio[chosen.pid]}) ran (rem BT={_fmt(rem_bt[chosen.pid])})"
            )
        t, last_pid = end_t, chosen.pid

    return _build_output(
        "Priority",
        mode_label,
        processes,
        completion,
        first_start,
        eff_prio,
        gantt,
        cs_points,
        cs_count,
        cs_time if cs_enabled else 0.0,
        logs,
    )


def run_round_robin(
    processes: List[ProcessInput],
    quantum: float = 2.0,
    cs_enabled: bool = False,
    cs_time: float = 0.0,
) -> ScheduleOutput:
    if quantum <= 0:
        raise ValueError("Time quantum must be greater than 0.")

    procs = sorted(processes, key=lambda p: (p.at, p.pid))
    rem_bt = {p.pid: p.bt for p in procs}
    arrived, completed = set(), set()
    ready_queue: List[ProcessInput] = []
    n = len(procs)
    t = 0.0
    last_pid: Optional[str] = None
    gantt, cs_points = [], []
    cs_count = 0
    completion, first_start, final_prio = {}, {}, {p.pid: p.priority for p in procs}
    logs = [
        f"=== Round Robin (Quantum={_fmt(quantum)}{f', CS={_fmt(cs_time)}' if cs_enabled and cs_time > 0 else ''}) ==="
    ]

    def enqueue_arrivals(up_to_t: float):
        for p in procs:
            if p.pid not in arrived and p.at <= up_to_t + 1e-9:
                ready_queue.append(p)
                arrived.add(p.pid)

    enqueue_arrivals(t)
    step = 1
    while len(completed) < n:
        if not ready_queue:
            next_at = min(p.at for p in procs if p.pid not in arrived)
            gantt.append(GanttSegment(pid="IDLE", start=t, end=next_at, is_idle=True))
            logs.append(f"Idle | t={_fmt(t)}->{_fmt(next_at)}: CPU IDLE")
            t = next_at
            enqueue_arrivals(t)
            continue

        chosen = ready_queue.pop(0)
        t, added_cs, had_cs = _apply_context_switch(
            t, last_pid, chosen.pid, cs_enabled, cs_time, cs_points, logs
        )
        cs_count += added_cs
        enqueue_arrivals(t)
        if chosen.pid not in first_start:
            first_start[chosen.pid] = t

        run_for = min(quantum, rem_bt[chosen.pid])
        start_t, end_t = t, round(t + run_for, 4)
        rem_bt[chosen.pid] = round(rem_bt[chosen.pid] - run_for, 4)
        gantt.append(
            GanttSegment(pid=chosen.pid, start=start_t, end=end_t, cs_before=had_cs)
        )
        t = end_t
        enqueue_arrivals(t)

        if rem_bt[chosen.pid] <= 1e-6:
            rem_bt[chosen.pid] = 0.0
            completed.add(chosen.pid)
            completion[chosen.pid] = end_t
            tat, wt, rt = (
                end_t - chosen.at,
                (end_t - chosen.at) - chosen.bt,
                first_start[chosen.pid] - chosen.at,
            )
            logs.append(
                f"Step {step} | t={_fmt(start_t)}->{_fmt(end_t)}: {chosen.pid} COMPLETED | "
                f"CT={_fmt(end_t)}, TAT={_fmt(tat)}, WT={_fmt(wt)}, RT={_fmt(rt)}"
            )
        else:
            ready_queue.append(chosen)
            logs.append(
                f"Step {step} | t={_fmt(start_t)}->{_fmt(end_t)}: {chosen.pid} "
                f"ran {_fmt(run_for)} (rem BT={_fmt(rem_bt[chosen.pid])})"
            )
        last_pid, step = chosen.pid, step + 1

    return _build_output(
        "Round Robin",
        f"Preemptive (Q={_fmt(quantum)})",
        processes,
        completion,
        first_start,
        final_prio,
        gantt,
        cs_points,
        cs_count,
        cs_time if cs_enabled else 0.0,
        logs,
    )


def run_hrrn(
    processes: List[ProcessInput], cs_enabled: bool = False, cs_time: float = 0.0
) -> ScheduleOutput:
    remaining = list(processes)
    t = 0.0
    last_pid: Optional[str] = None
    gantt, cs_points = [], []
    cs_count = 0
    completion, first_start, final_prio = {}, {}, {p.pid: p.priority for p in processes}
    logs = [
        f"=== HRRN (Non-Preemptive{f', CS={_fmt(cs_time)}' if cs_enabled and cs_time > 0 else ''}) ==="
    ]
    iteration = 1

    while remaining:
        ready = [p for p in remaining if p.at <= t + 1e-9]
        if not ready:
            next_at = min(p.at for p in remaining)
            gantt.append(GanttSegment(pid="IDLE", start=t, end=next_at, is_idle=True))
            logs.append(f"Idle | t={_fmt(t)}->{_fmt(next_at)}: CPU IDLE")
            t = next_at
            continue

        ratios = []
        logs.append(f"Iteration {iteration} (at t={_fmt(t)}):")
        for p in ready:
            wt_so_far = max(0.0, t - p.at)
            rr = (wt_so_far + p.bt) / p.bt
            ratios.append((rr, p.at, p.pid, p, wt_so_far))
            logs.append(
                f"  {p.pid}: WT={_fmt(wt_so_far)}, BT={_fmt(p.bt)}, "
                f"RR = ({_fmt(wt_so_far)} + {_fmt(p.bt)}) / {_fmt(p.bt)} = {rr:.2f}"
            )

        ratios.sort(key=lambda x: (-x[0], x[1], x[2]))
        best_rr, _, _, chosen, _ = ratios[0]
        remaining.remove(chosen)

        t, added_cs, had_cs = _apply_context_switch(
            t, last_pid, chosen.pid, cs_enabled, cs_time, cs_points, logs
        )
        cs_count += added_cs
        start_t, end_t = t, round(t + chosen.bt, 4)
        first_start[chosen.pid], completion[chosen.pid] = start_t, end_t
        gantt.append(
            GanttSegment(pid=chosen.pid, start=start_t, end=end_t, cs_before=had_cs)
        )
        tat, wt, rt = end_t - chosen.at, (end_t - chosen.at) - chosen.bt, start_t - chosen.at
        logs.append(
            f"  -> Selected {chosen.pid} (Highest RR={best_rr:.2f}) | "
            f"t={_fmt(start_t)}->{_fmt(end_t)} | CT={_fmt(end_t)}, TAT={_fmt(tat)}, "
            f"WT={_fmt(wt)}, RT={_fmt(rt)}"
        )
        t, last_pid, iteration = end_t, chosen.pid, iteration + 1

    return _build_output(
        "HRRN",
        "Non-Preemptive",
        processes,
        completion,
        first_start,
        final_prio,
        gantt,
        cs_points,
        cs_count,
        cs_time if cs_enabled else 0.0,
        logs,
    )


def run_multilevel_queue(
    processes: List[ProcessInput],
    q0_policy: str = "RR",
    q0_quantum: float = 2.0,
    q1_policy: str = "FCFS",
    q1_quantum: float = 4.0,
    cs_enabled: bool = False,
    cs_time: float = 0.0,
) -> ScheduleOutput:
    """
    Multi-Level Queue (MLQ) Scheduling:
    - Queue 0 (Foreground/High): runs 'RR' or 'FCFS' (preemptive over lower queues)
    - Queue 1 (Background/Low): runs 'FCFS', 'SJF', or 'RR' when Q0 is empty
    """
    if q0_policy.upper() == "RR" and q0_quantum <= 0:
        raise ValueError("Queue 0 Quantum must be greater than 0.")
    if q1_policy.upper() == "RR" and q1_quantum <= 0:
        raise ValueError("Queue 1 Quantum must be greater than 0.")

    rem_bt = {p.pid: p.bt for p in processes}
    completed = set()
    n = len(processes)
    t = 0.0
    last_pid: Optional[str] = None
    gantt, cs_points = [], []
    cs_count = 0
    completion, first_start = {}, {}
    final_prio = {p.pid: p.priority for p in processes}
    rr_q0: List[str] = []
    rr_q1: List[str] = []
    known_arrived = set()

    q0_desc = f"RR(Q={_fmt(q0_quantum)})" if q0_policy.upper() == "RR" else "FCFS"
    q1_desc = f"RR(Q={_fmt(q1_quantum)})" if q1_policy.upper() == "RR" else q1_policy.upper()
    mode_label = (
        f"MLQ (Q0={q0_desc}, Q1={q1_desc}"
        f"{f', CS={_fmt(cs_time)}' if cs_enabled and cs_time > 0 else ''})"
    )
    logs = [f"=== Multi-Level Queue ({mode_label}) ==="]

    def sync_arrivals(now_t: float):
        for p in sorted(processes, key=lambda x: (x.at, x.pid)):
            if (
                p.pid not in completed
                and p.pid not in known_arrived
                and p.at <= now_t + 1e-9
            ):
                known_arrived.add(p.pid)
                if p.queue_level == 0 and p.pid not in rr_q0:
                    rr_q0.append(p.pid)
                elif p.queue_level != 0 and p.pid not in rr_q1:
                    rr_q1.append(p.pid)

    sync_arrivals(t)
    proc_map = {p.pid: p for p in processes}

    while len(completed) < n:
        sync_arrivals(t)
        ready_q0 = [pid for pid in rr_q0 if pid not in completed]
        ready_q1 = [pid for pid in rr_q1 if pid not in completed]

        if not ready_q0 and not ready_q1:
            rem_procs = [p for p in processes if p.pid not in completed]
            next_at = min(p.at for p in rem_procs)
            gantt.append(GanttSegment(pid="IDLE", start=t, end=next_at, is_idle=True))
            logs.append(f"Idle | t={_fmt(t)}->{_fmt(next_at)}: CPU IDLE")
            t = next_at
            sync_arrivals(t)
            continue

        if ready_q0:
            q_level = 0
            if q0_policy.upper() == "RR":
                chosen_id = ready_q0[0]
                rr_q0.remove(chosen_id)
                slice_len = min(q0_quantum, rem_bt[chosen_id])
            else:
                chosen_id = min(ready_q0, key=lambda pid: (proc_map[pid].at, pid))
                rr_q0.remove(chosen_id)
                slice_len = rem_bt[chosen_id]
        else:
            q_level = 1
            pol1 = q1_policy.upper()
            if pol1 == "RR":
                chosen_id = ready_q1[0]
                rr_q1.remove(chosen_id)
                slice_len = min(q1_quantum, rem_bt[chosen_id])
            elif pol1 == "SJF":
                chosen_id = min(
                    ready_q1, key=lambda pid: (rem_bt[pid], proc_map[pid].at, pid)
                )
                rr_q1.remove(chosen_id)
                slice_len = rem_bt[chosen_id]
            else:
                chosen_id = min(ready_q1, key=lambda pid: (proc_map[pid].at, pid))
                rr_q1.remove(chosen_id)
                slice_len = rem_bt[chosen_id]

        chosen = proc_map[chosen_id]
        t, added_cs, had_cs = _apply_context_switch(
            t, last_pid, chosen.pid, cs_enabled, cs_time, cs_points, logs
        )
        cs_count += added_cs
        sync_arrivals(t)

        if chosen.pid not in first_start:
            first_start[chosen.pid] = t

        # Preempt Q1 immediately if a Q0 process arrives mid-burst
        if q_level == 1:
            future_q0 = [
                p.at
                for p in processes
                if p.pid not in completed
                and p.queue_level == 0
                and t + 1e-9 < p.at < t + slice_len - 1e-9
            ]
            if future_q0:
                slice_len = min(future_q0) - t

        slice_len = round(slice_len, 4)
        start_t, end_t = t, round(t + slice_len, 4)
        rem_bt[chosen.pid] = round(rem_bt[chosen.pid] - slice_len, 4)
        gantt.append(
            GanttSegment(
                pid=chosen.pid,
                start=start_t,
                end=end_t,
                cs_before=had_cs,
                queue_level=q_level,
            )
        )
        t = end_t
        sync_arrivals(t)

        if rem_bt[chosen.pid] <= 1e-6:
            rem_bt[chosen.pid] = 0.0
            completed.add(chosen.pid)
            completion[chosen.pid] = end_t
            tat, wt, rt = (
                end_t - chosen.at,
                (end_t - chosen.at) - chosen.bt,
                first_start[chosen.pid] - chosen.at,
            )
            logs.append(
                f"[Q{q_level}] t={_fmt(start_t)}->{_fmt(end_t)}: {chosen.pid} COMPLETED | "
                f"CT={_fmt(end_t)}, TAT={_fmt(tat)}, WT={_fmt(wt)}, RT={_fmt(rt)}"
            )
        else:
            if q_level == 0 and q0_policy.upper() == "RR" and chosen.pid not in rr_q0:
                rr_q0.append(chosen.pid)
            elif q_level == 1 and q1_policy.upper() == "RR" and chosen.pid not in rr_q1:
                rr_q1.append(chosen.pid)
            elif q_level == 1 and chosen.pid not in rr_q1:
                rr_q1.insert(0, chosen.pid)
            logs.append(
                f"[Q{q_level}] t={_fmt(start_t)}->{_fmt(end_t)}: {chosen.pid} "
                f"ran {_fmt(slice_len)} (rem BT={_fmt(rem_bt[chosen.pid])})"
            )

        last_pid = chosen.pid

    return _build_output(
        "Multi-Level Queue",
        mode_label,
        processes,
        completion,
        first_start,
        final_prio,
        gantt,
        cs_points,
        cs_count,
        cs_time if cs_enabled else 0.0,
        logs,
    )
