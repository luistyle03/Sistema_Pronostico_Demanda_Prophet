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
        a_bruto = list(errores_a)
        b_bruto = list(errores_b)
        n = len(a_bruto)
        # POLITICA DE PARES COMPLETOS. Un unico valor no finito -en cualquiera de
        # los dos vectores- basta para que la media de las diferencias sea inf o
        # nan y para invalidar en silencio todo el contraste. Se descarta el PAR
        # completo, no solo el valor, para que el emparejamiento se conserve, y
        # se informa cuantos quedaron: asi la perdida es visible en la evidencia
        # en lugar de producir un resultado corrupto sin aviso.
        pares = [(x, y) for x, y in zip(a_bruto, b_bruto) if math.isfinite(x) and math.isfinite(y)]
        if len(pares) < 2:
            return ResultadoPruebaPareada(
                comparacion=etiqueta,
                p_valor_t=float("nan"),
                p_valor_wilcoxon=float("nan"),
                d_cohen=float("nan"),
                n=n,
                diferencia_media=float("nan"),
                pares_validos=len(pares),
            )
        a = [x for x, _ in pares]
        b = [y for _, y in pares]
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
        media_dif = sum(diferencias) / len(diferencias)
        if len(diferencias) > 1:
            varianza = sum((d - media_dif) ** 2 for d in diferencias) / (len(diferencias) - 1)
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
            diferencia_media=media_dif,
            pares_validos=len(diferencias),
        )
