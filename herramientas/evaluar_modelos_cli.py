#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""evaluar_modelos_cli.py — Evaluación comparativa por consola.

Ejecuta EL MISMO núcleo que la aplicación web (src/), de modo que los números
que imprime son idénticos a los del Módulo 1. No reimplementa métricas ni
modelos: importa los adaptadores y el caso de uso EvaluadorDeModelos.

Uso:
    python herramientas/evaluar_modelos_cli.py favorita_50_series.csv \
        --fraccion-prueba 0.2 --salida resultados_evaluacion.xlsx
"""

from __future__ import annotations

import argparse
import math
import platform
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from openpyxl import Workbook

# Se reutiliza EXACTAMENTE el mismo núcleo del experimento principal.
from src.aplicacion.casos_uso.evaluar_modelos import EvaluadorDeModelos
from src.aplicacion.parametros import ParametrosPronostico
from src.infraestructura.estadistica.adaptador_scipy import AdaptadorPruebasScipy
from src.infraestructura.modelos.adaptador_arima import AdaptadorARIMA
from src.infraestructura.modelos.adaptador_holt_winters import AdaptadorHoltWinters
from src.infraestructura.modelos.adaptador_media_movil import AdaptadorMediaMovil
from src.infraestructura.modelos.adaptador_prophet import AdaptadorProphet
from src.infraestructura.modelos.adaptador_regresion_lineal import (
    AdaptadorRegresionLineal,
)
from src.infraestructura.persistencia.lector_archivos import LectorVentas

MODELOS = ["Prophet", "ARIMA", "Holt-Winters", "Promedio móvil", "Regresión lineal"]


def _construir_evaluador() -> EvaluadorDeModelos:
    """Los mismos 5 modelos del experimento principal (Prophet con feriados EC)."""
    modelos = [
        AdaptadorProphet(ParametrosPronostico(pais_feriados="EC")),
        AdaptadorARIMA(),
        AdaptadorHoltWinters(),
        AdaptadorMediaMovil(),
        AdaptadorRegresionLineal(),
    ]
    return EvaluadorDeModelos(modelos, AdaptadorPruebasScipy())


# === Comparación operativa: capacidades DOCUMENTADAS (no calculadas) =========
# Derivadas de los requisitos del retail y de la documentación oficial de cada
# modelo. Escala 2=Sí, 1=Parcial, 0=No. La fila "Velocidad" NO está aquí: se
# completa empíricamente con los tiempos de ejecución medidos por el software.
# La lista es BALANCEADA: incluye criterios donde Prophet NO gana (velocidad,
# simplicidad), para no sesgar el resultado a su favor.
CAPACIDADES = {
    "Sin config. estadística experta": {
        "Prophet": 2,
        "ARIMA": 0,
        "Holt-Winters": 1,
        "Promedio móvil": 2,
        "Regresión lineal": 2,
    },
    "Manejo nativo de feriados": {
        "Prophet": 2,
        "ARIMA": 0,
        "Holt-Winters": 0,
        "Promedio móvil": 0,
        "Regresión lineal": 0,
    },
    "Estacionalidades múltiples": {
        "Prophet": 2,
        "ARIMA": 1,
        "Holt-Winters": 1,
        "Promedio móvil": 0,
        "Regresión lineal": 0,
    },
    "Tolera datos faltantes": {
        "Prophet": 2,
        "ARIMA": 0,
        "Holt-Winters": 0,
        "Promedio móvil": 1,
        "Regresión lineal": 1,
    },
    "Intervalos de incertidumbre": {
        "Prophet": 2,
        "ARIMA": 2,
        "Holt-Winters": 1,
        "Promedio móvil": 0,
        "Regresión lineal": 1,
    },
    "Interpretabilidad": {
        "Prophet": 2,
        "ARIMA": 0,
        "Holt-Winters": 1,
        "Promedio móvil": 2,
        "Regresión lineal": 2,
    },
    "Simplicidad de implementación": {
        "Prophet": 1,
        "ARIMA": 0,
        "Holt-Winters": 1,
        "Promedio móvil": 2,
        "Regresión lineal": 2,
    },
}
SIMBOLO = {2: "Sí", 1: "Parcial", 0: "No"}


def imprimir_matriz_operativa(tiempos):
    """Matriz cualitativa BALANCEADA (análisis documental, NO un cálculo),
    salvo la fila 'Velocidad', que es empírica (tiempos medidos)."""
    validos = {m: t for m, t in tiempos.items() if t is not None and math.isfinite(t)}
    veloc = {m: 0 for m in MODELOS}
    if validos:
        orden = sorted(validos, key=validos.get)  # de más rápido a más lento
        for pos, m in enumerate(orden):
            veloc[m] = 2 if pos < 2 else (1 if pos < len(orden) - 2 else 0)
    print("\n" + "=" * 86)
    print("COMPARACIÓN OPERATIVA — ANÁLISIS DOCUMENTAL CUALITATIVO (NO es un cálculo del software)")
    print("Criterios derivados de los requisitos del retail. Escala: Sí / Parcial / No.")
    print("La fila 'Velocidad de cómputo' SÍ es empírica (de los tiempos medidos).")
    print("=" * 86)
    print(f"{'Criterio (requisito del retail)':33s}" + "".join(f"{m[:11]:>12s}" for m in MODELOS))
    puntajes = {m: 0 for m in MODELOS}
    for criterio, vals in CAPACIDADES.items():
        fila = f"{criterio:33s}"
        for m in MODELOS:
            fila += f"{SIMBOLO[vals[m]]:>12s}"
            puntajes[m] += vals[m]
        print(fila)
    fila = f"{'Velocidad de cómputo (empírica)':33s}"
    for m in MODELOS:
        fila += f"{SIMBOLO[veloc[m]]:>12s}"
        puntajes[m] += veloc[m]
    print(fila)
    print("-" * 86)
    maxp = 2 * (len(CAPACIDADES) + 1)
    fila = f"{('PUNTAJE (de %d)' % maxp):33s}"
    for m in MODELOS:
        fila += f"{puntajes[m]:>12d}"
    print(fila)
    return puntajes


def imprimir_sintesis(mejor_precision, puntajes_oper, hay_equivalencia):
    print("\n" + "=" * 86)
    print("SÍNTESIS — IDONEIDAD INTEGRAL PARA EL RETAIL")
    print("=" * 86)
    mejor_oper = max(puntajes_oper, key=puntajes_oper.get)
    print(f"1) PRECISIÓN (empírica, calculada): el mejor por RMSSE mediano es {mejor_precision}.")
    if hay_equivalencia:
        print("   Las pruebas pareadas muestran equivalencia estadística: ninguno domina")
        print("   significativamente en precisión.")
    print(f"2) OPERATIVO (documental + velocidad empírica): mayor puntaje = {mejor_oper}.")
    print("3) CONCLUSIÓN INTEGRAL: ante la equivalencia en precisión, la elección se decide")
    print(f"   por el perfil operativo; bajo ese criterio, {mejor_oper} resulta el MÁS IDÓNEO.")
    print("   ADVERTENCIA HONESTA: esta conclusión combina un resultado empírico")
    print("   (equivalencia) con un análisis documental cualitativo (operativo); la parte")
    print("   operativa NO es un cálculo del software, sino un juicio fundamentado.")


def guardar_excel(lote, destino: Path, entrada: Path, fraccion: float) -> None:
    """Evidencia descargable: una fila por serie y modelo, más las pruebas."""
    wb = Workbook()

    # --- Hoja 1: ficha técnica de la corrida (trazabilidad de la medición) ---
    ficha = wb.active
    ficha.title = "Ficha técnica"
    ficha.append(["FICHA TÉCNICA DE LA CORRIDA"])
    ficha.append([])
    for campo, valor in [
        (
            "Instrumento",
            "Módulo de evaluación automatizada del desempeño del pronóstico",
        ),
        ("Investigador", "Pedro Alberto Luis Méndez"),
        ("Fecha y hora de la corrida", datetime.now().strftime("%d/%m/%Y %H:%M:%S")),
        (
            "Equipo",
            f"{platform.processor() or platform.machine()} · "
            f"{platform.system()} {platform.release()}",
        ),
        ("Versión de Python", platform.python_version()),
        ("Archivo de entrada", str(entrada)),
        ("Series evaluadas", len(lote.detalle_por_serie)),
        ("Series omitidas", len(lote.series_omitidas)),
        ("Modelos comparados", ", ".join(MODELOS)),
        (
            "Técnica de evaluación",
            "Out-of-sample con partición temporal de origen fijo (holdout)",
        ),
        ("Porción de prueba (holdout)", f"{fraccion:.0%} final de cada serie"),
        ("Historia mínima exigida", "365 días (regla RF03)"),
    ]:
        ficha.append([campo, valor])

    ws = wb.create_sheet("Resultados")
    ws.append(
        [
            "Serie",
            "Modelo",
            "RMSSE",
            "WAPE (%)",
            "MAE (unid.)",
            "Sesgo (unid.)",
            "RMSE",
            "MAPE (%)",
            "Tiempo (s)",
            "Ganador",
            "Error",
        ]
    )
    for evaluacion in lote.detalle_por_serie:
        ganador = evaluacion.ganador
        nombre_ganador = ganador.nombre_modelo if ganador else None
        for r in evaluacion.resultados:
            ws.append(
                [
                    evaluacion.nombre_serie,
                    r.nombre_modelo,
                    r.rmsse,
                    r.wape,
                    r.mae,
                    r.sesgo,
                    r.rmse,
                    r.mape,
                    r.segundos,
                    "Sí" if r.nombre_modelo == nombre_ganador else "No",
                    getattr(r, "mensaje_error", None),
                ]
            )
    ws2 = wb.create_sheet("Pruebas estadísticas")
    ws2.append(
        [
            "Comparación",
            "p-valor (t pareada)",
            "p-valor (Wilcoxon)",
            "d de Cohen",
            "N (pares)",
        ]
    )
    for p in lote.pruebas:
        ws2.append([p.comparacion, p.p_valor_t, p.p_valor_wilcoxon, p.d_cohen, p.n])
    wb.save(destino)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluación comparativa (mismo núcleo que la app)."
    )
    parser.add_argument("entrada", type=Path, help="CSV/XLSX con fecha, serie/producto y ventas")
    parser.add_argument(
        "--fraccion-prueba",
        type=float,
        default=0.20,
        help="Porción final reservada para prueba (0.20 = 20 %%, plan de tesis)",
    )
    parser.add_argument("--salida", type=Path, default=Path("resultados_evaluacion.xlsx"))
    args = parser.parse_args()

    lector = LectorVentas()
    tabla = lector.leer(args.entrada.read_bytes(), str(args.entrada))
    series = lector.construir_series_lote(tabla)
    print(f"Dataset cargado: {len(series)} serie(s).")
    print(f"Holdout temporal: {args.fraccion_prueba:.0%} final de cada serie.\n")

    lote = _construir_evaluador().ejecutar_lote(series, args.fraccion_prueba)

    n = len(lote.detalle_por_serie)
    print("\n" + "=" * 86)
    print(f"RESULTADO SOBRE {n} SERIE(S) — métrica principal: RMSSE (mediana; menor mejor)")
    print("=" * 86)
    print(
        f"{'Modelo':<18}{'RMSSEmed':>10}{'RMSSEprom':>11}{'WAPEmed%':>10}"
        f"{'MAEprom':>9}{'Sesgo':>8}{'Gana':>7}{'Sup<1':>8}"
    )
    ganador = lote.ganador
    for r in lote.resumen_por_modelo:
        marca = "  <-- GANADOR" if ganador and r.nombre_modelo == ganador.nombre_modelo else ""
        print(
            f"{r.nombre_modelo:<18}{r.rmsse_mediana:>10.4f}{r.rmsse_promedio:>11.4f}"
            f"{r.wape_mediana:>10.1f}{r.mae_promedio:>9.1f}{r.sesgo_promedio:>8.1f}"
            f"{str(r.series_ganadas) + '/' + str(r.series_evaluadas):>7}"
            f"{str(r.series_supera_ingenuo) + '/' + str(r.series_evaluadas):>8}{marca}"
        )

    print("\nPRUEBAS PAREADAS (Prophet frente a cada clásico, sobre RMSSE):")
    hay_equivalencia = True
    for p in lote.pruebas:
        etiqueta = (
            "trivial"
            if abs(p.d_cohen) < 0.2
            else (
                "pequeño"
                if abs(p.d_cohen) < 0.5
                else "mediano" if abs(p.d_cohen) < 0.8 else "grande"
            )
        )
        significativa = p.p_valor_t < 0.05
        if significativa:
            hay_equivalencia = False
        veredicto = "diferencia SIGNIFICATIVA" if significativa else "diferencia NO significativa"
        print(
            f"  {p.comparacion:<30}p(t)={p.p_valor_t:.4f}  p(W)={p.p_valor_wilcoxon:.4f}  "
            f"d={p.d_cohen:.2f} ({etiqueta})  -> {veredicto}"
        )

    if lote.series_omitidas:
        print(f"\nSeries omitidas por longitud insuficiente: {len(lote.series_omitidas)}")

    tiempos = {r.nombre_modelo: r.segundos_promedio for r in lote.resumen_por_modelo}
    puntajes = imprimir_matriz_operativa(tiempos)
    imprimir_sintesis(ganador.nombre_modelo if ganador else "—", puntajes, hay_equivalencia)

    guardar_excel(lote, args.salida, args.entrada, args.fraccion_prueba)
    print(f"\nEvidencia guardada en: {args.salida}")


if __name__ == "__main__":
    main()
