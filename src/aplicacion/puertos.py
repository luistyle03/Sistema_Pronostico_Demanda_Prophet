"""
CAPA DE APLICACIÓN — Puertos (las "interfaces" de la arquitectura hexagonal).

Un puerto es un contrato abstracto: dice QUÉ se necesita, sin decir CÓMO se
implementa. Los casos de uso dependen solo de estos puertos (Principio de
Inversión de Dependencias — la D de SOLID). Prophet, ARIMA, openpyxl o
scipy viven afuera, en adaptadores que cumplen estos contratos.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Sequence

from src.dominio.entidades import Pronostico, SerieTemporal


class PuertoModeloPronostico(ABC):
    """
    Contrato de todo modelo de pronóstico. Cualquier clase que implemente
    estos tres miembros puede competir en la evaluación, sin tocar una sola
    línea de los casos de uso (Principio Abierto/Cerrado — la O de SOLID).
    """

    @property
    @abstractmethod
    def nombre(self) -> str:
        """Nombre legible del modelo (aparece en tablas y gráficos)."""

    @abstractmethod
    def entrenar(self, serie: SerieTemporal) -> None:
        """Aprende los patrones de la serie histórica recibida."""

    @abstractmethod
    def pronosticar(self, horizonte: int) -> Pronostico:
        """Proyecta `horizonte` días hacia el futuro. Requiere entrenar() antes."""


class PuertoExportadorPronostico(ABC):
    """Contrato para convertir resultados en un archivo descargable (Excel)."""

    @abstractmethod
    def exportar_pronostico(
        self,
        serie: SerieTemporal,
        pronostico: Pronostico,
        parametros_descripcion: List[tuple],
    ) -> bytes:
        """Devuelve los bytes de un .xlsx con el pronóstico del Módulo 2."""

    @abstractmethod
    def exportar_evaluacion(self, filas: List[dict], pruebas: List[dict]) -> bytes:
        """Devuelve los bytes de un .xlsx con la evidencia del Módulo 1."""


@dataclass
class ResultadoPruebaPareada:
    """Salida de una comparación estadística pareada entre dos modelos."""

    comparacion: str
    p_valor_t: float
    p_valor_wilcoxon: float
    d_cohen: float
    n: int
    # Media de las diferencias CON SIGNO (a - b). La d de Cohen se reporta en
    # valor absoluto porque mide magnitud, no direccion; el sentido de la
    # diferencia se lee aqui: negativo significa que el primer modelo obtiene
    # menor error que el segundo.
    diferencia_media: float = 0.0
    # Pares efectivamente utilizados tras descartar los no finitos. Si es menor
    # que n, hubo ajustes que fallaron en alguna serie.
    pares_validos: int = 0


class PuertoPruebasEstadisticas(ABC):
    """
    Contrato para las pruebas inferenciales del plan de tesis: t pareada,
    Wilcoxon y tamaño del efecto d de Cohen. El caso de uso pide "compara
    estos dos vectores de MAPE" y no sabe (ni le importa) que scipy lo hace.
    """

    @abstractmethod
    def comparar_pareado(
        self, etiqueta: str, errores_a: Sequence[float], errores_b: Sequence[float]
    ) -> ResultadoPruebaPareada:
        """Compara los errores del modelo A contra los del modelo B, serie a serie."""
