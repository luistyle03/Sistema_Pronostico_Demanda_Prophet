"""
CAPA DE APLICACIÓN — Caso de uso: Evaluar modelos (Módulo 1, experimental).

Orquesta el experimento de la tesis sobre una serie o sobre un lote de
series (las 50 series Favorita): divide en entrenamiento/prueba con holdout
temporal, hace competir a los 5 modelos en igualdad de condiciones, mide
MAPE / RMSE / RMSSE / tiempo y, en modo lote, aplica las pruebas
estadísticas pareadas (t, Wilcoxon, d de Cohen) del plan de tesis.

El caso de uso NO conoce a Prophet ni a scipy: recibe puertos (abstracciones)
por el constructor. Eso es Inyección de Dependencias.
"""

from __future__ import annotations

import math
import statistics
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from src.aplicacion.puertos import (
    PuertoModeloPronostico,
    PuertoPruebasEstadisticas,
    ResultadoPruebaPareada,
)
from src.dominio import metricas
from src.dominio.entidades import ResultadoEvaluacion, ResultadoModelo, SerieTemporal
from src.dominio.excepciones import SerieMuyCortaError

# Referencia ORIENTATIVA de lectura del MAPE en retail. El Plan NO fija umbral
# de aceptación de MAPE (es métrica de referencia, §7.5); el 15 % del Plan
# delimita la INTERMITENCIA de la población (criterio de inclusión, §7.3).
UMBRAL_MAPE_TESIS = 15.0


@dataclass
class ResumenModeloLote:
    """Métricas agregadas de UN modelo a través de TODAS las series del lote."""

    nombre_modelo: str
    mape_promedio: float
    mape_desviacion: float
    rmse_promedio: float
    rmsse_promedio: float
    rmsse_mediana: float
    rmsse_desviacion: float
    wape_promedio: float
    wape_mediana: float
    mae_promedio: float
    sesgo_promedio: float
    segundos_promedio: float
    series_ganadas: int
    series_evaluadas: int
    series_supera_ingenuo: int  # Cuántas series tienen RMSSE < 1.
    rmsses: List[float] = field(default_factory=list)  # Para el boxplot (métrica principal).
    mapes: List[float] = field(default_factory=list)  # Para las pruebas e histórico.


@dataclass
class ResultadoLote:
    """Salida completa del experimento por lotes: ranking + inferencia."""

    detalle_por_serie: List[ResultadoEvaluacion]
    resumen_por_modelo: List[ResumenModeloLote]  # Ordenado de mejor a peor RMSSE.
    pruebas: List[ResultadoPruebaPareada]
    series_omitidas: List[str]

    @property
    def ganador(self) -> Optional[ResumenModeloLote]:
        """
        Mejor modelo por la MEDIANA del RMSSE. Se usa la mediana (no el
        promedio) porque la distribución del RMSSE entre productos tiene cola
        pesada: unas pocas series muy volátiles disparan el promedio y lo
        vuelven engañoso. La mediana refleja el desempeño del producto típico.
        Calculado, nunca predefinido.
        """
        return self.resumen_por_modelo[0] if self.resumen_por_modelo else None


class EvaluadorDeModelos:
    """Caso de uso con una única responsabilidad: ejecutar la comparación justa."""

    MINIMO_ENTRENAMIENTO = 30  # Observaciones mínimas para que entrenar tenga sentido.

    def __init__(
        self,
        modelos: Sequence[PuertoModeloPronostico],
        pruebas_estadisticas: Optional[PuertoPruebasEstadisticas] = None,
    ):
        if not modelos:
            raise ValueError("Se requiere al menos un modelo para evaluar.")
        self._modelos = list(modelos)
        self._pruebas = pruebas_estadisticas

    # ------------------------------------------------------------------ #
    # Evaluación de UNA serie                                            #
    # ------------------------------------------------------------------ #
    def ejecutar(self, serie: SerieTemporal, horizonte: int) -> ResultadoEvaluacion:
        """Hace competir a todos los modelos sobre una misma serie."""
        if len(serie) < horizonte + self.MINIMO_ENTRENAMIENTO:
            raise SerieMuyCortaError(
                f"La serie '{serie.nombre}' tiene {len(serie)} observaciones; "
                f"se necesitan al menos {horizonte + self.MINIMO_ENTRENAMIENTO} "
                f"para reservar {horizonte} días de prueba."
            )
        entrenamiento, prueba = serie.dividir(horizonte)
        reales = prueba.valores()
        evaluacion = ResultadoEvaluacion(
            nombre_serie=serie.nombre,
            horizonte=horizonte,
            fechas_prueba=prueba.fechas(),
            valores_prueba=reales,
        )
        for modelo in self._modelos:
            evaluacion.resultados.append(
                self._evaluar_un_modelo(modelo, entrenamiento, reales, horizonte)
            )
        # Orden de mejor a peor MAPE; los que fallaron (mape = inf) van al final.
        evaluacion.resultados.sort(key=lambda r: r.mape)
        return evaluacion

    def _evaluar_un_modelo(
        self,
        modelo: PuertoModeloPronostico,
        entrenamiento: SerieTemporal,
        reales: List[float],
        horizonte: int,
    ) -> ResultadoModelo:
        """Entrena, pronostica y mide UN modelo, capturando sus fallos."""
        inicio = time.perf_counter()  # Cronómetro de alta precisión.
        try:
            modelo.entrenar(entrenamiento)
            pronostico = modelo.pronosticar(horizonte)
            segundos = time.perf_counter() - inicio
            return ResultadoModelo(
                nombre_modelo=modelo.nombre,
                pronostico=pronostico,
                mape=metricas.mape(reales, pronostico.valores),
                rmse=metricas.rmse(reales, pronostico.valores),
                rmsse=metricas.rmsse(entrenamiento.valores(), reales, pronostico.valores),
                wape=metricas.wape(reales, pronostico.valores),
                mae=metricas.mae(reales, pronostico.valores),
                sesgo=metricas.sesgo(reales, pronostico.valores),
                segundos=segundos,
            )
        except Exception as exc:  # Un modelo caído no debe tumbar el experimento.
            return ResultadoModelo(
                nombre_modelo=modelo.nombre,
                pronostico=None,
                mape=math.inf,
                rmse=math.inf,
                rmsse=math.inf,
                wape=math.inf,
                mae=math.inf,
                sesgo=math.inf,
                segundos=time.perf_counter() - inicio,
                error=str(exc),
            )

    # ------------------------------------------------------------------ #
    # Evaluación por LOTES (las 50 series de la tesis)                   #
    # ------------------------------------------------------------------ #
    def ejecutar_lote(
        self, series: Sequence[SerieTemporal], fraccion_prueba: float = 0.20
    ) -> ResultadoLote:
        """
        Evalúa cada serie con holdout temporal del `fraccion_prueba` final
        (20 % según el plan de tesis) y agrega los resultados.
        """
        detalle: List[ResultadoEvaluacion] = []
        omitidas: List[str] = []
        for i, serie in enumerate(series, start=1):
            horizonte = max(1, int(round(len(serie) * fraccion_prueba)))
            print(
                f"[{i}/{len(series)}] Evaluando '{serie.nombre}' "
                f"({len(serie)} obs., {horizonte} de prueba)...",
                flush=True,
            )
            try:
                detalle.append(self.ejecutar(serie, horizonte))
            except SerieMuyCortaError as exc:
                omitidas.append(f"{serie.nombre}: {exc}")
        resumen = self._resumir(detalle)
        pruebas = self._inferencia(detalle)
        return ResultadoLote(detalle, resumen, pruebas, omitidas)

    def _resumir(self, detalle: List[ResultadoEvaluacion]) -> List[ResumenModeloLote]:
        """Promedia las métricas de cada modelo a través de todas las series."""
        por_modelo: Dict[str, List[ResultadoModelo]] = {m.nombre: [] for m in self._modelos}
        ganadas: Dict[str, int] = {m.nombre: 0 for m in self._modelos}
        for evaluacion in detalle:
            ganador = evaluacion.ganador
            if ganador is not None:
                ganadas[ganador.nombre_modelo] += 1
            for r in evaluacion.resultados:
                # Se promedia sobre las series donde la métrica PRINCIPAL (RMSSE)
                # es finita; así los fallos no contaminan los promedios.
                if not r.fallo and math.isfinite(r.rmsse):
                    por_modelo[r.nombre_modelo].append(r)
        resumenes: List[ResumenModeloLote] = []
        for nombre, resultados in por_modelo.items():
            if not resultados:
                continue
            n = len(resultados)
            rmsses = [r.rmsse for r in resultados]
            wapes = [r.wape for r in resultados if math.isfinite(r.wape)]
            mapes = [r.mape for r in resultados if math.isfinite(r.mape)]
            rmsse_prom = sum(rmsses) / n
            rmsse_var = sum((x - rmsse_prom) ** 2 for x in rmsses) / (n - 1) if n > 1 else 0.0
            mape_prom = sum(mapes) / len(mapes) if mapes else math.inf
            mape_var = (
                sum((x - mape_prom) ** 2 for x in mapes) / (len(mapes) - 1)
                if len(mapes) > 1
                else 0.0
            )
            resumenes.append(
                ResumenModeloLote(
                    nombre_modelo=nombre,
                    mape_promedio=mape_prom,
                    mape_desviacion=math.sqrt(mape_var),
                    rmse_promedio=sum(r.rmse for r in resultados) / n,
                    rmsse_promedio=rmsse_prom,
                    rmsse_mediana=statistics.median(rmsses),
                    rmsse_desviacion=math.sqrt(rmsse_var),
                    wape_promedio=sum(wapes) / len(wapes) if wapes else math.inf,
                    wape_mediana=statistics.median(wapes) if wapes else math.inf,
                    mae_promedio=sum(r.mae for r in resultados) / n,
                    sesgo_promedio=sum(r.sesgo for r in resultados if math.isfinite(r.sesgo)) / n,
                    segundos_promedio=sum(r.segundos for r in resultados) / n,
                    series_ganadas=ganadas[nombre],
                    series_evaluadas=n,
                    series_supera_ingenuo=sum(1 for x in rmsses if x < 1.0),
                    rmsses=rmsses,
                    mapes=mapes,
                )
            )
        # Ranking por la MEDIANA del RMSSE (robusta a las series de cola pesada).
        resumenes.sort(key=lambda r: r.rmsse_mediana)
        return resumenes

    def _inferencia(self, detalle: List[ResultadoEvaluacion]) -> List[ResultadoPruebaPareada]:
        """
        Compara el RMSSE de Prophet contra cada clásico, serie a serie.
        Una prueba PAREADA exige que cada par provenga de la MISMA serie:
        (RMSSE de Prophet en la serie k, RMSSE del rival en la serie k). Se usa
        RMSSE por ser la métrica principal (libre de escala, comparable entre
        productos de distinto volumen).
        """
        if self._pruebas is None:
            return []
        rivales = [m.nombre for m in self._modelos if m.nombre != "Prophet"]
        salida: List[ResultadoPruebaPareada] = []
        for rival in rivales:
            pares_prophet: List[float] = []
            pares_rival: List[float] = []
            for evaluacion in detalle:
                por_nombre = {r.nombre_modelo: r for r in evaluacion.resultados}
                rp = por_nombre.get("Prophet")
                rr = por_nombre.get(rival)
                # Solo cuentan las series donde AMBOS lograron un RMSSE finito.
                if rp and rr and math.isfinite(rp.rmsse) and math.isfinite(rr.rmsse):
                    pares_prophet.append(rp.rmsse)
                    pares_rival.append(rr.rmsse)
            if len(pares_prophet) < 5:  # Con menos de 5 pares la inferencia no es informativa.
                continue
            salida.append(
                self._pruebas.comparar_pareado(f"Prophet vs {rival}", pares_prophet, pares_rival)
            )
        return salida
