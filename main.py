import sys
from typing import List, Optional

from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gantt_window import GanttChart, GanttChartWidget
from scheduler_engine import (
    ProcessInput,
    ScheduleOutput,
    _fmt,
    run_fcfs,
    run_hrrn,
    run_multilevel_queue,
    run_priority_non_preemptive,
    run_priority_preemptive,
    run_round_robin,
    run_sjf_non_preemptive,
    run_srtf_preemptive,
)


ALGORITHMS = [
    "FCFS (Non-Preemptive)",
    "SJF (Non-Preemptive)",
    "SRTF (Preemptive SJF)",
    "Priority (Non-Preemptive)",
    "Priority (Preemptive)",
    "Round Robin (Preemptive)",
    "HRRN (Non-Preemptive)",
    "Multi-Level Queue (MLQ)",
]


class FlowLayout(QLayout):
    """Pure-Python wrapping flow layout so controls never clip on narrower windows."""

    def __init__(self, parent=None, margin=0, h_spacing=8, v_spacing=6):
        super().__init__(parent)
        self._items = []
        self._h_space = h_spacing
        self._v_space = v_spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective.x()
        y = effective.y()
        line_height = 0

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._h_space
            if next_x - self._h_space > effective.right() and line_height > 0:
                x = effective.x()
                y = y + line_height + self._v_space
                next_x = x + hint.width() + self._h_space
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))

            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + margins.bottom()


def build_stylesheet(theme: str) -> str:
    if theme == "dark":
        return """
            QWidget {
                background-color: #0F172A;
                color: #F1F5F9;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 12px;
            }
            QScrollArea {
                background-color: #0F172A;
                border: none;
            }
            QFrame#Card {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 8px;
            }
            QFrame#MetricCard {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 8px;
            }
            QLabel#SectionTitle {
                color: #F8FAFC;
                font-size: 12px;
                font-weight: bold;
            }
            QLabel#MetricTitle {
                color: #94A3B8;
                font-size: 10px;
                font-weight: bold;
            }
            QLabel#MetricValue {
                color: #38BDF8;
                font-size: 15px;
                font-weight: bold;
            }
            QLabel#MutedLabel {
                color: #94A3B8;
                font-size: 11px;
            }
            QLineEdit, QComboBox {
                background-color: #0F172A;
                color: #F1F5F9;
                border: 1px solid #475569;
                border-radius: 5px;
                padding: 4px 7px;
            }
            QLineEdit:disabled, QComboBox:disabled {
                background-color: #172033;
                color: #64748B;
                border: 1px solid #293548;
            }
            QComboBox QAbstractItemView {
                background-color: #1E293B;
                color: #F1F5F9;
                selection-background-color: #2563EB;
            }
            QCheckBox {
                color: #F1F5F9;
                spacing: 5px;
            }
            QCheckBox:disabled {
                color: #64748B;
            }
            QPushButton {
                background-color: #2563EB;
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                padding: 5px 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
            QPushButton#SecondaryBtn {
                background-color: #334155;
                color: #F1F5F9;
            }
            QPushButton#SecondaryBtn:hover {
                background-color: #475569;
            }
            QPushButton#RunBtn {
                background-color: #10B981;
                color: #FFFFFF;
            }
            QPushButton#RunBtn:hover {
                background-color: #059669;
            }
            QPushButton#DangerBtn {
                background-color: #EF4444;
                color: #FFFFFF;
            }
            QPushButton#DangerBtn:hover {
                background-color: #DC2626;
            }
            QTableWidget {
                background-color: #1E293B;
                alternate-background-color: #162032;
                color: #F1F5F9;
                gridline-color: #334155;
                border: 1px solid #334155;
                border-radius: 6px;
            }
            QHeaderView::section {
                background-color: #0F172A;
                color: #E2E8F0;
                border: none;
                border-bottom: 1px solid #334155;
                padding: 5px 8px;
                font-weight: bold;
            }
            QTextEdit {
                background-color: #0F172A;
                color: #E2E8F0;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px;
            }
        """

    return """
        QWidget {
            background-color: #F1F5F9;
            color: #0F172A;
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 12px;
        }
        QScrollArea {
            background-color: #F1F5F9;
            border: none;
        }
        QFrame#Card {
            background-color: #FFFFFF;
            border: 1px solid #CBD5E1;
            border-radius: 8px;
        }
        QFrame#MetricCard {
            background-color: #FFFFFF;
            border: 1px solid #CBD5E1;
            border-radius: 8px;
        }
        QLabel#SectionTitle {
            color: #0F172A;
            font-size: 12px;
            font-weight: bold;
        }
        QLabel#MetricTitle {
            color: #64748B;
            font-size: 10px;
            font-weight: bold;
        }
        QLabel#MetricValue {
            color: #0284C7;
            font-size: 15px;
            font-weight: bold;
        }
        QLabel#MutedLabel {
            color: #475569;
            font-size: 11px;
        }
        QLineEdit, QComboBox {
            background-color: #FFFFFF;
            color: #0F172A;
            border: 1px solid #CBD5E1;
            border-radius: 5px;
            padding: 4px 7px;
        }
        QLineEdit:disabled, QComboBox:disabled {
            background-color: #E2E8F0;
            color: #94A3B8;
            border: 1px solid #CBD5E1;
        }
        QComboBox QAbstractItemView {
            background-color: #FFFFFF;
            color: #0F172A;
            selection-background-color: #DBEAFE;
            selection-color: #0F172A;
        }
        QCheckBox {
            color: #0F172A;
            spacing: 5px;
        }
        QCheckBox:disabled {
            color: #94A3B8;
        }
        QPushButton {
            background-color: #2563EB;
            color: #FFFFFF;
            border: none;
            border-radius: 5px;
            padding: 5px 11px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #1D4ED8;
        }
        QPushButton#SecondaryBtn {
            background-color: #E2E8F0;
            color: #1E293B;
        }
        QPushButton#SecondaryBtn:hover {
            background-color: #CBD5E1;
        }
        QPushButton#RunBtn {
            background-color: #10B981;
            color: #FFFFFF;
        }
        QPushButton#RunBtn:hover {
            background-color: #059669;
        }
        QPushButton#DangerBtn {
            background-color: #EF4444;
            color: #FFFFFF;
        }
        QPushButton#DangerBtn:hover {
            background-color: #DC2626;
        }
        QTableWidget {
            background-color: #FFFFFF;
            alternate-background-color: #F8FAFC;
            color: #0F172A;
            gridline-color: #E2E8F0;
            border: 1px solid #CBD5E1;
            border-radius: 6px;
        }
        QHeaderView::section {
            background-color: #1E293B;
            color: #FFFFFF;
            border: none;
            padding: 5px 8px;
            font-weight: bold;
        }
        QTextEdit {
            background-color: #FFFFFF;
            color: #0F172A;
            border: 1px solid #CBD5E1;
            border-radius: 6px;
            padding: 6px;
        }
    """


class CPUSchedulerApp(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("CPU Scheduling Simulator")
        self.setMinimumSize(720, 500)

        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            init_w = min(1140, max(760, int(avail.width() * 0.92)))
            init_h = min(720, max(540, int(avail.height() * 0.90)))
            self.resize(init_w, init_h)
        else:
            self.resize(1100, 700)

        self.theme = "light"
        self.processes: List[ProcessInput] = []
        self.last_output: Optional[ScheduleOutput] = None
        self.popout_window: Optional[GanttChart] = None

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        self.main_scroll = QScrollArea()
        self.main_scroll.setWidgetResizable(True)
        self.main_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.main_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.content_widget = QWidget()
        self.root_layout = QVBoxLayout(self.content_widget)
        self.root_layout.setContentsMargins(12, 10, 12, 10)
        self.root_layout.setSpacing(8)

        self.main_scroll.setWidget(self.content_widget)
        outer_layout.addWidget(self.main_scroll)

        self._build_header()
        self._build_controls_card()
        self._build_process_entry_card()
        self._build_metrics_row()
        self._build_workspace_splitter()

        self._apply_theme()
        self._sync_control_states()

    # ---------------- HELPER FOR INLINE GROUPS ----------------
    @staticmethod
    def _pair_widget(*widgets) -> QWidget:
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        for w in widgets:
            lay.addWidget(w)
        return box

    # ---------------- HEADER ----------------
    def _build_header(self):
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        title = QLabel("CPU Scheduling Simulator")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        subtitle = QLabel(
            "FCFS, SJF, SRTF, Priority (+Aging), Round Robin, HRRN & MLQ"
        )
        subtitle.setObjectName("MutedLabel")
        subtitle.setWordWrap(True)
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header_row.addLayout(title_col, stretch=1)

        self.theme_btn = QPushButton("Dark Theme")
        self.theme_btn.setObjectName("SecondaryBtn")
        self.theme_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.theme_btn.clicked.connect(self.toggle_theme)
        header_row.addWidget(self.theme_btn)

        self.root_layout.addLayout(header_row)

    # ---------------- ALGORITHM & OPTIONS CARD ----------------
    def _build_controls_card(self):
        card = QFrame()
        card.setObjectName("Card")
        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(10, 8, 10, 8)
        vbox.setSpacing(6)

        # Row 1: Algorithm selection + action buttons (always visible on right)
        top_flow = FlowLayout(margin=0, h_spacing=8, v_spacing=6)

        algo_lbl = QLabel("Algorithm:")
        algo_lbl.setObjectName("SectionTitle")
        self.algo_combo = QComboBox()
        self.algo_combo.addItems(ALGORITHMS)
        self.algo_combo.setMinimumWidth(190)
        self.algo_combo.currentTextChanged.connect(self._on_algorithm_changed)
        top_flow.addWidget(self._pair_widget(algo_lbl, self.algo_combo))

        self.sample_btn = QPushButton("Load Sample")
        self.sample_btn.setObjectName("SecondaryBtn")
        self.sample_btn.clicked.connect(self.load_sample_processes)

        self.run_btn = QPushButton("Run Schedule")
        self.run_btn.setObjectName("RunBtn")
        self.run_btn.clicked.connect(self.run_scheduler)

        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setObjectName("DangerBtn")
        self.reset_btn.clicked.connect(self.reset_all)

        top_flow.addWidget(self._pair_widget(self.sample_btn, self.run_btn, self.reset_btn))
        vbox.addLayout(top_flow)

        # Row 2: Wrapping parameters (Quantum, Aging, Context Switch, MLQ)
        opts_flow = FlowLayout(margin=0, h_spacing=12, v_spacing=6)

        self.quantum_lbl = QLabel("Quantum:")
        self.quantum_input = QLineEdit("2")
        self.quantum_input.setFixedWidth(50)
        self.quantum_input.setPlaceholderText("2")
        opts_flow.addWidget(self._pair_widget(self.quantum_lbl, self.quantum_input))

        self.aging_cb = QCheckBox("Aging")
        self.aging_cb.toggled.connect(self._sync_control_states)
        self.aging_lbl = QLabel("Interval:")
        self.aging_input = QLineEdit("4")
        self.aging_input.setFixedWidth(48)
        self.aging_input.setPlaceholderText("4")
        opts_flow.addWidget(
            self._pair_widget(self.aging_cb, self.aging_lbl, self.aging_input)
        )

        self.cs_cb = QCheckBox("Context Switch")
        self.cs_cb.toggled.connect(self._sync_control_states)
        self.cs_lbl = QLabel("CS Cost:")
        self.cs_input = QLineEdit("0.4")
        self.cs_input.setFixedWidth(55)
        self.cs_input.setPlaceholderText("0.4")
        opts_flow.addWidget(self._pair_widget(self.cs_cb, self.cs_lbl, self.cs_input))

        self.mlq_lbl = QLabel("MLQ:")
        self.mlq_lbl.setObjectName("SectionTitle")
        self.q0_lbl = QLabel("Q0:")
        self.q0_policy_combo = QComboBox()
        self.q0_policy_combo.addItems(["RR", "FCFS"])
        self.q0_policy_combo.currentTextChanged.connect(self._sync_control_states)
        self.q0_q_lbl = QLabel("q0:")
        self.q0_q_input = QLineEdit("2")
        self.q0_q_input.setFixedWidth(45)
        opts_flow.addWidget(
            self._pair_widget(
                self.mlq_lbl,
                self.q0_lbl,
                self.q0_policy_combo,
                self.q0_q_lbl,
                self.q0_q_input,
            )
        )

        self.q1_lbl = QLabel("Q1:")
        self.q1_policy_combo = QComboBox()
        self.q1_policy_combo.addItems(["FCFS", "SJF", "RR"])
        self.q1_policy_combo.currentTextChanged.connect(self._sync_control_states)
        self.q1_q_lbl = QLabel("q1:")
        self.q1_q_input = QLineEdit("4")
        self.q1_q_input.setFixedWidth(45)
        opts_flow.addWidget(
            self._pair_widget(
                self.q1_lbl,
                self.q1_policy_combo,
                self.q1_q_lbl,
                self.q1_q_input,
            )
        )

        vbox.addLayout(opts_flow)
        self.root_layout.addWidget(card)

    # ---------------- PROCESS ENTRY CARD ----------------
    def _build_process_entry_card(self):
        card = QFrame()
        card.setObjectName("Card")
        flow = FlowLayout(margin=8, h_spacing=8, v_spacing=6)
        card.setLayout(flow)

        entry_lbl = QLabel("Add Process:")
        entry_lbl.setObjectName("SectionTitle")
        flow.addWidget(entry_lbl)

        self.pid_input = QLineEdit()
        self.pid_input.setPlaceholderText("PID (P1)")
        self.pid_input.setFixedWidth(85)

        self.at_input = QLineEdit()
        self.at_input.setPlaceholderText("AT")
        self.at_input.setFixedWidth(75)

        self.bt_input = QLineEdit()
        self.bt_input.setPlaceholderText("BT")
        self.bt_input.setFixedWidth(75)

        self.prio_lbl = QLabel("Priority:")
        self.prio_input = QLineEdit("0")
        self.prio_input.setPlaceholderText("0")
        self.prio_input.setFixedWidth(55)

        self.queue_lbl = QLabel("Queue:")
        self.queue_combo = QComboBox()
        self.queue_combo.addItems(["0 (High)", "1 (Low)"])
        self.queue_combo.setFixedWidth(105)

        self.add_btn = QPushButton("Add Process")
        self.add_btn.clicked.connect(self.add_process)

        self.remove_btn = QPushButton("Remove Selected")
        self.remove_btn.setObjectName("SecondaryBtn")
        self.remove_btn.clicked.connect(self.remove_selected_process)

        flow.addWidget(self._pair_widget(self.pid_input, self.at_input, self.bt_input))
        flow.addWidget(self._pair_widget(self.prio_lbl, self.prio_input))
        flow.addWidget(self._pair_widget(self.queue_lbl, self.queue_combo))
        flow.addWidget(self._pair_widget(self.add_btn, self.remove_btn))

        self.root_layout.addWidget(card)

    # ---------------- METRICS CARDS (4x2 RESPONSIVE GRID) ----------------
    def _build_metrics_row(self):
        grid = QGridLayout()
        grid.setSpacing(6)

        self.metric_labels = {}
        specs = [
            ("avg_wt", "AVG WAITING TIME"),
            ("avg_tat", "AVG TURNAROUND TIME"),
            ("avg_rt", "AVG RESPONSE TIME"),
            ("avg_bt", "AVG BURST TIME"),
            ("throughput", "THROUGHPUT"),
            ("cpu_util", "CPU UTILIZATION"),
            ("cs_count", "CONTEXT SWITCHES"),
            ("cs_overhead", "TOTAL CS OVERHEAD"),
        ]

        for idx, (key, title_text) in enumerate(specs):
            card = QFrame()
            card.setObjectName("MetricCard")
            vbox = QVBoxLayout(card)
            vbox.setContentsMargins(8, 6, 8, 6)
            vbox.setSpacing(1)

            title_lbl = QLabel(title_text)
            title_lbl.setObjectName("MetricTitle")
            val_lbl = QLabel("-")
            val_lbl.setObjectName("MetricValue")

            vbox.addWidget(title_lbl)
            vbox.addWidget(val_lbl)
            grid.addWidget(card, idx // 4, idx % 4)
            self.metric_labels[key] = val_lbl

        self.root_layout.addLayout(grid)

    # ---------------- GANTT + BOTTOM PANELS IN VERTICAL SPLITTER ----------------
    def _build_workspace_splitter(self):
        v_splitter = QSplitter(Qt.Orientation.Vertical)

        # Top: Gantt Chart Card
        gantt_card = QFrame()
        gantt_card.setObjectName("Card")
        gantt_vbox = QVBoxLayout(gantt_card)
        gantt_vbox.setContentsMargins(10, 6, 10, 6)
        gantt_vbox.setSpacing(4)

        top_bar = QHBoxLayout()
        lbl = QLabel("Gantt Chart")
        lbl.setObjectName("SectionTitle")
        top_bar.addWidget(lbl)
        top_bar.addStretch()

        self.popout_btn = QPushButton("Pop Out Gantt")
        self.popout_btn.setObjectName("SecondaryBtn")
        self.popout_btn.setEnabled(False)
        self.popout_btn.clicked.connect(self.open_popout_gantt)
        top_bar.addWidget(self.popout_btn)
        gantt_vbox.addLayout(top_bar)

        self.gantt_widget = GanttChartWidget(theme=self.theme)
        self.gantt_widget.setMinimumHeight(185)
        gantt_vbox.addWidget(self.gantt_widget)

        # Bottom: Horizontal Splitter (Process Table | Iteration Log)
        h_splitter = QSplitter(Qt.Orientation.Horizontal)

        left_card = QFrame()
        left_card.setObjectName("Card")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(10, 6, 10, 6)
        left_layout.setSpacing(4)

        table_title = QLabel("Process Table & Metrics")
        table_title.setObjectName("SectionTitle")
        left_layout.addWidget(table_title)

        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setMinimumHeight(175)
        self.table.setHorizontalHeaderLabels([
            "PID",
            "AT",
            "BT",
            "Init Priority",
            "Final Priority",
            "Queue",
            "CT",
            "TAT",
            "WT",
            "RT",
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setMinimumSectionSize(52)
        header.setStretchLastSection(True)
        left_layout.addWidget(self.table)

        right_card = QFrame()
        right_card.setObjectName("Card")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(10, 6, 10, 6)
        right_layout.setSpacing(4)

        log_title = QLabel("Step-by-Step Iteration & Decision Log")
        log_title.setObjectName("SectionTitle")
        right_layout.addWidget(log_title)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(175)
        self.log_view.setFont(QFont("Consolas", 9))
        self.log_view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.log_view.setPlaceholderText(
            "Step-by-step scheduling iterations, aging calculations, response ratios, and context switches appear here..."
        )
        right_layout.addWidget(self.log_view)

        h_splitter.addWidget(left_card)
        h_splitter.addWidget(right_card)
        h_splitter.setSizes([600, 480])

        v_splitter.addWidget(gantt_card)
        v_splitter.addWidget(h_splitter)
        v_splitter.setSizes([225, 250])

        self.root_layout.addWidget(v_splitter, stretch=1)

    # ---------------- STATE MANAGEMENT ----------------
    def _on_algorithm_changed(self, algo_text: str):
        if algo_text == "Priority (Non-Preemptive)" and not self.aging_input.text().strip():
            self.aging_input.setText("4")
        elif algo_text == "Priority (Preemptive)" and self.aging_input.text().strip() in ("", "4"):
            self.aging_input.setText("3")
        self._sync_control_states()

    def _sync_control_states(self):
        algo = self.algo_combo.currentText()
        is_rr = algo == "Round Robin (Preemptive)"
        is_prio = algo in ("Priority (Non-Preemptive)", "Priority (Preemptive)")
        is_mlq = algo == "Multi-Level Queue (MLQ)"

        self.quantum_lbl.setEnabled(is_rr)
        self.quantum_input.setEnabled(is_rr)

        self.aging_cb.setEnabled(is_prio)
        if not is_prio and self.aging_cb.isChecked():
            self.aging_cb.blockSignals(True)
            self.aging_cb.setChecked(False)
            self.aging_cb.blockSignals(False)
        aging_active = is_prio and self.aging_cb.isChecked()
        self.aging_lbl.setEnabled(aging_active)
        self.aging_input.setEnabled(aging_active)

        self.cs_cb.setEnabled(True)
        cs_active = self.cs_cb.isChecked()
        self.cs_lbl.setEnabled(cs_active)
        self.cs_input.setEnabled(cs_active)

        self.mlq_lbl.setEnabled(is_mlq)
        self.q0_lbl.setEnabled(is_mlq)
        self.q0_policy_combo.setEnabled(is_mlq)
        q0_is_rr = is_mlq and self.q0_policy_combo.currentText() == "RR"
        self.q0_q_lbl.setEnabled(q0_is_rr)
        self.q0_q_input.setEnabled(q0_is_rr)

        self.q1_lbl.setEnabled(is_mlq)
        self.q1_policy_combo.setEnabled(is_mlq)
        q1_is_rr = is_mlq and self.q1_policy_combo.currentText() == "RR"
        self.q1_q_lbl.setEnabled(q1_is_rr)
        self.q1_q_input.setEnabled(q1_is_rr)

        self.prio_lbl.setEnabled(is_prio)
        self.prio_input.setEnabled(is_prio)
        self.queue_lbl.setEnabled(is_mlq)
        self.queue_combo.setEnabled(is_mlq)

        self.table.setColumnHidden(3, not is_prio)
        self.table.setColumnHidden(4, not is_prio)
        self.table.setColumnHidden(5, not is_mlq)

    # ---------------- THEME ----------------
    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        self._apply_theme()

    def _apply_theme(self):
        self.setStyleSheet(build_stylesheet(self.theme))
        self.theme_btn.setText("Light Theme" if self.theme == "dark" else "Dark Theme")
        self.gantt_widget.set_theme(self.theme)
        if self.popout_window:
            self.popout_window.setStyleSheet(build_stylesheet(self.theme))
            self.popout_window.chart_widget.set_theme(self.theme)

    # ---------------- PROCESS ACTIONS ----------------
    def add_process(self):
        raw_pid = self.pid_input.text().strip()
        pid = raw_pid if raw_pid else f"P{len(self.processes) + 1}"

        if any(p.pid == pid for p in self.processes):
            QMessageBox.warning(
                self, "Duplicate PID", f"Process '{pid}' already exists. Use a unique PID."
            )
            return

        try:
            at = float(self.at_input.text().strip())
            bt = float(self.bt_input.text().strip())
        except ValueError:
            QMessageBox.warning(
                self, "Invalid Input", "Arrival Time and Burst Time must be numeric."
            )
            return

        if at < 0 or bt <= 0:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Arrival Time must be >= 0 and Burst Time must be > 0.",
            )
            return

        prio = 0
        if self.prio_input.isEnabled():
            try:
                prio_txt = self.prio_input.text().strip()
                prio = int(prio_txt) if prio_txt else 0
                if prio < 0:
                    raise ValueError
            except ValueError:
                QMessageBox.warning(
                    self, "Invalid Priority", "Priority must be a non-negative integer."
                )
                return

        queue_level = self.queue_combo.currentIndex() if self.queue_combo.isEnabled() else 0

        self.processes.append(
            ProcessInput(pid=pid, at=at, bt=bt, priority=prio, queue_level=queue_level)
        )
        self.pid_input.clear()
        self.at_input.clear()
        self.bt_input.clear()
        if self.prio_input.isEnabled():
            self.prio_input.setText("0")

        self._refresh_preview_table()

    def remove_selected_process(self):
        selected_rows = sorted(
            {idx.row() for idx in self.table.selectionModel().selectedRows()},
            reverse=True,
        )
        if not selected_rows:
            return
        for r in selected_rows:
            if 0 <= r < len(self.processes):
                self.processes.pop(r)
        self._refresh_preview_table()

    def load_sample_processes(self):
        self.processes = [
            ProcessInput("P1", 0, 5, priority=2, queue_level=0),
            ProcessInput("P2", 1, 3, priority=1, queue_level=0),
            ProcessInput("P3", 2, 6, priority=4, queue_level=1),
            ProcessInput("P4", 4, 4, priority=3, queue_level=1),
        ]
        self.last_output = None
        self.popout_btn.setEnabled(False)
        self.gantt_widget.update_chart(None)
        self._clear_metric_cards()
        self.log_view.clear()
        self._refresh_preview_table()

    def _refresh_preview_table(self):
        self.table.setRowCount(len(self.processes))
        for i, p in enumerate(self.processes):
            vals = [
                p.pid,
                _fmt(p.at),
                _fmt(p.bt),
                str(p.priority),
                "-",
                f"Q{p.queue_level}",
                "-",
                "-",
                "-",
                "-",
            ]
            for col, text in enumerate(vals):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(i, col, item)

    def _clear_metric_cards(self):
        for lbl in self.metric_labels.values():
            lbl.setText("-")

    def reset_all(self):
        self.processes = []
        self.last_output = None
        self.table.setRowCount(0)
        self._clear_metric_cards()
        self.gantt_widget.update_chart(None)
        self.popout_btn.setEnabled(False)
        self.log_view.clear()

        if self.popout_window:
            self.popout_window.close()
            self.popout_window = None

        self.pid_input.clear()
        self.at_input.clear()
        self.bt_input.clear()
        self.prio_input.setText("0")
        self.queue_combo.setCurrentIndex(0)
        self.quantum_input.setText("2")
        self.aging_cb.setChecked(False)
        self.aging_input.setText("4")
        self.cs_cb.setChecked(False)
        self.cs_input.setText("0.4")
        self.q0_policy_combo.setCurrentText("RR")
        self.q0_q_input.setText("2")
        self.q1_policy_combo.setCurrentText("FCFS")
        self.q1_q_input.setText("4")
        self.algo_combo.setCurrentIndex(0)
        self._sync_control_states()

    # ---------------- RUN SCHEDULER ----------------
    def run_scheduler(self):
        if not self.processes:
            QMessageBox.information(
                self, "No Processes", "Add processes or click 'Load Sample' first."
            )
            return

        algo = self.algo_combo.currentText()

        cs_enabled = self.cs_cb.isChecked()
        cs_time = 0.0
        if cs_enabled:
            try:
                cs_time = float(self.cs_input.text().strip())
                if cs_time < 0:
                    raise ValueError
            except ValueError:
                QMessageBox.warning(
                    self,
                    "Invalid Context Switch",
                    "CS Duration must be a non-negative number.",
                )
                return

        procs = [
            ProcessInput(
                pid=p.pid,
                at=p.at,
                bt=p.bt,
                priority=p.priority,
                queue_level=p.queue_level,
            )
            for p in self.processes
        ]

        if algo == "FCFS (Non-Preemptive)":
            out = run_fcfs(procs, cs_enabled=cs_enabled, cs_time=cs_time)

        elif algo == "SJF (Non-Preemptive)":
            out = run_sjf_non_preemptive(procs, cs_enabled=cs_enabled, cs_time=cs_time)

        elif algo == "SRTF (Preemptive SJF)":
            out = run_srtf_preemptive(procs, cs_enabled=cs_enabled, cs_time=cs_time)

        elif algo in ("Priority (Non-Preemptive)", "Priority (Preemptive)"):
            aging_enabled = self.aging_cb.isChecked()
            aging_interval = 4.0
            if aging_enabled:
                try:
                    aging_interval = float(self.aging_input.text().strip())
                    if aging_interval <= 0:
                        raise ValueError
                except ValueError:
                    QMessageBox.warning(
                        self,
                        "Invalid Aging Interval",
                        "Aging Interval must be greater than 0.",
                    )
                    return
            if algo == "Priority (Non-Preemptive)":
                out = run_priority_non_preemptive(
                    procs,
                    aging_enabled=aging_enabled,
                    aging_interval=aging_interval,
                    cs_enabled=cs_enabled,
                    cs_time=cs_time,
                )
            else:
                out = run_priority_preemptive(
                    procs,
                    aging_enabled=aging_enabled,
                    aging_interval=aging_interval,
                    cs_enabled=cs_enabled,
                    cs_time=cs_time,
                )

        elif algo == "Round Robin (Preemptive)":
            try:
                quantum = float(self.quantum_input.text().strip())
                if quantum <= 0:
                    raise ValueError
            except ValueError:
                QMessageBox.warning(
                    self, "Invalid Quantum", "Time Quantum must be greater than 0."
                )
                return
            out = run_round_robin(
                procs, quantum=quantum, cs_enabled=cs_enabled, cs_time=cs_time
            )

        elif algo == "HRRN (Non-Preemptive)":
            out = run_hrrn(procs, cs_enabled=cs_enabled, cs_time=cs_time)

        elif algo == "Multi-Level Queue (MLQ)":
            q0_pol = self.q0_policy_combo.currentText()
            q1_pol = self.q1_policy_combo.currentText()
            try:
                q0_q = float(self.q0_q_input.text().strip()) if q0_pol == "RR" else 2.0
                q1_q = float(self.q1_q_input.text().strip()) if q1_pol == "RR" else 4.0
                if q0_q <= 0 or q1_q <= 0:
                    raise ValueError
            except ValueError:
                QMessageBox.warning(
                    self, "Invalid Queue Quantum", "MLQ Quanta must be greater than 0."
                )
                return
            out = run_multilevel_queue(
                procs,
                q0_policy=q0_pol,
                q0_quantum=q0_q,
                q1_policy=q1_pol,
                q1_quantum=q1_q,
                cs_enabled=cs_enabled,
                cs_time=cs_time,
            )
        else:
            return

        self.last_output = out
        self._render_output(out)

    def _render_output(self, out: ScheduleOutput):
        self.metric_labels["avg_wt"].setText(f"{out.avg_wt:.2f}")
        self.metric_labels["avg_tat"].setText(f"{out.avg_tat:.2f}")
        self.metric_labels["avg_rt"].setText(f"{out.avg_rt:.2f}")
        self.metric_labels["avg_bt"].setText(f"{out.avg_bt:.2f}")
        self.metric_labels["throughput"].setText(f"{out.throughput:.4f} /unit")
        self.metric_labels["cpu_util"].setText(f"{out.cpu_utilization:.2f}%")
        self.metric_labels["cs_count"].setText(str(out.context_switch_count))
        self.metric_labels["cs_overhead"].setText(_fmt(out.total_cs_overhead))

        self.gantt_widget.update_chart(out)
        self.popout_btn.setEnabled(True)
        if self.popout_window and self.popout_window.isVisible():
            self.popout_window.close()
            self.open_popout_gantt()

        self.table.setRowCount(len(out.results))
        for i, r in enumerate(out.results):
            vals = [
                r.pid,
                _fmt(r.at),
                _fmt(r.bt),
                str(r.initial_priority),
                str(r.final_priority),
                f"Q{r.queue_level}",
                _fmt(r.ct),
                _fmt(r.tat),
                _fmt(r.wt),
                _fmt(r.rt),
            ]
            for col, text in enumerate(vals):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(i, col, item)

        lines = list(out.iteration_logs)
        lines.append("")
        lines.append("=== Summary Metrics ===")
        lines.append(f"Average Waiting Time    : {out.avg_wt:.2f}")
        lines.append(f"Average Turnaround Time : {out.avg_tat:.2f}")
        lines.append(f"Average Response Time   : {out.avg_rt:.2f}")
        lines.append(f"Average Burst Time      : {out.avg_bt:.2f}")
        lines.append(f"Throughput              : {out.throughput:.4f} proc/unit")
        lines.append(f"CPU Utilization         : {out.cpu_utilization:.2f}%")
        if out.context_switch_count > 0:
            pts = ", ".join(_fmt(p) for p in out.context_switch_points)
            lines.append(
                f"Context Switches        : {out.context_switch_count} "
                f"(at t=[{pts}], total overhead={_fmt(out.total_cs_overhead)})"
            )
        else:
            lines.append("Context Switches        : 0")
        self.log_view.setPlainText("\n".join(lines))

    def open_popout_gantt(self):
        if not self.last_output:
            return
        if self.popout_window:
            self.popout_window.close()
        self.popout_window = GanttChart(self.last_output, theme=self.theme)
        self.popout_window.setStyleSheet(build_stylesheet(self.theme))
        self.popout_window.show()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CPUSchedulerApp()
    window.show()
    sys.exit(app.exec())
