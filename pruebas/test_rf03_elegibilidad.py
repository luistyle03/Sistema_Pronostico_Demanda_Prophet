"""[RF03 · Elegibilidad de series] Corrección de coherencia documento–código.
La regla vive en el DOMINIO (DIAS_MINIMOS_ELEGIBLE = 365, es_elegible), el
lector la DETECTA por producto y el servidor la HACE CUMPLIR con HTTP 400.
Cubre el caso de caja negra CN-4 (Tabla 20): con menos de 365 días de historia
se muestra la advertencia de elegibilidad y se impide el pronóstico."""

import io
from datetime import date, timedelta

from test_s14_lector_y_pantallas import app_de_prueba, xlsx_bytes

from src.dominio.entidades import DIAS_MINIMOS_ELEGIBLE, PuntoSerie, SerieTemporal
from src.dominio.excepciones import DatosInvalidosError, SerieNoElegibleError
from src.infraestructura.persistencia.lector_archivos import LectorVentas


def serie_de(n_dias):
    inicio = date(2025, 1, 1)
    return SerieTemporal(
        "prueba", [PuntoSerie(inicio + timedelta(days=i), 5.0) for i in range(n_dias)]
    )


def filas_de(producto, n_dias, inicio=date(2025, 1, 1)):
    return [(inicio + timedelta(days=i), producto, 4 + i % 3) for i in range(n_dias)]


def test_dominio_frontera_de_elegibilidad_en_365_dias():
    assert DIAS_MINIMOS_ELEGIBLE == 365
    assert not serie_de(DIAS_MINIMOS_ELEGIBLE - 1).es_elegible()  # 364: NO elegible
    assert serie_de(DIAS_MINIMOS_ELEGIBLE).es_elegible()  # 365: elegible


def test_dominio_la_excepcion_mapea_a_error_de_datos_http_400():
    # Al heredar de DatosInvalidosError, el servidor la traduce a 400 (no 500).
    assert issubclass(SerieNoElegibleError, DatosInvalidosError)


def test_lector_detecta_dias_y_elegibilidad_por_producto():
    lector = LectorVentas()
    tabla = lector.leer(xlsx_bytes(filas_de("Elegible", 400) + filas_de("Corto", 90)), "v.xlsx")
    info = {e["nombre"]: e for e in lector.productos_con_elegibilidad(tabla)}
    assert info["Elegible"]["elegible"] and info["Elegible"]["dias"] == 400
    assert not info["Corto"]["elegible"] and info["Corto"]["dias"] == 90


def test_lector_marca_el_agregado_cuando_no_hay_columna_producto():
    lector = LectorVentas()
    filas = [(date(2025, 1, 1) + timedelta(days=i), 3) for i in range(30)]
    tabla = lector.leer(xlsx_bytes(filas, ("Fecha", "Unidades")), "v.xlsx")
    (item,) = lector.productos_con_elegibilidad(tabla)
    assert item["agregado"] and item["dias"] == 30 and not item["elegible"]


def test_caja_negra_cn4_el_endpoint_advierte_y_bloquea():
    """A través de la interfaz (caja negra): cargar informa la advertencia de
    elegibilidad; generar responde 400 para el producto corto y 200 para el
    elegible. El motor inyectado es promedio móvil: mismo puerto, milisegundos."""
    cliente = app_de_prueba().test_client()
    contenido = xlsx_bytes(filas_de("Elegible", 400) + filas_de("Corto", 90))
    r1 = cliente.post(
        "/api/pronostico/cargar",
        data={"archivo": (io.BytesIO(contenido), "ventas.xlsx")},
        content_type="multipart/form-data",
    )
    assert r1.status_code == 200
    datos = r1.get_json()
    info = {e["nombre"]: e["elegible"] for e in datos["elegibilidad"]}
    assert info == {"Corto": False, "Elegible": True}  # ADVERTENCIA visible.

    r_corto = cliente.post(
        "/api/pronostico/generar",
        json={"token_datos": datos["token_datos"], "producto": "Corto", "horizonte": 7},
    )
    assert r_corto.status_code == 400  # SE IMPIDE el pronóstico.
    assert "365" in r_corto.get_json()["error"]  # Mensaje claro con la regla.

    r_ok = cliente.post(
        "/api/pronostico/generar",
        json={
            "token_datos": datos["token_datos"],
            "producto": "Elegible",
            "horizonte": 7,
        },
    )
    assert r_ok.status_code == 200  # Resultado: Conforme.
