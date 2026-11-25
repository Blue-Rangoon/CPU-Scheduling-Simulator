"""Gantt chart widgets (PyQt6) with colour families, idle/context-switch blocks and step-by-step reveal."""
from typing import Dict, List, Optional

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget)

from scheduler_engine import GanttSegment, ScheduleOutput, _fmt, text_color_for

THEMES = {
    "light": dict(bg="#FFFFFF", axis="#374151", muted="#9CA3AF", idle="#E5E7EB", idle_line="#9CA3AF",
                  cs="#374151", marker="#DC2626", text="#111827"),
    "dark": dict(bg="#111827", axis="#D1D5DB", muted="#6B7280", idle="#374151", idle_line="#6B7280",
                 cs="#9CA3AF", marker="#F87171", text="#F9FAFB"),
}


class GanttCanvas(QWidget):
    LEFT, TOP, BAR_H = 20, 34, 64

    def __init__(self, theme: str = "light"):
        super().__init__()
        self.theme = theme
        self.segments: List[GanttSegment] = []
        self.colors: Dict[str, str] = {}
        self.reveal: Optional[float] = None     # None = show everything
        self.title = ""
        self.unit_px = 34
        self.setMinimumHeight(self.TOP + self.BAR_H + 70)

    def set_data(self, segments, colors, title="", reveal=None):
        self.segments, self.colors, self.title, self.reveal = segments, colors, title, reveal
        total = max((s.end for s in segments), default=1)
        self.unit_px = 34 if total <= 40 else (24 if total <= 80 else 14)
        self.setMinimumWidth(int(self.LEFT * 2 + total * self.unit_px) + 20)
        self.update()

    def set_reveal(self, t: Optional[float]):
        self.reveal = t
        self.update()

    def set_theme(self, theme: str):
        self.theme = theme
        self.update()

    def paintEvent(self, _):
        th = THEMES[self.theme]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(th["bg"]))
        if not self.segments:
            p.setPen(QColor(th["muted"]))
            p.setFont(QFont("Segoe UI", 11))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Run an algorithm to see the Gantt chart")
            return
        f = QFont("Segoe UI", 10, QFont.Weight.Bold)
        small = QFont("Segoe UI", 8)
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        p.setPen(QColor(th["text"]))
        p.drawText(self.LEFT, 22, self.title)
        y = self.TOP
        last_label_x = -100
        end_all = max(s.end for s in self.segments)
        for s in self.segments:
            x0 = self.LEFT + s.start * self.unit_px
            x1 = self.LEFT + s.end * self.unit_px
            visible_end = s.end if self.reveal is None else min(s.end, self.reveal)
            if visible_end <= s.start:
                p.setPen(QPen(QColor(th["muted"]), 1, Qt.PenStyle.DotLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(QRectF(x0 + 1, y, x1 - x0 - 2, self.BAR_H), 4, 4)
                continue
            xv = self.LEFT + visible_end * self.unit_px
            rect = QRectF(x0 + 1, y, xv - x0 - 2, self.BAR_H)
            if s.kind == "run":
                col = QColor(self.colors.get(s.pid, "#3B82F6"))
                p.setPen(QPen(QColor(th["bg"]), 2))
                p.setBrush(QBrush(col))
                label_col = QColor(text_color_for(col.name()))
            elif s.kind == "idle":
                col = QColor(th["idle"])
                p.setPen(QPen(QColor(th["idle_line"]), 1))
                p.setBrush(QBrush(col, Qt.BrushStyle.BDiagPattern))
                label_col = QColor(th["axis"])
            else:
                col = QColor(th["cs"])
                p.setPen(QPen(QColor(th["bg"]), 2))
                p.setBrush(QBrush(col, Qt.BrushStyle.Dense4Pattern))
                label_col = QColor(th["text"])
            p.drawRoundedRect(rect, 4, 4)
            label = s.pid if s.kind == "run" else ("IDLE" if s.kind == "idle" else "CS")
            p.setFont(f if s.kind == "run" else small)
            if rect.width() > QFontMetrics(p.font()).horizontalAdvance(label) + 6:
                p.setPen(label_col)
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
            # time labels
            p.setFont(small)
            p.setPen(QColor(th["axis"]))
            for tv, xx in ((s.start, x0),):
                lab = _fmt(tv)
                w = QFontMetrics(small).horizontalAdvance(lab)
                if xx - last_label_x > w + 6:
                    p.drawText(QRectF(xx - 20, y + self.BAR_H + 6, 40, 16), Qt.AlignmentFlag.AlignCenter, lab)
                    last_label_x = xx
            if visible_end >= s.end and s.end >= end_all - 1e-9:
                lab = _fmt(s.end)
                p.drawText(QRectF(x1 - 20, y + self.BAR_H + 6, 40, 16), Qt.AlignmentFlag.AlignCenter, lab)
        if self.reveal is not None:
            xm = self.LEFT + min(self.reveal, end_all) * self.unit_px
            p.setPen(QPen(QColor(th["marker"]), 2))
            p.drawLine(int(xm), y - 8, int(xm), y + self.BAR_H + 8)
            p.setFont(small)
            p.drawText(QRectF(xm - 25, y - 24, 50, 14), Qt.AlignmentFlag.AlignCenter, f"t={_fmt(min(self.reveal, end_all))}")
        # axis line
        p.setPen(QPen(QColor(th["axis"]), 1))
        p.drawLine(self.LEFT, y + self.BAR_H + 2, int(self.LEFT + end_all * self.unit_px), y + self.BAR_H + 2)
        # legend
        lx, ly = self.LEFT, y + self.BAR_H + 40
        p.setFont(small)
        for pid, c in self.colors.items():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(c))
            p.drawRoundedRect(QRectF(lx, ly, 14, 14), 3, 3)
            p.setPen(QColor(th["text"]))
            p.drawText(QRectF(lx + 18, ly - 1, 40, 16), Qt.AlignmentFlag.AlignVCenter, pid)
            lx += 18 + QFontMetrics(small).horizontalAdvance(pid) + 16
        p.setBrush(QBrush(QColor(th["idle"]), Qt.BrushStyle.BDiagPattern))
        p.setPen(QPen(QColor(th["idle_line"]), 1))
        p.drawRoundedRect(QRectF(lx, ly, 14, 14), 3, 3)
        p.setPen(QColor(th["text"]))
        p.drawText(QRectF(lx + 18, ly - 1, 40, 16), Qt.AlignmentFlag.AlignVCenter, "Idle")
        lx += 62
        p.setBrush(QBrush(QColor(th["cs"]), Qt.BrushStyle.Dense4Pattern))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(lx, ly, 14, 14), 3, 3)
        p.setPen(QColor(th["text"]))
        p.drawText(QRectF(lx + 18, ly - 1, 90, 16), Qt.AlignmentFlag.AlignVCenter, "Context switch")


class GanttChartWidget(QScrollArea):
    def __init__(self, theme: str = "light"):
        super().__init__()
        self.canvas = GanttCanvas(theme)
        self.setWidget(self.canvas)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setMinimumHeight(self.canvas.minimumHeight() + 18)

    def show_output(self, out: Optional[ScheduleOutput], colors: Dict[str, str], reveal: Optional[float] = None):
        if out is None:
            self.canvas.set_data([], {})
        else:
            self.canvas.set_data(out.gantt, colors, f"{out.algorithm}", reveal)

    def set_reveal(self, t: Optional[float]):
        self.canvas.set_reveal(t)

    def set_theme(self, theme: str):
        self.canvas.set_theme(theme)


class GanttPopup(QDialog):
    def __init__(self, out: ScheduleOutput, colors: Dict[str, str], theme: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Gantt Chart - {out.algorithm}")
        self.resize(1100, 300)
        lay = QVBoxLayout(self)
        self.chart = GanttChartWidget(theme)
        self.chart.show_output(out, colors)
        lay.addWidget(self.chart)
