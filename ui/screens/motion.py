# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, List
from PySide6.QtWidgets import QLabel, QHBoxLayout, QPushButton, QGridLayout
from PySide6.QtCore import QTimer

from ui.screens.base import AnalysisScreen
from data_access import get_motion_frames
from ui.gfx.heatmap import gerar_matriz_heatmap, calcular_cop_interpolado
from ui.constants import CANVAS_W, CANVAS_H
import time
class TelaMovimento(AnalysisScreen):
    def __init__(self, stack):
        super().__init__(stack)

        # Player 30fps
        self.controls_layout.addWidget(self._sep())
        self.controls_layout.addWidget(QLabel("<b>3. Controle de Reprodução</b>"))
        player = QGridLayout()
        self.btn_play = QPushButton("▶ Play"); self.btn_pause = QPushButton("⏸ Pause"); self.btn_stop = QPushButton("⏹ Stop")
        player.addWidget(self.btn_play,0,0); player.addWidget(self.btn_pause,0,1); player.addWidget(self.btn_stop,0,2)
        player.addWidget(QLabel("Velocidade: 30 fps (fixo)"),1,0,1,3)
        self.controls_layout.addLayout(player)

        nav = QHBoxLayout()
        self.btn_prev = QPushButton("⬅ Frame Ant."); self.btn_next = QPushButton("Próx. Frame ➡")
        self.controls_layout.addWidget(QLabel("Navegação Manual:")); self.controls_layout.addLayout(nav)
        nav.addWidget(self.btn_prev); nav.addWidget(self.btn_next)

        self.timer = QTimer(); self.timer.timeout.connect(self.next_frame)

        self.uid=None; self.cpf=None; self.session_key=None
        self.framesL: List[Dict]=[]; self.framesR: List[Dict]=[]
        self.idx=0

        self.btn_play.clicked.connect(self.play); self.btn_pause.clicked.connect(self.pause)
        self.btn_stop.clicked.connect(self.stop); self.btn_prev.clicked.connect(self.prev_frame)
        self.btn_next.clicked.connect(self.next_frame)

    def load_session(self, uid: str, cpf: str, session_key: str):
        self.uid, self.cpf, self.session_key = uid, cpf, session_key
        data = get_motion_frames(uid, cpf, session_key)
        self.framesL = data.get("left", []); self.framesR = data.get("right", [])
        self.idx=0
        self.info_box.setText(f"<b>CPF:</b> {cpf} | <b>Sessão:</b> {session_key}")
        self.show_current()

    def show_current(self):
        n=max(len(self.framesL), len(self.framesR))
        if n==0: return
        L = self.framesL[self.idx] if self.idx < len(self.framesL) else {}
        R = self.framesR[self.idx] if self.idx < len(self.framesR) else {}
        if L: self._render_side(L,"left")
        if R: self._render_side(R,"right")

        nomeL,kpaL = self.peak_kpa(L) if L else ("--",0.0)
        nomeR,kpaR = self.peak_kpa(R) if R else ("--",0.0)

        cop=[]
        if L:
            mL=gerar_matriz_heatmap(L,"left", self.contorno_esquerdo.width() or CANVAS_W, self.contorno_esquerdo.height() or CANVAS_H)
            cL=calcular_cop_interpolado(mL)
            if cL: cop.append(f"<b>E:</b> ({cL[0]/(self.contorno_esquerdo.width() or 1):.2f}, {cL[1]/(self.contorno_esquerdo.height() or 1):.2f})")
        if R:
            mR=gerar_matriz_heatmap(R,"right", self.contorno_direito.width() or CANVAS_W, self.contorno_direito.height() or CANVAS_H)
            cR=calcular_cop_interpolado(mR)
            if cR: cop.append(f"<b>D:</b> ({cR[0]/(self.contorno_direito.width() or 1):.2f}, {cR[1]/(self.contorno_direito.height() or 1):.2f})")

        self.peak_box.setText(f"<b>Pico de Pressão:</b><br>E: {nomeL} ({kpaL:.1f} kPa) &nbsp;&nbsp; D: {nomeR} ({kpaR:.1f} kPa)")
        self.cop_box.setText("<b>Baricentro (CoP):</b><br>" + " ".join(cop))
        self._update_legends(kpaL, kpaR)

    def _render_side(self, vals: Dict[str,float], side: str):
        if side=="left":
            d=self.dists(vals,"left"); self.dist_ap_left.update_data(d["post"], d["ant"]); self.dist_ml_left.update_data(d["med"], d["lat"])
            self.draw_foot_visualization(self.foot_display_left, vals, "left", [None], [None], 0)
        else:
            d=self.dists(vals,"right"); self.dist_ap_right.update_data(d["post"], d["ant"]); self.dist_ml_right.update_data(d["med"], d["lat"])
            self.draw_foot_visualization(self.foot_display_right, vals, "right", [None], [None], 0)

    # player 30 fps
    def play(self): self.timer.start(33)
    def pause(self): self.timer.stop()
    def stop(self): self.timer.stop(); self.idx=0; self.show_current()
    def next_frame(self):
        n=max(len(self.framesL), len(self.framesR));
        if n>0: self.idx=(self.idx+1)%n; self.show_current()

    def prev_frame(self):
        n=max(len(self.framesL), len(self.framesR)); 
        if n>0: self.idx=(self.idx-1+n)%n; self.show_current()
