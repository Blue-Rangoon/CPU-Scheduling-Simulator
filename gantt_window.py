from typing import Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from scheduler_engine import GanttSegment, ScheduleOutput, _fmt


PROCESS_PALETTE = [
    "#3B82F6",  # Blue
    "#10B981",  # Emerald
    "#8B5CF6",  # Violet
    "#EC4899",  # Pink
    "#14B8A6",  # Teal
    "#F59E0B",  # Amber
    "#06B6D4",  # Cyan
    "#EF4444",  # Rose
]


class _LegendSwatch(QWidget):
    """Draws an exact visual swatch (process block, gray IDLE block, or thin orange CS line)."""

    def __init__(self, kind: str, theme: str = "light", color: str = "#3B82F6"):
        super().__init__()
        self.kind = kind
        self.theme = theme
        self.color = color
        self.setFixedSize(16 if kind != "cs" else 12, 18)

    def set_theme(self, theme: str):
        self.theme = theme
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.kind == "cs":
            painter.setPen(QPen(QColor("#F97316"), 3))
            cx = self.width() // 2
            painter.drawLine(cx, 1, cx, self.height() - 2)
        else:
            if self.kind == "idle":
                fill = QColor("#CBD5E1") if self.theme == "light" else QColor("#475569")
            else:
                fill = QColor(self.color)
            border = QColor("#1E293B") if self.theme == "light" else QColor("#E2E8F0")
            painter.setBrush(fill)
            painter.setPen(QPen(border, 1))
            painter.drawRoundedRect(1, 2, 13, 13, 2, 2)

        painter.end()


class _GanttCanvas(QWidget):
    """Pure-Python QPainter canvas for process blocks, IDLE blocks, and CS divider lines."""

    def __init__(self, segments: List[GanttSegment], theme: str = "light"):
        super().__init__()
        self.segments = segments
        self.theme = theme
        self.scale = 44.0
        self.margin_x = 42
        self.min_block_width = 52.0

        self.pid_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        self.sub_font = QFont("Segoe UI", 8)
        self.interval_font = QFont("Segoe UI", 8)
        self.tick_font = QFont("Segoe UI", 9)

        self.pid_colors: Dict[str, str] = {}
        idx = 0
        for seg in self.segments:
            if not seg.is_idle and seg.pid != "IDLE" and seg.pid not in self.pid_colors:
                self.pid_colors[seg.pid] = PROCESS_PALETTE[idx % len(PROCESS_PALETTE)]
                idx += 1

        self.blocks, self.cs_positions, self.tick_points, total_x = self._compute_layout()
        self.setMinimumSize(max(360, total_x + self.margin_x), 178)

    def set_data(self, segments: List[GanttSegment]):
        self.segments = segments
        self.pid_colors = {}
        idx = 0
        for seg in self.segments:
            if not seg.is_idle and seg.pid != "IDLE" and seg.pid not in self.pid_colors:
                self.pid_colors[seg.pid] = PROCESS_PALETTE[idx % len(PROCESS_PALETTE)]
                idx += 1
        self.blocks, self.cs_positions, self.tick_points, total_x = self._compute_layout()
        self.setMinimumSize(max(360, total_x + self.margin_x), 178)
        self.update()

    def set_theme(self, theme: str):
        self.theme = theme
        self.update()

    def _compute_layout(self):
        pid_fm = QFontMetrics(self.pid_font)
        x = float(self.margin_x)
        blocks = []
        cs_positions = []
        tick_points = []
        prev_end: Optional[float] = None

        for seg in self.segments:
            is_idle = seg.is_idle or seg.pid == "IDLE"
            label = "IDLE" if is_idle else str(seg.pid)
            min_pid_w = pid_fm.horizontalAdvance(label) + 18
            width = max(
                self.min_block_width,
                float(min_pid_w),
                float(seg.end - seg.start) * self.scale,
            )

            ix = int(round(x))
            iw = int(round(width))

            if seg.cs_before:
                cs_positions.append(ix)

            start_lbl = _fmt(seg.start)
            end_lbl = _fmt(seg.end)

            blocks.append({
                "pid": label,
                "is_idle": is_idle,
                "queue_level": seg.queue_level,
                "x": ix,
                "w": iw,
                "start_lbl": start_lbl,
                "end_lbl": end_lbl,
            })

            if prev_end is not None and abs(prev_end - seg.start) > 1e-6:
                tick_points.append((ix, f"{_fmt(prev_end)}/{start_lbl}"))
            else:
                tick_points.append((ix, start_lbl))

            prev_end = seg.end
            x += iw

        if prev_end is not None:
            tick_points.append((int(round(x)), _fmt(prev_end)))

        return blocks, cs_positions, tick_points, int(round(x))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        is_dark = self.theme == "dark"
        bg_color = QColor("#1E293B") if is_dark else QColor("#FFFFFF")
        text_color = QColor("#F1F5F9") if is_dark else QColor("#0F172A")
        muted_color = QColor("#94A3B8") if is_dark else QColor("#475569")
        border_color = QColor("#475569") if is_dark else QColor("#334155")
        idle_fill = QColor("#475569") if is_dark else QColor("#CBD5E1")
        idle_text = QColor("#E2E8F0") if is_dark else QColor("#334155")

        painter.fillRect(self.rect(), bg_color)

        if not self.blocks:
            painter.setFont(QFont("Segoe UI", 10))
            painter.setPen(muted_color)
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Run a scheduling algorithm to render the Gantt chart.",
            )
            painter.end()
            return

        y = 18
        height = 48
        interval_y = y + height + 6
        line_y = y + height + 30

        interval_fm = QFontMetrics(self.interval_font)
        tick_fm = QFontMetrics(self.tick_font)

        for blk in self.blocks:
            ix, iw = blk["x"], blk["w"]
            is_idle = blk["is_idle"]
            fill = idle_fill if is_idle else QColor(self.pid_colors.get(blk["pid"], PROCESS_PALETTE[0]))

            painter.setBrush(fill)
            painter.setPen(QPen(border_color, 1))
            painter.drawRect(ix, y, iw, height)

            painter.setFont(self.pid_font)
            painter.setPen(idle_text if is_idle else QColor("#FFFFFF"))
            if blk["queue_level"] is not None and not is_idle:
                painter.drawText(ix, y + 6, iw, 24, Qt.AlignmentFlag.AlignCenter, blk["pid"])
                painter.setFont(self.sub_font)
                painter.drawText(
                    ix, y + 29, iw, 18, Qt.AlignmentFlag.AlignCenter, f"Q{blk['queue_level']}"
                )
            else:
                painter.drawText(ix, y, iw, height, Qt.AlignmentFlag.AlignCenter, blk["pid"])

            interval_text = f"{blk['start_lbl']}-{blk['end_lbl']}"
            if interval_fm.horizontalAdvance(interval_text) <= iw - 6:
                painter.setFont(self.interval_font)
                painter.setPen(muted_color)
                painter.drawText(
                    ix, interval_y, iw, 16, Qt.AlignmentFlag.AlignCenter, interval_text
                )

        start_x = self.blocks[0]["x"]
        end_x = self.blocks[-1]["x"] + self.blocks[-1]["w"]
        painter.setPen(QPen(border_color, 1))
        painter.drawLine(start_x, line_y, end_x, line_y)

        # Collision-free staggered timeline tick labels
        painter.setFont(self.tick_font)
        row_right_edge = [-10_000, -10_000]
        row_y = [line_y + 18, line_y + 34]
        min_gap = 10
        last_idx = len(self.tick_points) - 1

        for idx, (tx, label) in enumerate(self.tick_points):
            painter.setPen(QPen(border_color, 1))
            painter.drawLine(tx, line_y - 4, tx, line_y + 4)

            text_w = tick_fm.horizontalAdvance(label)
            left_x = tx - (text_w // 2)
            if idx == 0:
                left_x = max(4, left_x)
            right_x = left_x + text_w

            chosen_row = None
            for r in (0, 1):
                if left_x >= row_right_edge[r] + min_gap:
                    chosen_row = r
                    break

            if chosen_row is None and idx == last_idx:
                chosen_row = 1 if row_right_edge[1] <= row_right_edge[0] else 0

            if chosen_row is not None:
                painter.setPen(QPen(text_color, 1))
                painter.drawText(left_x, row_y[chosen_row], label)
                row_right_edge[chosen_row] = right_x

        # Thin orange context-switch boundary dividers (never a CS box or extra label)
        if self.cs_positions:
            painter.setPen(QPen(QColor("#F97316"), 3))
            for cx in self.cs_positions:
                painter.drawLine(cx, y - 6, cx, y + height + 6)

        painter.end()


class GanttChartWidget(QWidget):
    """Reusable Gantt chart panel with visual color-swatch legend and scrollable canvas."""

    def __init__(self, segments: Optional[List[GanttSegment]] = None, theme: str = "light"):
        super().__init__()
        self.theme = theme
        self._swatches: List[_LegendSwatch] = []
        self._legend_labels: List[QLabel] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        legend_row = QHBoxLayout()
        legend_row.setContentsMargins(4, 0, 4, 0)
        legend_row.setSpacing(6)

        for kind, color, text in (
            ("process", PROCESS_PALETTE[0], "Process"),
            ("idle", "#CBD5E1", "Idle"),
            ("cs", "#F97316", "Context Switch"),
        ):
            swatch = _LegendSwatch(kind, theme=self.theme, color=color)
            self._swatches.append(swatch)
            legend_row.addWidget(swatch)

            lbl = QLabel(text)
            lbl.setStyleSheet("font-size: 12px; margin-right: 14px;")
            self._legend_labels.append(lbl)
            legend_row.addWidget(lbl)

        legend_row.addStretch()
        layout.addLayout(legend_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.canvas = _GanttCanvas(segments or [], theme=self.theme)
        self.scroll.setWidget(self.canvas)
        layout.addWidget(self.scroll)

        self.set_theme(self.theme)

    def update_chart(self, output: Optional[ScheduleOutput]):
        self.canvas.set_data(output.gantt if output else [])

    def set_theme(self, theme: str):
        self.theme = theme
        for sw in self._swatches:
            sw.set_theme(theme)
        text_hex = "#CBD5E1" if theme == "dark" else "#334155"
        for lbl in self._legend_labels:
            lbl.setStyleSheet(f"font-size: 12px; color: {text_hex}; margin-right: 14px;")
        self.canvas.set_theme(theme)


class GanttChart(QWidget):
    """Standalone Gantt Chart Viewer window (for pop-out viewing or direct instantiation)."""

    def __init__(self, output: ScheduleOutput, theme: str = "light"):
        super().__init__()
        self.setWindowTitle(f"Gantt Chart — {output.algorithm} ({output.mode})")
        self.resize(1020, 310)

        layout = QVBoxLayout(self)
        summary = QLabel(
            f"Avg WT: {output.avg_wt:.2f}  |  Avg TAT: {output.avg_tat:.2f}  |  "
            f"Avg RT: {output.avg_rt:.2f}  |  Avg BT: {output.avg_bt:.2f}  |  "
            f"Throughput: {output.throughput:.4f}  |  CPU Utilization: {output.cpu_utilization:.2f}%"
        )
        summary.setStyleSheet("font-weight: bold; font-size: 13px; padding: 4px;")
        layout.addWidget(summary)

        self.chart_widget = GanttChartWidget(output.gantt, theme=theme)
        layout.addWidget(self.chart_widget)
