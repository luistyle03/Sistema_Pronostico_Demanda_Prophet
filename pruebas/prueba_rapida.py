"""
PRUEBA RÁPIDA (smoke test) — Ejercita el sistema completo sin navegador.

Genera una serie sintética de 200 días con patrón semanal + tendencia,
evalúa los 5 modelos (Módulo 1), genera un pronóstico Prophet (Módulo 2),
exporta ambos Excel y prueba el lector con un archivo en memoria.

Ejecución:  python pruebas/prueba_rapida.py
Éxito: imprime el ranking, el ganador calculado y "TODAS LAS PRUEBAS PASARON".
"""

from __future__ import annotations

import io
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

# Permite ejecutar este archivo desde cualquier carpeta del proyecto.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openpyxl import Workbook
from src.aplicacion.casos_uso.evaluar_modelos import EvaluadorDeModelos
from src.infraestructura.estadistica.adaptador_scipy import AdaptadorPruebasScipy
from src.infraestructura.modelos.adaptador_arima import AdaptadorARIMA
from src.infraestructura.modelos.adaptador_media_movil import AdaptadorMediaMovil
from src.infraestructura.modelos.adaptador_regresion_lineal import (
    AdaptadorRegresionLineal,
)
from src.infraestructura.persistencia.exportador_excel import ExportadorExcel, sha256_de
from src.infraestructura.persistencia.lector_archivos import LectorVentas

from src.aplicacion.casos_uso.generar_pronostico import GeneradorDePronostico
from src.aplicacion.parametros import ParametrosPronostico
from src.dominio.entidades import PuntoSerie, SerieTemporal
from src.infraestructura.modelos.adaptador_holt_winters import AdaptadorHoltWinters
from src.infraestructura.modelos.adaptador_prophet import AdaptadorProphet


def serie_sintetica(nombre: str = "Producto demo", dias: int = 200) -> SerieTemporal:
    """200 días con base 50, tendencia suave, pico de fin de semana y ruido."""
    azar = random.Random(42)
    inicio = date(2025, 1, 1)
    puntos = []
    for i in range(dias):
        fecha = inicio + timedelta(days=i)
        base = 50 + 0.08 * i  # Tendencia creciente.
        semanal = 18 if fecha.weekday() >= 5 else 0  # Sábado/domingo venden más.
        ruido = azar.gauss(0, 4)
        puntos.append(PuntoSerie(fecha, max(0.0, base + semanal + ruido)))
    return SerieTemporal(nombre, puntos)


def probar_modulo_1(evaluador: EvaluadorDeModelos, exportador: ExportadorExcel) -> None:
    print("\n[1/3] Módulo 1 — evaluación de 5 modelos sobre una serie de 200 días…")
    serie = serie_sintetica()
    evaluacion = evaluador.ejecutar(serie, horizonte=40)  # 20 % de 200.
    assert len(evaluacion.resultados) == 5, "Deben evaluarse los 5 modelos."
    print(f"   {'Modelo':<18}{'MAPE %':>9}{'RMSE':>9}{'RMSSE':>9}{'seg':>8}")
    for r in evaluacion.resultados:
        if r.fallo:
            print(f"   {r.nombre_modelo:<18} FALLÓ: {r.error}")
        else:
            print(
                f"   {r.nombre_modelo:<18}{r.mape:>9.2f}{r.rmse:>9.2f}"
                f"{r.rmsse:>9.3f}{r.segundos:>8.2f}"
            )
    ganador = evaluacion.ganador
    assert ganador is not None and math.isfinite(ganador.mape), "Debe haber un ganador."
    print(f"   GANADOR CALCULADO: {ganador.nombre_modelo} (MAPE {ganador.mape:.2f} %)")

    filas = [
        {
            "Serie": serie.nombre,
            "Modelo": r.nombre_modelo,
            "MAPE (%)": None if r.fallo else round(r.mape, 2),
            "Ganador": "Sí" if r is ganador else "No",
            "Error": r.error or "",
        }
        for r in evaluacion.resultados
    ]
    excel = exportador.exportar_evaluacion(filas, [])
    assert excel[:2] == b"PK", "Un .xlsx empieza con la firma ZIP 'PK'."
    print(
        f"   Excel de evidencia OK ({len(excel):,} bytes, "
        f"SHA-256 {sha256_de(excel)[:16]}…)"
    )


def probar_modulo_2(
    generador: GeneradorDePronostico, exportador: ExportadorExcel
) -> None:
    print("\n[2/3] Módulo 2 — pronóstico Prophet a 28 días con feriados PE…")
    serie = serie_sintetica("Yogurt Fresa 1L")
    parametros = ParametrosPronostico(
        horizonte=28,
        pais_feriados="PE",
        feriados_personalizados=[(date(2025, 8, 1), "Aniversario de la tienda")],
        estacionalidad_mensual=True,
    )
    pronostico, resumen = generador.ejecutar(AdaptadorProphet(parametros), serie, 28)
    assert len(pronostico.fechas) == 28
    assert pronostico.limites_inferiores is not None, "Prophet debe dar banda."
    assert all(v >= 0 for v in pronostico.valores), "Sin pronósticos negativos."
    assert pronostico.fechas[0] == serie.puntos[-1].fecha + timedelta(
        days=1
    ), "El pronóstico empieza el día siguiente al último histórico."
    print(
        f"   Total proyectado: {resumen.total_proyectado:,.1f} uds. | "
        f"pico {resumen.fecha_pico} ({resumen.valor_pico:.1f}) | "
        f"promedio {resumen.promedio_diario:.1f}/día"
    )
    excel = exportador.exportar_pronostico(serie, pronostico, parametros.descripcion())
    assert excel[:2] == b"PK"
    print(f"   Excel del pronóstico OK ({len(excel):,} bytes)")


def probar_lector(lector: LectorVentas) -> None:
    print("\n[3/3] Lector — Excel en memoria con sinónimos, duplicados y huecos…")
    libro = Workbook()
    hoja = libro.active
    # Cabeceras a propósito "humanas": con tildes, mayúsculas y espacios.
    hoja.append(["Fecha", "Nombre del Producto", "Unidades Vendidas"])
    hoja.append([date(2026, 3, 1), "Yogurt Fresa 1L", 30])
    hoja.append([date(2026, 3, 2), "Yogurt Fresa 1L", 38])
    hoja.append([date(2026, 3, 2), "Yogurt Fresa 1L", 4])  # Duplicado: se suma.
    hoja.append([date(2026, 3, 4), "Yogurt Fresa 1L", -5])  # Negativo: se vuelve 0.
    hoja.append([date(2026, 3, 1), "Pan integral", 12])  # Otro producto.
    flujo = io.BytesIO()
    libro.save(flujo)

    tabla = lector.leer(flujo.getvalue(), "ventas.xlsx")
    assert lector.productos(tabla) == ["Pan integral", "Yogurt Fresa 1L"]
    serie = lector.construir_serie(tabla, "Yogurt Fresa 1L")
    valores = {p.fecha: p.valor for p in serie.puntos}
    assert valores[date(2026, 3, 2)] == 42.0, "30/38+4: el duplicado debe sumarse."
    assert valores[date(2026, 3, 3)] == 0.0, "El día sin registro se rellena con 0."
    assert valores[date(2026, 3, 4)] == 0.0, "El negativo se recorta a 0."
    assert len(serie) == 4, "Calendario continuo del 1 al 4 de marzo."
    print("   Sinónimos, suma de duplicados, relleno de huecos y recorte: OK")


if __name__ == "__main__":
    modelos = [
        AdaptadorProphet(ParametrosPronostico()),
        AdaptadorARIMA(),
        AdaptadorHoltWinters(),
        AdaptadorMediaMovil(),
        AdaptadorRegresionLineal(),
    ]
    probar_modulo_1(
        EvaluadorDeModelos(modelos, AdaptadorPruebasScipy()), ExportadorExcel()
    )
    probar_modulo_2(GeneradorDePronostico(), ExportadorExcel())
    probar_lector(LectorVentas())
    print("\n" + "=" * 50)
    print("TODAS LAS PRUEBAS PASARON")
    print("=" * 50)
