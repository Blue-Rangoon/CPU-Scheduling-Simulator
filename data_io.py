"""Excel / CSV import, Excel / CSV / PNG export for the CPU Scheduling Simulator."""
from __future__ import annotations

import csv
import os
import tempfile
from typing import Dict, List, Optional

from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from scheduler_engine import (ALGO_BY_KEY, ProcessInput, ScheduleOutput, _fmt, algo_color,
                              comparison_rows, comparison_text, process_colors, text_color_for)

HEADERS = ["PID", "Arrival Time", "Burst Time", "Priority", "Queue", "Deadline"]
_ALIASES = {
    "pid": "pid", "process": "pid", "process id": "pid", "id": "pid", "name": "pid", "process name": "pid",
    "at": "at", "arrival": "at", "arrival time": "at", "arrival_time": "at",
    "bt": "bt", "burst": "bt", "burst time": "bt", "burst_time": "bt", "cpu burst": "bt",
    "priority": "priority", "prio": "priority",
    "queue": "queue", "queue level": "queue", "queue_level": "queue",
    "deadline": "deadline", "due": "deadline",
}


# --------------------------------------------------------------------------- #
#  Import
# --------------------------------------------------------------------------- #
def _num(v, row, col, integer=False, allow_blank=False, default=0):
    if v is None or str(v).strip() == "":
        if allow_blank:
            return default
        raise ValueError(f"Row {row}: '{col}' is empty.")
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"Row {row}: '{col}' must be a number (got '{v}').")
    return int(f) if integer else f


def _rows_to_processes(rows: List[list]) -> List[ProcessInput]:
    if not rows:
        raise ValueError("The file is empty.")
    head = [_ALIASES.get(str(c).strip().lower(), None) if c is not None else None for c in rows[0]]
    if "at" not in head or "bt" not in head:
        raise ValueError("Header row must contain at least 'Arrival Time' and 'Burst Time' columns.")
    idx = {name: i for i, name in enumerate(head) if name}
    procs, seen = [], set()
    for r, row in enumerate(rows[1:], start=2):
        if row is None or all(c is None or str(c).strip() == "" for c in row):
            continue
        get = lambda k: row[idx[k]] if k in idx and idx[k] < len(row) else None
        pid = str(get("pid")).strip() if get("pid") not in (None, "") else f"P{len(procs) + 1}"
        if pid in seen:
            raise ValueError(f"Row {r}: duplicate PID '{pid}'.")
        seen.add(pid)
        at = _num(get("at"), r, "Arrival Time")
        bt = _num(get("bt"), r, "Burst Time")
        if at < 0:
            raise ValueError(f"Row {r}: arrival time cannot be negative.")
        if bt <= 0:
            raise ValueError(f"Row {r}: burst time must be greater than 0.")
        pr = _num(get("priority"), r, "Priority", True, True, 0)
        q = _num(get("queue"), r, "Queue", True, True, 0)
        dl = get("deadline")
        dl = None if dl is None or str(dl).strip() == "" else _num(dl, r, "Deadline")
        procs.append(ProcessInput(pid, at, bt, pr, q, dl))
    if not procs:
        raise ValueError("No process rows found in the file.")
    return procs


def import_processes(path: str) -> List[ProcessInput]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = [list(r) for r in csv.reader(f)]
    else:
        wb = load_workbook(path, data_only=True, read_only=True)
        rows = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    return _rows_to_processes(rows)


def write_template(path: str, procs: Optional[List[ProcessInput]] = None):
    procs = procs or [ProcessInput("P1", 0, 5, 2, 0, 12), ProcessInput("P2", 1, 3, 1, 0, 6),
                      ProcessInput("P3", 2, 8, 4, 1, 30), ProcessInput("P4", 3, 6, 3, 1, 20),
                      ProcessInput("P5", 4, 2, 5, 2, 9)]
    wb = Workbook()
    ws = wb.active
    ws.title = "Processes"
    _header(ws, 1, HEADERS, "2563EB")
    for p in procs:
        ws.append([p.pid, p.at, p.bt, p.priority, p.queue_level, p.deadline])
    for i in range(1, 7):
        ws.column_dimensions[get_column_letter(i)].width = 16
    info = wb.create_sheet("Instructions")
    for line in ["How to fill the sheet",
                 "PID: process name (optional, auto-generated if blank)",
                 "Arrival Time and Burst Time are required (Burst > 0)",
                 "Priority: integer (used by Priority / Lottery / Stride / MLQ)",
                 "Queue: 0, 1, 2 ... (used by Multilevel Queue, 0 = highest queue)",
                 "Deadline: optional absolute time (used by EDF)"]:
        info.append([line])
    info.column_dimensions["A"].width = 80
    info["A1"].font = Font(bold=True, size=13)
    wb.save(path)


# --------------------------------------------------------------------------- #
#  Export helpers
# --------------------------------------------------------------------------- #
_thin = Side(style="thin", color="D1D5DB")
_border = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)


def _fc(h):
    return text_color_for(h).lstrip('#')


def _header(ws, row, titles, color):
    for i, t in enumerate(titles, start=1):
        c = ws.cell(row=row, column=i, value=t)
        c.font = Font(bold=True, color=_fc("#" + color))
        c.fill = PatternFill("solid", fgColor=color)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = _border


def _autowidth(ws, minw=10, maxw=70):
    for col in ws.columns:
        w = max((len(str(c.value)) for c in col if c.value is not None), default=0)
        ws.column_dimensions[get_column_letter(col[0].column)].width = max(minw, min(maxw, w + 3))


def export_gantt_png(path: str, out: ScheduleOutput, colors: Dict[str, str]):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch, Rectangle

    total = max(out.end_time, 1)
    fig, ax = plt.subplots(figsize=(max(9, min(26, total * 0.55 + 3)), 3.4), dpi=150)
    for g in out.gantt:
        w = g.end - g.start
        if g.kind == "run":
            ax.add_patch(Rectangle((g.start, 0), w, 1, facecolor=colors[g.pid], edgecolor="white", lw=1.5))
            ax.text(g.start + w / 2, 0.5, g.pid, ha="center", va="center", fontsize=9, fontweight="bold",
                    color=text_color_for(colors[g.pid]))
        elif g.kind == "idle":
            ax.add_patch(Rectangle((g.start, 0), w, 1, facecolor="#E5E7EB", edgecolor="#9CA3AF", hatch="//", lw=1))
        else:
            ax.add_patch(Rectangle((g.start, 0), w, 1, facecolor="#374151", edgecolor="white", lw=1))
    ticks = sorted({g.start for g in out.gantt} | {out.end_time})
    ax.set_xticks(ticks)
    ax.set_xticklabels([_fmt(t) for t in ticks], fontsize=8)
    ax.set_xlim(0, total)
    ax.set_ylim(0, 1.15)
    ax.set_yticks([])
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.set_title(f"{out.algorithm} - Gantt Chart", fontsize=12, fontweight="bold", loc="left")
    handles = [Patch(facecolor=c, label=p) for p, c in colors.items()]
    handles += [Patch(facecolor="#E5E7EB", hatch="//", edgecolor="#9CA3AF", label="Idle")]
    if out.cs_count:
        handles.append(Patch(facecolor="#374151", label="Context switch"))
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=min(len(handles), 10),
              frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def export_csv(path: str, out: ScheduleOutput):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Algorithm", out.algorithm])
        w.writerow([])
        w.writerow(["PID", "Arrival", "Burst", "Priority", "Completion", "Turnaround", "Waiting", "Response",
                    "Preemptions"])
        for r in out.results:
            w.writerow([r.pid, r.at, r.bt, r.priority, r.ct, r.tat, r.wt, r.rt, r.preemptions])
        w.writerow([])
        w.writerow(["Avg WT", out.avg_wt, "Avg TAT", out.avg_tat, "Avg RT", out.avg_rt,
                    "CPU %", out.cpu_utilization, "Throughput", out.throughput])
        w.writerow([])
        w.writerow(["Gantt start", "Gantt end", "Running"])
        for g in out.gantt:
            w.writerow([g.start, g.end, g.pid])


def export_excel(path: str, out: ScheduleOutput, procs: List[ProcessInput], colors: Dict[str, str],
                 all_outputs: Optional[Dict[str, ScheduleOutput]] = None):
    accent = algo_color(out.key).lstrip("#")
    wb = Workbook()

    # ---- Summary
    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = f"{out.algorithm} - Scheduling Report"
    ws["A1"].font = Font(bold=True, size=16, color=accent)
    ws["A2"] = out.mode + "  |  " + out.options_text
    ws["A2"].font = Font(italic=True, color="6B7280")
    r = 4
    metrics = [("Average Waiting Time", out.avg_wt), ("Average Turnaround Time", out.avg_tat),
               ("Average Response Time", out.avg_rt), ("Average Completion Time", out.avg_ct),
               ("CPU Utilization (%)", out.cpu_utilization), ("Throughput (proc/unit)", out.throughput),
               ("Total Time", out.end_time), ("Idle Time", out.idle_time),
               ("Context Switches", out.cs_count), ("Context Switch Overhead", out.cs_overhead)]
    _header(ws, r, ["Metric", "Value"], accent)
    for k, v in metrics:
        r += 1
        ws.cell(row=r, column=1, value=k).border = _border
        ws.cell(row=r, column=2, value=v).border = _border
    r += 2
    ws.cell(row=r, column=1, value="What happened (step by step story)").font = Font(bold=True, size=12)
    for line in out.summary:
        r += 1
        ws.cell(row=r, column=1, value=line).alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
        ws.row_dimensions[r].height = 32 if len(line) > 110 else 18
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 16
    for c in "CDEFGH":
        ws.column_dimensions[c].width = 16

    # ---- Input
    wi = wb.create_sheet("Input")
    _header(wi, 1, HEADERS, accent)
    for p in procs:
        wi.append([p.pid, p.at, p.bt, p.priority, p.queue_level, p.deadline])
    _autowidth(wi)

    # ---- Results
    wr = wb.create_sheet("Results")
    _header(wr, 1, ["PID", "Arrival", "Burst", "Priority", "Completion", "Turnaround", "Waiting", "Response",
                    "First Start", "Preemptions", "Deadline", "Deadline Met"], accent)
    for x in out.results:
        wr.append([x.pid, x.at, x.bt, x.priority, x.ct, x.tat, x.wt, x.rt, x.first_start, x.preemptions,
                   x.deadline, "" if x.deadline_met is None else ("Yes" if x.deadline_met else "No")])
        wr.cell(row=wr.max_row, column=1).fill = PatternFill("solid", fgColor=colors[x.pid].lstrip("#"))
        wr.cell(row=wr.max_row, column=1).font = Font(bold=True, color=_fc(colors[x.pid]))
    wr.append([])
    wr.append(["AVERAGE", "", "", "", out.avg_ct, out.avg_tat, out.avg_wt, out.avg_rt])
    for c in wr[wr.max_row]:
        c.font = Font(bold=True)
    _autowidth(wr)

    # ---- Gantt table + visual grid
    wg = wb.create_sheet("Gantt")
    _header(wg, 1, ["From", "To", "Duration", "Running"], accent)
    for g in out.gantt:
        wg.append([g.start, g.end, round(g.end - g.start, 2), g.pid])
        col = colors.get(g.pid, "#9CA3AF" if g.kind == "idle" else "#374151").lstrip("#")
        wg.cell(row=wg.max_row, column=4).fill = PatternFill("solid", fgColor=col)
        wg.cell(row=wg.max_row, column=4).font = Font(bold=True, color=_fc("#" + col))
    T = int(round(out.end_time))
    if 0 < T <= 300:
        top = wg.max_row + 3
        wg.cell(row=top - 1, column=1, value="Visual timeline (1 cell = 1 time unit)").font = Font(bold=True)
        pids = [x.pid for x in out.results]
        wg.cell(row=top, column=1, value="Process").font = Font(bold=True)
        for t in range(T):
            c = wg.cell(row=top, column=2 + t, value=t)
            c.font = Font(size=8)
            c.alignment = Alignment(horizontal="center")
        for i, pid in enumerate(pids, start=1):
            wg.cell(row=top + i, column=1, value=pid).font = Font(bold=True)
            for g in out.gantt:
                if g.pid != pid:
                    continue
                for t in range(int(round(g.start)), int(round(g.end))):
                    wg.cell(row=top + i, column=2 + t).fill = PatternFill("solid", fgColor=colors[pid].lstrip("#"))
        extra = top + len(pids) + 1
        wg.cell(row=extra, column=1, value="Idle / CS").font = Font(bold=True)
        for g in out.gantt:
            if g.kind != "run":
                for t in range(int(round(g.start)), int(round(g.end))):
                    wg.cell(row=extra, column=2 + t).fill = PatternFill(
                        "solid", fgColor="9CA3AF" if g.kind == "idle" else "374151")
        for t in range(T):
            wg.column_dimensions[get_column_letter(2 + t)].width = max(wg.column_dimensions[get_column_letter(2 + t)].width or 0, 4)
    wg.column_dimensions["A"].width = 12
    wg.column_dimensions["D"].width = 12

    # ---- Steps
    wst = wb.create_sheet("Steps")
    _header(wst, 1, ["#", "From", "To", "Type", "Running", "Ready Queue", "Remaining (before slice)", "Events",
                     "Why this decision", "Outcome"], accent)
    for s in out.steps:
        wst.append([s.no, s.start, s.end, {"run": "Run", "idle": "Idle", "cs": "Context switch"}[s.kind], s.pid,
                    ", ".join(s.ready) or "-",
                    ", ".join(f"{p}:{_fmt(v)}" for p, v in s.remaining.items()) or "-",
                    "; ".join(s.events) or "-", s.reason, s.outcome])
    _autowidth(wst, maxw=60)
    for row in wst.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")

    # ---- Comparison
    if all_outputs:
        wc = wb.create_sheet("Comparison")
        rows = comparison_rows(all_outputs)
        _header(wc, 1, ["Rank", "Algorithm", "Mode", "Avg WT", "Avg TAT", "Avg RT", "CPU %", "Throughput",
                        "Ctx Switches", "Total Time"], accent)
        for i, x in enumerate(rows, start=1):
            wc.append([i, x["name"], x["mode"], x["avg_wt"], x["avg_tat"], x["avg_rt"], x["util"],
                       x["throughput"], x["cs"], x["end"]])
            wc.cell(row=wc.max_row, column=2).fill = PatternFill("solid", fgColor=algo_color(x["key"]).lstrip("#"))
            wc.cell(row=wc.max_row, column=2).font = Font(bold=True, color=_fc(algo_color(x["key"])))
        wc.append([])
        for line in comparison_text(rows):
            wc.append([line])
        _autowidth(wc)

    # ---- Gantt picture
    try:
        tmp = os.path.join(tempfile.gettempdir(), "cpu_sched_gantt_tmp.png")
        export_gantt_png(tmp, out, colors)
        img = XLImage(tmp)
        img.width, img.height = int(img.width * 0.5), int(img.height * 0.5)
        wp = wb.create_sheet("Gantt Image")
        wp.add_image(img, "A1")
        wb.save(path)
        os.remove(tmp)
    except Exception:
        wb.save(path)
