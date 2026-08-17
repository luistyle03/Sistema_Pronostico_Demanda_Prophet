"""
CAPA DE INFRAESTRUCTURA — Adaptador de pruebas estadísticas (scipy).

Implementa el puerto PuertoPruebasEstadisticas con las tres herramientas
inferenciales del plan de tesis:

* Prueba t pareada (paramétrica) sobre las diferencias de MAPE.
* Prueba de Wilcoxon (no paramétrica, robusta a no-normalidad).
* d de Cohen para muestras pareadas (d_z = media de diferencias / desviación
  de diferencias), con los umbrales de Cohen (1988): 0.2 pequeño,
  0.5 mediano, 0.8 grande.
"""

from __future__ import annotations

import math
from typing import Sequence

from scipy import stats

from src.aplicacion.puertos import PuertoPruebasEstadisticas, ResultadoPruebaPareada


class AdaptadorPruebasScipy(PuertoPruebasEstadisticas):
    """Pruebas pareadas calculadas con scipy.stats."""

    def comparar_pareado(
        self, etiqueta: str, errores_a: Sequence[float], errores_b: Sequence[float]
    ) -> ResultadoPruebaPareada:
        a = list(errores_a)
        b = list(errores_b)
        n = len(a)
        diferencias = [x - y for x, y in zip(a, b)]
        # --- Prueba t pareada -------------------------------------------------
        t_resultado = stats.ttest_rel(a, b)
        # --- Prueba de Wilcoxon ----------------------------------------------
        # Si TODAS las diferencias son cero, Wilcoxon no está definida.
        if all(d == 0 for d in diferencias):
            p_wilcoxon = 1.0
        else:
            p_wilcoxon = float(stats.wilcoxon(a, b).pvalue)
        # --- d de Cohen pareada (d_z) ----------------------------------------
        media_dif = sum(diferencias) / n
        if n > 1:
            varianza = sum((d - media_dif) ** 2 for d in diferencias) / (n - 1)
            desviacion = math.sqrt(varianza)
        else:
            desviacion = 0.0
        d_cohen = abs(media_dif) / desviacion if desviacion > 0 else math.inf
        return ResultadoPruebaPareada(
            comparacion=etiqueta,
            p_valor_t=float(t_resultado.pvalue),
            p_valor_wilcoxon=p_wilcoxon,
            d_cohen=d_cohen,
            n=n,
        )
