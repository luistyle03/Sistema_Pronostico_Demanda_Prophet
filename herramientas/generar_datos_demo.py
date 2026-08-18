#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""generar_datos_demo.py — Genera un historial de ventas SINTÉTICO pero REALISTA
para demostrar el Módulo 2 (Pronóstico retail).

A diferencia de unos datos puramente al azar, aquí cada producto se construye a
partir de una estructura conocida y documentada:

    ventas = nivel × tendencia × perfil semanal × perfil anual × efecto feriado
             × promociones  + ruido      (y luego: quiebres de stock = 0)

Como la estructura es conocida, se guarda además una FICHA DE VERDAD-TERRENO con
los parámetros usados. Eso permite verificar que la descomposición de Prophet
recupera lo que realmente se sembró: si el producto se creó con pico los sábados,
el "perfil semanal" del Módulo 2 debe mostrar el sábado arriba. Es la mejor forma
de demostrar ante un jurado que el gráfico de descomposición dice algo real.

Uso típico:
    python herramientas/generar_datos_demo.py --productos 5 --anios 4 \
        --salida datos_demo.csv --ficha ficha_datos_demo.xlsx

Para demostrar la regla RF03 (serie con menos de 365 días se rechaza):
    python herramientas/generar_datos_demo.py --productos 5 --incluir-producto-corto
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import holidays as lib_holidays
except ImportError:  # pragma: no cover
    lib_holidays = None

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

# Catálogo de productos con perfiles de comportamiento DISTINTOS entre sí, para
# que el Módulo 2 tenga casos variados que mostrar.
CATALOGO = [
    # nombre, nivel, tendencia %/año, patrón semanal, mes pico, efecto feriado
    ("Arroz Extra Costeño Bolsa 5kg", 45, +6.0, "fin_de_semana", 12, +0.35),
    (
        "Aceite Vegetal Premium PRIMOR Botella 900ml",
        24,
        -4.0,
        "fin_de_semana",
        12,
        +0.20,
    ),
    ("Gaseosa Inca Kola 1.5L", 38, +12.0, "fin_de_semana", 1, +0.60),
    ("Leche Evaporada Gloria Tarro 400g", 30, +2.0, "estable", 7, +0.10),
    ("Panetón D'Onofrio Caja 900g", 12, +18.0, "fin_de_semana", 12, +0.80),
    ("Detergente Bolívar Bolsa 780g", 18, -1.0, "quincena", 3, -0.15),
    ("Fideos Don Vittorio Spaghetti 500g", 28, +3.0, "estable", 6, +0.15),
    ("Atún Florida Lomito Lata 170g", 16, +5.0, "quincena", 4, +0.25),
]

PERFILES_SEMANALES = {
    # Lun   Mar   Mié   Jue   Vie   Sáb   Dom
    "fin_de_semana": [0.85, 0.85, 0.90, 1.00, 1.20, 1.45, 1.10],
    "estable": [1.00, 1.00, 1.05, 1.00, 1.05, 1.05, 0.90],
    "quincena": [0.95, 0.95, 1.00, 1.00, 1.15, 1.25, 0.85],
}


def _feriados_pais(inicio: date, fin: date, pais: str) -> dict[date, str]:
    if lib_holidays is None:
        return {}
    años = list(range(inicio.year, fin.year + 1))
    return {d: n for d, n in lib_holidays.country_holidays(pais, years=años).items()}


def _serie_producto(
    rng,
    fechas,
    nombre,
    nivel,
    tendencia_anual,
    patron,
    mes_pico,
    efecto_feriado,
    feriados,
    feriados_propios,
    prob_promo,
    prob_quiebre,
):
    """Construye una serie diaria con estructura conocida."""
    n = len(fechas)
    t = np.arange(n)

    # 1) Tendencia compuesta (porcentaje anual convertido a diario)
    factor_diario = (1 + tendencia_anual / 100.0) ** (1 / 365.25)
    tendencia = nivel * factor_diario**t

    # 2) Perfil semanal (multiplicativo)
    pesos_semana = np.array(PERFILES_SEMANALES[patron])
    semanal = np.array([pesos_semana[f.weekday()] for f in fechas])

    # 3) Perfil anual: pico en `mes_pico` (coseno centrado en ese mes)
    dia_del_año = np.array([f.timetuple().tm_yday for f in fechas])
    desfase = (mes_pico - 1) * 30.4
    anual = 1 + 0.25 * np.cos(2 * np.pi * (dia_del_año - desfase) / 365.25)

    # 4) Efecto de feriados (nacionales y propios del negocio)
    efecto = np.ones(n)
    for i, f in enumerate(fechas):
        if f in feriados:
            efecto[i] *= 1 + efecto_feriado
        if f in feriados_propios:
            efecto[i] *= 1 + 1.20  # el aniversario dispara la venta
        # Víspera de feriado: la gente se abastece
        if (f + timedelta(days=1)) in feriados:
            efecto[i] *= 1 + efecto_feriado * 0.5

    base = tendencia * semanal * anual * efecto

    # 5) Promociones puntuales (picos altos)
    promos = rng.random(n) < prob_promo
    base = np.where(promos, base * rng.uniform(1.8, 3.2, n), base)

    # 6) Ruido de conteo (sobredisperso, como la demanda real)
    valores = rng.poisson(np.clip(base, 0.1, None)).astype(float)
    valores += rng.normal(0, np.sqrt(np.clip(base, 1, None)) * 0.4, n)
    valores = np.clip(np.round(valores), 0, None)

    # 7) Quiebres de stock: rachas de días SIN venta (ceros reales)
    dias_quiebre = 0
    i = 0
    while i < n:
        if rng.random() < prob_quiebre:
            largo = int(rng.integers(1, 5))
            valores[i : i + largo] = 0
            dias_quiebre += min(largo, n - i)
            i += largo
        i += 1

    ficha = {
        "Producto": nombre,
        "Nivel base (uds/día)": nivel,
        "Tendencia (%/año)": tendencia_anual,
        "Patrón semanal": patron,
        "Día más fuerte": DIAS[int(np.argmax(pesos_semana))],
        "Día más débil": DIAS[int(np.argmin(pesos_semana))],
        "Mes pico (anual)": mes_pico,
        "Efecto feriado (%)": round(efecto_feriado * 100, 1),
        "Días con promoción": int(promos.sum()),
        "Días sin venta (quiebre)": dias_quiebre,
        "Días totales": n,
        "Media (uds/día)": round(float(valores.mean()), 2),
    }
    return valores, ficha


def main() -> None:
    p = argparse.ArgumentParser(
        description="Genera datos de demostración realistas para el Módulo 2."
    )
    p.add_argument("--productos", type=int, default=5, help="Cuántos productos generar (1-8)")
    p.add_argument("--anios", type=float, default=4.0, help="Años de historia")
    p.add_argument(
        "--fin",
        type=str,
        default=None,
        help="Fecha final dd/mm/aaaa (por defecto, ayer)",
    )
    p.add_argument("--pais", type=str, default="PE", help="Calendario de feriados (PE, EC, CL...)")
    p.add_argument(
        "--feriados-propios",
        type=int,
        default=2,
        help="Cuántos feriados propios del negocio sembrar (aniversarios/campañas)",
    )
    p.add_argument(
        "--prob-promo",
        type=float,
        default=0.03,
        help="Probabilidad diaria de promoción",
    )
    p.add_argument(
        "--prob-quiebre",
        type=float,
        default=0.006,
        help="Probabilidad de iniciar un quiebre de stock",
    )
    p.add_argument(
        "--incluir-producto-corto",
        action="store_true",
        help="Añade un producto con menos de 365 días para demostrar la regla RF03",
    )
    p.add_argument("--semilla", type=int, default=42)
    p.add_argument("--salida", type=Path, default=Path("datos_demo.csv"))
    p.add_argument("--ficha", type=Path, default=Path("ficha_datos_demo.xlsx"))
    args = p.parse_args()

    rng = np.random.default_rng(args.semilla)
    fin = (
        (date.today() - timedelta(days=1))
        if args.fin is None
        else pd.to_datetime(args.fin, dayfirst=True).date()
    )
    inicio = fin - timedelta(days=int(args.anios * 365.25))
    fechas = [inicio + timedelta(days=i) for i in range((fin - inicio).days + 1)]

    feriados = _feriados_pais(inicio, fin, args.pais)
    if not feriados:
        print(
            "Aviso: la librería 'holidays' no está disponible; se omiten los feriados nacionales."
        )

    # Feriados propios del negocio: mismo día cada año (aniversario, campaña)
    propios: dict[date, str] = {}
    etiquetas = [
        "aniversario de la tienda",
        "campaña escolar",
        "remate de fin de mes",
        "feria del barrio",
    ]
    for k in range(min(args.feriados_propios, len(etiquetas))):
        mes = int(rng.integers(3, 12))
        dia = int(rng.integers(2, 28))
        for a in range(inicio.year, fin.year + 1):
            try:
                propios[date(a, mes, dia)] = etiquetas[k]
            except ValueError:
                pass

    n_prod = max(1, min(args.productos, len(CATALOGO)))
    filas, fichas = [], []
    for nombre, nivel, tend, patron, mes_pico, ef in CATALOGO[:n_prod]:
        valores, ficha = _serie_producto(
            rng,
            fechas,
            nombre,
            nivel,
            tend,
            patron,
            mes_pico,
            ef,
            feriados,
            propios,
            args.prob_promo,
            args.prob_quiebre,
        )
        filas.append(
            pd.DataFrame(
                {
                    "fecha": [f.strftime("%d/%m/%Y") for f in fechas],
                    "producto": nombre,
                    "unidades_vendidas": valores.astype(int),
                }
            )
        )
        fichas.append(ficha)

    # Producto con historia insuficiente, para demostrar el rechazo por RF03
    if args.incluir_producto_corto:
        cortas = fechas[-200:]
        valores, ficha = _serie_producto(
            rng,
            cortas,
            "Producto Nuevo (lanzamiento reciente)",
            20,
            0.0,
            "estable",
            6,
            0.1,
            feriados,
            propios,
            args.prob_promo,
            args.prob_quiebre,
        )
        filas.append(
            pd.DataFrame(
                {
                    "fecha": [f.strftime("%d/%m/%Y") for f in cortas],
                    "producto": "Producto Nuevo (lanzamiento reciente)",
                    "unidades_vendidas": valores.astype(int),
                }
            )
        )
        ficha["Observación"] = "Menos de 365 días: el sistema debe rechazarlo (RF03)"
        fichas.append(ficha)

    tabla = pd.concat(filas, ignore_index=True)
    tabla.to_csv(args.salida, index=False, encoding="utf-8-sig")

    # Ficha de verdad-terreno: qué se sembró en cada producto
    with pd.ExcelWriter(args.ficha, engine="openpyxl") as xl:
        pd.DataFrame(fichas).to_excel(xl, sheet_name="Estructura sembrada", index=False)
        pd.DataFrame(
            {
                "Fecha": [d.strftime("%d/%m/%Y") for d in sorted(feriados)],
                "Feriado nacional": [feriados[d] for d in sorted(feriados)],
            }
        ).to_excel(xl, sheet_name="Feriados nacionales", index=False)
        pd.DataFrame(
            {
                "Fecha": [d.strftime("%d/%m/%Y") for d in sorted(propios)],
                "Feriado propio": [propios[d] for d in sorted(propios)],
            }
        ).to_excel(xl, sheet_name="Feriados propios", index=False)

    print(
        f"Datos generados : {args.salida}  "
        f"({len(tabla)} filas, {tabla['producto'].nunique()} productos)"
    )
    print(f"Período         : {fechas[0].strftime('%d/%m/%Y')} a {fechas[-1].strftime('%d/%m/%Y')}")
    print(f"Feriados        : {len(feriados)} nacionales ({args.pais}) + {len(propios)} propios")
    print(f"Ficha de verdad : {args.ficha}")
    print()
    print("Estructura sembrada (verifíquela contra la descomposición del Módulo 2):")
    for f in fichas:
        print(
            f"  · {f['Producto'][:44]:<46} tendencia {f['Tendencia (%/año)']:+5.1f}%/año | "
            f"pico {f['Día más fuerte']:<9} | mes {f['Mes pico (anual)']:>2} | "
            f"promos {f['Días con promoción']:>3} | ceros {f['Días sin venta (quiebre)']:>3}"
        )
    print()
    print("Feriados propios sembrados (agréguelos en el Módulo 2 para ver su efecto):")
    for d in sorted(set(propios))[:4]:
        print(f"  · {d.strftime('%d/%m/%Y')} — {propios[d]}")


if __name__ == "__main__":
    main()
