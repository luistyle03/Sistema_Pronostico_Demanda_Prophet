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
