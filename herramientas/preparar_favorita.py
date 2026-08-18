"""
HERRAMIENTA — Preparar el dataset Corporación Favorita para el Módulo 1.

El train.csv de Kaggle (competencia "Corporación Favorita Grocery Sales
Forecasting") pesa ~5 GB: no se puede abrir en Excel ni cargar entero en
memoria. Este script lo procesa por TROZOS (chunks) y produce un CSV liviano
listo para subir al Módulo 1.

Modo 'series' (el de la tesis: 50 series = 10 tiendas × 5 productos):
    python herramientas/preparar_favorita.py train.csv --modo series ^
        --tiendas 10 --productos-por-tienda 5 --semilla 42 ^
        --min-promedio-diario 30 --max-prop-ceros 0.15 ^
        --salida favorita_50_series.csv

Modo 'total' (una sola serie agregada, para demostraciones rápidas):
    python herramientas/preparar_favorita.py train.csv --modo total ^
        --salida favorita_total.csv

Columnas del train.csv original: id, date, store_nbr, item_nbr, unit_sales,
onpromotion. Rango: 2013-01-01 a 2017-08-15.

IMPORTANTE — CRITERIO DE INCLUSIÓN (léase el documento de diagnóstico):
La métrica MAPE se vuelve inestable y enorme en series de demanda BAJA o
INTERMITENTE (productos que venden 2-6 unidades/día con muchos días en cero).
Ese es un problema de medición conocido (Croston; Syntetos & Boylan), NO un
defecto de los modelos. Para que la comparación sea informativa, este script
selecciona series de demanda REGULAR mediante dos filtros explícitos y
documentables:
  --min-promedio-diario : unidades/día promedio mínimas (sobre el calendario
                          completo). Filtra productos de bajo volumen.
  --max-prop-ceros      : proporción máxima de días sin venta. Filtra la
                          intermitencia.
Estos umbrales DEBEN reportarse en la metodología de la tesis como el criterio
que define la población de estudio (SKU de demanda regular en retail MIPYME).
"""

from __future__ import annotations

import argparse
import random
from collections import defaultdict
from pathlib import Path

import pandas as pd

# Rango calendario completo del dataset (documentado por Kaggle).
FECHA_INICIO = "2013-01-01"
FECHA_FIN = "2017-08-15"
TROZO = 1_000_000  # Filas por trozo: ~1 millón cabe holgado en memoria.

# Número de días del calendario completo (para promedios y proporción de ceros).
N_DIAS_CALENDARIO = len(pd.date_range(FECHA_INICIO, FECHA_FIN, freq="D"))

# Umbral de historia: el producto debe tener registro en al menos este número
# de días (asegura una serie larga y presente casi todo el período).
MINIMO_DIAS_CON_VENTA = 1200


def _trozos(ruta: Path, columnas: list[str]):
    """Itera el CSV gigante por trozos, leyendo solo las columnas necesarias."""
    return pd.read_csv(
        ruta,
        usecols=columnas,
        parse_dates=["date"],
        chunksize=TROZO,
    )


# --------------------------------------------------------------------- #
# Modo TOTAL: una sola serie con la venta diaria de toda la cadena      #
# --------------------------------------------------------------------- #
def preparar_total(entrada: Path, salida: Path) -> None:
    print("Pasada única: sumando unit_sales por fecha…")
    acumulado: dict = defaultdict(float)
    for i, trozo in enumerate(_trozos(entrada, ["date", "unit_sales"]), start=1):
        # Devoluciones (negativos) se tratan como 0, igual que en el sistema.
        trozo.loc[trozo["unit_sales"] < 0, "unit_sales"] = 0.0
        for fecha, valor in trozo.groupby("date")["unit_sales"].sum().items():
            acumulado[fecha] += float(valor)
        print(f"  trozo {i} procesado ({i * TROZO:,} filas aprox.)", flush=True)
    serie = pd.Series(acumulado).sort_index()
    calendario = pd.date_range(FECHA_INICIO, FECHA_FIN, freq="D")
    serie = serie.reindex(calendario, fill_value=0.0)
    tabla = pd.DataFrame({"fecha": serie.index.strftime("%d/%m/%Y"), "ventas": serie.values})
    tabla.to_csv(salida, index=False)
    print(f"Listo: {salida} ({len(tabla)} filas).")


# --------------------------------------------------------------------- #
# Modo TIENDAS: una serie por tienda = venta diaria TOTAL de la tienda  #
# --------------------------------------------------------------------- #
def preparar_por_tienda(entrada: Path, salida: Path, n_tiendas: int, semilla: int) -> None:
    """
    Agrega la venta de TODOS los productos de cada tienda en un total diario.
    El resultado son series SUAVES y de alto volumen (los picos de promoción de
    un producto se diluyen entre cientos de productos), donde el MAPE es estable
    y bajo. Es la unidad de análisis típica para pronosticar la demanda de un
    negocio completo (encaja con el enfoque MIPYME de la tesis).
    """
    print("Pasada única: sumando la venta diaria total de cada tienda…")
    por_tienda_fecha: dict = defaultdict(float)  # (tienda, fecha) -> unidades
    for i, trozo in enumerate(_trozos(entrada, ["date", "store_nbr", "unit_sales"]), start=1):
        trozo.loc[trozo["unit_sales"] < 0, "unit_sales"] = 0.0
        agr = trozo.groupby(["store_nbr", "date"])["unit_sales"].sum()
        for (tienda, fecha), valor in agr.items():
            por_tienda_fecha[(int(tienda), fecha)] += float(valor)
        print(f"  trozo {i} procesado", flush=True)

    tiendas = sorted({clave[0] for clave in por_tienda_fecha})
    # Opcionalmente, muestrear n_tiendas de las disponibles (con semilla fija).
    if 0 < n_tiendas < len(tiendas):
        tiendas = sorted(random.Random(semilla).sample(tiendas, n_tiendas))
    print(f"Tiendas en el resultado: {len(tiendas)}.")

    calendario = pd.date_range(FECHA_INICIO, FECHA_FIN, freq="D")
    filas = []
    promedios = []
    for tienda in tiendas:
        serie_dict = {f: v for (t, f), v in por_tienda_fecha.items() if t == tienda}
        serie = pd.Series(serie_dict).sort_index().reindex(calendario, fill_value=0.0)
        nombre = f"Tienda {tienda}"
        filas.append(
            pd.DataFrame(
                {
                    "fecha": serie.index.strftime("%d/%m/%Y"),
                    "serie": nombre,
                    "ventas": serie.values,
                }
            )
        )
        promedios.append(serie.mean())
    tabla = pd.concat(filas, ignore_index=True)
    tabla.to_csv(salida, index=False)
    print(
        f"\nListo: {salida} ({len(tabla):,} filas = "
        f"{len(tiendas)} tiendas × {len(calendario)} días)."
    )
    print(
        f"Venta diaria promedio por tienda: mínimo {min(promedios):,.0f}, "
        f"mediana {sorted(promedios)[len(promedios)//2]:,.0f}, "
        f"máximo {max(promedios):,.0f} unidades."
    )
    print("(Series agregadas = suaves y de alto volumen → MAPE bajo y estable.)")


# --------------------------------------------------------------------- #
# Modo SERIES: muestreo estratificado de series de demanda REGULAR      #
# --------------------------------------------------------------------- #
def preparar_series(
    entrada: Path,
    salida: Path,
    n_tiendas: int,
    n_productos: int,
    semilla: int,
    min_promedio_diario: float,
    max_prop_ceros: float,
    min_dias_con_venta: int,
) -> None:
    # ---- PASADA 1: por (tienda, producto) acumular días-con-venta y volumen --
    print("Pasada 1/2: midiendo historia, volumen e intermitencia por serie…")
    dias: dict = defaultdict(int)  # nº de días con registro de venta
    volumen: dict = defaultdict(float)  # suma de unit_sales (negativos→0)
    for i, trozo in enumerate(
        _trozos(entrada, ["date", "store_nbr", "item_nbr", "unit_sales"]), start=1
    ):
        trozo.loc[trozo["unit_sales"] < 0, "unit_sales"] = 0.0
        agr = trozo.groupby(["store_nbr", "item_nbr"])["unit_sales"].agg(["size", "sum"])
        for clave, fila in agr.iterrows():
            dias[clave] += int(fila["size"])
            volumen[clave] += float(fila["sum"])
        print(f"  trozo {i} procesado", flush=True)

    # ---- Filtro de demanda REGULAR (los tres criterios documentables) --------
    candidatos_por_tienda: dict = defaultdict(list)
    examinados = 0
    for clave, d in dias.items():
        examinados += 1
        promedio_diario = volumen[clave] / N_DIAS_CALENDARIO
        prop_ceros = 1.0 - (d / N_DIAS_CALENDARIO)
        if (
            d >= min_dias_con_venta
            and promedio_diario >= min_promedio_diario
            and prop_ceros <= max_prop_ceros
        ):
            tienda, producto = int(clave[0]), int(clave[1])
            candidatos_por_tienda[tienda].append(producto)

    n_candidatos = sum(len(p) for p in candidatos_por_tienda.values())
    print(
        f"  Series candidatas (demanda regular): {n_candidatos} de {examinados} "
        f"pares evaluados.\n"
        f"  Criterio: ≥{min_dias_con_venta} días con venta, "
        f"≥{min_promedio_diario:g} u/día promedio, ≤{max_prop_ceros:.0%} días en cero."
    )

    tiendas_validas = sorted(
        t for t, prods in candidatos_por_tienda.items() if len(prods) >= n_productos
    )
    if len(tiendas_validas) < n_tiendas:
        raise SystemExit(
            f"Solo {len(tiendas_validas)} tiendas tienen ≥ {n_productos} productos de "
            f"demanda regular con estos umbrales. Baje --min-promedio-diario o suba "
            f"--max-prop-ceros y vuelva a intentar."
        )

    # ---- Muestreo aleatorio reproducible (la semilla fija el sorteo) -------
    azar = random.Random(semilla)
    tiendas_elegidas = sorted(azar.sample(tiendas_validas, n_tiendas))
    seleccion: set = set()
    for tienda in tiendas_elegidas:
        productos = sorted(azar.sample(candidatos_por_tienda[tienda], n_productos))
        for producto in productos:
            seleccion.add((tienda, producto))
    print(
        f"Seleccionadas {len(seleccion)} series "
        f"({n_tiendas} tiendas × {n_productos} productos, semilla={semilla})."
    )

    # ---- PASADA 2: extraer solo las filas de las series elegidas ----------
    print("Pasada 2/2: extrayendo las filas de las series elegidas…")
    partes = []
    for i, trozo in enumerate(
        _trozos(entrada, ["date", "store_nbr", "item_nbr", "unit_sales"]), start=1
    ):
        mascara = trozo.apply(
            lambda f: (int(f["store_nbr"]), int(f["item_nbr"])) in seleccion, axis=1
        )
        partes.append(trozo[mascara])
        print(f"  trozo {i} filtrado", flush=True)
    datos = pd.concat(partes, ignore_index=True)
    datos.loc[datos["unit_sales"] < 0, "unit_sales"] = 0.0

    # ---- Calendario completo y formato final (fecha, serie, ventas) --------
    calendario = pd.date_range(FECHA_INICIO, FECHA_FIN, freq="D")
    filas = []
    resumen = []
    for tienda, producto in sorted(seleccion):
        sub = datos[(datos["store_nbr"] == tienda) & (datos["item_nbr"] == producto)]
        serie = sub.groupby("date")["unit_sales"].sum().reindex(calendario, fill_value=0.0)
        nombre = f"Tienda {tienda} - Producto {producto}"
        filas.append(
            pd.DataFrame(
                {
                    "fecha": serie.index.strftime("%d/%m/%Y"),
                    "serie": nombre,
                    "ventas": serie.values,
                }
            )
        )
        resumen.append((nombre, serie.mean(), (serie == 0).mean()))
    tabla = pd.concat(filas, ignore_index=True)
    tabla.to_csv(salida, index=False)

    # ---- Reporte de control: confirme que las series son de buen volumen ---
    promedios = [r[1] for r in resumen]
    print(
        f"\nListo: {salida} ({len(tabla):,} filas = "
        f"{len(seleccion)} series × {len(calendario)} días)."
    )
    print("Control de calidad de las series seleccionadas:")
    print(
        f"  Promedio de unidades/día: mínimo {min(promedios):.1f}, "
        f"mediana {sorted(promedios)[len(promedios)//2]:.1f}, "
        f"máximo {max(promedios):.1f}"
    )
    print(
        "  (Series de mayor volumen y menos ceros producen MAPE más bajo y "
        "una comparación entre modelos más informativa.)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("entrada", type=Path, help="Ruta al train.csv de Kaggle")
    parser.add_argument(
        "--modo",
        choices=["series", "tiendas", "total"],
        default="series",
        help="series=producto×tienda (granular); tiendas=total por "
        "tienda (agregado, suave, MAPE bajo); total=toda la cadena.",
    )
    parser.add_argument("--tiendas", type=int, default=10)
    parser.add_argument("--productos-por-tienda", type=int, default=5)
    parser.add_argument(
        "--semilla",
        type=int,
        default=42,
        help="Semilla del muestreo (reproducibilidad)",
    )
    parser.add_argument(
        "--min-promedio-diario",
        type=float,
        default=30.0,
        help="Unidades/día promedio mínimas (filtra bajo volumen). "
        "Default 30. Suba a 50-100 para series aún más suaves.",
    )
    parser.add_argument(
        "--max-prop-ceros",
        type=float,
        default=0.15,
        help="Proporción máxima de días sin venta (filtra " "intermitencia). Default 0.15 (15%%).",
    )
    parser.add_argument(
        "--min-dias-con-venta",
        type=int,
        default=MINIMO_DIAS_CON_VENTA,
        help=f"Días mínimos con registro. Default {MINIMO_DIAS_CON_VENTA}.",
    )
    parser.add_argument("--salida", type=Path, default=Path("favorita_preparado.csv"))
    argumentos = parser.parse_args()

    if argumentos.modo == "total":
        preparar_total(argumentos.entrada, argumentos.salida)
    elif argumentos.modo == "tiendas":
        preparar_por_tienda(
            argumentos.entrada,
            argumentos.salida,
            argumentos.tiendas,
            argumentos.semilla,
        )
    else:
        preparar_series(
            argumentos.entrada,
            argumentos.salida,
            argumentos.tiendas,
            argumentos.productos_por_tienda,
            argumentos.semilla,
            argumentos.min_promedio_diario,
            argumentos.max_prop_ceros,
            argumentos.min_dias_con_venta,
        )


if __name__ == "__main__":
    main()
