#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

SEMILLA = 42
N_TIENDAS = 10
N_PRODUCTOS = 5
UMBRAL_PROMEDIO_DIARIO = 30.0   # inclusión: volumen mínimo (u/día en promedio)
UMBRAL_PROP_CEROS = 0.15        # inclusión: máx. proporción de días sin venta
COLUMNAS_FUENTE = ["date", "store_nbr", "item_nbr", "unit_sales"]
TIPOS_FUENTE = {"store_nbr": "int16", "item_nbr": "int32", "unit_sales": "float32"}
TAMANO_LOTE = 1_000_000


# ------------------------- Modo demostración -------------------------
def generar_datos_demo(ruta_csv: Path) -> None:
    """Mini-Favorita sintética con la misma estructura que train.csv, con niveles
    de venta que permiten ejercitar el criterio de inclusión (algunas series
    pasan el filtro y otras no) y con los tres defectos que el limpiador trata."""
    rng = np.random.default_rng(SEMILLA)
    fechas = pd.date_range("2013-01-01", "2015-06-30", freq="D")
    filas = []
    for tienda in range(1, 15):
        factor_tienda = rng.uniform(0.8, 2.5)
        for producto in range(101, 110):
            base = rng.uniform(25, 60)
            patron_semana = rng.uniform(0.7, 1.6, size=7)
            for i, f in enumerate(fechas):
                if rng.random() < 0.08:
                    continue                                  # día sin registro
                media = base * factor_tienda * patron_semana[f.dayofweek] * (1 + 0.0002 * i)
                venta = float(rng.poisson(media))
                if rng.random() < 0.005:
                    venta = -abs(rng.poisson(2))              # devolución
                if rng.random() < 0.003:
                    venta *= 6                                # pico atípico
                filas.append((f.date().isoformat(), tienda, producto, venta))
    df = pd.DataFrame(filas, columns=COLUMNAS_FUENTE)
    df.insert(0, "id", range(len(df)))
    df["onpromotion"] = ""
    ruta_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta_csv, index=False)
    print(f"[demo] archivo sintético generado: {ruta_csv} ({len(df):,} filas)")
    
    
# --------------- PASADA 1a: métricas globales del archivo ---------------
def resumir_archivo(ruta: Path):
    filas_totales = 0
    fecha_min, fecha_max = None, None
    tiendas = set()
    for lote in pd.read_csv(ruta, usecols=COLUMNAS_FUENTE, dtype=TIPOS_FUENTE,
                            chunksize=TAMANO_LOTE):
        filas_totales += len(lote)
        tiendas.update(int(t) for t in lote["store_nbr"].unique())
        lo, hi = lote["date"].min(), lote["date"].max()
        fecha_min = lo if fecha_min is None or lo < fecha_min else fecha_min
        fecha_max = hi if fecha_max is None or hi > fecha_max else fecha_max
    return filas_totales, fecha_min, fecha_max, len(tiendas)

# --------------- PASADA 1b: elegibilidad por par tienda-producto ---------------
def evaluar_elegibilidad(ruta: Path, dias_totales: int):
    """Aplica los criterios de inclusión del Plan §7.3 por cada par tienda-producto.

    promedio diario = suma de ventas positivas / días del periodo completo;
    proporción de ceros = 1 − (días con venta / días del periodo). El archivo de
    Kaggle viene ordenado por fecha, por lo que contar filas con venta > 0
    aproxima fielmente los días con venta (mismo criterio que la herramienta de
    producción preparar_favorita.py del proyecto)."""
    suma: dict[tuple[int, int], float] = {}
    dias_venta: dict[tuple[int, int], int] = {}
    for lote in pd.read_csv(ruta, usecols=COLUMNAS_FUENTE, dtype=TIPOS_FUENTE,
                            chunksize=TAMANO_LOTE):
        positivas = lote[lote["unit_sales"] > 0]
        agregado = positivas.groupby(["store_nbr", "item_nbr"])["unit_sales"].agg(["sum", "count"])
        for (t, p), fila in agregado.iterrows():
            clave = (int(t), int(p))
            suma[clave] = suma.get(clave, 0.0) + float(fila["sum"])
            dias_venta[clave] = dias_venta.get(clave, 0) + int(fila["count"])
    elegibles: dict[int, list[int]] = {}
    for (tienda, producto), total in suma.items():
        promedio = total / dias_totales
        prop_ceros = 1.0 - dias_venta[(tienda, producto)] / dias_totales
        if promedio >= UMBRAL_PROMEDIO_DIARIO and prop_ceros <= UMBRAL_PROP_CEROS:
            elegibles.setdefault(tienda, []).append(producto)
    return elegibles, len(suma)


# --------------- Muestreo aleatorio estratificado en dos etapas ---------------
def seleccionar_muestra(elegibles: dict[int, list[int]]):
    """Etapa 1: 10 tiendas al azar entre las que tienen ≥ 5 productos elegibles.
    Etapa 2: 5 productos elegibles al azar POR TIENDA (Lohr, 2010; Plan §7.3)."""
    azar = random.Random(SEMILLA)
    validas = sorted(t for t, productos in elegibles.items() if len(productos) >= N_PRODUCTOS)
    if len(validas) < N_TIENDAS:
        print(f"[aviso] solo {len(validas)} tiendas cumplen el criterio; se usan todas.")
    tiendas = sorted(azar.sample(validas, min(N_TIENDAS, len(validas))))
    pares: list[tuple[int, int]] = []
    for tienda in tiendas:
        productos = sorted(azar.sample(sorted(elegibles[tienda]), N_PRODUCTOS))
        pares.extend((tienda, producto) for producto in productos)
    return tiendas, pares


# --------------- PASADA 2: cargar solo los pares de la muestra ---------------
def cargar_muestra(ruta: Path, pares: list[tuple[int, int]]) -> pd.DataFrame:
    pares_df = pd.DataFrame(pares, columns=["store_nbr", "item_nbr"])
    partes = []
    for lote in pd.read_csv(ruta, usecols=COLUMNAS_FUENTE, dtype=TIPOS_FUENTE,
                            chunksize=TAMANO_LOTE):
        sub = lote.merge(pares_df, on=["store_nbr", "item_nbr"])
        if len(sub):
            partes.append(sub)
    df = pd.concat(partes, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
    return df
