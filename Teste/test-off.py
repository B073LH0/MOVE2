# -*- coding: utf-8 -*-
"""
teste-off.py — Versão offline corrigida e otimizada da Tela de Análise Dinâmica
- Lê dados de arquivo JSON (constante DADOS)
- Mantém nomes de funções originais e estrutura (comentada)
- Otimizações e correções:
    * heatmap gerado em resolução reduzida (SCALE_FACTOR)
    * aplicação de alpha via QImage.setAlphaChannel() (robusto e não-intrusivo)
    * borda do contorno calculada por diferença morfológica (não cobre o heatmap)
    * profiling por frame (PROFILE=True)

NOTA: Versão ajustada para usar **máscara fixa** pré-gerada (overlay RGBA com buraco transparente).
      As mudanças são mínimas e localizadas; estrutura e nomes foram mantidos.
"""
from __future__ import annotations
import sys, os, json, time, math
from typing import Dict, List, Any, Tuple, Optional

# =========== CONFIGURAÇÃO ===========
DADOS = "bioapp-496ae-default-rtdb-2025-10-15_09-09-48-776-export.json"
FOOT_OUTLINE_IMG = "foot_outline2.png"
PROFILE = True
SCALE_FACTOR = 1
GRID_MAX = 100
# =====================================

try:
    from PySide6.QtWidgets import (
        QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
        QGridLayout, QFrame, QMessageBox, QComboBox
    )
    from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QFont, QTransform
    from PySide6.QtCore import Qt, QTimer, QPointF, QRect
except Exception:
    raise RuntimeError("Instale dependências: pip install PySide6")

import numpy as np
try:
    from scipy.signal import fftconvolve
    _HAS_FFTCONV = True
except Exception:
    _HAS_FFTCONV = False
try:
    from scipy.ndimage import gaussian_filter
    _HAS_GAUSSIAN = True
except Exception:
    _HAS_GAUSSIAN = False

# ############## 'constants.py' ##################
CANVAS_W, CANVAS_H = 340, 450
BORRADO = 2
GAMMA = 1.0
KPA_PER_UNIT = 67.6 / 1000.0

SENSOR_POS_RIGHT = {
    "SR1": (0.28, 0.12), "SR2": (0.55, 0.15), "SR3": (0.62, 0.45),
    "SR4": (0.49, 0.30), "SR5": (0.30, 0.40), "SR6": (0.53, 0.59),
    "SR7": (0.51, 0.72), "SR8": (0.49, 0.85), "SR9": (0.34, 0.85),
}
SENSOR_POS_LEFT = {k: (1.0 - v[0], v[1]) for k, v in SENSOR_POS_RIGHT.items()}

SR_NAMES = {
    "SR1": "Hálux", "SR2": "Metatarso 1", "SR3": "Metatarso 5",
    "SR4": "Arco Medial", "SR5": "Arco Lateral", "SR6": "Mediopé Lat.",
    "SR7": "Calc. Med.", "SR8": "Calc. Cent.", "SR9": "Calc. Lat.",
}
SR_KEYS = {f"SR{i}" for i in range(1, 10)}
# ############## FIM ############################

# ############## 'data_access' (adaptado) ##################
def _to_float(x: Any) -> float:
    """(origem: data_access._to_float)"""
    try:
        if isinstance(x, (int, float)): return float(x)
        if isinstance(x, str): return float(x.replace(",", ".").strip())
    except Exception:
        pass
    return float("nan")

def _last_non_null(node: Any) -> float:
    """(origem: data_access._last_non_null)"""
    v = _to_float(node)
    if v == v: return v
    if isinstance(node, list):
        for it in reversed(node):
            val = _last_non_null(it)
            if val == val: return val
        return float("nan")
    if isinstance(node, dict):
        if "value" in node:
            val = _last_non_null(node["value"])
            if val == val: return val
        def key_sort(k):
            try: return int(k)
            except: return str(k)
        last = float("nan")
        for k in sorted(node.keys(), key=key_sort):
            val = _last_non_null(node[k])
            if val == val: last = val
        return last
    return float("nan")

def _series(node: Any) -> List[float]:
    """(origem: data_access._series)"""
    if isinstance(node, list):
        out=[]
        for it in node:
            v = _to_float(it) if not isinstance(it, (list, dict)) else _last_non_null(it)
            if v == v: out.append(v)
        return out
    if isinstance(node, dict):
        if "value" in node and isinstance(node["value"], (list, dict)):
            return _series(node["value"])
        def key_sort(k):
            try: return int(k)
            except: return str(k)
        out=[]
        for _, it in sorted(node.items(), key=lambda kv: key_sort(kv[0])):
            v = _to_float(it) if not isinstance(it, (list, dict)) else _last_non_null(it)
            if v == v: out.append(v)
        return out
    v = _to_float(node)
    return [v] if v == v else []

def get_motion_frames(uid: str=None, cpf: str=None, session_key: str=None):
    """
    (origem/adaptado: data_access.get_motion_frames)
    Lê DADOS local (arquivo JSON) e retorna {'left': [frames], 'right': [frames']}
    """
    if not os.path.exists(DADOS):
        raise FileNotFoundError(f"Arquivo de dados não encontrado: {DADOS}")
    with open(DADOS, "r", encoding="utf-8") as f:
        root = json.load(f)

    def extract_series_from(node):
        series = {}
        lengths = []
        if isinstance(node, list) and node and isinstance(node[0], dict):
            for i in range(1,10):
                key=f"SR{i}"
                arr = [_to_float(fr.get(key, float("nan"))) for fr in node]
                series[key] = [v for v in arr if v == v]
                lengths.append(len(series[key]))
            return series, (min(lengths) if lengths else 0)
        payload = None
        if isinstance(node, dict):
            payload = node.get("payload", node)
        if not isinstance(payload, dict):
            for i in range(1,10): series[f"SR{i}"]=[]
            return series, 0
        for i in range(1,10):
            key = f"SR{i}"
            s = _series(payload.get(key, []))
            series[key] = s
            lengths.append(len(s))
        min_len = min(lengths) if lengths else 0
        return series, min_len

    def build_frames_from(node):
        series, min_len = extract_series_from(node)
        frames=[]
        for k in range(min_len):
            frame = {sr: float(series[sr][k]) for sr in series.keys()}
            frames.append(frame)
        return frames

    left_node = None; right_node = None
    if isinstance(root, dict):
        if "left" in root and "right" in root:
            left_node = root["left"]; right_node = root["right"]
        else:
            keys = set(root.keys())
            if any(k in keys for k in SR_KEYS):
                left_node = root; right_node = {}
            elif "payload" in root and isinstance(root["payload"], dict):
                left_node = root["payload"]; right_node = {}
            else:
                def find_lr(d):
                    if not isinstance(d, dict): return (None,None)
                    if "left" in d and "right" in d: return (d["left"], d["right"])
                    for v in d.values():
                        if isinstance(v, dict):
                            l,r = find_lr(v)
                            if l is not None or r is not None: return (l,r)
                    return (None,None)
                left_node, right_node = find_lr(root)
                left_node = left_node or {}
                right_node = right_node or {}
    else:
        left_node, right_node = {}, {}

    framesL = build_frames_from(left_node)
    framesR = build_frames_from(right_node)
    return {"left": framesL, "right": framesR}
# ############## FIM ############################

# ############## 'ui/gfx/heatmap.py' ##################
_kernel_cache = {}

def precompute_gaussian_kernel(gh, gw, sigma):
    """(origem: ui/gfx/heatmap.precompute_gaussian_kernel)"""
    key = (gh, gw, round(float(sigma), 4))
    if key in _kernel_cache:
        return _kernel_cache[key]
    y = np.arange(gh) - (gh-1)/2.0
    x = np.arange(gw) - (gw-1)/2.0
    xx, yy = np.meshgrid(x, y)
    k = np.exp(-(xx**2 + yy**2) / (2.0 * sigma**2))
    k /= (k.sum() + 1e-12)
    _kernel_cache[key] = k.astype(np.float32)
    return _kernel_cache[key]

def convolve_with_kernel(canvas, kernel):
    """(origem/adaptado: ui/gfx/heatmap.convolve_with_kernel)"""
    if _HAS_FFTCONV:
        try:
            return fftconvolve(canvas, kernel, mode="same")
        except Exception:
            pass
    if _HAS_GAUSSIAN:
        return gaussian_filter(canvas, sigma=1.0, mode="constant").astype(np.float32)
    try:
        from scipy.signal import convolve2d
        return convolve2d(canvas, kernel, mode="same").astype(np.float32)
    except Exception:
        return canvas

def gerar_matriz_heatmap(sr_vals: Dict[str, float], lado_pe: str, largura: int, altura: int, grid_max: int = GRID_MAX) -> np.ndarray:
    """(origem: ui/gfx/heatmap.gerar_matriz_heatmap)"""
    if largura <= 0 or altura <= 0:
        return np.zeros((max(1, altura), max(1, largura)), dtype=np.float32)
    pos = SENSOR_POS_RIGHT if lado_pe == "right" else SENSOR_POS_LEFT
    aspect = altura / float(largura)
    if largura >= altura:
        gw = min(grid_max, largura); gh = max(1, int(round(gw * aspect)))
    else:
        gh = min(grid_max, altura); gw = max(1, int(round(gh / aspect)))
    canvas = np.zeros((gh, gw), dtype=np.float32)
    for i in range(1, 10):
        key = f"SR{i}"
        try:
            v = float(sr_vals.get(key, 0.0) or 0.0)
        except Exception:
            v = 0.0
        fx, fy = pos.get(key, (0.5, 0.5))
        x = max(0, min(gw - 1, int(round(fx * (gw - 1)))) )
        y = max(0, min(gh - 1, int(round(fy * (gh - 1)))) )
        canvas[y, x] += v
    sigma_rel = BORRADO * (max(1.0, min(max(gw, gh) * 0.06, 30.0)))
    kernel = precompute_gaussian_kernel(canvas.shape[0], canvas.shape[1], sigma_rel)
    sm = convolve_with_kernel(canvas, kernel).astype(np.float32)
    rep_y = int(np.ceil(altura / float(sm.shape[0]))); rep_x = int(np.ceil(largura / float(sm.shape[1])))
    temp = np.repeat(np.repeat(sm, rep_y, axis=0), rep_x, axis=1)
    return temp[:altura, :largura].astype(np.float32)

def encontrar_pico_interpolado(m: np.ndarray) -> Optional[Tuple[float, float]]:
    if m.size == 0 or m.max() == 0: return None
    yx = np.unravel_index(int(m.argmax()), m.shape)
    return (float(yx[1]), float(yx[0]))

def calcular_cop_interpolado(m: np.ndarray) -> Optional[Tuple[float, float]]:
    if m.size == 0: return None
    total = float(m.sum())
    if total == 0: return None
    h, w = m.shape
    grid_x, grid_y = np.meshgrid(np.arange(w), np.arange(h))
    cx = float(np.sum(m * grid_x) / total); cy = float(np.sum(m * grid_y) / total)
    return (cx, cy)

def normalize_heatmap(m: np.ndarray) -> np.ndarray:
    if m.size == 0 or m.max() == 0: return m
    mn, mx = float(m.min()), float(m.max())
    n = (m - mn) / (mx - mn + 1e-12)
    return n ** GAMMA

def colorize_normalized(n: np.ndarray) -> np.ndarray:
    """(origem: ui/gfx/heatmap.colorize_normalized)"""
    hue = (1.0 - n) * 240.0 / 360.0
    i = (hue * 6.0).astype(int) % 6
    f = (hue * 6.0) - i
    v = np.ones_like(hue); s = np.ones_like(hue)
    p = v * (1 - s); q = v * (1 - s * f); t = v * (1 - s * (1 - f))
    r = (np.choose(i, [v, q, p, p, t, v]) * 255).astype(np.uint8)
    g = (np.choose(i, [t, v, v, q, p, p]) * 255).astype(np.uint8)
    b = (np.choose(i, [p, p, t, v, v, q]) * 255).astype(np.uint8)
    a = np.full_like(r, 255, dtype=np.uint8)
    return np.dstack([r, g, b, a])
# ############## FIM ############################

# ############## UI helpers / widgets ##################
class SingleDistributionBar(QWidget):
    """(ADAPTADO) barra de distribuição (mantém API do projeto)."""
    def __init__(self, title: str, left_label: str, right_label: str, left_color: str, right_color: str):
        super().__init__()
        self.title = title; self.left_label = left_label; self.right_label = right_label
        self.left_color = QColor(left_color); self.right_color = QColor(right_color)
        self.left_pct = 50.0; self.right_pct = 50.0
        self.setMinimumHeight(28)

    def update_data(self, left_value_percent: float, right_value_percent: float):
        self.left_pct = max(0.0, min(100.0, left_value_percent))
        self.right_pct = max(0.0, min(100.0, right_value_percent))
        self.update()

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(44, 62, 80))
        p.drawRoundedRect(rect, 4, 4)
        margin = 6
        bar_rect = QRect(rect.x()+margin, rect.y()+margin, rect.width()-2*margin, rect.height()-2*margin)
        left_w = int(bar_rect.width() * (self.left_pct/100.0))
        left_rect = QRect(bar_rect.x(), bar_rect.y(), left_w, bar_rect.height())
        right_rect = QRect(bar_rect.x()+left_w, bar_rect.y(), bar_rect.width()-left_w, bar_rect.height())
        p.setBrush(self.left_color); p.drawRect(left_rect)
        p.setBrush(self.right_color); p.drawRect(right_rect)
        p.setPen(Qt.white); font = QFont(); font.setPointSize(9); p.setFont(font)
        p.drawText(left_rect, Qt.AlignCenter, f"{int(round(self.left_pct))}%")
        p.drawText(right_rect, Qt.AlignCenter, f"{int(round(self.right_pct))}%")
        small = QFont(); small.setPointSize(8); p.setFont(small)
        p.drawText(rect.x()+4, rect.y()+rect.height()-4, self.left_label)
        w_right = p.fontMetrics().horizontalAdvance(self.right_label)
        p.drawText(rect.right()-w_right-4, rect.y()+rect.height()-4, self.right_label)
        p.end()

def peak_kpa(sr_vals: Dict[str,float]) -> Tuple[str, float]:
    """(origem: ui/screens/base.peak_kpa)"""
    max_key, max_val = None, -1.0
    for i in range(1,10):
        k = f"SR{i}"
        try: v=float(sr_vals.get(k,0.0) or 0.0)
        except: v=0.0
        if v>max_val: max_val=v; max_key=k
    nome = SR_NAMES.get(max_key or "", max_key or "--")
    return nome or "--", max(0.0, max_val*KPA_PER_UNIT)

def dists(vals: Dict[str,float], foot_side: str):
    """(origem: ui/screens/base.dists)"""
    ant=["SR1","SR2","SR3","SR4","SR5"]; pos=["SR6","SR7","SR8","SR9"]
    med_r=["SR1","SR4","SR5","SR9"]; lat_r=["SR2","SR3","SR6","SR7","SR8"]
    med_l=["SR2","SR3","SR6","SR7","SR8"]; lat_l=["SR1","SR4","SR5","SR9"]
    med,lat=(med_r,lat_r) if foot_side=="right" else (med_l,lat_l)
    tot=sum(float(vals.get(f"SR{i}",0.0) or 0.0) for i in range(1,10)) or 1.0
    s=lambda r: sum(float(vals.get(k,0.0) or 0.0) for k in r)
    return {"ant":100*s(ant)/tot,"post":100*s(pos)/tot,"med":100*s(med)/tot,"lat":100*s(lat)/tot}

def _create_legend_pixmap(max_kpa: float, width: int, height: int) -> QPixmap:
    """(ADAPTADO) cria legenda com gradiente e ticks (mantém visual)"""
    width = max(180, width); height = max(48, height)
    pm = QPixmap(width, height); pm.fill(Qt.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
    pad_l, pad_r, pad_t = 20, 20, 8
    grad_h = 28; grad_w = max(80, width - pad_l - pad_r)
    import colorsys
    for x in range(grad_w):
        frac = x / float(max(1, grad_w - 1))
        hue = (1 - frac) * 240.0
        r, g, b = colorsys.hsv_to_rgb(hue / 360.0, 1.0, 1.0)
        p.setPen(QColor(int(r*255), int(g*255), int(b*255)))
        p.drawLine(pad_l + x, pad_t, pad_l + x, pad_t + grad_h)
    p.setPen(Qt.white); font = QFont(); font.setPointSize(10); p.setFont(font)
    def fmt(v: float) -> str:
        if max_kpa >= 100: return f"{v:.0f}"
        if max_kpa >= 10: return f"{v:.1f}"
        if max_kpa >= 1: return f"{v:.2f}"
        return f"{v:.3f}"
    ticks = 5
    for i in range(ticks+1):
        frac = i / ticks; x = int(pad_l + frac * grad_w)
        p.drawLine(x, pad_t + grad_h, x, pad_t + grad_h + 6)
        rect = QRect(x - 30, pad_t + grad_h + 8, 60, 18)
        p.drawText(rect, Qt.AlignCenter, fmt(frac * max_kpa))
    p.drawText(width - pad_r - 30, height - 6, "kPa")
    p.end()
    return pm
# ############## FIM ############################

# ############## AnalysisScreen (pré alpha + máscara numpy) ##################
class AnalysisScreen(QWidget):
    """
    (ADAPTADO) base de tela que carrega contorno do pé e pré-computa:
    - alpha_qimage (para setAlphaChannel)
    - mask_alpha numpy (para calcular borda sem cobrir heatmap)
    """
    def __init__(self):
        super().__init__()
        self.main_layout = QGridLayout(self)
        self.setLayout(self.main_layout)

        # carregar contorno (QPixmap). Se não existir, cria transparente.
        cont = QPixmap(FOOT_OUTLINE_IMG) if os.path.exists(FOOT_OUTLINE_IMG) else None
        if cont is None or cont.isNull():
            cont = QPixmap(CANVAS_W, CANVAS_H); cont.fill(Qt.transparent)
        self.contorno_direito = cont
        self.contorno_esquerdo = cont.transformed(QTransform().scale(-1, 1))

        # PRE-CALCULA ALPHA QIMAGE (Format_Alpha8) para uso em setAlphaChannel
        try:
            self._alpha_right_qimage = self.contorno_direito.toImage().convertToFormat(QImage.Format_Alpha8)
            self._alpha_left_qimage = self.contorno_esquerdo.toImage().convertToFormat(QImage.Format_Alpha8)
        except Exception:
            # fallback: alpha total
            w = self.contorno_direito.width(); h = self.contorno_direito.height()
            alpha = QImage(w, h, QImage.Format_Alpha8); alpha.fill(255)
            self._alpha_right_qimage = alpha
            self._alpha_left_qimage = alpha

        # PRE-CALCULA mask_alpha numpy (0..1 float) para uso na geração de bordas
        def qimage_alpha_to_numpy(qimg: QImage) -> np.ndarray:
            """Converte QImage.Format_Alpha8 -> array HxW float32 [0..1]"""
            img = qimg.convertToFormat(QImage.Format_Alpha8)
            w = img.width(); h = img.height()
            ptr = img.constBits(); ptr.setsize(img.byteCount())
            arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, img.bytesPerLine()))
            arr = arr[:, :w]
            return (arr.astype(np.float32) / 255.0)

        try:
            self._mask_right_alpha = qimage_alpha_to_numpy(self._alpha_right_qimage)
            self._mask_left_alpha = qimage_alpha_to_numpy(self._alpha_left_qimage)
        except Exception:
            self._mask_right_alpha = np.ones((self.contorno_direito.height(), self.contorno_direito.width()), dtype=np.float32)
            self._mask_left_alpha = np.ones((self.contorno_esquerdo.height(), self.contorno_esquerdo.width()), dtype=np.float32)

        # painel lateral e displays (estrutura parecida com original)
        control_panel = QWidget()
        control_panel.setStyleSheet("background-color: rgba(20,30,40,0.9); border-radius: 6px;")
        self.controls_layout = QVBoxLayout(control_panel)
        self.controls_layout.setContentsMargins(12,12,12,12)
        self.main_layout.addWidget(control_panel, 0, 0, 2, 1)

        self.foot_display_left = QLabel("Aguardando dados..."); self.foot_display_left.setAlignment(Qt.AlignCenter)
        self.foot_display_left.setMinimumSize(480,640)
        self.foot_display_right = QLabel("Aguardando dados..."); self.foot_display_right.setAlignment(Qt.AlignCenter)
        self.foot_display_right.setMinimumSize(480,640)
        self.main_layout.addWidget(self.foot_display_left, 0, 1)
        self.main_layout.addWidget(self.foot_display_right, 0, 2)

        self.legend_left = QLabel(); self.legend_right = QLabel()
        self.main_layout.addWidget(self.legend_left, 1, 1)
        self.main_layout.addWidget(self.legend_right, 1, 2)

        self.main_layout.setColumnStretch(0, 1); self.main_layout.setColumnStretch(1, 3); self.main_layout.setColumnStretch(2, 3)
        self.main_layout.setRowStretch(0, 10); self.main_layout.setRowStretch(1, 1)

    def _compute_border_from_mask(self, mask: np.ndarray) -> np.ndarray:
        """
        Calcula máscara de borda (True nos pixels de contorno) por erosão simples 4-vizinhos.
        - mask: HxW float (0..1) ou bool
        - retorna boolean array (H x W) True onde borda
        """
        if mask.dtype != np.bool_:
            m = (mask > 0.5)
        else:
            m = mask
        if m.size == 0:
            return m
        # erosão 4-vizinhos (apenas vizinhos N S E W) - rápido em numpy
        er = m.copy()
        er[1:, :] &= m[:-1, :]
        er[:-1, :] &= m[1:, :]
        er[:, 1:] &= m[:, :-1]
        er[:, :-1] &= m[:, 1:]
        border = m & (~er)
        return border

    def draw_foot_visualization(self, label: QLabel, sr_vals: Dict, lado_pe: str, traj_cop: List, traj_pico: List,
                                idx: int) -> None:
        """
        VERSÃO CORRIGIDA E PERFORMÁTICA:
        - Gera heatmap reduzido, upsample.
        - Converte em QPixmap.
        - Aplica QImage.setAlphaChannel() com alpha pré-computado -> recorte robusto.
        - Desenha borda pré-computada (pixmap) por cima.
        - Desenha CoP / pico.
        """
        contorno = self.contorno_direito if lado_pe == "right" else self.contorno_esquerdo
        # mask_qbitmap left for backward compatibility (may be unused)
        mask_qbitmap = getattr(self, "_mask_right_qbitmap", None) if lado_pe == "right" else getattr(self, "_mask_left_qbitmap", None)
        border_pixmap = getattr(self, "_border_right_pixmap", QPixmap()) if lado_pe == "right" else getattr(self, "_border_left_pixmap", QPixmap())
        # --- FIX: obter máscara fixa pré-gerada (overlay RGBA com buraco transparente)
        fixed_mask_pixmap = getattr(self, "_fixed_mask_right_pixmap", QPixmap()) if lado_pe == "right" else getattr(self, "_fixed_mask_left_pixmap", QPixmap())

        cont_w, cont_h = contorno.width() or CANVAS_W, contorno.height() or CANVAS_H

        # resolução reduzida
        scale = max(0.1, float(SCALE_FACTOR))
        small_w = max(8, int(round(cont_w * scale)))
        small_h = max(8, int(round(cont_h * scale)))
        rel_grid_max = max(20, int(GRID_MAX * scale))

        # 1) gerar matriz reduzida
        t0 = time.perf_counter() if PROFILE else 0.0
        m_small = gerar_matriz_heatmap(sr_vals, lado_pe, small_w, small_h, grid_max=rel_grid_max)
        if PROFILE: t_m = time.perf_counter() - t0

        # 2) normaliza + coloriza
        t0 = time.perf_counter() if PROFILE else 0.0
        n_small = normalize_heatmap(m_small)
        rgba_small = colorize_normalized(n_small)
        if PROFILE: t_col = time.perf_counter() - t0

        # 3) upsample para contorno
        t0 = time.perf_counter() if PROFILE else 0.0
        rep_y = int(math.ceil(cont_h / float(rgba_small.shape[0])))
        rep_x = int(math.ceil(cont_w / float(rgba_small.shape[1])))
        rgba_big = np.repeat(np.repeat(rgba_small, rep_y, axis=0), rep_x, axis=1)[:cont_h, :cont_w].astype(np.uint8)
        if PROFILE: t_up = time.perf_counter() - t0

        # 4) criar QImage do heatmap (SEM alterar alpha por setAlphaChannel)
        t0 = time.perf_counter() if PROFILE else 0.0
        rgba_big = np.ascontiguousarray(rgba_big)
        h, w = rgba_big.shape[:2]

        # cria QImage RGBA do heatmap (não aplicamos setAlphaChannel por frame)
        qimg = QImage(rgba_big.data, w, h, int(rgba_big.strides[0]), QImage.Format_RGBA8888).copy()

        # --- FIX: vamos usar uma máscara fixa pré-gerada (pixmap RGBA) com fora opaco e dentro transparente
        # Em vez de qimg.setAlphaChannel(alpha_for_set) por frame, iremos desenhar o overlay pré-gerado.
        # cria pixmap do heatmap (não recortado)
        heatmap_pix = QPixmap.fromImage(qimg)
        if PROFILE: t_alpha = time.perf_counter() - t0  # renomeado: tempo de conversão p/ pixmap

        # 5) compor final: heatmap + máscara fixa + borda + CoP/pico
        t0 = time.perf_counter() if PROFILE else 0.0
        final_pix = QPixmap(cont_w, cont_h)
        final_pix.fill(Qt.transparent)
        p = QPainter(final_pix)
        p.setRenderHint(QPainter.Antialiasing)

        # desenha heatmap (origem: heatmap_pix)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        p.drawPixmap(0, 0, heatmap_pix)

        # aplica máscara fixa (precomputada) — cobre fora do pé e deixa "buraco" transparente
        if not fixed_mask_pixmap.isNull():
            mp = fixed_mask_pixmap.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            p.drawPixmap(0, 0, mp)

        # desenha borda pré-computada por cima (escalada)
        if not border_pixmap.isNull():
            bp = border_pixmap.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            p.drawPixmap(0, 0, bp)

        # --- FIX ADICIONAL: desenha explicitamente o contorno (foot_outline) escalado por cima,
        # para garantir que o usuário veja o traço/contorno. Ajuste a opacidade se for preciso.
        try:
            cont_scaled = contorno.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            p.setOpacity(0.95)  # ajuste: 1.0 é opaco; reduza se cobrir o heatmap demais
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            p.drawPixmap(0, 0, cont_scaled)
            p.setOpacity(1.0)
        except Exception:
            # se houver algum erro ao desenhar o contorno, ignoramos e continuamos
            pass

        # desenha CoP / pico por cima de tudo
        cop_small = calcular_cop_interpolado(m_small)
        if cop_small and cop_small[0] is not None:
            sx = cop_small[0] * (cont_w / float(m_small.shape[1])) if m_small.shape[1] else 0.0
            sy = cop_small[1] * (cont_h / float(m_small.shape[0])) if m_small.shape[0] else 0.0
            p.setBrush(QColor(255, 255, 255, 200));
            p.setPen(QPen(QColor(0, 0, 0, 220), 1))
            p.drawEllipse(QPointF(sx, sy), 10, 10)
        pico_small = encontrar_pico_interpolado(m_small)
        if pico_small and pico_small[0] is not None:
            sx = pico_small[0] * (cont_w / float(m_small.shape[1])) if m_small.shape[1] else 0.0
            sy = pico_small[1] * (cont_h / float(m_small.shape[0])) if m_small.shape[0] else 0.0
            pen = QPen(QColor(0, 0, 0), 3)
            p.setPen(pen)
            t = 10;
            c = QPointF(sx, sy)
            p.drawLine(c + QPointF(-t, -t), c + QPointF(t, t))
            p.drawLine(c + QPointF(-t, t), c + QPointF(t, -t))
        p.end()

        if PROFILE: t_draw = time.perf_counter() - t0

        # 6) set pixmap scaled to label
        label.setPixmap(final_pix.scaled(label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

        # retornar temporizações se profiling
        if PROFILE:
            return {"m": t_m, "col": t_col, "up": t_up, "alpha": t_alpha, "draw": t_draw}
        return None
# ############## FIM ############################

# ############## TelaMovimento (com profiling) ##################


class TelaMovimento(AnalysisScreen):
    def __init__(self):
        super().__init__()
        btn_voltar = QPushButton("⬅ Voltar ao Menu");
        btn_voltar.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.controls_layout.addWidget(btn_voltar);
        self.controls_layout.addWidget(self.create_separator())
        self.controls_layout.addWidget(QLabel("<b>1. Seleção de Paciente</b>"))
        self.combo_user = QComboBox();
        self.combo_date = QComboBox()
        self.controls_layout.addWidget(QLabel("Paciente:"));
        self.controls_layout.addWidget(self.combo_user)
        self.controls_layout.addWidget(QLabel("Data da Coleta:"));
        self.controls_layout.addWidget(self.combo_date)
        self.btn_open = QPushButton("Carregar Análise");
        self.controls_layout.addWidget(self.btn_open)
        self.controls_layout.addWidget(self.create_separator());
        self.controls_layout.addWidget(QLabel("<b>2. Informações da Análise</b>"))
        self.info_box = self.create_info_label("Aguardando dados...");
        self.peak_box = self.create_info_label("Pico de Pressão: --")
        self.cop_box = self.create_info_label("Baricentro (CoP): --")
        self.controls_layout.addWidget(self.info_box);
        self.controls_layout.addWidget(self.peak_box);
        self.controls_layout.addWidget(self.cop_box)
        self.controls_layout.addWidget(self.create_separator());
        self.controls_layout.addWidget(QLabel("<b>Distribuição de Força (Pé Esquerdo)</b>"))
        self.dist_ap_left = SingleDistributionBar("Antero-Posterior", "P", "A", "#3498db", "#2ecc71")
        self.dist_ml_left = SingleDistributionBar("Médio-Lateral", "M", "L", "#f1c40f", "#e74c3c")
        self.controls_layout.addWidget(self.dist_ap_left);
        self.controls_layout.addWidget(self.dist_ml_left)
        self.controls_layout.addWidget(QLabel("<b>Distribuição de Força (Pé Direito)</b>"))
        self.dist_ap_right = SingleDistributionBar("Antero-Posterior", "P", "A", "#3498db", "#2ecc71")
        self.dist_ml_right = SingleDistributionBar("Médio-Lateral", "M", "L", "#f1c40f", "#e74c3c")
        self.controls_layout.addWidget(self.dist_ap_right);
        self.controls_layout.addWidget(self.dist_ml_right)
        self.controls_layout.addStretch()

        self.controls_layout.addSpacing(10)
        self.controls_layout.addWidget(QLabel("<b>Controle de Reprodução</b>"))
        row = QHBoxLayout()
        self.btn_play = QPushButton("▶ Play"); self.btn_pause = QPushButton("⏸ Pause"); self.btn_stop = QPushButton("⏹ Stop")
        row.addWidget(self.btn_play); row.addWidget(self.btn_pause); row.addWidget(self.btn_stop)
        self.controls_layout.addLayout(row)
        self.btn_play.clicked.connect(self.play); self.btn_pause.clicked.connect(self.pause); self.btn_stop.clicked.connect(self.stop)

        # ---------------------------------------------------------------------
        # Pré-computa QBitmap de máscara 1-bit e pixmap de borda (feito UMA vez)
        # ---------------------------------------------------------------------
        def _alpha_numpy_to_qbitmap(alpha_arr: np.ndarray) -> 'QBitmap':
            """
            Converte array float (0..1) alpha -> QImage Mono -> QBitmap (1-bit)
            Usado como mask rápida via QPixmap.setMask(...)
            """
            h, w = alpha_arr.shape
            # converte para 0..255 uint8
            a8 = (np.clip(alpha_arr, 0.0, 1.0) * 255.0).astype(np.uint8)
            # cria QImage Format_Indexed8 (1 byte por pixel) e então converte para Mono
            q = QImage(a8.data, w, h, int(a8.strides[0]), QImage.Format_Grayscale8).copy()
            mono = q.convertToFormat(QImage.Format_Mono)  # threshold automático
            from PySide6.QtGui import QBitmap
            return QBitmap.fromImage(mono)

        def _border_pixmap_from_alpha(alpha_arr: np.ndarray, color=(32, 200, 120, 220)) -> QPixmap:
            """
            Gera um QPixmap RGBA contendo apenas a borda do contorno (uma vez).
            A borda é computada a partir de alpha_arr com operação simples de erosão.
            """
            h, w = alpha_arr.shape
            m = (alpha_arr > 0.5)
            if m.size == 0:
                img = QImage(w, h, QImage.Format_RGBA8888)
                img.fill(Qt.transparent)
                return QPixmap.fromImage(img)
            # erosão simples 4-vizinhos
            er = m.copy()
            er[1:, :] &= m[:-1, :]
            er[:-1, :] &= m[1:, :]
            er[:, 1:] &= m[:, :-1]
            er[:, :-1] &= m[:, 1:]
            border = m & (~er)
            # cria RGBA array
            border_rgba = np.zeros((h, w, 4), dtype=np.uint8)
            br, bg, bb, ba = color
            border_rgba[border, 0] = br
            border_rgba[border, 1] = bg
            border_rgba[border, 2] = bb
            border_rgba[border, 3] = ba
            border_rgba = np.ascontiguousarray(border_rgba)
            img = QImage(border_rgba.data, w, h, int(border_rgba.strides[0]), QImage.Format_RGBA8888).copy()
            return QPixmap.fromImage(img)

        # --- FIX: função que gera a máscara fixa (overlay) com borda externa opaca e interior transparente
        def _fixed_mask_pixmap_from_alpha(alpha_arr: np.ndarray, outside_color=(20, 30, 40, 230)) -> QPixmap:
            """
            Gera um QPixmap RGBA que tem:
             - fora do contorno: preenchido com outside_color (RGBA)
             - dentro do contorno: totalmente transparente (alpha=0) -> 'buraco' para ver heatmap
            Essa pixmap é precomputada UMA vez e reaplicada a cada frame com drawPixmap (muito barato).
            """
            h, w = alpha_arr.shape
            if h == 0 or w == 0:
                img = QImage(1, 1, QImage.Format_RGBA8888); img.fill(Qt.transparent)
                return QPixmap.fromImage(img)
            inside = (alpha_arr > 0.5)
            rgba = np.zeros((h, w, 4), dtype=np.uint8)
            or_, og, ob, oa = outside_color
            # fora do pé (= not inside) -> colorido/opaco
            mask_outside = ~inside
            rgba[mask_outside, 0] = or_
            rgba[mask_outside, 1] = og
            rgba[mask_outside, 2] = ob
            rgba[mask_outside, 3] = oa
            # dentro do pé -> alpha = 0 (transparent)
            rgba[inside, 3] = 0
            rgba = np.ascontiguousarray(rgba)
            img = QImage(rgba.data, w, h, int(rgba.strides[0]), QImage.Format_RGBA8888).copy()
            return QPixmap.fromImage(img)

        # cria QBitmaps (1-bit masks) e pixmaps de borda para direita/esquerda
        try:
            self._mask_right_qbitmap = _alpha_numpy_to_qbitmap(self._mask_right_alpha)
            self._mask_left_qbitmap = _alpha_numpy_to_qbitmap(self._mask_left_alpha)
            # bordas (pixmap RGBA) também pré-geradas; serão escaladas por frame (rápido)
            self._border_right_pixmap = _border_pixmap_from_alpha(self._mask_right_alpha)
            self._border_left_pixmap = _border_pixmap_from_alpha(self._mask_left_alpha)

            # --- FIX: pré-gerar a máscara fixa overlay (fora opaco, dentro transparente) UMA vez
            self._fixed_mask_right_pixmap = _fixed_mask_pixmap_from_alpha(self._mask_right_alpha, outside_color=(20,30,40,230))
            self._fixed_mask_left_pixmap  = _fixed_mask_pixmap_from_alpha(self._mask_left_alpha,  outside_color=(20,30,40,230))
        except Exception:
            # fallback: máscara total (não recorta) e borda vazia
            from PySide6.QtGui import QBitmap
            w = self.contorno_direito.width(); h = self.contorno_direito.height()
            self._mask_right_qbitmap = QBitmap(w, h); self._mask_right_qbitmap.fill(Qt.color0)
            self._mask_left_qbitmap  = QBitmap(w, h); self._mask_left_qbitmap.fill(Qt.color0)
            img = QImage(w, h, QImage.Format_RGBA8888); img.fill(Qt.transparent)
            self._border_right_pixmap = QPixmap.fromImage(img)
            self._border_left_pixmap = QPixmap.fromImage(img)
            # máscaras fixas vazias
            self._fixed_mask_right_pixmap = QPixmap.fromImage(img)
            self._fixed_mask_left_pixmap = QPixmap.fromImage(img)


        # carregar frames do JSON
        data = get_motion_frames(None, None, None)
        self.framesL = data.get("left", []); self.framesR = data.get("right", [])
        self.idx = 0

        # timer (30fps target)
        self.timer = QTimer(); self.timer.timeout.connect(self.next_frame_profiled if PROFILE else self.next_frame); self.timer.setInterval(33)
        self.fps_label = QLabel("FPS: --"); self.controls_layout.addWidget(self.fps_label)

        self._acc_stats = {"m":0.0,"col":0.0,"up":0.0,"alpha":0.0,"draw":0.0,"frames":0}
        self.show_current()


    def create_info_label(self, text):
        label = QLabel(text);
        label.setWordWrap(True);
        label.setStyleSheet("background: #2c3e50; border-radius: 4px; padding: 6px;")
        return label
    def create_separator(self):
        line = QFrame();
        line.setFrameShape(QFrame.HLine);
        line.setFrameShadow(QFrame.Sunken);
        return line

    def show_current(self):
        n = max(len(self.framesL), len(self.framesR))
        if n == 0: return
        L = self.framesL[self.idx] if self.idx < len(self.framesL) else {}
        R = self.framesR[self.idx] if self.idx < len(self.framesR) else {}
        if L: self._render_side(L, "left")
        if R: self._render_side(R, "right")

        nomeL, kpaL = peak_kpa(L) if L else ("--", 0.0)
        nomeR, kpaR = peak_kpa(R) if R else ("--", 0.0)
        cop_texts = []

        if L:
            mL = gerar_matriz_heatmap(L, "left", self.contorno_esquerdo.width() or CANVAS_W,
                                      self.contorno_esquerdo.height() or CANVAS_H)
            cL = calcular_cop_interpolado(mL)
            if cL:
                cop_texts.append(
                    f"E: ({cL[0] / (self.contorno_esquerdo.width() or 1):.2f}, {cL[1] / (self.contorno_esquerdo.height() or 1):.2f})")
        if R:
            mR = gerar_matriz_heatmap(R, "right", self.contorno_direito.width() or CANVAS_W,
                                      self.contorno_direito.height() or CANVAS_H)
            cR = calcular_cop_interpolado(mR)
            if cR:
                cop_texts.append(
                    f"D: ({cR[0] / (self.contorno_direito.width() or 1):.2f}, {cR[1] / (self.contorno_direito.height() or 1):.2f})")

        # Exibe o Pico de Pressão (E e D em linhas separadas)
        self.peak_box.setText(
            f"<b>Pico de Pressão:</b><br>"
            f"E: {nomeL} ({kpaL:.1f} kPa)<br>"
            f"D: {nomeR} ({kpaR:.1f} kPa)"
        )

        # Exibe o Baricentro (CoP) com E e D em linhas separadas
        # Em vez de ' '.join(cop_texts), usamos '<br>'.join(cop_texts)
        self.cop_box.setText(
            "<b>Baricentro (CoP):</b><br>" + "<br>".join(cop_texts)
        )

        maxL = 0.0; maxR = 0.0
        if L:
            mL = gerar_matriz_heatmap(L, "left", self.contorno_esquerdo.width() or CANVAS_W, self.contorno_esquerdo.height() or CANVAS_H)
            maxL = float(mL.max()) * KPA_PER_UNIT if mL.size else 0.0
        if R:
            mR = gerar_matriz_heatmap(R, "right", self.contorno_direito.width() or CANVAS_W, self.contorno_direito.height() or CANVAS_H)
            maxR = float(mR.max()) * KPA_PER_UNIT if mR.size else 0.0
        self.legend_left.setPixmap(_create_legend_pixmap(maxL or 1.0, self.legend_left.width() or 440, 64))
        self.legend_right.setPixmap(_create_legend_pixmap(maxR or 1.0, self.legend_right.width() or 440, 64))

        if L:
            dL = dists(L, "left")
            self.dist_ap_left.update_data(dL["post"], dL["ant"])
            self.dist_ml_left.update_data(dL["med"], dL["lat"])
        if R:
            dR = dists(R, "right")
            self.dist_ap_right.update_data(dR["post"], dR["ant"])
            self.dist_ml_right.update_data(dR["med"], dR["lat"])

    def _render_side(self, vals: Dict[str,float], side: str):
        if side=="left":
            if vals:
                dL = dists(vals,"left")
                self.dist_ap_left.update_data(dL["post"], dL["ant"])
                self.dist_ml_left.update_data(dL["med"], dL["lat"])
            if PROFILE:
                times = self.draw_foot_visualization(self.foot_display_left, vals, "left", [None], [None], 0)
                if times:
                    for k in ("m","col","up","alpha","draw"):
                        self._acc_stats[k] += times.get(k,0.0)
                    self._acc_stats["frames"] += 1
            else:
                self.draw_foot_visualization(self.foot_display_left, vals, "left", [None], [None], 0)
        else:
            if vals:
                dR = dists(vals,"right")
                self.dist_ap_right.update_data(dR["post"], dR["ant"])
                self.dist_ml_right.update_data(dR["med"], dR["lat"])
            if PROFILE:
                times = self.draw_foot_visualization(self.foot_display_right, vals, "right", [None], [None], 0)
                if times:
                    for k in ("m","col","up","alpha","draw"):
                        self._acc_stats[k] += times.get(k,0.0)
                    self._acc_stats["frames"] += 1
            else:
                self.draw_foot_visualization(self.foot_display_right, vals, "right", [None], [None], 0)

    def play(self):
        if not (self.framesL or self.framesR):
            QMessageBox.warning(self, "Atenção", "Nenhuma sessão carregada.")
            return
        self.timer.start(); self._fps_start_time = time.perf_counter(); self._fps_frames = 0

    def pause(self): self.timer.stop()
    def stop(self): self.timer.stop(); self.idx = 0; self.show_current()

    def next_frame(self):
        n = max(len(self.framesL), len(self.framesR));
        if n == 0: return
        self.idx = (self.idx + 1) % n; self.show_current()
        try:
            self._fps_frames += 1
            elapsed = time.perf_counter() - self._fps_start_time
            if elapsed >= 1.0:
                fps = self._fps_frames / elapsed
                self.fps_label.setText(f"FPS: {fps:.1f}")
                self._fps_start_time = time.perf_counter(); self._fps_frames = 0
        except Exception:
            pass

    def next_frame_profiled(self):
        n = max(len(self.framesL), len(self.framesR))
        if n == 0: return
        self.idx = (self.idx + 1) % n

        t0 = time.perf_counter()
        L = self.framesL[self.idx] if self.idx < len(self.framesL) else {}
        R = self.framesR[self.idx] if self.idx < len(self.framesR) else {}
        t_fetch = time.perf_counter() - t0

        t_render0 = time.perf_counter()
        if L: self._render_side(L, "left")
        if R: self._render_side(R, "right")
        t_render = time.perf_counter() - t_render0

        nomeL, kpaL = peak_kpa(L) if L else ("--",0.0)
        nomeR, kpaR = peak_kpa(R) if R else ("--",0.0)


        self.peak_box.setText(f"<b>Pico de Pressão:</b><br>E: {nomeL} ({kpaL:.1f} kPa) <br> D: {nomeR} ({kpaR:.1f} kPa)")
        cop_texts=[]
        if L:
            mL = gerar_matriz_heatmap(L, "left", self.contorno_esquerdo.width() or CANVAS_W, self.contorno_esquerdo.height() or CANVAS_H)
            cL = calcular_cop_interpolado(mL)
            if cL: cop_texts.append(f"E: ({cL[0]/(self.contorno_esquerdo.width() or 1):.2f},{cL[1]/(self.contorno_esquerdo.height() or 1):.2f})")
        if R:
            mR = gerar_matriz_heatmap(R, "right", self.contorno_direito.width() or CANVAS_W, self.contorno_direito.height() or CANVAS_H)
            cR = calcular_cop_interpolado(mR)
            if cR: cop_texts.append(f"D: ({cR[0]/(self.contorno_direito.width() or 1):.2f},{cR[1]/(self.contorno_direito.height() or 1):.2f})")
        self.cop_box.setText("<b>Baricentro (CoP):</b><br>" + " <br>".join(cop_texts))

        try:
            self._fps_frames += 1
            elapsed = time.perf_counter() - self._fps_start_time
            if elapsed >= 1.0:
                fps = self._fps_frames / elapsed
                frames = max(1, self._acc_stats.get("frames",1))
                avg = {k: (self._acc_stats.get(k,0.0)/frames) for k in ("m","col","up","alpha","draw")}
                print(f"[FRAME {self.idx}] FPS:{fps:.1f} fetch_ms:{t_fetch*1000:.1f} render_ms:{t_render*1000:.1f} avg_step_ms: " +
                      ", ".join([f"{k}:{avg[k]*1000:.1f}" for k in avg]))
                self.fps_label.setText(f"FPS: {fps:.1f}")
                for k in ("m","col","up","alpha","draw","frames"):
                    self._acc_stats[k] = 0.0
                self._fps_start_time = time.perf_counter(); self._fps_frames = 0
        except Exception:
            pass
# ############## FIM ############################

# ============== Entrypoint ==============
def main():
    if not os.path.exists(DADOS):
        print(f"Arquivo DADOS não encontrado: {DADOS}")
        sys.exit(1)
    app = QApplication(sys.argv)
    app.setStyleSheet("""
        QWidget { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #141E30, stop:1 #243B55); color: #E0E0E0; font-family: 'Segoe UI','Roboto','Arial'; }
        QLabel { color: #E8F0F2; }
        QPushButton { background-color:#2C3E50;color:#E8F0F2;border-radius:6px;padding:6px; }
    """)
    w = TelaMovimento()
    w.setWindowTitle("teste-off - ANÁLISE DINÂMICA (offline) - MÁSCARA FIXA")
    w.showMaximized()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
