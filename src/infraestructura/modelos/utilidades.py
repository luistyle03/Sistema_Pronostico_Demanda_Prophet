"""
CAPA DE INFRAESTRUCTURA — Utilidades compartidas por los adaptadores de modelo.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import List


def fechas_futuras(ultima_fecha: date, horizonte: int) -> List[date]:
    """
    Genera las fechas del pronóstico: los `horizonte` días calendario que
    siguen inmediatamente a la última fecha del historial.
    """
    return [ultima_fecha + timedelta(days=i) for i in range(1, horizonte + 1)]


def recortar_negativos(valores) -> List[float]:
    """
    Las ventas no pueden ser negativas: cualquier proyección bajo cero se
    recorta a 0 (decisión documentada; los modelos lineales pueden extrapolar
    por debajo de cero en series con tendencia a la baja).
    """
    return [max(0.0, float(v)) for v in valores]
