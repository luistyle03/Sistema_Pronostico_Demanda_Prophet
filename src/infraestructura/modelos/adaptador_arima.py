"""
CAPA DE INFRAESTRUCTURA — Adaptador del modelo ARIMA (Box & Jenkins, 1970).

ARIMA(p, d, q) combina autorregresión (p), diferenciación (d) y promedio
móvil de errores (q). Como la tesis exige una comparación justa, el orden
no se fija a dedo: se prueba una rejilla de combinaciones y se elige la de
menor AIC (criterio de información de Akaike), procedimiento estándar.
"""

from __future__ import annotations

import itertools
import warnings

from statsmodels.tsa.arima.model import ARIMA

from src.aplicacion.puertos import PuertoModeloPronostico
from src.dominio.entidades import Pronostico, SerieTemporal
from src.dominio.excepciones import ModeloNoEntrenadoError
from src.infraestructura.modelos.utilidades import fechas_futuras, recortar_negativos


class AdaptadorARIMA(PuertoModeloPronostico):
    """Implementación del puerto de modelo usando ARIMA de statsmodels."""

    def __init__(self, max_p: int = 2, max_d: int = 1, max_q: int = 2):
        self._max_p = max_p
        self._max_d = max_d
        self._max_q = max_q
        self._ajuste = None  # Modelo ya entrenado (resultado de .fit()).
        self._ultima_fecha = None  # Para construir las fechas del pronóstico.
        self.orden_elegido = None  # (p, d, q) ganador, visible para auditoría.

    @property
    def nombre(self) -> str:
        return "ARIMA"

    def entrenar(self, serie: SerieTemporal) -> None:
        """Prueba todas las combinaciones (p,d,q) y conserva la de menor AIC."""
        valores = serie.valores()
        self._ultima_fecha = serie.fechas()[-1]
        mejor_aic = float("inf")
        mejor_ajuste = None
        combinaciones = itertools.product(
            range(self._max_p + 1), range(self._max_d + 1), range(self._max_q + 1)
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # statsmodels avisa mucho al iterar.
            for orden in combinaciones:
                if orden == (0, 0, 0):
                    continue  # ARIMA(0,0,0) es solo una constante: sin interés.
                try:
                    ajuste = ARIMA(valores, order=orden).fit()
                except Exception:
                    continue  # Algunas combinaciones no convergen: se descartan.
                if ajuste.aic < mejor_aic:
                    mejor_aic = ajuste.aic
                    mejor_ajuste = ajuste
                    self.orden_elegido = orden
        if mejor_ajuste is None:
            raise ModeloNoEntrenadoError("ARIMA: ninguna combinación (p,d,q) convergió.")
        self._ajuste = mejor_ajuste

    def pronosticar(self, horizonte: int) -> Pronostico:
        if self._ajuste is None:
            raise ModeloNoEntrenadoError("ARIMA: debe llamarse entrenar() primero.")
        proyeccion = self._ajuste.forecast(steps=horizonte)
        return Pronostico(
            nombre_modelo=self.nombre,
            fechas=fechas_futuras(self._ultima_fecha, horizonte),
            valores=recortar_negativos(proyeccion),
        )
