#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""no_inferioridad.py — Prueba formal de no inferioridad del sistema.

POR QUE HACE FALTA. La ausencia de significacion en una prueba t no demuestra
que dos modelos sean equivalentes: solo indica que no se detecto diferencia.
Es la distincion entre «ausencia de evidencia» y «evidencia de ausencia». Para
afirmar que el sistema NO ES PEOR que un competidor por una cantidad que
importe, hace falta declarar de antemano cuanta diferencia se considera
irrelevante —el MARGEN, denotado delta— y comprobar que la diferencia real
queda por debajo de el.

QUE HACE. Para cada comparacion del sistema frente a un modelo clasico:

  1. Calcula la diferencia pareada serie por serie (sistema - clasico) sobre el
     RMSSE. Una diferencia negativa significa que el sistema erro menos.
  2. Construye el intervalo de confianza unilateral al 95 % para la media de
     esas diferencias, es decir su LIMITE SUPERIOR.
  3. Compara ese limite con el margen delta declarado.

REGLA DE DECISION. Si el limite superior del intervalo es menor que delta, se
concluye NO INFERIORIDAD: se ha demostrado, con 95 % de confianza, que el
sistema no es peor que el competidor por mas de delta. Si ademas el limite
inferior es mayor que -delta, se concluye EQUIVALENCIA en sentido estricto,
que es una version conservadora de la prueba TOST: el TOST estandar con alfa
0,05 se representa con un intervalo del 90 %, de modo que exigir el bilateral
del 95 % impone una condicion mas estricta. Se emplea la version conservadora
y se nombra explicitamente para no inducir a confusion.

SOBRE EL MARGEN. delta se expresa en unidades de RMSSE, que es una razon
respecto del error del metodo ingenuo de un paso. Un delta de 0,05 significa
«tolero que el sistema cometa hasta un 5 % mas de error que el competidor,
medido en unidades del error ingenuo». El valor debe justificarse ANTES de
ejecutar este programa y consignarse en la seccion 3.6 de la tesis; fijarlo
despues de ver el resultado invalidaria la prueba.

Uso:
    uv run python herramientas/no_inferioridad.py favorita_50_series.csv \
        --delta 0.05 --fraccion-prueba 0.20 --salida no_inferioridad.xlsx
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import pandas as pd
from scipy import stats

from entorno import imprimir_entorno
from herramientas.sensibilidad_origen import _construir_evaluador
from src.dominio import metricas
from src.infraestructura.persistencia.lector_archivos import LectorVentas


def intervalo_unilateral(diferencias: list[float], confianza: float = 0.95) -> tuple:
    """Media, error estandar y limites del intervalo de confianza bilateral."""
    n = len(diferencias)
    media = sum(diferencias) / n
    varianza = sum((d - media) ** 2 for d in diferencias) / (n - 1)
    error_estandar = math.sqrt(varianza / n)
    t_bilateral = stats.t.ppf(1 - (1 - confianza) / 2, df=n - 1)
    t_unilateral = stats.t.ppf(confianza, df=n - 1)
    return (
        media,
        error_estandar,
        media - t_bilateral * error_estandar,
        media + t_bilateral * error_estandar,
        media + t_unilateral * error_estandar,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("entrada", type=Path, help="CSV con las series preparadas")
    parser.add_argument(
        "--delta",
        type=float,
        required=True,
        help="Margen de no inferioridad en unidades de RMSSE. Debe estar "
        "justificado en la tesis ANTES de ejecutar este programa.",
    )
    parser.add_argument("--fraccion-prueba", type=float, default=0.20)
    parser.add_argument("--salida", type=Path, default=Path("no_inferioridad.xlsx"))
    args = parser.parse_args()

    delta = args.delta
    lector = LectorVentas()
    series = lector.construir_series_lote(lector.leer(args.entrada.read_bytes(), str(args.entrada)))
    print(f"Series cargadas: {len(series)}")
    print(f"Margen de no inferioridad declarado: delta = {delta:.4f} (unidades de RMSSE)\n")

    evaluador = _construir_evaluador()
    modelos = evaluador_modelos(evaluador)
    rmsse: dict[str, list[float]] = {}
    descartadas = 0
    for i, serie in enumerate(series, start=1):
        n_prueba = max(1, int(round(len(serie) * args.fraccion_prueba)))
        # Mismo criterio de elegibilidad que contraste_hipotesis.py: una serie
        # cuyo tramo de ajuste quede por debajo de 30 observaciones no permite
        # estimar ningun modelo estacional y se descarta antes de evaluar.
        if len(serie) < n_prueba + 30:
            descartadas += 1
            continue
        entrenamiento, prueba = serie.dividir(n_prueba)
        reales = prueba.valores()
        for modelo in modelos:
            try:
                modelo.entrenar(entrenamiento)
                pron = modelo.pronosticar(n_prueba)
                valor = metricas.rmsse(entrenamiento.valores(), reales, pron.valores)
                if not math.isfinite(valor):
                    raise ValueError("RMSSE no finito")
            except Exception:  # noqa: BLE001
                valor = float("nan")
            rmsse.setdefault(modelo.nombre, []).append(valor)
        print(f"  serie {i}/{len(series)} lista", end="\r", flush=True)
    print(" " * 40, end="\r")
    if descartadas:
        print(f"  Series descartadas por historia insuficiente: {descartadas}")

    sistema = next(iter(rmsse))
    filas = []
    for rival, valores in rmsse.items():
        if rival == sistema:
            continue
        pares = [
            (a, b) for a, b in zip(rmsse[sistema], valores) if math.isfinite(a) and math.isfinite(b)
        ]
        diferencias = [a - b for a, b in pares]
        media, ee, li, ls, ls_uni = intervalo_unilateral(diferencias)
        no_inferior = ls_uni < delta
        equivalente = ls < delta and li > -delta
        veredicto = (
            "EQUIVALENCIA (IC bilateral 95 %, mas estricto que TOST): "
            "el intervalo cae dentro de ±delta"
            if equivalente
            else (
                "NO INFERIORIDAD: el limite superior queda por debajo de delta"
                if no_inferior
                else "NO DEMOSTRADA: el limite superior supera delta"
            )
        )
        filas.append(
            {
                "Comparación": f"{sistema} vs {rival}",
                "Pares válidos": len(diferencias),
                "Diferencia media (RMSSE)": round(media, 5),
                "Error estándar": round(ee, 5),
                "IC 95 % inferior": round(li, 5),
                "IC 95 % superior": round(ls, 5),
                "Límite superior unilateral 95 %": round(ls_uni, 5),
                "Margen δ": delta,
                "¿No inferior?": "Sí" if no_inferior else "No",
                "¿Equivalente (IC 95 %)?": "Sí" if equivalente else "No",
                "Veredicto": veredicto,
            }
        )

    tabla = pd.DataFrame(filas)
    print("=" * 78)
    print(f"PRUEBA DE NO INFERIORIDAD — margen δ = {delta:.4f} en unidades de RMSSE")
    print("=" * 78)
    for _, f in tabla.iterrows():
        print(f"\n  {f['Comparación']}   ({f['Pares válidos']} pares)")
        print(f"    Diferencia media (sistema - rival) : {f['Diferencia media (RMSSE)']:+.5f}")
        print(
            f"    IC 95 % bilateral                  : "
            f"[{f['IC 95 % inferior']:+.5f}, {f['IC 95 % superior']:+.5f}]"
        )
        print(
            f"    Limite superior unilateral 95 %    : {f['Límite superior unilateral 95 %']:+.5f}"
        )
        print(f"    VEREDICTO                          : {f['Veredicto']}")

    with pd.ExcelWriter(args.salida) as writer:
        tabla.to_excel(writer, sheet_name="No inferioridad", index=False)
    print(f"\nEvidencia guardada en: {args.salida}")


def evaluador_modelos(evaluador):
    """Devuelve la lista de modelos del evaluador sin depender del nombre del campo."""
    for valor in vars(evaluador).values():
        if isinstance(valor, list) and valor and hasattr(valor[0], "nombre"):
            return valor
    raise RuntimeError("No se hallaron los modelos en el evaluador.")


if __name__ == "__main__":
    imprimir_entorno()
    main()
