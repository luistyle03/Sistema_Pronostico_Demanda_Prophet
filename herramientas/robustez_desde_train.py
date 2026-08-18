"""
robustez_desde_train.py
Prueba de ROBUSTEZ sacando varias muestras directamente del train.csv crudo de
Favorita (no de un pozo pequeño). Para cada semilla que usted indique por línea
de comandos, selecciona una muestra estratificada de N tiendas x M productos
(= la muestra), corre los 5 modelos en cada serie y reporta quién gana en cada
muestra y en el agregado. Guarda un detalle en robustez.xlsx.

CÓMO FUNCIONA (reutiliza sus herramientas ya probadas)
- Para cada semilla, llama a preparar_favorita.py (su limpiador) para construir
  la muestra desde el train.csv con los mismos filtros de inclusión.
- Evalúa cada serie con los modelos de evaluar_modelos_cli.py (Prophet con
  feriados de Ecuador). Usa las FECHAS REALES para que los feriados calcen.

REQUISITOS
- En la misma carpeta: preparar_favorita.py y evaluar_modelos_cli.py
- pip install pandas numpy statsmodels scikit-learn scipy prophet xlsxwriter
- Prophet DEBE estar instalado; si no, ese modelo aparecerá como fallido.

USO
    python robustez_desde_train.py train.csv --semillas 11 22 33 44 55 66 77 88 99 100
    # con parámetros explícitos:
    python robustez_desde_train.py train.csv --semillas 11 22 33 \\
        --tiendas 10 --productos-por-tienda 5 \\
        --min-promedio-diario 30 --max-prop-ceros 0.15 --salida robustez.xlsx

NOTA: cada semilla vuelve a leer el train.csv (~5 GB), así que con 10 semillas
puede tardar bastante; conviene dejarlo corriendo. Si necesita acelerarlo,
avíseme y lo cambiamos a una sola lectura.
"""

from __future__ import annotations

import argparse
import math
import os
import statistics
import subprocess
import sys
import tempfile
import warnings

import pandas as pd

warnings.simplefilter("ignore")

from evaluar_modelos_cli import MODELOS, evaluar_serie


def correr_preparador(
    preparador,
    train,
    semilla,
    tiendas,
    productos,
    min_prom,
    max_ceros,
    min_dias,
    salida,
):
    cmd = [
        sys.executable,
        preparador,
        train,
        "--modo",
        "series",
        "--tiendas",
        str(tiendas),
        "--productos-por-tienda",
        str(productos),
        "--semilla",
        str(semilla),
        "--min-promedio-diario",
        str(min_prom),
        "--max-prop-ceros",
        str(max_ceros),
        "--min-dias-con-venta",
        str(min_dias),
        "--salida",
        salida,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-800:])
        print(r.stderr[-800:])
        raise RuntimeError(f"preparar_favorita.py falló para la semilla {semilla}")


def cargar_muestra(ruta):
    """Devuelve {serie: (valores, fechas_reales)} a partir del CSV preparado."""
    df = pd.read_csv(ruta)
    cols = {c.lower(): c for c in df.columns}
    col_f = cols.get("fecha") or next(c for c in df.columns if "fecha" in c.lower())
    col_s = cols.get("serie") or next(c for c in df.columns if "serie" in c.lower())
    col_v = cols.get("ventas") or next(c for c in df.columns if "venta" in c.lower())
    df[col_f] = pd.to_datetime(df[col_f], dayfirst=True, errors="coerce")
    series = {}
    for nom, g in df.groupby(col_s):
        g = g.sort_values(col_f)
        series[nom] = (g[col_v].to_numpy(float), pd.DatetimeIndex(g[col_f]))
    return series


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("train", help="Ruta del train.csv crudo de Favorita")
    ap.add_argument(
        "--semillas",
        type=int,
        nargs="+",
        required=True,
        help="Lista de semillas (una muestra por semilla).",
    )
    ap.add_argument("--tiendas", type=int, default=10)
    ap.add_argument("--productos-por-tienda", type=int, default=5)
    ap.add_argument("--min-promedio-diario", type=float, default=30.0)
    ap.add_argument("--max-prop-ceros", type=float, default=0.15)
    ap.add_argument("--min-dias-con-venta", type=int, default=60)
    ap.add_argument("--fraccion-prueba", type=float, default=0.20)
    ap.add_argument(
        "--preparador",
        default="preparar_favorita.py",
        help="Ruta a preparar_favorita.py (default: misma carpeta).",
    )
    ap.add_argument("--salida", default="robustez.xlsx")
    args = ap.parse_args()

    if not os.path.exists(args.preparador):
        sys.exit(f"No encuentro {args.preparador}. Use --preparador con la ruta correcta.")

    detalle = []  # filas para la hoja Detalle
    med_por_muestra = {m: [] for m in MODELOS}  # mediana RMSSE por muestra
    victorias = {m: 0 for m in MODELOS}
    posiciones = {m: [] for m in MODELOS}  # ranking por muestra
    ganadores = []  # ganador de cada muestra

    n = len(args.semillas)
    print(
        f"Robustez desde train.csv: {n} muestras de "
        f"{args.tiendas}x{args.productos_por_tienda} series.\n"
    )
    for k, semilla in enumerate(args.semillas, 1):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            ruta = tmp.name
        try:
            print(f"[Muestra {k}/{n}] semilla {semilla}: preparando desde train.csv...")
            correr_preparador(
                args.preparador,
                args.train,
                semilla,
                args.tiendas,
                args.productos_por_tienda,
                args.min_promedio_diario,
                args.max_prop_ceros,
                args.min_dias_con_venta,
                ruta,
            )
            series = cargar_muestra(ruta)
        finally:
            if os.path.exists(ruta):
                os.unlink(ruta)

        print(f"            {len(series)} series; evaluando los 5 modelos...")
        rmsse_m = {m: [] for m in MODELOS}
        for nom, (val, fechas) in series.items():
            res = evaluar_serie(val, fechas, args.fraccion_prueba)
            for m, r in res.items():
                if math.isfinite(r["rmsse"]):
                    rmsse_m[m].append(r["rmsse"])
                    detalle.append(
                        {
                            "Muestra": k,
                            "Semilla": semilla,
                            "Serie": nom,
                            "Modelo": m,
                            "RMSSE": round(r["rmsse"], 4),
                            "WAPE_%": round(r.get("wape", float("nan")), 2),
                            "MAE": round(r.get("mae", float("nan")), 3),
                            "Sesgo": round(r.get("sesgo", float("nan")), 3),
                        }
                    )
        med = {m: statistics.median(rmsse_m[m]) for m in MODELOS if rmsse_m[m]}
        if not med:
            print("            (ningún modelo produjo resultados válidos en esta muestra)")
            continue
        orden = sorted(med, key=med.get)
        for pos, m in enumerate(orden, 1):
            posiciones[m].append(pos)
            med_por_muestra[m].append(med[m])
        victorias[orden[0]] += 1
        ganadores.append((k, semilla, orden[0], med[orden[0]]))
        print(f"            ganador: {orden[0]} (RMSSE mediano {med[orden[0]]:.3f})")

    # --- Resumen agregado ---------------------------------------------------
    resumen = []
    for m in MODELOS:
        if med_por_muestra[m]:
            resumen.append(
                {
                    "Modelo": m,
                    "RMSSE_med_promedio": round(
                        sum(med_por_muestra[m]) / len(med_por_muestra[m]), 4
                    ),
                    "Muestras_ganadas": victorias[m],
                    "Posicion_promedio": round(sum(posiciones[m]) / len(posiciones[m]), 2),
                }
            )
    resumen.sort(key=lambda d: d["RMSSE_med_promedio"])
    for i, d in enumerate(resumen, 1):
        d["Ranking"] = i

    print("\n" + "=" * 80)
    print(f"RESUMEN DE ROBUSTEZ — {n} muestras tomadas del train.csv (menor RMSSE = mejor)")
    print("=" * 80)
    print(
        f"{'Pos':4s}{'Modelo':18s}{'RMSSE med prom':>16s}"
        f"{'Muestras ganadas':>18s}{'Pos. prom':>11s}"
    )
    for d in resumen:
        marca = "  <-- 1.º" if d["Ranking"] == 1 else ""
        print(
            f"{d['Ranking']:<4d}{d['Modelo']:18s}{d['RMSSE_med_promedio']:>16.3f}"
            f"{(str(d['Muestras_ganadas']) + '/' + str(n)):>18s}"
            f"{d['Posicion_promedio']:>11.2f}{marca}"
        )
    pos_prophet = next((d["Ranking"] for d in resumen if d["Modelo"] == "Prophet"), None)
    if pos_prophet:
        print(f"\nProphet quedó en la posición {pos_prophet} de {len(resumen)}.")
    print("\nInterpretación: si las posiciones se mantienen parecidas entre muestras y las")
    print("diferencias de RMSSE son pequeñas, se confirma la EQUIVALENCIA (el empate no fue")
    print("suerte). Si Prophet sube consistentemente al 1.º, sería un hallazgo a favor de Prophet.")

    # --- Guardar robustez.xlsx ---------------------------------------------
    with pd.ExcelWriter(args.salida, engine="xlsxwriter") as wr:
        pd.DataFrame(resumen).to_excel(wr, sheet_name="Resumen", index=False)
        pd.DataFrame(
            [
                {"Muestra": k, "Semilla": s, "Ganador": g, "RMSSE_mediano": round(r, 4)}
                for k, s, g, r in ganadores
            ]
        ).to_excel(wr, sheet_name="Ganador_por_muestra", index=False)
        pd.DataFrame(detalle).to_excel(wr, sheet_name="Detalle", index=False)
    print(f"\nDetalle guardado en: {args.salida}")


if __name__ == "__main__":
    main()
