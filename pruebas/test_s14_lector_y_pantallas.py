"""[S14 · Iteración 5] Lector de ventas: validación, limpieza y series continuas.

Alcance de esta iteración: el lector que convierte el Excel/CSV del comerciante
en series limpias y continuas, con errores en idioma humano.

La capa web se construye en S15, cuando ya existe el exportador del que depende
`servidor.py`. Las comprobaciones de las pantallas se incorporan en esa semana.
"""

import io
from datetime import date, timedelta

import pytest
from openpyxl import Workbook

from src.dominio.excepciones import ColumnasFaltantesError, DatosInvalidosError
from src.infraestructura.persistencia.lector_archivos import LectorVentas


def xlsx_bytes(filas, encabezados=("Fecha", "Producto", "Unidades Vendidas")):
    libro = Workbook()
    hoja = libro.active
    hoja.append(list(encabezados))
    for fila in filas:
        hoja.append(list(fila))
    flujo = io.BytesIO()
    libro.save(flujo)
    return flujo.getvalue()


def filas_demo():
    inicio, filas = date(2026, 1, 1), []
    for i in range(30):
        f = inicio + timedelta(days=i)
        if i != 10:  # hueco a propósito el día 10
            filas.append((f, "Gaseosa 500ml", 5 + i % 3))
        filas.append((f, "Galleta soda", 3))
    filas.append((inicio, "Gaseosa 500ml", 2))  # fila duplicada: debe sumarse
    filas.append((inicio + timedelta(days=1), "Galleta soda", -4))  # devolución -> 0
    return filas


def test_lector_valida_limpia_y_construye_series_continuas():
    lector = LectorVentas()
    tabla = lector.leer(xlsx_bytes(filas_demo()), "ventas.xlsx")
    assert set(tabla.columns) == {"fecha", "producto", "unidades"}
    assert lector.productos(tabla) == ["Galleta soda", "Gaseosa 500ml"]
    serie = lector.construir_serie(tabla, "Gaseosa 500ml")
    assert len(serie) == 30  # calendario continuo completo
    assert serie.valores()[10] == 0.0  # el hueco se rellenó con 0
    assert serie.valores()[0] == 7.0  # 5 + 2 (duplicado sumado)
    assert min(lector.construir_serie(tabla, "Galleta soda").valores()) >= 0.0
    assert len(lector.construir_series_lote(tabla)) == 2


def test_lector_reporta_errores_en_lenguaje_del_usuario():
    lector = LectorVentas()
    with pytest.raises(ColumnasFaltantesError, match="unidades"):
        lector.leer(
            xlsx_bytes([(date(2026, 1, 1), "A", 1)], ("Fecha", "Producto", "Precio")),
            "v.xlsx",
        )
    with pytest.raises(DatosInvalidosError):
        lector.leer(xlsx_bytes([("no-es-fecha", "A", 1)]), "v.xlsx")
    with pytest.raises(DatosInvalidosError):
        lector.leer(b"cualquier cosa", "notas.txt")
