"""
CAPA DE INFRAESTRUCTURA — Adaptador Regresión Lineal Simple.

Ajusta la recta y = a + b·t, donde t es el número de día (0, 1, 2, ...).
Captura la tendencia general (crece o decrece) pero, por construcción, es
ciega a la estacionalidad: esa limitación es justamente parte del contraste
que el experimento de la tesis quiere evidenciar.
"""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import LinearRegression

from src.aplicacion.puertos import PuertoModeloPronostico
from src.dominio.entidades import Pronostico, SerieTemporal
from src.dominio.excepciones import ModeloNoEntrenadoError
from src.infraestructura.modelos.utilidades import fechas_futuras, recortar_negativos


class AdaptadorRegresionLineal(PuertoModeloPronostico):
    """Implementación del puerto de modelo con la recta de mínimos cuadrados."""

    def __init__(self):
        self._modelo = None
        self._n_observaciones = 0
        self._ultima_fecha = None

    @property
    def nombre(self) -> str:
        return "Regresión lineal"

    def entrenar(self, serie: SerieTemporal) -> None:
        valores = serie.valores()
        self._n_observaciones = len(valores)
        self._ultima_fecha = serie.fechas()[-1]
        # X = columna con el índice de tiempo: [[0], [1], [2], ...].
        indices_tiempo = np.arange(self._n_observaciones).reshape(-1, 1)
        self._modelo = LinearRegression()
        self._modelo.fit(indices_tiempo, np.array(valores))

    def pronosticar(self, horizonte: int) -> Pronostico:
        if self._modelo is None:
            raise ModeloNoEntrenadoError("Regresión lineal: debe llamarse entrenar() primero.")
        # Los días futuros continúan la numeración: n, n+1, ..., n+h-1.
        indices_futuros = np.arange(
            self._n_observaciones, self._n_observaciones + horizonte
        ).reshape(-1, 1)
        proyeccion = self._modelo.predict(indices_futuros)
        return Pronostico(
            nombre_modelo=self.nombre,
            fechas=fechas_futuras(self._ultima_fecha, horizonte),
            valores=recortar_negativos(proyeccion),
        )
