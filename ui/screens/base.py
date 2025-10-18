# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, List, Optional, Tuple
import re
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QGridLayout, QFrame
from PySide6.QtGui import QPixmap, QImage, QPainter, QPen, QFont, QColor, QPolygonF, QTransform
from PySide6.QtCore import Qt, QPointF, QRect

import numpy as np

from ui.constants import (
    LOGO_IMG, FOOT_OUTLINE_IMG, CANVAS_W, CANVAS_H, KPA_PER_UNIT,
    SR_NAMES
)
from ui.widgets.distribution_bar import SingleDistributionBar
from ui.gfx.heatmap import (
    gerar_matriz_heatmap, calcular_cop_interpolado, encontrar_pico_interpolado,
    normalize_heatmap, colorize_normalized
)

class AnalysisScreen(QWidget):
    """Classe base: painel lateral, legendas de kPa e draw do pé."""
    def __init__(self, stack: QStackedWidget):
        super().__init__()
        self.stack = stack
        self.main_layout = QGridLayout(self)

        # contornos
        cont = QPixmap(FOOT_OUTLINE_IMG)
        if cont.isNull():
            cont = QPixmap(CANVAS_W, CANVAS_H); cont.fill(Qt.transparent)
        self.contorno_direito = cont
        self.contorno_esquerdo = cont.transformed(QTransform().scale(-1, 1))

        # painel lateral
        control_panel = QWidget()
        control_panel.setStyleSheet("background-color: rgba(0,0,0,0.2); border-radius: 8px;")
        self.controls_layout = QVBoxLayout(control_panel)
        self.controls_layout.setContentsMargins(15, 15, 15, 15)
        self.main_layout.addWidget(control_panel, 0, 0, 2, 1)

        # displays
        self.foot_display_left = self._create_foot_display()
        self.foot_display_right = self._create_foot_display()
        self.main_layout.addWidget(self.foot_display_left, 0, 1)
        self.main_layout.addWidget(self.foot_display_right, 0, 2)

        # legendas kPa (grandes e responsivas)
        self.legend_panel = QHBoxLayout()
        self.legend_left = QLabel(); self.legend_right = QLabel()
        self.legend_left.setMinimumHeight(90); self.legend_right.setMinimumHeight(90)
        self.legend_panel.addWidget(self.legend_left, 1); self.legend_panel.addWidget(self.legend_right, 1)
        self.main_layout.addLayout(self.legend_panel, 1, 1, 1, 2)

        self.main_layout.setColumnStretch(0, 1); self.main_layout.setColumnStretch(1, 2); self.main_layout.setColumnStretch(2, 2)
        self.main_layout.setRowStretch(0, 10); self.main_layout.setRowStretch(1, 1)

        self._setup_controls()

    # ----- UI helpers
    def _create_foot_display(self) -> QLabel:
        lbl = QLabel("Aguardando dados..."); lbl.setAlignment(Qt.AlignCenter)
        lbl.setMinimumSize(400, 600)
        lbl.setStyleSheet("background-color: rgba(10,10,10,0.4); border-radius: 8px;")
        return lbl

    def _setup_controls(self) -> None:
        btn_voltar = QPushButton("⬅ Voltar"); btn_voltar.clicked.connect(lambda: self.stack.setCurrentIndex(4))
        self.controls_layout.addWidget(btn_voltar); self.controls_layout.addWidget(self._sep())
        self.controls_layout.addWidget(QLabel("<b>Informações da Análise</b>"))
        self.info_box = self._info("Aguardando sessão...")
        self.peak_box = self._info("Pico de Pressão: --")
        self.cop_box = self._info("Baricentro (CoP): --")
        self.controls_layout.addWidget(self.info_box)
        self.controls_layout.addWidget(self.peak_box)
        self.controls_layout.addWidget(self.cop_box)
        self.controls_layout.addWidget(self._sep())
        self.controls_layout.addWidget(QLabel("<b>Distribuição de Força (Pé Esquerdo)</b>"))
        self.dist_ap_left = SingleDistributionBar("Antero-Posterior", "P", "A", "#3498db", "#2ecc71")
        self.dist_ml_left = SingleDistributionBar("Médio-Lateral", "M", "L", "#f1c40f", "#e74c3c")
        self.controls_layout.addWidget(self.dist_ap_left); self.controls_layout.addWidget(self.dist_ml_left)
        self.controls_layout.addWidget(self._sep())
        self.controls_layout.addWidget(QLabel("<b>Distribuição de Força (Pé Direito)</b>"))
        self.dist_ap_right = SingleDistributionBar("Antero-Posterior", "P", "A", "#3498db", "#2ecc71")
        self.dist_ml_right = SingleDistributionBar("Médio-Lateral", "M", "L", "#f1c40f", "#e74c3c")
        self.controls_layout.addWidget(self.dist_ap_right); self.controls_layout.addWidget(self.dist_ml_right)
        self.controls_layout.addStretch()

    def _info(self, text: str) -> QLabel:
        l = QLabel(text); l.setWordWrap(True)
        l.setStyleSheet("background: #2c3e50; border-radius: 4px; padding: 6px;")
        return l

    def _sep(self) -> QFrame:
        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Sunken); return line

    # ----- Legendas kPa
    def _create_legend_pixmap(self, max_kpa: float, label: QLabel) -> QPixmap:
        width = max(260, label.width() or 260)
        height = max(90, label.height() or 90)
        pad_l, pad_r, pad_t, pad_b = 20, 20, 12, 30
        grad_h = 28; grad_w = max(60, width - (pad_l + pad_r))

        pm = QPixmap(width, height); pm.fill(Qt.transparent)
        p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)

        import colorsys
        for x in range(grad_w):
            frac = x / float(max(1, grad_w - 1))
            hue = (1 - frac) * 240.0
            r, g, b = colorsys.hsv_to_rgb(hue / 360.0, 1.0, 1.0)
            p.setPen(QColor(int(r * 255), int(g * 255), int(b * 255)))
            p.drawLine(pad_l + x, pad_t, pad_l + x, pad_t + grad_h)

        p.setPen(Qt.white); font = QFont(); font.setPointSize(12); p.setFont(font)

        def fmt(v: float) -> str:
            if max_kpa >= 100: return f"{v:.0f}"
            if max_kpa >= 10:  return f"{v:.1f}"
            if max_kpa >= 1:   return f"{v:.2f}"
            return f"{v:.3f}"

        ticks = 5
        for i in range(ticks + 1):
            frac = i / ticks; x = int(pad_l + frac * grad_w)
            p.drawLine(x, pad_t + grad_h, x, pad_t + grad_h + 6)
            rect = QRect(x - 30, pad_t + grad_h + 8, 60, 24)
            p.drawText(rect, Qt.AlignHCenter | Qt.AlignVCenter, fmt(frac * max_kpa))

        p.drawText(width - pad_r - 40, height - 8, "kPa")
        p.end()
        return pm

    def _update_legends(self, left_kpa: float, right_kpa: float):
        self.legend_left.setPixmap(self._create_legend_pixmap(max(left_kpa, 0.1), self.legend_left))
        self.legend_right.setPixmap(self._create_legend_pixmap(max(right_kpa, 0.1), self.legend_right))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        try:
            vals = [float(x) for x in re.findall(r"\(([\d\.]+)\s*kPa\)", self.peak_box.text())]
            l = vals[0] if len(vals) > 0 else 0.1
            r = vals[1] if len(vals) > 1 else 0.1
            self._update_legends(l, r)
        except Exception:
            self._update_legends(1.0,
                                 1.0)

    # ----- Draw do pé + marcadores (usado pelas telas)
    def draw_foot_visualization(self, label: QLabel, sr_vals: Dict, lado_pe: str, traj_cop: List, traj_pico: List, idx: int) -> None:
        contorno = self.contorno_direito if lado_pe == "right" else self.contorno_esquerdo
        largura, altura = (contorno.width() or CANVAS_W, contorno.height() or CANVAS_H)

        m = gerar_matriz_heatmap(sr_vals, lado_pe, largura, altura)
        if len(traj_cop) <= idx: traj_cop.extend([None] * (idx - len(traj_cop) + 1))
        if len(traj_pico) <= idx: traj_pico.extend([None] * (idx - len(traj_pico) + 1))
        if traj_cop[idx] is None or traj_pico[idx] is None:
            traj_cop[idx] = calcular_cop_interpolado(m)
            traj_pico[idx] = encontrar_pico_interpolado(m)

        n = normalize_heatmap(m)
        rgba = colorize_normalized(n)
        img = QImage(rgba.data, largura, altura, int(rgba.strides[0]), QImage.Format_RGBA8888).copy()

        canvas = QPixmap(contorno.size()); canvas.fill(Qt.transparent)
        p = QPainter(canvas)
        p.drawPixmap(0, 0, contorno)
        p.setCompositionMode(QPainter.CompositionMode_SourceIn); p.drawImage(0, 0, img)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver); p.setRenderHint(QPainter.Antialiasing)

        cop = traj_cop[idx] if idx < len(traj_cop) else None
        if cop and cop[0] is not None:
            p.setBrush(QColor(255, 255, 255, 180)); p.setPen(QPen(QColor(0,0,0,220),1))
            p.drawEllipse(QPointF(cop[0], cop[1]), 10, 10)

        pico = traj_pico[idx] if idx < len(traj_pico) else None
        if pico and pico[0] is not None:
            pen = QPen(QColor(0,0,0), 2, Qt.SolidLine, Qt.RoundCap)
            p.setPen(pen); t = 10; c = QPointF(pico[0], pico[1])
            p.drawLine(c + QPointF(-t,-t), c + QPointF(t, t))
            p.drawLine(c + QPointF(-t, t), c + QPointF(t,-t))

        p.end()
        label.setPixmap(canvas.scaled(label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    # util p/ pico e kPa
    @staticmethod
    def peak_kpa(sr_vals: Dict[str,float]) -> tuple[str,float]:
        max_key, max_val = None, -1.0
        for i in range(1,10):
            k=f"SR{i}"
            try: v=float(sr_vals.get(k,0.0) or 0.0)
            except: v=0.0
            if v>max_val: max_val=v; max_key=k
        nome = SR_NAMES.get(max_key or "", max_key or "--")
        return nome or "--", max(0.0, max_val*KPA_PER_UNIT)

    @staticmethod
    def dists(vals: Dict[str,float], foot_side: str):
        ant=["SR1","SR2","SR3","SR4","SR5"]; pos=["SR6","SR7","SR8","SR9"]
        med_r=["SR1","SR4","SR5","SR9"]; lat_r=["SR2","SR3","SR6","SR7","SR8"]
        med_l=["SR2","SR3","SR6","SR7","SR8"]; lat_l=["SR1","SR4","SR5","SR9"]
        med,lat=(med_r,lat_r) if foot_side=="right" else (med_l,lat_l)
        tot=sum(float(vals.get(f"SR{i}",0.0) or 0.0) for i in range(1,10)) or 1.0
        s=lambda r: sum(float(vals.get(k,0.0) or 0.0) for k in r)
        return {"ant":100*s(ant)/tot,"post":100*s(pos)/tot,"med":100*s(med)/tot,"lat":100*s(lat)/tot}
