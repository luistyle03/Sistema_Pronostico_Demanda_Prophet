"""
CAPA DE INFRAESTRUCTURA — Adaptador Promedio Móvil Simple.

Es la línea base ingenua del experimento: "mañana se venderá el promedio de
los últimos k días". No necesita ninguna librería; es el modelo que un
tendero calcula mentalmente, y por eso es el piso justo de la comparación.
"""
from __future__ import annotations

from src.aplicacion.puertos import PuertoModeloPronostico
from src.dominio.entidades import Pronostico, SerieTemporal
from src.dominio.excepciones import ModeloNoEntrenadoError, SerieMuyCortaError
from src.infraestructura.modelos.utilidades import fechas_futuras


class AdaptadorMediaMovil(PuertoModeloPronostico):
    """Implementación del puerto de modelo con un promedio móvil de ventana k."""

    def __init__(self, ventana: int = 7):
        self._ventana = ventana
        self._promedio = None
        self._ultima_fecha = None

    @property
    def nombre(self) -> str:
        return "Promedio móvil"

    def entrenar(self, serie: SerieTemporal) -> None:
        """'Entrenar' aquí es solo promediar las últimas `ventana` observaciones."""
        valores = serie.valores()
        if len(valores) < self._ventana:
            raise SerieMuyCortaError(
                f"Promedio móvil: se necesitan al menos {self._ventana} observaciones."
            )
        ultimos = valores[-self._ventana:]
        self._promedio = sum(ultimos) / self._ventana
        self._ultima_fecha = serie.fechas()[-1]

    def pronosticar(self, horizonte: int) -> Pronostico:
        if self._promedio is None:
            raise ModeloNoEntrenadoError("Promedio móvil: debe llamarse entrenar() primero.")
        # El pronóstico es plano: el mismo promedio repetido para cada día futuro.
        return Pronostico(
            nombre_modelo=self.nombre,
            fechas=fechas_futuras(self._ultima_fecha, horizonte),
            valores=[self._promedio] * horizonte,
        )
