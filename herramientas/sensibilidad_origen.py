#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sensibilidad_origen.py — Analisis de sensibilidad al origen de la particion.

Responde a la objecion clasica contra la particion de origen fijo: que la
conclusion podria depender de DONDE cae el corte entre ajuste y validacion.

El experimento principal (evaluar_modelos_cli.py) y el analisis de robustez
(robustez_experimento.py) varian la MUESTRA de series manteniendo el corte en
80/20. Esta herramienta hace lo contrario: mantiene la muestra y varia el corte,
de modo que ambos factores del diseno quedan sometidos a comprobacion.

Diseno por defecto: un factor a la vez (OFAT). Se evalua la misma muestra bajo
tres cortes —70/30, 80/20 y 90/10— y se comprueba si el ordenamiento de los
cinco modelos se mantiene.

Diseno factorial (opcional, con --semillas): cada corte se evalua sobre varias
muestras independientes, de modo que se cubre tambien la interaccion entre
ambos factores. Multiplica el costo por el numero de semillas.

Uso basico (los tres cortes sobre la muestra principal):
    uv run python herramientas/sensibilidad_origen.py favorita_50_series.csv \
        --salida sensibilidad_origen.xlsx

Uso factorial (tres cortes x diez muestras; corrida larga):
    uv run python herramientas/sensibilidad_origen.py favorita_pool.csv \
        --semillas 101 102 103 104 105 106 107 108 109 110 \
        --n-series 50 --salida sensibilidad_origen.xlsx
"""

from __future__ import annotations

import argparse
import contextlib
import io
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import pandas as pd

from entorno import imprimir_entorno
from src.aplicacion.casos_uso.evaluar_modelos import EvaluadorDeModelos
from src.aplicacion.parametros import ParametrosPronostico
from src.infraestructura.estadistica.adaptador_scipy import AdaptadorPruebasScipy
from src.infraestructura.modelos.adaptador_arima import AdaptadorARIMA
from src.infraestructura.modelos.adaptador_holt_winters import AdaptadorHoltWinters
from src.infraestructura.modelos.adaptador_media_movil import AdaptadorMediaMovil
from src.infraestructura.modelos.adaptador_prophet import AdaptadorProphet
from src.infraestructura.modelos.adaptador_regresion_lineal import AdaptadorRegresionLineal
from src.infraestructura.persistencia.lector_archivos import LectorVentas

CORTES_POR_DEFECTO = [0.30, 0.20, 0.10]


def _construir_evaluador() -> EvaluadorDeModelos:
    """Cableado IDENTICO al del experimento principal (evaluar_modelos_cli.py).

    Prophet recibe el calendario nacional de Ecuador, que es de donde procede el
    dataset Corporacion Favorita. Omitirlo desactivaria la capacidad nativa de
    manejo de feriados que el diseno del estudio declara como parte del
    tratamiento, y las corridas de estabilidad no serian comparables con la
    corrida principal.
    """
    modelos = [
        AdaptadorProphet(ParametrosPronostico(pais_feriados="EC")),
        AdaptadorARIMA(),
        AdaptadorHoltWinters(),
        AdaptadorMediaMovil(),
        AdaptadorRegresionLineal(),
    ]
    return EvaluadorDeModelos(modelos, AdaptadorPruebasScipy())


def etiqueta(fraccion: float) -> str:
    """0.20 -> '80/20'."""
    return f"{round((1 - fraccion) * 100):d}/{round(fraccion * 100):d}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("entrada", type=Path, help="CSV con las series (fecha, serie, ventas)")
    parser.add_argument(
        "--cortes",
        type=float,
        nargs="+",
        default=CORTES_POR_DEFECTO,
        help="Fracciones de validacion a comparar (default 0.30 0.20 0.10).",
    )
    parser.add_argument(
        "--semillas",
        type=int,
        nargs="*",
        default=[],
        help="Si se indican, cada corte se evalua sobre una muestra por semilla "
        "(diseno factorial). Sin semillas se usa el archivo completo (OFAT).",
    )
    parser.add_argument(
        "--n-series",
        type=int,
        default=50,
        help="Series por muestra cuando se usan semillas (default 50).",
    )
    parser.add_argument("--salida", type=Path, default=Path("sensibilidad_origen.xlsx"))
    args = parser.parse_args()

    lector = LectorVentas()
    tabla = lector.leer(args.entrada.read_bytes(), str(args.entrada))
    series = lector.construir_series_lote(tabla)
    print(f"Series cargadas: {len(series)}")

    if args.semillas and len(series) <= args.n_series:
        raise SystemExit(
            f"El archivo tiene {len(series)} series y --n-series es {args.n_series}. "
            f"Para el diseno factorial se necesita un pool mayor que la muestra."
        )

    configuraciones = [
        (corte, semilla) for corte in args.cortes for semilla in (args.semillas or [None])
    ]
    print(
        f"Configuraciones a evaluar: {len(configuraciones)} "
        f"({len(args.cortes)} cortes x {len(args.semillas) or 1} muestra(s))\n"
    )

    evaluador = _construir_evaluador()
    filas = []
    ganadores_por_corte: dict[str, list[str]] = {etiqueta(c): [] for c in args.cortes}

    for i, (corte, semilla) in enumerate(configuraciones, start=1):
        muestra = (
            random.Random(semilla).sample(series, args.n_series)
            if semilla is not None
            else series
        )
        marca = etiqueta(corte)
        sufijo = f", semilla={semilla}" if semilla is not None else ""
        print(f"[{i}/{len(configuraciones)}] corte {marca}{sufijo}… ", end="", flush=True)

        with contextlib.redirect_stdout(io.StringIO()):
            lote = evaluador.ejecutar_lote(muestra, fraccion_prueba=corte)

        ganador = lote.ganador
        ganadores_por_corte[marca].append(ganador.nombre_modelo)
        print(f"ganó {ganador.nombre_modelo} (RMSSE mediano {ganador.rmsse_mediana:.4f})")

        for r in lote.resumen_por_modelo:
            filas.append(
                {
                    "Corte": marca,
                    "Fracción de validación": corte,
                    "Semilla": semilla if semilla is not None else "muestra principal",
                    "Modelo": r.nombre_modelo,
                    "RMSSE mediano": round(r.rmsse_mediana, 4),
                    "WAPE mediano (%)": round(r.wape_mediana, 2),
                    "Victorias": r.series_ganadas,
                    "Supera ingenuo": r.series_supera_ingenuo,
                    "Series evaluadas": r.series_evaluadas,
                    "Ganó la configuración": (
                        "Sí" if r.nombre_modelo == ganador.nombre_modelo else "No"
                    ),
                }
            )

    # ---------------------------------------------------------------- resumen
    detalle = pd.DataFrame(filas)
    orden_por_corte = {}
    for marca in ganadores_por_corte:
        sub = detalle[detalle["Corte"] == marca].groupby("Modelo")["RMSSE mediano"].median()
        orden_por_corte[marca] = list(sub.sort_values().index)

    print("\n" + "=" * 72)
    print("SENSIBILIDAD AL ORIGEN DE LA PARTICIÓN")
    print("=" * 72)
    for marca, orden in orden_por_corte.items():
        print(f"  Corte {marca:>6}  ordenamiento: {' > '.join(orden)}")

    ordenes = list(orden_por_corte.values())
    estable_total = all(o == ordenes[0] for o in ordenes)
    lideres = {o[0] for o in ordenes}
    estable_lider = len(lideres) == 1

    print()
    if estable_total:
        veredicto = (
            "ESTABLE: el ordenamiento completo de los cinco modelos se mantiene "
            "en los tres cortes. La conclusión no depende del punto de partición."
        )
    elif estable_lider:
        veredicto = (
            f"ESTABLE EN EL LIDERAZGO: {lideres.pop()} encabeza en todos los cortes, "
            "aunque el orden de las posiciones siguientes varía. Consistente con la "
            "equivalencia estadística declarada."
        )
    else:
        veredicto = (
            "SENSIBLE AL ORIGEN: el modelo con menor RMSSE mediano cambia según el "
            "corte. Debe declararse como limitación y discutirse en el capítulo de "
            "resultados."
        )
    print(f"  Veredicto: {veredicto}")

    # Rango del RMSSE de cada modelo entre cortes: mide cuánto se mueve
    print("\n  Variación del RMSSE mediano entre cortes:")
    for modelo in sorted(detalle["Modelo"].unique()):
        vals = [
            detalle[(detalle["Corte"] == m) & (detalle["Modelo"] == modelo)][
                "RMSSE mediano"
            ].median()
            for m in orden_por_corte
        ]
        print(
            f"    {modelo:20s} [{min(vals):.4f}, {max(vals):.4f}]  "
            f"amplitud {max(vals) - min(vals):.4f}"
        )

    resumen = pd.DataFrame(
        [
            {
                "Corte": marca,
                "Ordenamiento (de menor a mayor RMSSE mediano)": " > ".join(orden),
                "Modelo líder": orden[0],
            }
            for marca, orden in orden_por_corte.items()
        ]
    )
    veredicto_df = pd.DataFrame([{"Veredicto": veredicto}])
    with pd.ExcelWriter(args.salida) as writer:
        resumen.to_excel(writer, sheet_name="Resumen", index=False)
        veredicto_df.to_excel(writer, sheet_name="Resumen", index=False, startrow=len(resumen) + 2)
        detalle.to_excel(writer, sheet_name="Detalle por configuración", index=False)
    print(f"\nEvidencia guardada en: {args.salida}")


if __name__ == "__main__":
    imprimir_entorno()
    main()