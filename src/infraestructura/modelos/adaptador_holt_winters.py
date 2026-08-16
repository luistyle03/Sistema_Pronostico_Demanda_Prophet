"""
CAPA DE INFRAESTRUCTURA — Adaptador Holt-Winters (suavizamiento exponencial).

Holt-Winters modela tres componentes con promedios ponderados que dan más
peso a lo reciente: nivel, tendencia y estacionalidad. En ventas diarias el
ciclo natural es la semana, por eso el período estacional por defecto es 7.
"""

from __future__ import annotations

import warnings

from statsmodels.tsa.holtwinters import ExponentialSmoothing

from src.aplicacion.puertos import PuertoModeloPronostico
from src.dominio.entidades import Pronostico, SerieTemporal
from src.dominio.excepciones import ModeloNoEntrenadoError
from src.infraestructura.modelos.utilidades import fechas_futuras, recortar_negativos


class AdaptadorHoltWinters(PuertoModeloPronostico):
    """Implementación del puerto de modelo con suavizamiento exponencial triple."""

    def __init__(self, periodo_estacional: int = 7):
        self._periodo = periodo_estacional
        self._ajuste = None
        self._ultima_fecha = None

    @property
    def nombre(self) -> str:
        return "Holt-Winters"

    def entrenar(self, serie: SerieTemporal) -> None:
        valores = serie.valores()
        self._ultima_fecha = serie.fechas()[-1]
        # La componente estacional exige al menos 2 ciclos completos; si la
        # serie es más corta, se degrada con elegancia a Holt (solo tendencia).
        usar_estacionalidad = len(valores) >= 2 * self._periodo
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            modelo = ExponentialSmoothing(
                valores,
                trend="add",
                seasonal="add" if usar_estacionalidad else None,
                seasonal_periods=self._periodo if usar_estacionalidad else None,
                initialization_method="estimated",
            )
            self._ajuste = modelo.fit()

    def pronosticar(self, horizonte: int) -> Pronostico:
        if self._ajuste is None:
            raise ModeloNoEntrenadoError("Holt-Winters: debe llamarse entrenar() primero.")
        proyeccion = self._ajuste.forecast(horizonte)
        return Pronostico(
            nombre_modelo=self.nombre,
            fechas=fechas_futuras(self._ultima_fecha, horizonte),
            valores=recortar_negativos(proyeccion),
        )
