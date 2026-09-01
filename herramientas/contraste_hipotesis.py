#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contraste_hipotesis.py — Contraste formal de HE1 y HE2–HE5 (Plan de Tesis, §7.7).

Ejecuta EXACTAMENTE la regla de decisión declarada en el plan y la tesis:
  · HE1: Shapiro–Wilk sobre los RMSSE del sistema; si hay normalidad, prueba t de
    una muestra unilateral contra 1; si no, Wilcoxon de una muestra unilateral.
    Se reporta además la proporción de series con RMSSE < 1.
  · HE2–HE5: prueba t pareada y Wilcoxon de Prophet frente a cada clásico, con
    p exactos SIN ajustar y AJUSTADOS por la corrección de Holm (1979), más la
    d de Cohen pareada.

Uso (tras generar la muestra con preparar_favorita.py):
    python herramientas/contraste_hipotesis.py favorita_50_series.csv \
        --fraccion-prueba 0.2 --salida contraste.xlsx
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from openpyxl import Workbook
from scipy import stats

from src.aplicacion.parametros import ParametrosPronostico
from src.dominio import metricas
from src.infraestructura.estadistica.adaptador_scipy import AdaptadorPruebasScipy
from src.infraestructura.modelos.adaptador_arima import AdaptadorARIMA
from src.infraestructura.modelos.adaptador_holt_winters import AdaptadorHoltWinters
from src.infraestructura.modelos.adaptador_media_movil import AdaptadorMediaMovil
from src.infraestructura.modelos.adaptador_prophet import AdaptadorProphet
from src.infraestructura.modelos.adaptador_regresion_lineal import (
    AdaptadorRegresionLineal,
)

ALFA = 0.05


def ajuste_holm(p_valores: list[float]) -> list[float]:
    """Corrección de Holm (1979), método step-down.

    Devuelve los p ajustados EN EL ORDEN ORIGINAL de entrada: se ordenan los p de
    menor a mayor, el i-ésimo se multiplica por (m − i), se fuerza la monotonía
    acumulada y se recorta a 1. Controla el error familiar siendo uniformemente
    más potente que Bonferroni.
    """
    m = len(p_valores)
    orden = sorted(range(m), key=lambda i: p_valores[i])
    ajustados = [0.0] * m
    acumulado = 0.0
    for rango, indice in enumerate(orden):
        candidato = min(1.0, (m - rango) * p_valores[indice])
        acumulado = max(acumulado, candidato)
        ajustados[indice] = acumulado
    return ajustados


def contraste_he1(rmsse_sistema: list[float], alfa: float = ALFA) -> dict:
    """Regla de decisión de la HE1 (Plan §7.7): normalidad y prueba contra 1."""
    _, p_shapiro = stats.shapiro(rmsse_sistema)
    if p_shapiro > alfa:
        resultado = stats.ttest_1samp(rmsse_sistema, 1.0, alternative="less")
        prueba = "t de una muestra, unilateral (< 1)"
        estadistico, p_valor = float(resultado.statistic), float(resultado.pvalue)
    else:
        diferencias = [x - 1.0 for x in rmsse_sistema]
        estadistico, p_valor = (float(v) for v in stats.wilcoxon(diferencias, alternative="less"))
        prueba = "Wilcoxon de una muestra, unilateral (< 1)"
    proporcion = sum(1 for x in rmsse_sistema if x < 1.0) / len(rmsse_sistema)
    return {
        "n": len(rmsse_sistema),
        "p_shapiro": float(p_shapiro),
        "prueba_aplicada": prueba,
        "estadistico": estadistico,
        "p_valor": p_valor,
        "proporcion_rmsse_menor_1": proporcion,
        "decision": ("HE1 confirmada (p < 0.05)" if p_valor < alfa else "HE1 no confirmada"),
    }


def _modelos_del_experimento():
    """Los mismos cinco motores y en el mismo orden que run.py / el CLI:
    Prophet con feriados de Ecuador (el dataset Favorita es ecuatoriano)."""
    return [
        AdaptadorProphet(ParametrosPronostico(pais_feriados="EC")),
        AdaptadorARIMA(),
        AdaptadorHoltWinters(),
        AdaptadorMediaMovil(),
        AdaptadorRegresionLineal(),
    ]


def ejecutar(entrada: Path, fraccion_prueba: float, salida: Path) -> None:
    # El lector se importa AQUÍ y no en la cabecera del módulo a propósito: las
    # funciones de contraste (ajuste_holm, contraste_he1) son estadística pura y
    # no dependen de la lectura de archivos. Importarlo arriba obligaría a que la
    # capa de persistencia exista para poder siquiera importar este módulo, y las
    # pruebas del instrumento de medición (S13) se escribieron antes que esa capa
    # (S14). La importación diferida mantiene el módulo utilizable en ambos casos.
    from src.infraestructura.persistencia.lector_archivos import LectorVentas

    # Se usa EXACTAMENTE el mismo lector que la aplicación web: normaliza los
    # nombres de columna, interpreta las fechas dd/mm/aaaa, suma duplicados,
    # rellena los días sin registro con 0 y descarta valores negativos.
    lector = LectorVentas()
    tabla = lector.leer(entrada.read_bytes(), str(entrada))
    series = lector.construir_series_lote(tabla)
    modelos = _modelos_del_experimento()
    rmsse_por_modelo: dict[str, list[float]] = {m.nombre: [] for m in modelos}

    fallos: list[tuple[str, str, str]] = []
    descartadas = []

    for serie in series:
        etiqueta = serie.nombre
        n_prueba = max(1, int(round(len(serie) * fraccion_prueba)))
        if len(serie) < n_prueba + 30:
            descartadas.append(etiqueta)
            continue
        entrenamiento, prueba = serie.dividir(n_prueba)
        reales = prueba.valores()
        for modelo in modelos:
            try:
                modelo.entrenar(entrenamiento)
                pronostico = modelo.pronosticar(n_prueba)
                valor = metricas.rmsse(entrenamiento.valores(), reales, pronostico.valores)
            except Exception:
                valor = float("inf")
            rmsse_por_modelo[modelo.nombre].append(valor)
        print(f"  serie {etiqueta}: lista")

    nombre_prophet = modelos[0].nombre
    he1 = contraste_he1(rmsse_por_modelo[nombre_prophet])

    pruebas = AdaptadorPruebasScipy()
    filas_pareadas = []
    for modelo in modelos[1:]:
        r = pruebas.comparar_pareado(
            f"{nombre_prophet} vs {modelo.nombre}",
            rmsse_por_modelo[nombre_prophet],
            rmsse_por_modelo[modelo.nombre],
        )
        filas_pareadas.append(
            {
                "comparacion": f"{nombre_prophet} vs {modelo.nombre}",
                "n": r.n,
                "p_t": r.p_valor_t,
                "p_wilcoxon": r.p_valor_wilcoxon,
                "d_cohen": r.d_cohen,
            }
        )
    for clave in ("p_t", "p_wilcoxon"):
        ajustados = ajuste_holm([f[clave] for f in filas_pareadas])
        for fila, aj in zip(filas_pareadas, ajustados):
            fila[clave + "_holm"] = aj

    libro = Workbook()
    hoja1 = libro.active
    hoja1.title = "HE1"
    hoja1.append(["Campo", "Valor"])
    for campo, valor in he1.items():
        hoja1.append([campo, valor])
    hoja2 = libro.create_sheet("Pareadas_Holm")
    columnas = [
        "comparacion",
        "n",
        "p_t",
        "p_t_holm",
        "p_wilcoxon",
        "p_wilcoxon_holm",
        "d_cohen",
    ]
    hoja2.append(columnas)
    for fila in filas_pareadas:
        hoja2.append([fila[c] for c in columnas])
    libro.save(salida)

    print("\n===== HE1 =====")
    for campo, valor in he1.items():
        print(f"  {campo}: {valor}")
    print("===== HE2–HE5 (p exactos y ajustados por Holm) =====")
    for fila in filas_pareadas:
        print(
            f"  {fila['comparacion']}: p_t={fila['p_t']:.4f} (Holm {fila['p_t_holm']:.4f}) | "
            f"p_W={fila['p_wilcoxon']:.4f} (Holm {fila['p_wilcoxon_holm']:.4f}) "
            f"| d={fila['d_cohen']:.3f}"
        )
    if descartadas:
        print(f"  Series descartadas por historia insuficiente: {descartadas}")
    print(f"\nEvidencia guardada en: {salida}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Contraste formal de HE1 y HE2–HE5")
    parser.add_argument("entrada", type=Path, help="favorita_50_series.csv (fecha, serie, ventas)")
    parser.add_argument("--fraccion-prueba", type=float, default=0.2)
    parser.add_argument("--salida", type=Path, default=Path("contraste.xlsx"))
    main_args = parser.parse_args()
    ejecutar(main_args.entrada, main_args.fraccion_prueba, main_args.salida)


if __name__ == "__main__":
    main()
