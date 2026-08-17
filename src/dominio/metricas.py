"""
CAPA DE DOMINIO — Métricas de precisión del pronóstico.

Implementadas con la librería estándar (math), sin numpy, para que el
dominio siga siendo puro. Son las tres métricas del plan de tesis:

* MAPE  — error porcentual absoluto medio (comunicación de negocio).
* RMSE  — raíz del error cuadrático medio (misma unidad que las ventas).
* RMSSE — raíz del error cuadrático escalado medio (métrica oficial de la
          competencia M5; compara el error del modelo contra el error del
          método ingenuo "mañana venderé lo mismo que hoy").

Tratamiento de ceros en MAPE (decisión documentada en el plan de tesis):
los días con venta real igual a 0 se EXCLUYEN del promedio, porque la
división |real − pronóstico| / real no está definida cuando real = 0.
"""

from __future__ import annotations

import math
from typing import List


def mape(reales: List[float], pronosticados: List[float]) -> float:
    """Error Porcentual Absoluto Medio, en %. Excluye los días con real = 0."""
    pares = [(r, p) for r, p in zip(reales, pronosticados) if r != 0]
    if not pares:
        return math.inf  # No hay días comparables: el MAPE no es calculable.
    suma = sum(abs((r - p) / r) for r, p in pares)
    return 100.0 * suma / len(pares)


def rmse(reales: List[float], pronosticados: List[float]) -> float:
    """Raíz del Error Cuadrático Medio, en unidades vendidas."""
    n = len(reales)
    if n == 0:
        return math.inf
    suma_cuadrados = sum((r - p) ** 2 for r, p in zip(reales, pronosticados))
    return math.sqrt(suma_cuadrados / n)


def rmsse(
    entrenamiento: List[float],
    reales: List[float],
    pronosticados: List[float],
) -> float:
    """
    Raíz del Error Cuadrático Escalado Medio (definición de la competencia M5,
    Makridakis et al., 2022). Un RMSSE < 1 significa "mejor que el método
    ingenuo"; > 1 significa "peor que repetir el último valor".
    """
    n = len(reales)
    if n == 0 or len(entrenamiento) < 2:
        return math.inf
    # Numerador: error cuadrático medio del modelo en el período de prueba.
    numerador = sum((r - p) ** 2 for r, p in zip(reales, pronosticados)) / n
    # Denominador: error cuadrático medio del método ingenuo DENTRO del
    # entrenamiento (cada día comparado con el día anterior).
    m = len(entrenamiento)
    denominador = sum((entrenamiento[t] - entrenamiento[t - 1]) ** 2 for t in range(1, m)) / (m - 1)
    if denominador == 0:
        return math.inf  # Serie de entrenamiento constante: escala indefinida.
    return math.sqrt(numerador / denominador)


def wape(reales: List[float], pronosticados: List[float]) -> float:
    """
    Error Porcentual Absoluto PONDERADO (Weighted Absolute Percentage Error),
    en %. A diferencia del MAPE, NO divide día por día (no se dispara con
    valores pequeños): suma todos los errores y los divide entre la venta total.
    Es el estándar de la industria retail para pronóstico por producto, porque
    pondera por volumen. WAPE = Σ|real − pronóstico| / Σ real × 100.
    """
    suma_ventas = sum(abs(r) for r in reales)
    if suma_ventas == 0:
        return math.inf  # Sin ventas en el período: no es ponderable.
    suma_errores = sum(abs(r - p) for r, p in zip(reales, pronosticados))
    return 100.0 * suma_errores / suma_ventas


def mae(reales: List[float], pronosticados: List[float]) -> float:
    """
    Error Absoluto Medio, en UNIDADES vendidas. Es el más directo para
    inventario: "en promedio me equivoco por X unidades al día". A diferencia
    del RMSE, no penaliza extra los errores grandes (no eleva al cuadrado).
    """
    n = len(reales)
    if n == 0:
        return math.inf
    return sum(abs(r - p) for r, p in zip(reales, pronosticados)) / n


def sesgo(reales: List[float], pronosticados: List[float]) -> float:
    """
    Sesgo (Mean Error), en unidades. Indica la DIRECCIÓN del error, clave para
    inventario: sesgo > 0 → el modelo subestima (real > pronóstico): riesgo de
    QUIEBRE de stock. Sesgo < 0 → el modelo sobreestima: riesgo de
    SOBRE-STOCK (capital inmovilizado). Cerca de 0 = sin tendencia sistemática.
    """
    n = len(reales)
    if n == 0:
        return math.inf
    return sum(r - p for r, p in zip(reales, pronosticados)) / n
