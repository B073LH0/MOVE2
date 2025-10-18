# -*- coding: utf-8 -*-
"""
Leitura do RTDB no formato:
Users/{uid}/patients/{cpf}/{estatico|movimento}/{sessao}/{left|right}/payload/
  ├─ SR1..SR9 -> lista OU dict de índices ("0","1",...) OU {"value":[...]} ...
  ├─ battery/hour/minute/second/... (ignorar)
"""

from __future__ import annotations
from typing import Dict, List, Any, Tuple
from firebase_client import rtdb_get, firebase_session

SR_KEYS = {f"SR{i}" for i in range(1, 10)}

# ---------------------
# Helpers robustos
# ---------------------

def _to_float(x: Any) -> float:
    try:
        if isinstance(x, (int, float)):
            return float(x)
        if isinstance(x, str):
            return float(x.replace(",", ".").strip())
    except Exception:
        pass
    return float("nan")

def _last_non_null(node: Any) -> float:
    """Retorna o último valor numérico válido encontrado (em list/dict/valor)."""
    v = _to_float(node)
    if v == v:  # not NaN
        return v

    if isinstance(node, list):
        for item in reversed(node):
            val = _last_non_null(item)
            if val == val:
                return val
        return float("nan")

    if isinstance(node, dict):
        # Se houver 'value', priorize
        if "value" in node:
            val = _last_non_null(node["value"])
            if val == val:
                return val
        # Ordena chaves tentando numérico
        def key_sort(k):
            try:
                return int(k)
            except Exception:
                return str(k)
        last = float("nan")
        for k in sorted(node.keys(), key=key_sort):
            val = _last_non_null(node[k])
            if val == val:
                last = val
        return last

    return float("nan")

def _series(node: Any) -> List[float]:
    """Extrai uma série de floats (em ordem) de list/dict/{"value":[...]}/valor."""
    # Lista direta
    if isinstance(node, list):
        out: List[float] = []
        for it in node:
            v = _to_float(it) if not isinstance(it, (list, dict)) else _last_non_null(it)
            if v == v:
                out.append(v)
        return out

    # Dict
    if isinstance(node, dict):
        # {"value": [...]}
        if "value" in node and isinstance(node["value"], (list, dict)):
            return _series(node["value"])

        # Dict "0": val, "1": val ...
        def key_sort(k):
            try:
                return int(k)
            except Exception:
                return str(k)
        out: List[float] = []
        for _, it in sorted(node.items(), key=lambda kv: key_sort(kv[0])):  # type: ignore
            v = _to_float(it) if not isinstance(it, (list, dict)) else _last_non_null(it)
            if v == v:
                out.append(v)
        return out

    # Valor isolado
    v = _to_float(node)
    return [v] if v == v else []

# ---------------------
# API usada pelas telas
# ---------------------

def list_patients_by_cpf(search_cpf: str):
    uid = firebase_session.user_uid or ""
    snap = rtdb_get(f"Users/{uid}/patients") or {}
    out = []
    needle = (search_cpf or "").strip()
    for cpf, pdata in snap.items():
        if not needle or needle in str(cpf):
            out.append((cpf, (pdata.get("_profile", {}) or {})))
    return sorted(out, key=lambda x: x[0])

def list_sessions(uid: str, cpf: str, tipo: str = "estatico") -> List[str]:
    snap = rtdb_get(f"Users/{uid}/patients/{cpf}/{tipo}") or {}
    return sorted(snap.keys())

def _extract_payload_static(node: dict) -> Dict[str, float]:
    """Pega o ÚLTIMO valor válido de cada SR dentro do payload (estático)."""
    payload = node.get("payload", {}) if isinstance(node, dict) else {}
    out: Dict[str, float] = {f"SR{i}": 0.0 for i in range(1, 10)}
    for key, sub in payload.items():
        if key in SR_KEYS:
            val = _last_non_null(sub)
            out[key] = 0.0 if val != val else float(val)
    return out

def get_static_reading(uid: str, cpf: str, session_key: str):
    """
    Retorna:
      {"left": {SR1..SR9: float}, "right": {SR1..SR9: float}}
    """
    node = rtdb_get(f"Users/{uid}/patients/{cpf}/estatico/{session_key}") or {}
    return {
        "left": _extract_payload_static(node.get("left", {})),
        "right": _extract_payload_static(node.get("right", {})),
    }

def _extract_series_motion(payload: dict) -> Tuple[Dict[str, List[float]], int]:
    """
    Extrai séries por SR para movimento, ignorando campos extras.
    Retorna (series, min_len_comum) onde min_len_comum é o menor
    comprimento comum entre SR1..SR9 (para alinhar frames completos).
    """
    series: Dict[str, List[float]] = {}
    lengths: List[int] = []
    for i in range(1, 10):
        key = f"SR{i}"
        s = _series(payload.get(key, []))
        series[key] = s
        lengths.append(len(s))
    # usar o comprimento comum (todos SR presentes) para garantir frame completo
    min_len = min(lengths) if lengths else 0
    return series, min_len

def get_motion_frames(uid: str, cpf: str, session_key: str):
    """
    Retorna:
      {"left": [ {SR1..SR9}, ... ], "right": [ {SR1..SR9}, ... ]}
    Cada item da lista é um frame (índice k), composto por um valor por SR.
    """
    node = rtdb_get(f"Users/{uid}/patients/{cpf}/movimento/{session_key}") or {}

    def build_frames(side_key: str):
        side = node.get(side_key, {})
        payload = side.get("payload", {})
        if not isinstance(payload, dict):
            return []
        series, min_len = _extract_series_motion(payload)
        frames: List[Dict[str, float]] = []
        for k in range(min_len):
            frame = {sr: float(series[sr][k]) for sr in series.keys()}
            frames.append(frame)
        return frames

    return {"left": build_frames("left"), "right": build_frames("right")}
