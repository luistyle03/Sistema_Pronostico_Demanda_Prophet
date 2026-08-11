"""
CAPA DE DOMINIO — Entidades.

Esta es la capa más interna de la arquitectura hexagonal. Aquí viven los
conceptos del negocio (una serie temporal, un pronóstico, un resultado de
evaluación) expresados en Python puro: NO se importa pandas, ni Prophet,
ni Flask. Gracias a eso, el corazón del sistema no depende de ninguna
tecnología y puede probarse de forma aislada.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from src.dominio.excepciones import SerieMuyCortaError

# RF03 — Regla de negocio de ELEGIBILIDAD: para un pronóstico confiable con
# estacionalidad anual, la serie debe cubrir al menos un año completo de
# historia continua. La regla vive AQUÍ (dominio); las capas externas solo
# la detectan (lector) y la hacen cumplir (servidor).
DIAS_MINIMOS_ELEGIBLE = 365


@dataclass(frozen=True)
class PuntoSerie:
    """Una observación de la serie: un día y cuántas unidades se vendieron."""

    fecha: date
    valor: float


@dataclass
class SerieTemporal:
    """Una secuencia ordenada de observaciones diarias de ventas."""

    nombre: str
    puntos: List[PuntoSerie]

    def fechas(self) -> List[date]:
        """Devuelve solo las fechas, en el mismo orden de la serie."""
        return [p.fecha for p in self.puntos]

    def valores(self) -> List[float]:
        """Devuelve solo los valores (unidades vendidas), en orden."""
        return [p.valor for p in self.puntos]

    def __len__(self) -> int:
        """Permite usar len(serie) para saber cuántas observaciones tiene."""
        return len(self.puntos)

    def es_elegible(self) -> bool:
        """
        RF03: ¿la serie alcanza la historia mínima (365 días continuos) para
        un pronóstico confiable? La serie ya es diaria y continua (el lector
        rellena huecos), por lo que su longitud equivale a días de calendario.
        """
        return len(self.puntos) >= DIAS_MINIMOS_ELEGIBLE

    def dividir(self, n_prueba: int) -> tuple["SerieTemporal", "SerieTemporal"]:
        """
        Parte la serie en (entrenamiento, prueba) para la validación holdout:
        las últimas `n_prueba` observaciones se reservan como prueba y el
        resto queda como entrenamiento. Es la división temporal clásica.
        """
        if n_prueba <= 0 or n_prueba >= len(self.puntos):
            raise SerieMuyCortaError(
                f"No se puede reservar {n_prueba} observaciones de prueba en "
                f"una serie de {len(self.puntos)} observaciones."
            )
        entrenamiento = SerieTemporal(self.nombre, self.puntos[:-n_prueba])
        prueba = SerieTemporal(self.nombre, self.puntos[-n_prueba:])
        return entrenamiento, prueba


@dataclass
class ComponentesPronostico:
    """
    Descomposición aditiva del pronóstico (HU02 · RF06): si el modelo la
    ofrece (como Prophet), cada pieza —tendencia, estacionalidades y
    feriados— puede graficarse por separado para explicarle al dueño del
    negocio POR QUÉ el sistema pronostica ese número.
    """

    fechas: List[date]                             # Eje temporal de tendencia y feriados.
    tendencia: List[float]                         # Nivel base y su evolución.
    perfil_semanal: Optional[List[float]] = None   # 7 efectos: lunes .. domingo.
    perfil_anual_dias: Optional[List[str]] = None  # Etiquetas 'MM-DD' (enero .. diciembre).
    perfil_anual: Optional[List[float]] = None     # Efecto por día del año.
    feriados: Optional[List[float]] = None         # Efecto de feriados (mismo eje que fechas).


@dataclass
class Pronostico:
    """
    El resultado de un modelo: para cada fecha futura, el valor estimado y
    (si el modelo lo ofrece, como Prophet) un intervalo de confianza y la
    descomposición en componentes.
    """

    nombre_modelo: str
    fechas: List[date]
    valores: List[float]
    limites_inferiores: Optional[List[float]] = None
    limites_superiores: Optional[List[float]] = None
    componentes: Optional[ComponentesPronostico] = None


@dataclass
class ResultadoModelo:
    """Las métricas que obtuvo UN modelo al evaluarse contra la prueba."""

    nombre_modelo: str
    pronostico: Optional[Pronostico]
    mape: float
    rmse: float
    rmsse: float
    segundos: float
    wape: float = math.inf       # % ponderado por volumen (estándar retail).
    mae: float = math.inf        # error medio en UNIDADES (directo para inventario).
    sesgo: float = 0.0           # dirección del error: +subestima / −sobreestima.
    error: Optional[str] = None  # Si el modelo falló, aquí queda el motivo.

    @property
    def fallo(self) -> bool:
        """True cuando el modelo no pudo entrenarse o pronosticar."""
        return self.error is not None


@dataclass
class ResultadoEvaluacion:
    """
    La evaluación completa de UNA serie: los 5 modelos compitieron sobre los
    mismos datos y aquí quedan sus métricas, ordenadas de mejor a peor RMSSE.
    """

    nombre_serie: str
    horizonte: int
    fechas_prueba: List[date]
    valores_prueba: List[float]
    resultados: List[ResultadoModelo] = field(default_factory=list)

    @property
    def ganador(self) -> Optional[ResultadoModelo]:
        """
        El modelo con MENOR RMSSE entre los que no fallaron. RMSSE es la métrica
        principal (libre de escala, robusta a la volatilidad de cada producto y
        comparable entre series de distinto volumen, según la competencia M5).
        El ganador se CALCULA a partir de los datos; nunca está predefinido.
        """
        validos = [r for r in self.resultados if not r.fallo]
        if not validos:
            return None
        return min(validos, key=lambda r: r.rmsse)


@dataclass
class ResumenGerencial:
    """
    Indicadores en lenguaje de negocio que acompañan a un pronóstico, pensados
    para el dueño del retail (Módulo 2): cuánto venderá, si crece y cuándo
    será su día pico.
    """

    total_proyectado: float
    total_periodo_anterior: Optional[float]
    variacion_porcentual: Optional[float]
    fecha_pico: date
    valor_pico: float
    promedio_diario: float
