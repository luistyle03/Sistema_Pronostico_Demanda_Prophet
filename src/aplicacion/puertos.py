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
