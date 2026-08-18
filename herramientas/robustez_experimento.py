"""
HERRAMIENTA — Análisis de robustez del experimento (multi-semilla).

Repite el experimento del Módulo 1 sobre VARIAS muestras aleatorias distintas
de productos. Demuestra que el resultado NO depende de una selección afortunada:
si Prophet gana en todas (o casi todas) las muestras, es evidencia de robustez
metodológica — mucho más fuerte que una sola corrida.

El ganador de cada muestra se CALCULA y se reporta tal cual (no está predefinido);
si en alguna muestra ganara otro modelo, el reporte lo dirá honestamente.

Uso:
    python herramientas/robustez_experimento.py favorita_pool.csv \
        --n-series 50 --semillas 101 102 103 104 105 106 107 108 109 110 \
        --salida robustez.xlsx

`favorita_pool.csv` debe ser un CSV (columnas: fecha, serie, ventas) con un POOL
de productos MAYOR que --n-series. Prepárelo con un pool amplio, por ejemplo:
    python herramientas/preparar_favorita.py train.csv --modo series \
        --tiendas 30 --productos-por-tienda 6 \
        --min-promedio-diario 30 --max-prop-ceros 0.15 \
        --salida favorita_pool.csv         (≈180 productos en el pool)

ADVERTENCIA DE TIEMPO: cada muestra corre los 5 modelos (la rejilla de ARIMA es
lo costoso). 50 productos × 10 semillas pueden tardar varias horas. Reduzca --n-series
o el número de semillas si necesita una corrida más rápida.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import random
import statistics
import sys
from pathlib import Path

import pandas as pd

# Permite importar el paquete `src` aunque el script se ejecute directamente
# (añade la raíz del proyecto, la carpeta que contiene src/, al path de Python).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "pool", type=Path, help="CSV con el pool de productos (fecha, serie, ventas)"
    )
    parser.add_argument(
        "--n-series",
        type=int,
        default=50,
        help="Productos por muestra (default 30). Debe ser menor que el pool.",
    )
    parser.add_argument(
        "--semillas",
        type=int,
        nargs="+",
        default=[101, 102, 103, 104, 105, 106, 107, 108, 109, 110],
        help="Lista de semillas; una muestra aleatoria por semilla.",
    )
    parser.add_argument(
        "--fraccion-prueba",
        type=float,
        default=0.20,
        help="Porción final de holdout (default 0.20).",
    )
    parser.add_argument("--salida", type=Path, default=Path("robustez.xlsx"))
    args = parser.parse_args()

    # --- Cargar el pool de productos reutilizando el lector del proyecto -----
    lector = LectorVentas()
    contenido = args.pool.read_bytes()
    tabla = lector.leer(contenido, str(args.pool))
    pool = lector.construir_series_lote(tabla)
    if len(pool) <= args.n_series:
        raise SystemExit(
            f"El pool tiene {len(pool)} productos pero --n-series es {args.n_series}. "
            f"Prepare un pool MÁS GRANDE (p. ej. --tiendas 30 --productos-por-tienda 6) "
            f"o reduzca --n-series."
        )
    print(
        f"Pool cargado: {len(pool)} productos. "
        f"Se evaluarán {args.n_series} por muestra, en {len(args.semillas)} muestras.\n"
    )

    evaluador = _construir_evaluador()
    filas_detalle = []  # una fila por (semilla, modelo)
    ganadores = []  # ganador de cada muestra
    prophet_medianas = []  # RMSSE mediano de Prophet en cada muestra
    prophet_winrate = []  # victorias de Prophet en cada muestra

    # --- Una muestra aleatoria por semilla ----------------------------------
    for i, semilla in enumerate(args.semillas, start=1):
        muestra = random.Random(semilla).sample(pool, args.n_series)
        print(
            f"[Muestra {i}/{len(args.semillas)}] semilla={semilla} "
            f"({args.n_series} productos)… ",
            end="",
            flush=True,
        )

        # Se silencia el progreso interno del lote; mostramos solo el resumen.
        with contextlib.redirect_stdout(io.StringIO()):
            lote = evaluador.ejecutar_lote(muestra, fraccion_prueba=args.fraccion_prueba)

        ganador = lote.ganador
        ganadores.append(ganador.nombre_modelo)
        print(f"ganó {ganador.nombre_modelo} " f"(RMSSE mediano {ganador.rmsse_mediana:.3f})")

        for r in lote.resumen_por_modelo:
            filas_detalle.append(
                {
                    "Semilla": semilla,
                    "Modelo": r.nombre_modelo,
                    "RMSSE mediano": round(r.rmsse_mediana, 4),
                    "RMSSE promedio": round(r.rmsse_promedio, 4),
                    "WAPE mediano (%)": round(r.wape_mediana, 2),
                    "Victorias": r.series_ganadas,
                    "Supera ingenuo": r.series_supera_ingenuo,
                    "Productos": r.series_evaluadas,
                    "Ganó la muestra": ("Sí" if r.nombre_modelo == ganador.nombre_modelo else "No"),
                }
            )
            if r.nombre_modelo == "Prophet":
                prophet_medianas.append(r.rmsse_mediana)
                prophet_winrate.append(r.series_ganadas)

    # --- Resumen de robustez -------------------------------------------------
    n = len(args.semillas)
    veces_prophet = ganadores.count("Prophet")
    print("\n" + "=" * 64)
    print("RESUMEN DE ROBUSTEZ")
    print("=" * 64)
    conteo = {m: ganadores.count(m) for m in sorted(set(ganadores))}
    for modelo, veces in sorted(conteo.items(), key=lambda x: -x[1]):
        print(f"  {modelo:18s} ganó en {veces} de {n} muestras")
    if prophet_medianas:
        print(
            f"\n  Prophet — RMSSE mediano: rango [{min(prophet_medianas):.3f}, "
            f"{max(prophet_medianas):.3f}], promedio {statistics.mean(prophet_medianas):.3f}"
        )
        print(
            f"  Prophet — victorias por muestra: rango [{min(prophet_winrate)}, "
            f"{max(prophet_winrate)}] de {args.n_series}"
        )
    veredicto = (
        "ROBUSTO: Prophet ganó en TODAS las muestras."
        if veces_prophet == n
        else f"Prophet ganó en {veces_prophet} de {n} muestras "
        f"(revise el detalle para las demás)."
    )
    print(f"\n  Veredicto: {veredicto}")

    # --- Guardar evidencia para los anexos ----------------------------------
    detalle = pd.DataFrame(filas_detalle)
    resumen = pd.DataFrame(
        [{"Modelo": m, "Muestras ganadas": v, "De": n} for m, v in conteo.items()]
    ).sort_values("Muestras ganadas", ascending=False)
    with pd.ExcelWriter(args.salida) as writer:
        resumen.to_excel(writer, sheet_name="Resumen", index=False)
        detalle.to_excel(writer, sheet_name="Detalle por muestra", index=False)
    print(f"\nEvidencia guardada en: {args.salida}")


if __name__ == "__main__":
    main()
