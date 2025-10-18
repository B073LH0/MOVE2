# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, Optional, Tuple
import numpy as np
from scipy.ndimage import gaussian_filter

from ui.constants import (
    BORRADO, GRID_MAX, GAMMA,
    SENSOR_POS_LEFT, SENSOR_POS_RIGHT
)
############################################-ADIÇÃO-###################################################################
import numpy as np
from scipy.signal import fftconvolve

_kernel_cache = {}

def precompute_gaussian_kernel(gh, gw, sigma):
    """
    Retorna kernel 2D (gh x gw) centrado, normalizado.
    Cache por (gh,gw,sigma_round).
    """
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
    """
    Usa FFT-based convolution (scipy.signal.fftconvolve) para maior velocidade em kernels grandes.
    """
    # 'same' retorna resultado com mesma forma de canvas
    return fftconvolve(canvas, kernel, mode="same")

########################################################################################################################
def gerar_matriz_heatmap(sr_vals: Dict[str, float], lado_pe: str, largura: int, altura: int, grid_max: int = GRID_MAX) -> np.ndarray:
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
        try: v = float(sr_vals.get(key, 0.0) or 0.0)
        except: v = 0.0
        fx, fy = pos.get(key, (0.5, 0.5))
        x = max(0, min(gw - 1, int(round(fx * (gw - 1)))))
        y = max(0, min(gh - 1, int(round(fy * (gh - 1)))))
        canvas[y, x] += v

    sigma_rel = BORRADO * (max(1.0, min(max(gw, gh) * 0.06, 30.0)))
    #sm = gaussian_filter(canvas, sigma=sigma_rel,  mode="constant", cval=0.0) #mode="reflect,

    # ########################################-MODIFICAÇÃO-############################################################
    #
    kernel = precompute_gaussian_kernel(canvas.shape[0], canvas.shape[1], sigma_rel)
    sm = convolve_with_kernel(canvas, kernel).astype(np.float32)
    # #################################################################################################################

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

def colorize_normalized(n: np.ndarray) -> np.ndarray:
    """Converte [0..1] -> RGBA (HSV arco-íris) uint8."""
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

def normalize_heatmap(m: np.ndarray) -> np.ndarray:
    if m.size == 0 or m.max() == 0: return m
    mn, mx = float(m.min()), float(m.max())
    n = (m - mn) / (mx - mn + 1e-12)
    return n ** GAMMA

if __name__ == "__main__":
    import time
    sr = {f"SR{i}": np.random.rand() * 100 for i in range(1, 10)}
    t0 = time.perf_counter()
    for i in range(100):
        m = gerar_matriz_heatmap(sr, "left", 340, 450)
    dt = time.perf_counter() - t0
    print(f"Tempo total: {dt:.3f}s  -> {100/dt:.2f} FPS médios")

# ==========================================================
# FIM DO ARQUIVO
# ==========================================================
