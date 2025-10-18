# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, List
from ui.screens.base import AnalysisScreen
from data_access import get_static_reading
from ui.gfx.heatmap import gerar_matriz_heatmap, calcular_cop_interpolado
from ui.constants import CANVAS_W, CANVAS_H

class TelaEstatico(AnalysisScreen):
    def __init__(self, stack):
        super().__init__(stack)
        self.uid=None; self.cpf=None; self.session_key=None

    def load_session(self, uid: str, cpf: str, session_key: str):
        self.uid, self.cpf, self.session_key = uid, cpf, session_key
        data = get_static_reading(uid, cpf, session_key)
        left = data.get("left", {}); right = data.get("right", {})
        self.info_box.setText(f"<b>CPF:</b> {cpf} | <b>Sessão:</b> {session_key}")

        # render e barras
        self._render_side(left, "left")
        self._render_side(right, "right")

        # pico + CoP + legendas
        nomeL, kpaL = self.peak_kpa(left); nomeR, kpaR = self.peak_kpa(right)
        cop_txts=[]
        if left:
            mL = gerar_matriz_heatmap(left,"left", self.contorno_esquerdo.width() or CANVAS_W, self.contorno_esquerdo.height() or CANVAS_H)
            cL = calcular_cop_interpolado(mL)
            if cL: cop_txts.append(f"<b>E:</b> ({cL[0]/(self.contorno_esquerdo.width() or 1):.2f}, {cL[1]/(self.contorno_esquerdo.height() or 1):.2f})")
        if right:
            mR = gerar_matriz_heatmap(right,"right", self.contorno_direito.width() or CANVAS_W, self.contorno_direito.height() or CANVAS_H)
            cR = calcular_cop_interpolado(mR)
            if cR: cop_txts.append(f"<b>D:</b> ({cR[0]/(self.contorno_direito.width() or 1):.2f}, {cR[1]/(self.contorno_direito.height() or 1):.2f})")

        self.peak_box.setText(f"<b>Pico de Pressão:</b><br>E: {nomeL} ({kpaL:.1f} kPa) &nbsp;&nbsp; D: {nomeR} ({kpaR:.1f} kPa)")
        self.cop_box.setText("<b>Baricentro (CoP):</b><br>" + " ".join(cop_txts))
        self._update_legends(kpaL, kpaR)

    def _render_side(self, sr_vals: Dict[str,float], side: str):
        if side=="left":
            d=self.dists(sr_vals,"left")
            self.dist_ap_left.update_data(d["post"], d["ant"]); self.dist_ml_left.update_data(d["med"], d["lat"])
            self.draw_foot_visualization(self.foot_display_left, sr_vals, "left", [None], [None], 0)
        else:
            d=self.dists(sr_vals,"right")
            self.dist_ap_right.update_data(d["post"], d["ant"]); self.dist_ml_right.update_data(d["med"], d["lat"])
            self.draw_foot_visualization(self.foot_display_right, sr_vals, "right", [None], [None], 0)
