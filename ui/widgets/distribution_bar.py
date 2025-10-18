# -*- coding: utf-8 -*-
from __future__ import annotations
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QFont, QColor
from PySide6.QtCore import Qt, QRect

class SingleDistributionBar(QWidget):
    def __init__(self, title: str, label1: str, label2: str, color1: str, color2: str):
        super().__init__()
        self.setMinimumHeight(45)
        self.title = title
        self.label1, self.label2 = label1, label2
        self.color1, self.color2 = QColor(color1), QColor(color2)
        self.pct1, self.pct2 = 50.0, 50.0
        self.font_bold = QFont(); self.font_bold.setBold(True); self.font_bold.setPointSize(10)
        self.font_normal = QFont(); self.font_normal.setPointSize(9)

    def update_data(self, pct1: float, pct2: float) -> None:
        self.pct1, self.pct2 = float(pct1), float(pct2); self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.white); p.setFont(self.font_normal); p.drawText(5, 12, self.title)

        bar_y, bar_h = 20, 22
        w1 = (self.width() * self.pct1) / 100.0
        w2 = self.width() - w1

        p.setPen(Qt.NoPen); p.setBrush(self.color1); p.drawRect(0, bar_y, int(w1), bar_h)
        p.setBrush(self.color2); p.drawRect(int(w1), bar_y, int(w2), bar_h)

        p.setPen(Qt.black); p.setFont(self.font_bold)
        if w1 > 40: p.drawText(QRect(0, bar_y, int(w1), bar_h), Qt.AlignCenter, f"{self.pct1:.0f}%")
        if w2 > 40: p.drawText(QRect(int(w1), bar_y, int(w2), bar_h), Qt.AlignCenter, f"{self.pct2:.0f}%")

        p.setPen(Qt.white); p.setFont(self.font_normal)
        p.drawText(QRect(0, bar_y, 20, bar_h), Qt.AlignCenter, self.label1)
        p.drawText(QRect(self.width()-20, bar_y, 20, bar_h), Qt.AlignCenter, self.label2)
        p.end()
