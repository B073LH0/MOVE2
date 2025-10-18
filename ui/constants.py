# -*- coding: utf-8 -*-
from __future__ import annotations

# Assets
LOGO_IMG = "assets/feet.png"
FOOT_OUTLINE_IMG = "assets/foot_outline.png"

# Visual / Consts (como no original)
CANVAS_W, CANVAS_H = 340, 450
BORRADO = 2           # multiplicador do sigma relativo
GAMMA = 1
GRID_MAX = 100
KPA_PER_UNIT = 67.6 / 1000.0  # mesmo fator do seu app

# Posições dos sensores (frações no contorno do pé direito)
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
