#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""experimento_factorial.py — Diseno factorial completo: muestra x corte.

Somete a comprobacion los DOS factores del diseno experimental a la vez y,
ademas, su interaccion:

  · Factor MUESTRA — que series componen la muestra evaluada.
  · Factor ORIGEN  — donde cae el corte entre ajuste y validacion.

Cada muestra se extrae DIRECTAMENTE del train.csv con su propia semilla, de modo
que tambien varia la seleccion de tiendas y productos: se elimina asi la
limitacion del muestreo en dos etapas, en el que el pool intermedio se generaba
una sola vez con una semilla fija.

DISENO. Se emplean N semillas y C cortes, y CADA muestra se evalua bajo TODOS
los cortes. Eso produce N x C configuraciones a partir de solo N lecturas del
dataset. Es importante no asignar una semilla distinta a cada combinacion: si
cada corte usara series distintas, los efectos de muestra y de origen quedarian
confundidos y no seria posible atribuir una diferencia a ninguno de los dos.

Uso (10 muestras x 3 cortes = 30 configuraciones, 10 lecturas del dataset):
    uv run python herramientas/experimento_factorial.py "RUTA/train.csv" \
        --semillas 101 102 103 104 105 106 107 108 109 110 \
        --salida factorial.xlsx

Las muestras preparadas se guardan como muestra_<semilla>.csv y se reutilizan si
ya existen, de modo que la corrida puede interrumpirse y reanudarse.

Alternativa sin preparar (para pruebas o si ya tiene las muestras):
    uv run python herramientas/experimento_factorial.py --muestras a.csv b.csv \
        --salida factorial.xlsx
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import pandas as pd

from entorno import imprimir_entorno
from herramientas.contraste_hipotesis import ajuste_holm
from herramientas.sensibilidad_origen import _construir_evaluador, etiqueta
from src.infraestructura.persistencia.lector_archivos import LectorVentas

CORTES_POR_DEFECTO = [0.30, 0.20, 0.10]


def preparar_muestra(
    train: Path, semilla: int, tiendas: int, productos: int, destino: Path
) -> Path:
    """Extrae una muestra del train.csv con la semilla indicada, si no existe ya."""
    if destino.is_file() and destino.stat().st_size > 0:
        print(f"  muestra ya preparada, se reutiliza: {destino.name}")
        return destino
    orden = [
        sys.executable,
        str(RAIZ / "herramientas" / "preparar_favorita.py"),
        str(train),
        "--modo", "series",
        "--tiendas", str(tiendas),
        "--productos-por-tienda", str(productos),
        "--semilla", str(semilla),
        "--min-promedio-diario", "30",
        "--max-prop-ceros", "0.15",
        "--salida", str(destino),
    ]

    # El proceso hijo escribe caracteres como «≥» y «×» en su informe de avance.
    # Cuando su salida va a una consola, Windows la maneja sin problema; cuando va
    # a una tubería —que es lo que ocurre al capturarla desde aquí— Python usa la
    # codificación regional (cp1252 en Windows en español) y esos caracteres la
    # hacen fallar. Forzar el modo UTF-8 en el hijo elimina esa dependencia del
    # idioma del sistema operativo.
    entorno_hijo = dict(os.environ)
    entorno_hijo["PYTHONUTF8"] = "1"
    entorno_hijo["PYTHONIOENCODING"] = "utf-8"

    registro = destino.with_suffix(".log")
    inicio = time.time()
    resultado = subprocess.run(
        orden,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=entorno_hijo,
    )
    registro.write_text(
        (resultado.stdout or "") + (resultado.stderr or ""), encoding="utf-8"
    )
    if resultado.returncode != 0:
        print(f"\n  FALLÓ. Últimas líneas (registro completo en {registro.name}):")
        for linea in (resultado.stdout or "").rstrip().splitlines()[-5:]:
            print("    " + linea)
        for linea in (resultado.stderr or "").rstrip().splitlines()[-12:]:
            print("    " + linea)
        raise SystemExit(f"Fallo al preparar la muestra de la semilla {semilla}.")
    if not destino.is_file() or destino.stat().st_size == 0:
        raise SystemExit(
            f"La muestra de la semilla {semilla} quedó vacía. Revise {registro.name}."
        )
    print(
        f"  muestra preparada en {time.time() - inicio:.0f} s: {destino.name} "
        f"(registro en {registro.name})"
    )
    return destino


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "train", type=Path, nargs="?", help="Ruta al train.csv de Kaggle (omitir si usa --muestras)"
    )
    parser.add_argument(
        "--muestras",
        type=Path,
        nargs="*",
        default=[],
        help="CSV de muestras ya preparadas; omite la extraccion desde el dataset.",
    )
    parser.add_argument("--semillas", type=int, nargs="+", default=list(range(101, 111)))
    parser.add_argument("--cortes", type=float, nargs="+", default=CORTES_POR_DEFECTO)
    parser.add_argument("--tiendas", type=int, default=10)
    parser.add_argument("--productos-por-tienda", type=int, default=5)
    parser.add_argument("--salida", type=Path, default=Path("factorial.xlsx"))
    args = parser.parse_args()

    if not args.muestras and args.train is None:
        raise SystemExit("Indique la ruta al train.csv o una lista con --muestras.")

    # ------------------------------------------------- 1) preparar las muestras
    if args.muestras:
        muestras = [(f"archivo:{p.stem}", p) for p in args.muestras]
        print(f"Se usaran {len(muestras)} muestras ya preparadas.\n")
    else:
        print(f"Preparando {len(args.semillas)} muestras desde {args.train.name}…")
        muestras = []
        for semilla in args.semillas:
            destino = Path(f"muestra_{semilla}.csv")
            preparar_muestra(
                args.train, semilla, args.tiendas, args.productos_por_tienda, destino
            )
            muestras.append((str(semilla), destino))
        print()

    # ------------------------------------------------- 2) evaluar cada celda
    lector = LectorVentas()
    evaluador = _construir_evaluador()
    total = len(muestras) * len(args.cortes)
    filas = []
    contrastes = []
    n = 0
    inicio_global = time.time()

    for clave, ruta in muestras:
        series = lector.construir_series_lote(lector.leer(ruta.read_bytes(), str(ruta)))
        for corte in args.cortes:
            n += 1
            marca = etiqueta(corte)
            print(f"[{n}/{total}] muestra {clave}, corte {marca}… ", end="", flush=True)
            t0 = time.time()
            with contextlib.redirect_stdout(io.StringIO()):
                lote = evaluador.ejecutar_lote(series, fraccion_prueba=corte)
            ganador = lote.ganador

            # Contraste pareado de Prophet frente a cada clásico, con la regla
            # declarada a priori: equivalencia = ausencia de significación tras
            # Holm Y tamaño de efecto despreciable (|d| < 0,20).
            pruebas = list(lote.pruebas)
            p_ajustados = ajuste_holm([pr.p_valor_t for pr in pruebas]) if pruebas else []
            for pr, p_aj in zip(pruebas, p_ajustados):
                equivalente = p_aj >= 0.05 and abs(pr.d_cohen) < 0.20
                contrastes.append(
                    {
                        "Muestra": clave,
                        "Corte": marca,
                        "Comparación": pr.comparacion,
                        "p (t pareada)": round(pr.p_valor_t, 4),
                        "p (Wilcoxon)": round(pr.p_valor_wilcoxon, 4),
                        "p ajustado (Holm)": round(p_aj, 4),
                        "d de Cohen": round(pr.d_cohen, 4),
                        "n": pr.n,
                        "¿Equivalente?": "Sí" if equivalente else "No",
                        "Motivo si no": (
                            ""
                            if equivalente
                            else ("significativo tras Holm" if p_aj < 0.05 else "")
                            + ("; " if p_aj < 0.05 and abs(pr.d_cohen) >= 0.20 else "")
                            + ("efecto no despreciable" if abs(pr.d_cohen) >= 0.20 else "")
                        ),
                    }
                )
            print(
                f"ganó {ganador.nombre_modelo} "
                f"(RMSSE {ganador.rmsse_mediana:.4f}, {time.time() - t0:.0f} s)"
            )
            for r in lote.resumen_por_modelo:
                filas.append(
                    {
                        "Muestra": clave,
                        "Corte": marca,
                        "Modelo": r.nombre_modelo,
                        "RMSSE mediano": round(r.rmsse_mediana, 4),
                        "WAPE mediano (%)": round(r.wape_mediana, 2),
                        "Victorias": r.series_ganadas,
                        "Supera ingenuo": r.series_supera_ingenuo,
                        "Series": r.series_evaluadas,
                        "Ganó la celda": (
                            "Sí" if r.nombre_modelo == ganador.nombre_modelo else "No"
                        ),
                    }
                )

    detalle = pd.DataFrame(filas)
    ganadoras = detalle[detalle["Ganó la celda"] == "Sí"]
    tabla_contrastes = pd.DataFrame(contrastes)

    # ------------------------------------------------- 3) lectura de resultados
    print("\n" + "=" * 74)
    print(f"DISEÑO FACTORIAL — {len(muestras)} muestras × {len(args.cortes)} cortes")
    print("=" * 74)

    conteo = ganadoras["Modelo"].value_counts()
    print("\n  Celdas ganadas, en total:")
    for modelo, veces in conteo.items():
        print(f"    {modelo:20s} {veces:2d} de {total}")

    print("\n  Celdas ganadas, por corte (efecto del ORIGEN):")
    tabla_corte = pd.crosstab(ganadoras["Corte"], ganadoras["Modelo"])
    print(tabla_corte.to_string().replace("\n", "\n    "))

    print("\n  Celdas ganadas, por muestra (efecto de la MUESTRA):")
    tabla_muestra = pd.crosstab(ganadoras["Muestra"], ganadoras["Modelo"])
    print(tabla_muestra.to_string().replace("\n", "\n    "))

    lider_global = conteo.index[0]
    lideres_por_corte = {
        c: tabla_corte.loc[c].idxmax() for c in tabla_corte.index
    }
    estable = len(set(lideres_por_corte.values())) == 1 and conteo.iloc[0] == total

    print()
    if estable:
        veredicto = (
            f"ESTABLE EN TODA LA REJILLA: {lider_global} encabeza en las {total} "
            "configuraciones. La conclusión no depende ni de la muestra ni del origen."
        )
    elif len(set(lideres_por_corte.values())) == 1:
        veredicto = (
            f"ESTABLE EN EL LIDERAZGO POR CORTE: {lider_global} encabeza en los "
            f"{len(args.cortes)} cortes, aunque no gana todas las celdas "
            f"({conteo.iloc[0]} de {total}). Consistente con la equivalencia estadística."
        )
    else:
        veredicto = (
            "SENSIBLE: el modelo líder cambia según el corte "
            f"({lideres_por_corte}). Debe declararse y discutirse."
        )
    print(f"  Veredicto sobre el liderazgo: {veredicto}")

    # ------------------------------------------------- 4) equivalencia pareada
    if not tabla_contrastes.empty:
        print("\n" + "=" * 74)
        print("CONTRASTE DE LAS HIPÓTESIS HE2 A HE5 EN CADA CONFIGURACIÓN")
        print("=" * 74)
        print("  Regla a priori: equivalencia = p ajustado por Holm ≥ 0,05 Y |d| < 0,20\n")
        resumen_eq = (
            tabla_contrastes.groupby("Comparación")["¿Equivalente?"]
            .apply(lambda c: (c == "Sí").sum())
            .sort_values(ascending=False)
        )
        for comparacion, veces in resumen_eq.items():
            sub = tabla_contrastes[tabla_contrastes["Comparación"] == comparacion]
            d_med = sub["d de Cohen"].median()
            print(
                f"    {comparacion:34s} equivalente en {veces:2d} de {total} "
                f"configuraciones  |  d mediano {d_med:+.3f}"
            )
        eq_total = (tabla_contrastes["¿Equivalente?"] == "Sí").sum()
        print(
            f"\n    Total: {eq_total} de {len(tabla_contrastes)} contrastes "
            f"({eq_total / len(tabla_contrastes):.0%}) cumplen la regla de equivalencia."
        )
    print(f"\n  Tiempo total: {(time.time() - inicio_global) / 60:.1f} minutos")

    resumen = pd.DataFrame(
        [{"Modelo": m, "Celdas ganadas": int(v), "De": total} for m, v in conteo.items()]
    )
    with pd.ExcelWriter(args.salida) as writer:
        resumen.to_excel(writer, sheet_name="Resumen", index=False)
        pd.DataFrame([{"Veredicto": veredicto}]).to_excel(
            writer, sheet_name="Resumen", index=False, startrow=len(resumen) + 2
        )
        tabla_corte.to_excel(writer, sheet_name="Por corte")
        tabla_muestra.to_excel(writer, sheet_name="Por muestra")
        detalle.to_excel(writer, sheet_name="Detalle por celda", index=False)
        if not tabla_contrastes.empty:
            resumen_eq_df = (
                tabla_contrastes.groupby("Comparación")
                .agg(
                    equivalente_en=("¿Equivalente?", lambda c: (c == "Sí").sum()),
                    de=("¿Equivalente?", "size"),
                    d_mediano=("d de Cohen", "median"),
                    p_holm_mediano=("p ajustado (Holm)", "median"),
                )
                .reset_index()
            )
            resumen_eq_df.to_excel(writer, sheet_name="Equivalencia HE2-HE5", index=False)
            tabla_contrastes.to_excel(
                writer, sheet_name="Contrastes por celda", index=False
            )
    print(f"\nEvidencia guardada en: {args.salida}")


if __name__ == "__main__":
    imprimir_entorno()
    main()