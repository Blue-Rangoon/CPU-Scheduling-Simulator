"""CPU Scheduling Simulator - main window (PyQt6)."""
import random
import sys
from typing import Dict, List, Optional

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDoubleSpinBox, QFileDialog, QFrame,
                             QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
                             QMainWindow, QMessageBox, QPushButton, QScrollArea, QSpinBox, QSplitter,
                             QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

import data_io
from gantt_window import GanttChartWidget, GanttPopup
from scheduler_engine import (ALGO_BY_KEY, ALGOS, ProcessInput, SchedOptions, ScheduleOutput, _fmt, algo_color,
                              comparison_rows, comparison_text, process_colors, run_algorithm, run_all,
                              text_color_for)

PROC_HEADERS = ["PID", "Arrival", "Burst", "Priority", "Queue", "Deadline"]
SAMPLE = [("P1", 0, 5, 2, 0, 12), ("P2", 1, 3, 1, 0, 6), ("P3", 2, 8, 4, 1, 30),
          ("P4", 3, 6, 3, 1, 20), ("P5", 4, 2, 5, 2, 9)]


# --------------------------------------------------------------------------- #
#  Styling
# --------------------------------------------------------------------------- #
def build_stylesheet(theme: str) -> str:
    d = theme == "dark"
    c = dict(
        bg="#0F172A" if d else "#F3F4F6", card="#1E293B" if d else "#FFFFFF",
        border="#334155" if d else "#E5E7EB", text="#F1F5F9" if d else "#111827",
        muted="#94A3B8" if d else "#6B7280", primary="#3B82F6" if d else "#2563EB",
        input="#0F172A" if d else "#F9FAFB", alt="#172033" if d else "#F9FAFB",
        head="#334155" if d else "#E5E7EB", hover="#475569" if d else "#D1D5DB")
    return f"""
    QMainWindow, QWidget#root {{ background: {c['bg']}; }}
    QWidget {{ color: {c['text']}; font-family: 'Segoe UI', 'Inter', 'Helvetica Neue', Arial; font-size: 13px; }}
    QScrollArea {{ border: none; background: transparent; }}
    QWidget#panel {{ background: transparent; }}
    QFrame#card {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 12px; }}
    QFrame#metric {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 10px; }}
    QFrame#header {{ background: {c['card']}; border-bottom: 1px solid {c['border']}; }}
    QLabel {{ background: transparent; }}
    QLabel#title {{ font-size: 20px; font-weight: 700; }}
    QLabel#subtitle, QLabel#muted {{ color: {c['muted']}; font-size: 12px; }}
    QLabel#cardTitle {{ font-size: 14px; font-weight: 700; }}
    QLabel#metricValue {{ font-size: 22px; font-weight: 700; }}
    QLabel#metricName {{ color: {c['muted']}; font-size: 11px; }}
    QLabel#detail {{ background: {c['alt']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 10px; }}
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: {c['input']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 5px 8px;
        min-height: 20px; }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {c['primary']}; }}
    QComboBox QAbstractItemView {{ background: {c['card']}; selection-background-color: {c['primary']};
        selection-color: white; }}
    QPushButton {{ background: {c['head']}; border: none; border-radius: 6px; padding: 7px 12px; font-weight: 600; }}
    QPushButton:hover {{ background: {c['hover']}; }}
    QPushButton:disabled {{ color: {c['muted']}; }}
    QPushButton#primary {{ background: {c['primary']}; color: white; padding: 10px 14px; font-size: 14px; }}
    QPushButton#primary:hover {{ background: #1D4ED8; }}
    QPushButton#success {{ background: #16A34A; color: white; }}
    QPushButton#success:hover {{ background: #15803D; }}
    QPushButton#danger {{ background: #DC2626; color: white; }}
    QPushButton#danger:hover {{ background: #B91C1C; }}
    QTableWidget {{ background: {c['card']}; alternate-background-color: {c['alt']}; border: 1px solid {c['border']};
        border-radius: 8px; gridline-color: {c['border']}; selection-background-color: {c['primary']};
        selection-color: white; }}
    QHeaderView::section {{ background: {c['head']}; border: none; padding: 6px; font-weight: 700; }}
    QTabWidget::pane {{ border: none; }}
    QTabBar::tab {{ background: transparent; padding: 9px 18px; margin-right: 4px; font-weight: 600;
        color: {c['muted']}; border-bottom: 3px solid transparent; }}
    QTabBar::tab:selected {{ color: {c['primary']}; border-bottom: 3px solid {c['primary']}; }}
    QTextBrowser {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 10px; padding: 12px; }}
    QSplitter::handle {{ background: transparent; }}
    QScrollBar:vertical {{ width: 10px; background: transparent; }}
    QScrollBar::handle:vertical {{ background: {c['hover']}; border-radius: 5px; min-height: 30px; }}
    QScrollBar:horizontal {{ height: 10px; background: transparent; }}
    QScrollBar::handle:horizontal {{ background: {c['hover']}; border-radius: 5px; min-width: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    """


def card(title: str = "") -> (QFrame, QVBoxLayout):
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(14, 12, 14, 14)
    lay.setSpacing(8)
    if title:
        t = QLabel(title)
        t.setObjectName("cardTitle")
        lay.addWidget(t)
    return f, lay


def field(label: str, widget: QWidget) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(2)
    lb = QLabel(label)
    lb.setObjectName("muted")
    lay.addWidget(lb)
    lay.addWidget(widget)
    return w


def spin(lo, hi, val, step=1.0, decimals=1, suffix="") -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(decimals)
    s.setSingleStep(step)
    s.setValue(val)
    if suffix:
        s.setSuffix(suffix)
    return s


def ro_item(text, align_center=True) -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if align_center:
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    return it


class MetricCard(QFrame):
    def __init__(self, name: str):
        super().__init__()
        self.setObjectName("metric")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(0)
        self.name = QLabel(name)
        self.name.setObjectName("metricName")
        self.value = QLabel("-")
        self.value.setObjectName("metricValue")
        lay.addWidget(self.name)
        lay.addWidget(self.value)

    def set(self, text: str, color: str = ""):
        self.value.setText(text)
        self.value.setStyleSheet(f"color: {color};" if color else "")


class BarChart(QWidget):
    """Simple horizontal bar chart for the algorithm comparison."""

    def __init__(self):
        super().__init__()
        self.items: List[tuple] = []     # (label, value, colour)
        self.lower_better = True
        self.theme = "light"
        self.setMinimumHeight(200)

    def set_data(self, items, lower_better=True):
        self.items, self.lower_better = items, lower_better
        self.setMinimumHeight(max(200, 30 * len(items) + 20))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        txt = QColor("#F1F5F9" if self.theme == "dark" else "#111827")
        if not self.items:
            return
        vals = [v for _, v, _ in self.items]
        best = min(vals) if self.lower_better else max(vals)
        top = max(vals) or 1
        left, right, row_h = 270, 80, 28
        w = max(self.width() - left - right, 50)
        p.setFont(QFont("Segoe UI", 9))
        for i, (label, val, col) in enumerate(self.items):
            y = 10 + i * (row_h + 2)
            p.setPen(txt)
            p.drawText(QRectF(0, y, left - 10, row_h), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)
            bw = max(3.0, w * val / top)
            p.setPen(QPen(QColor("#FACC15"), 3) if abs(val - best) < 1e-9 else Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(col)))
            p.drawRoundedRect(QRectF(left, y + 3, bw, row_h - 6), 5, 5)
            p.setPen(txt)
            p.drawText(QRectF(left + bw + 8, y, 70, row_h), Qt.AlignmentFlag.AlignVCenter,
                       _fmt(val) + ("  ★" if abs(val - best) < 1e-9 else ""))


# --------------------------------------------------------------------------- #
#  Main window
# --------------------------------------------------------------------------- #
class CPUSchedulerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CPU Scheduling Simulator")
        self.resize(1480, 900)
        self.theme = "light"
        self.out: Optional[ScheduleOutput] = None
        self.procs: List[ProcessInput] = []
        self.colors: Dict[str, str] = {}
        self.all_outputs: Optional[Dict[str, ScheduleOutput]] = None
        self.step_idx = -1
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        rl = QVBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self._build_header())
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._build_left())
        split.addWidget(self._build_right())
        split.setStretchFactor(1, 1)
        split.setSizes([430, 1050])
        body = QWidget()
        bl = QHBoxLayout(body)
        bl.setContentsMargins(14, 12, 14, 12)
        bl.addWidget(split)
        rl.addWidget(body, 1)

        self._apply_theme()
        self._on_algo_changed()
        self.load_sample()
        self.statusBar().showMessage("Ready. Add processes (or import an Excel sheet), choose an algorithm and press Run.")

    # ------------------------------------------------------------------ UI
    def _build_header(self) -> QFrame:
        h = QFrame()
        h.setObjectName("header")
        lay = QHBoxLayout(h)
        lay.setContentsMargins(20, 12, 20, 12)
        col = QVBoxLayout()
        t = QLabel("CPU Scheduling Simulator")
        t.setObjectName("title")
        s = QLabel("15 algorithms · Gantt charts · step-by-step iterations · summaries · Excel import & export")
        s.setObjectName("subtitle")
        col.addWidget(t)
        col.addWidget(s)
        lay.addLayout(col)
        lay.addStretch()
        self.theme_btn = QPushButton("🌙 Dark mode")
        self.theme_btn.clicked.connect(self.toggle_theme)
        lay.addWidget(self.theme_btn)
        return h

    def _build_left(self) -> QScrollArea:
        panel = QWidget()
        panel.setObjectName("panel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(12)

        # --- algorithm card
        c1, l1 = card("1 · Algorithm & settings")
        self.algo_combo = QComboBox()
        for a in ALGOS:
            self.algo_combo.addItem(a.name, a.key)
        self.algo_combo.currentIndexChanged.connect(self._on_algo_changed)
        l1.addWidget(self.algo_combo)
        self.algo_info = QLabel()
        self.algo_info.setWordWrap(True)
        l1.addWidget(self.algo_info)

        self.sp_quantum = spin(0.5, 1000, 2, 0.5)
        self.sp_cs = spin(0, 100, 0, 0.5)
        self.cb_prio = QComboBox()
        self.cb_prio.addItem("Lower number = higher priority", False)
        self.cb_prio.addItem("Higher number = higher priority", True)
        self.sp_aging = spin(0, 1000, 0, 1, 0)
        self.sp_aging.setSpecialValueText("Off")
        self.sp_seed = QSpinBox()
        self.sp_seed.setRange(0, 999999)
        self.sp_seed.setValue(1)
        self.opt_widgets = {
            "quantum": field("Time quantum", self.sp_quantum),
            "prio": field("Priority convention", self.cb_prio),
            "aging": field("Aging (priority improves every N units)", self.sp_aging),
            "seed": field("Random seed (lottery)", self.sp_seed),
        }
        self.mlq_box = QWidget()
        ml = QVBoxLayout(self.mlq_box)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(4)
        cap = QLabel("Queue configuration (process 'Queue' column decides its queue)")
        cap.setObjectName("muted")
        ml.addWidget(cap)
        self.mlq_rows = []
        defaults = [("RR", 2.0), ("SJF", 0.0), ("FCFS", 0.0)]
        for i, (a, q) in enumerate(defaults):
            row = QHBoxLayout()
            lb = QLabel(f"Q{i}" + (" (highest)" if i == 0 else ""))
            lb.setMinimumWidth(80)
            cb = QComboBox()
            for name, k in (("FCFS", "FCFS"), ("Round Robin", "RR"), ("SJF", "SJF"), ("Priority", "PRIORITY")):
                cb.addItem(name, k)
            cb.setCurrentIndex(cb.findData(a))
            sq = spin(0.5, 1000, q if q else 2, 0.5, 1, " q")
            row.addWidget(lb)
            row.addWidget(cb, 1)
            row.addWidget(sq)
            ml.addLayout(row)
            self.mlq_rows.append((cb, sq))
        self.mlfq_edit = QLineEdit("2, 4")
        self.opt_widgets["mlq"] = self.mlq_box
        self.opt_widgets["mlfq"] = field("Quanta of Q0, Q1 … (last queue is FCFS)", self.mlfq_edit)
        for w in self.opt_widgets.values():
            l1.addWidget(w)
        l1.addWidget(field("Context switch time", self.sp_cs))
        lay.addWidget(c1)

        # --- process card
        c2, l2 = card("2 · Processes")
        g = QGridLayout()
        g.setHorizontalSpacing(6)
        self.in_pid = QLineEdit()
        self.in_pid.setPlaceholderText("auto")
        self.in_at = spin(0, 100000, 0, 1, 1)
        self.in_bt = spin(0.1, 100000, 1, 1, 1)
        self.in_pr = QSpinBox()
        self.in_pr.setRange(-1000, 1000)
        self.in_q = QSpinBox()
        self.in_q.setRange(0, 9)
        self.in_dl = QLineEdit()
        self.in_dl.setPlaceholderText("optional")
        for i, (lb, w) in enumerate([("PID", self.in_pid), ("Arrival", self.in_at), ("Burst", self.in_bt),
                                     ("Priority", self.in_pr), ("Queue", self.in_q), ("Deadline", self.in_dl)]):
            g.addWidget(field(lb, w), i // 3, i % 3)
        l2.addLayout(g)
        add = QPushButton("＋  Add process")
        add.setObjectName("success")
        add.clicked.connect(self.add_process)
        l2.addWidget(add)
        r1 = QHBoxLayout()
        for text, fn in (("📥 Import Excel/CSV", self.import_file), ("📄 Template", self.save_template)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            r1.addWidget(b)
        l2.addLayout(r1)
        r2 = QHBoxLayout()
        for text, fn in (("Sample", self.load_sample), ("Random", self.random_processes),
                         ("Remove selected", self.remove_selected), ("Clear", self.clear_processes)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            r2.addWidget(b)
        l2.addLayout(r2)
        self.table = QTableWidget(0, len(PROC_HEADERS))
        self.table.setHorizontalHeaderLabels(PROC_HEADERS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(220)
        self.table.itemChanged.connect(self._invalidate)
        l2.addWidget(self.table)
        hint = QLabel("Tip: double-click any cell to edit it directly.")
        hint.setObjectName("muted")
        l2.addWidget(hint)
        lay.addWidget(c2)

        # --- actions
        c3, l3 = card()
        run = QPushButton("▶  Run algorithm")
        run.setObjectName("primary")
        run.clicked.connect(self.run_scheduler)
        cmp_ = QPushButton("📊  Compare all algorithms")
        cmp_.clicked.connect(self.compare_all)
        rst = QPushButton("Reset results")
        rst.setObjectName("danger")
        rst.clicked.connect(self.reset_results)
        l3.addWidget(run)
        l3.addWidget(cmp_)
        l3.addWidget(rst)
        lay.addWidget(c3)
        lay.addStretch()

        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(panel)
        sc.setMinimumWidth(400)
        return sc

    def _build_right(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 0, 0, 0)
        lay.setSpacing(8)

        bar = QHBoxLayout()
        self.chip = QLabel("No result yet")
        self.chip.setObjectName("cardTitle")
        bar.addWidget(self.chip)
        bar.addStretch()
        for text, fn, obj in (("⬇ Export Excel", self.export_excel, "success"), ("CSV", self.export_csv, ""),
                              ("🖼 Gantt PNG", self.export_png, ""), ("⤢ Pop-out Gantt", self.popout, "")):
            b = QPushButton(text)
            if obj:
                b.setObjectName(obj)
            b.clicked.connect(fn)
            bar.addWidget(b)
        lay.addLayout(bar)

        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)

        # ---- Overview tab
        ov = QWidget()
        ol = QVBoxLayout(ov)
        ol.setContentsMargins(0, 8, 0, 0)
        ol.setSpacing(10)
        self.opt_label = QLabel("")
        self.opt_label.setObjectName("muted")
        ol.addWidget(self.opt_label)
        mg = QGridLayout()
        names = ["Avg Waiting", "Avg Turnaround", "Avg Response", "CPU Utilization", "Throughput", "Context Switches"]
        self.metric_cards = [MetricCard(n) for n in names]
        for i, m in enumerate(self.metric_cards):
            mg.addWidget(m, 0, i)
        ol.addLayout(mg)
        gc, gl = card("Gantt chart")
        self.gantt = GanttChartWidget(self.theme)
        gl.addWidget(self.gantt)
        ol.addWidget(gc)
        self.res_table = QTableWidget(0, 9)
        self.res_table.setHorizontalHeaderLabels(["PID", "Arrival", "Burst", "Priority", "Completion",
                                                  "Turnaround", "Waiting", "Response", "Preempted"])
        self.res_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.res_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.res_table.setAlternatingRowColors(True)
        self.res_table.verticalHeader().setVisible(False)
        ol.addWidget(self.res_table, 1)
        self.tabs.addTab(ov, "📈 Overview")

        # ---- Steps tab
        st = QWidget()
        sl = QVBoxLayout(st)
        sl.setContentsMargins(0, 8, 0, 0)
        sl.setSpacing(8)
        ctl = QHBoxLayout()
        self.btn_first = QPushButton("⏮ Start")
        self.btn_prev = QPushButton("◀ Prev")
        self.btn_next = QPushButton("Next ▶")
        self.btn_play = QPushButton("▶ Play")
        self.btn_play.setObjectName("primary")
        self.btn_last = QPushButton("End ⏭")
        self.btn_first.clicked.connect(lambda: self.goto_step(0))
        self.btn_prev.clicked.connect(lambda: self.goto_step(self.step_idx - 1))
        self.btn_next.clicked.connect(lambda: self.goto_step(self.step_idx + 1))
        self.btn_last.clicked.connect(lambda: self.goto_step(len(self.out.steps) - 1 if self.out else 0))
        self.btn_play.clicked.connect(self.toggle_play)
        self.speed = QComboBox()
        for name, ms in (("Slow", 1400), ("Normal", 800), ("Fast", 300)):
            self.speed.addItem(name, ms)
        self.speed.setCurrentIndex(1)
        self.speed.currentIndexChanged.connect(self._speed_changed)
        self.step_label = QLabel("Step - / -")
        self.step_label.setObjectName("cardTitle")
        for b in (self.btn_first, self.btn_prev, self.btn_next, self.btn_play, self.btn_last):
            ctl.addWidget(b)
        ctl.addWidget(QLabel("Speed:"))
        ctl.addWidget(self.speed)
        ctl.addStretch()
        ctl.addWidget(self.step_label)
        sl.addLayout(ctl)
        sg, sgl = card()
        self.step_gantt = GanttChartWidget(self.theme)
        sgl.addWidget(self.step_gantt)
        sl.addWidget(sg)
        self.detail = QLabel("Run an algorithm, then step through every decision here.")
        self.detail.setObjectName("detail")
        self.detail.setWordWrap(True)
        self.detail.setTextFormat(Qt.TextFormat.RichText)
        sl.addWidget(self.detail)
        self.step_table = QTableWidget(0, 9)
        self.step_table.setHorizontalHeaderLabels(["#", "From", "To", "Running", "Ready queue",
                                                   "Remaining (before)", "Events", "Why this decision", "Outcome"])
        hh = self.step_table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.step_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.step_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.step_table.setAlternatingRowColors(True)
        self.step_table.setWordWrap(True)
        self.step_table.verticalHeader().setVisible(False)
        self.step_table.cellClicked.connect(lambda r, _c: self.goto_step(r))
        sl.addWidget(self.step_table, 1)
        self.tabs.addTab(st, "🔍 Step-by-step")

        # ---- Summary tab
        self.summary = QTextBrowser()
        self.tabs.addTab(self.summary, "📝 Summary")

        # ---- Comparison tab
        cp = QWidget()
        cl = QVBoxLayout(cp)
        cl.setContentsMargins(0, 8, 0, 0)
        top = QHBoxLayout()
        top.addWidget(QLabel("Chart metric:"))
        self.cmp_metric = QComboBox()
        for name, key, lower in (("Average waiting time", "avg_wt", True), ("Average turnaround time", "avg_tat", True),
                                 ("Average response time", "avg_rt", True), ("CPU utilization %", "util", False),
                                 ("Throughput", "throughput", False), ("Context switches", "cs", True)):
            self.cmp_metric.addItem(name, (key, lower))
        self.cmp_metric.currentIndexChanged.connect(self._draw_compare_chart)
        top.addWidget(self.cmp_metric)
        top.addStretch()
        cl.addLayout(top)
        self.bars = BarChart()
        bs = QScrollArea()
        bs.setWidgetResizable(True)
        bs.setWidget(self.bars)
        bs.setMinimumHeight(260)
        cl.addWidget(bs)
        self.cmp_text = QLabel("Press “Compare all algorithms” to see which one performs best on your processes.")
        self.cmp_text.setObjectName("detail")
        self.cmp_text.setWordWrap(True)
        cl.addWidget(self.cmp_text)
        self.cmp_table = QTableWidget(0, 9)
        self.cmp_table.setHorizontalHeaderLabels(["Rank", "Algorithm", "Mode", "Avg WT", "Avg TAT", "Avg RT",
                                                  "CPU %", "Ctx switches", "Total time"])
        self.cmp_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.cmp_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.cmp_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.cmp_table.setAlternatingRowColors(True)
        self.cmp_table.verticalHeader().setVisible(False)
        cl.addWidget(self.cmp_table, 1)
        self.tabs.addTab(cp, "🏆 Comparison")
        return w

    # ------------------------------------------------------------- themes
    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        self._apply_theme()

    def _apply_theme(self):
        self.setStyleSheet(build_stylesheet(self.theme))
        self.theme_btn.setText("☀ Light mode" if self.theme == "dark" else "🌙 Dark mode")
        self.gantt.set_theme(self.theme)
        self.step_gantt.set_theme(self.theme)
        self.bars.theme = self.theme
        self.bars.update()

    # -------------------------------------------------------- algorithm UI
    def _key(self) -> str:
        return self.algo_combo.currentData()

    def _on_algo_changed(self):
        k = self._key()
        a = ALGO_BY_KEY[k]
        col = algo_color(k)
        self.algo_info.setText(
            f"<span style='background:{col}; color:{text_color_for(col)}; padding:2px 8px; border-radius:8px;'>"
            f"<b>{a.mode}</b></span><br>{a.desc}<br><span style='color:gray'>Uses: {a.uses}</span>")
        show = {"quantum": k in ("RR", "PRIO_RR", "LOTTERY", "STRIDE"),
                "prio": k in ("PRIO_NP", "PRIO_P", "PRIO_RR", "LOTTERY", "STRIDE", "MLQ"),
                "aging": k in ("PRIO_NP", "PRIO_P", "PRIO_RR"),
                "seed": k == "LOTTERY", "mlq": k == "MLQ", "mlfq": k == "MLFQ"}
        for name, w in self.opt_widgets.items():
            w.setVisible(show[name])

    def read_options(self) -> SchedOptions:
        o = SchedOptions()
        o.quantum = self.sp_quantum.value()
        o.cs_time = self.sp_cs.value()
        o.high_is_priority = bool(self.cb_prio.currentData())
        o.aging = self.sp_aging.value()
        o.seed = self.sp_seed.value()
        o.mlq_levels = [(cb.currentData(), sq.value()) for cb, sq in self.mlq_rows]
        try:
            q = [float(x) for x in self.mlfq_edit.text().replace(";", ",").split(",") if x.strip()]
            if not q or any(v <= 0 for v in q):
                raise ValueError
        except ValueError:
            raise ValueError("MLFQ quanta must be positive numbers separated by commas, e.g. 2, 4, 8")
        o.mlfq_quanta = q
        return o

    # ------------------------------------------------------------ process IO
    def _invalidate(self, *_):
        self.all_outputs = None

    def _set_row(self, r: int, vals):
        for c, v in enumerate(vals):
            it = QTableWidgetItem("" if v is None else _fmt(v) if isinstance(v, (int, float)) else str(v))
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, c, it)

    def _fill_table(self, procs: List[ProcessInput]):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for p in procs:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self._set_row(r, [p.pid, p.at, p.bt, p.priority, p.queue_level, p.deadline])
        self.table.blockSignals(False)
        self._invalidate()

    def add_process(self):
        pid = self.in_pid.text().strip() or f"P{self.table.rowCount() + 1}"
        existing = {self.table.item(r, 0).text() for r in range(self.table.rowCount()) if self.table.item(r, 0)}
        if pid in existing:
            QMessageBox.warning(self, "Duplicate PID", f"A process named '{pid}' already exists.")
            return
        dl = self.in_dl.text().strip()
        try:
            dl_val = float(dl) if dl else None
        except ValueError:
            QMessageBox.warning(self, "Invalid deadline", "Deadline must be a number or empty.")
            return
        self.table.blockSignals(True)
        r = self.table.rowCount()
        self.table.insertRow(r)
        self._set_row(r, [pid, self.in_at.value(), self.in_bt.value(), self.in_pr.value(), self.in_q.value(), dl_val])
        self.table.blockSignals(False)
        self._invalidate()
        self.in_pid.clear()
        self.in_dl.clear()
        self.statusBar().showMessage(f"Added {pid}.")

    def read_processes(self) -> List[ProcessInput]:
        procs, seen = [], set()
        for r in range(self.table.rowCount()):
            cell = lambda c: (self.table.item(r, c).text().strip() if self.table.item(r, c) else "")
            pid = cell(0) or f"P{r + 1}"
            try:
                at, bt = float(cell(1)), float(cell(2))
                pr = int(float(cell(3) or 0))
                q = int(float(cell(4) or 0))
                dl = float(cell(5)) if cell(5) else None
            except ValueError:
                raise ValueError(f"Row {r + 1} ({pid}): Arrival, Burst, Priority, Queue and Deadline must be numbers.")
            if pid in seen:
                raise ValueError(f"Duplicate PID '{pid}' in row {r + 1}.")
            if at < 0 or bt <= 0:
                raise ValueError(f"Row {r + 1} ({pid}): arrival must be ≥ 0 and burst must be > 0.")
            seen.add(pid)
            procs.append(ProcessInput(pid, at, bt, pr, max(0, q), dl))
        if not procs:
            raise ValueError("Please add at least one process.")
        return procs

    def load_sample(self):
        self._fill_table([ProcessInput(*s) for s in SAMPLE])
        self.statusBar().showMessage("Sample processes loaded.")

    def random_processes(self):
        n, ok = QInputDialog.getInt(self, "Random processes", "How many processes?", 6, 1, 40)
        if not ok:
            return
        procs = []
        for i in range(n):
            at = random.randint(0, 10)
            bt = random.randint(1, 10)
            procs.append(ProcessInput(f"P{i + 1}", at, bt, random.randint(1, 5), random.randint(0, 2),
                                      at + bt + random.randint(2, 12)))
        self._fill_table(procs)

    def clear_processes(self):
        self._fill_table([])

    def remove_selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)
        self._invalidate()

    def import_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import processes", "", "Excel / CSV (*.xlsx *.xlsm *.csv)")
        if not path:
            return
        try:
            procs = data_io.import_processes(path)
        except Exception as e:
            QMessageBox.critical(self, "Import failed", str(e))
            return
        self._fill_table(procs)
        self.statusBar().showMessage(f"Imported {len(procs)} processes from {path}")

    def save_template(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Excel template", "processes_template.xlsx", "Excel (*.xlsx)")
        if path:
            data_io.write_template(path)
            self.statusBar().showMessage(f"Template saved: {path}")

    # ----------------------------------------------------------------- run
    def run_scheduler(self):
        try:
            procs = self.read_processes()
            opts = self.read_options()
            out = run_algorithm(self._key(), procs, opts)
        except Exception as e:
            QMessageBox.warning(self, "Cannot run", str(e))
            return
        self.timer.stop()
        self.btn_play.setText("▶ Play")
        self.procs, self.out = procs, out
        self.colors = process_colors(out.key, [p.pid for p in procs])
        self._render()
        self.tabs.setCurrentIndex(0)
        self.statusBar().showMessage(f"{out.algorithm} finished at t={_fmt(out.end_time)}.")

    def _render(self):
        o = self.out
        col = algo_color(o.key)
        self.chip.setText(f"{o.algorithm}  ·  {o.mode}")
        self.chip.setStyleSheet(f"color: {col};")
        self.opt_label.setText(o.options_text)
        vals = [_fmt(o.avg_wt), _fmt(o.avg_tat), _fmt(o.avg_rt), f"{_fmt(o.cpu_utilization)}%",
                f"{o.throughput:g}", f"{o.cs_count}"]
        for m, v in zip(self.metric_cards, vals):
            m.set(v, col)
        self.gantt.show_output(o, self.colors)
        self.step_gantt.show_output(o, self.colors)

        t = self.res_table
        t.setRowCount(0)
        for x in o.results:
            r = t.rowCount()
            t.insertRow(r)
            vals = [x.pid, x.at, x.bt, x.priority, x.ct, x.tat, x.wt, x.rt, x.preemptions]
            for c, v in enumerate(vals):
                it = ro_item(v if c == 0 else _fmt(v))
                if c == 0:
                    it.setBackground(QColor(self.colors[x.pid]))
                    it.setForeground(QColor(text_color_for(self.colors[x.pid])))
                    it.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                t.setItem(r, c, it)
        r = t.rowCount()
        t.insertRow(r)
        for c, v in ((0, "AVERAGE"), (4, o.avg_ct), (5, o.avg_tat), (6, o.avg_wt), (7, o.avg_rt)):
            it = ro_item(v if c == 0 else _fmt(v))
            it.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            t.setItem(r, c, it)

        st = self.step_table
        st.setRowCount(0)
        for s in o.steps:
            r = st.rowCount()
            st.insertRow(r)
            vals = [s.no, _fmt(s.start), _fmt(s.end), s.pid, ", ".join(s.ready) or "-",
                    ", ".join(f"{p}:{_fmt(v)}" for p, v in s.remaining.items()) or "-",
                    "; ".join(s.events) or "-", s.reason, s.outcome]
            for c, v in enumerate(vals):
                it = ro_item(v, c not in (6, 7, 8))
                if c == 3 and s.kind == "run":
                    it.setBackground(QColor(self.colors[s.pid]))
                    it.setForeground(QColor(text_color_for(self.colors[s.pid])))
                st.setItem(r, c, it)
        st.resizeRowsToContents()
        self.summary.setHtml(self._summary_html())
        self.goto_step(len(o.steps) - 1)

    def _summary_html(self) -> str:
        o = self.out
        col = algo_color(o.key)
        h = [f"<h2 style='color:{col}'>{o.algorithm}</h2><p><i>{o.mode} · {o.options_text}</i></p>",
             "<h3>What happened overall</h3><ul>"]
        for line in o.summary:
            h.append(f"<li style='margin-bottom:6px'>{line}</li>")
        h.append("</ul><h3>Key numbers</h3><table cellpadding='5'>")
        for k, v in (("Total time", o.end_time), ("Idle time", o.idle_time), ("Context switches", o.cs_count),
                     ("Context switch overhead", o.cs_overhead), ("Average waiting time", o.avg_wt),
                     ("Average turnaround time", o.avg_tat), ("Average response time", o.avg_rt),
                     ("CPU utilization", f"{_fmt(o.cpu_utilization)}%"), ("Throughput", f"{o.throughput:g}")):
            h.append(f"<tr><td><b>{k}</b></td><td>{v if isinstance(v, str) else _fmt(v)}</td></tr>")
        h.append("</table>")
        return "".join(h)

    # --------------------------------------------------------- step player
    def goto_step(self, i: int):
        if not self.out or not self.out.steps:
            return
        n = len(self.out.steps)
        i = max(0, min(n - 1, i))
        self.step_idx = i
        s = self.out.steps[i]
        self.step_gantt.set_reveal(s.end)
        self.step_label.setText(f"Step {i + 1} / {n}")
        self.step_table.selectRow(i)
        self.step_table.scrollToItem(self.step_table.item(i, 0))
        col = self.colors.get(s.pid, "#6B7280")
        who = {"run": f"<b style='color:{col}'>{s.pid}</b> runs for {_fmt(s.end - s.start)} unit(s)",
               "idle": "<b>CPU is idle</b>", "cs": "<b>Context switch</b>"}[s.kind]
        self.detail.setText(
            f"<b>t = {_fmt(s.start)} → {_fmt(s.end)}</b> &nbsp;·&nbsp; {who}<br>"
            f"<b>Why:</b> {s.reason}<br>"
            f"<b>Waiting (ready queue):</b> {', '.join(s.ready) or '—'} &nbsp;&nbsp; "
            f"<b>Remaining before this step:</b> {', '.join(f'{p}:{_fmt(v)}' for p, v in s.remaining.items()) or '—'}<br>"
            f"<b>Events:</b> {'; '.join(s.events) or '—'}<br><b>Result:</b> {s.outcome}")

    def toggle_play(self):
        if not self.out:
            return
        if self.timer.isActive():
            self.timer.stop()
            self.btn_play.setText("▶ Play")
            return
        if self.step_idx >= len(self.out.steps) - 1:
            self.goto_step(0)
        self.timer.start(self.speed.currentData())
        self.btn_play.setText("⏸ Pause")

    def _speed_changed(self):
        if self.timer.isActive():
            self.timer.start(self.speed.currentData())

    def _tick(self):
        if not self.out or self.step_idx >= len(self.out.steps) - 1:
            self.timer.stop()
            self.btn_play.setText("▶ Play")
            return
        self.goto_step(self.step_idx + 1)

    # ---------------------------------------------------------- comparison
    def compare_all(self):
        try:
            procs = self.read_processes()
            opts = self.read_options()
            outs = run_all(procs, opts)
        except Exception as e:
            QMessageBox.warning(self, "Cannot compare", str(e))
            return
        self.all_outputs = outs
        rows = comparison_rows(outs)
        self._cmp_rows = rows
        t = self.cmp_table
        t.setRowCount(0)
        for i, x in enumerate(rows, start=1):
            r = t.rowCount()
            t.insertRow(r)
            vals = [i, x["name"], x["mode"], x["avg_wt"], x["avg_tat"], x["avg_rt"], x["util"], x["cs"], x["end"]]
            for c, v in enumerate(vals):
                it = ro_item(v if c in (1, 2) else _fmt(v), c not in (1, 2))
                if c == 1:
                    cc = algo_color(x["key"])
                    it.setBackground(QColor(cc))
                    it.setForeground(QColor(text_color_for(cc)))
                if i == 1:
                    it.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                t.setItem(r, c, it)
        self.cmp_text.setText("<br>".join("• " + s for s in comparison_text(rows)) +
                              "<br><i>Ranking is by average waiting time. ★ marks the best value in the chart.</i>")
        self._draw_compare_chart()
        self.tabs.setCurrentIndex(3)
        self.statusBar().showMessage("Compared all 15 algorithms on your processes.")

    def _draw_compare_chart(self):
        if not getattr(self, "_cmp_rows", None) or not self.all_outputs:
            return
        key, lower = self.cmp_metric.currentData()
        items = [(x["name"], x[key], algo_color(x["key"])) for x in self._cmp_rows]
        self.bars.set_data(items, lower)

    # -------------------------------------------------------------- export
    def _need_result(self) -> bool:
        if not self.out:
            QMessageBox.information(self, "Nothing to export", "Run an algorithm first.")
            return False
        return True

    def export_excel(self):
        if not self._need_result():
            return
        name = f"{self.out.key}_report.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "Export to Excel", name, "Excel (*.xlsx)")
        if not path:
            return
        try:
            data_io.export_excel(path, self.out, self.procs, self.colors, self.all_outputs)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))
            return
        self.statusBar().showMessage(f"Excel report saved: {path}")
        QMessageBox.information(self, "Exported", f"Excel report saved:\n{path}")

    def export_csv(self):
        if not self._need_result():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", f"{self.out.key}_results.csv", "CSV (*.csv)")
        if path:
            data_io.export_csv(path, self.out)
            self.statusBar().showMessage(f"CSV saved: {path}")

    def export_png(self):
        if not self._need_result():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Gantt chart", f"{self.out.key}_gantt.png", "PNG (*.png)")
        if path:
            data_io.export_gantt_png(path, self.out, self.colors)
            self.statusBar().showMessage(f"Gantt chart saved: {path}")

    def popout(self):
        if self._need_result():
            GanttPopup(self.out, self.colors, self.theme, self).show()

    # --------------------------------------------------------------- reset
    def reset_results(self):
        self.timer.stop()
        self.out, self.all_outputs, self.step_idx = None, None, -1
        self.chip.setText("No result yet")
        self.chip.setStyleSheet("")
        self.opt_label.setText("")
        for m in self.metric_cards:
            m.set("-")
        self.gantt.show_output(None, {})
        self.step_gantt.show_output(None, {})
        for t in (self.res_table, self.step_table, self.cmp_table):
            t.setRowCount(0)
        self.summary.clear()
        self.detail.setText("Run an algorithm, then step through every decision here.")
        self.step_label.setText("Step - / -")
        self.bars.set_data([])
        self.cmp_text.setText("Press “Compare all algorithms” to see which one performs best on your processes.")
        self.statusBar().showMessage("Results cleared.")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = CPUSchedulerApp()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
