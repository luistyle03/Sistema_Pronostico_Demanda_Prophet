"""[S16 · Iteración 7] Integración: Excel del usuario -> API -> pronóstico -> descarga.
Se inyecta promedio móvil como motor (mismo puerto): la prueba corre en
milisegundos y demuestra que la arquitectura acepta cualquier modelo."""

import io
from datetime import date, timedelta

from test_s14_lector_y_pantallas import app_de_prueba, xlsx_bytes


def carga_valida():
    # 400 días: supera el mínimo de elegibilidad del RF03 (365) para que el
    # flujo feliz de generación sea válido. Con promedio móvil corre igual de rápido.
    inicio = date(2025, 1, 1)
    filas = [(inicio + timedelta(days=i), "Gaseosa 500ml", 5 + i % 4) for i in range(400)]
    return xlsx_bytes(filas)


def test_flujo_completo_cargar_generar_descargar():
    cliente = app_de_prueba().test_client()
    r1 = cliente.post(
        "/api/pronostico/cargar",
        data={"archivo": (io.BytesIO(carga_valida()), "ventas.xlsx")},
        content_type="multipart/form-data",
    )
    assert r1.status_code == 200
    datos = r1.get_json()
    assert datos["productos"] == ["Gaseosa 500ml"] and datos["filas"] == 400

    r2 = cliente.post(
        "/api/pronostico/generar",
        json={
            "token_datos": datos["token_datos"],
            "producto": "Gaseosa 500ml",
            "horizonte": 7,
        },
    )
    assert r2.status_code == 200
    cuerpo = r2.get_json()
    assert len(cuerpo["pronostico"]["valores"]) == 7
    assert cuerpo["resumen"]["total_proyectado"] > 0

    r3 = cliente.get(f"/api/pronostico/descargar/{cuerpo['token_excel']}")
    assert r3.status_code == 200 and r3.data[:2] == b"PK"


def test_errores_de_negocio_devuelven_400_con_mensaje():
    cliente = app_de_prueba().test_client()
    assert (
        cliente.post(
            "/api/pronostico/cargar", data={}, content_type="multipart/form-data"
        ).status_code
        == 400
    )
    r = cliente.post("/api/pronostico/generar", json={"token_datos": "inexistente"})
    assert r.status_code == 400 and "cargar" in r.get_json()["error"].lower()


def test_el_cableado_real_de_run_arranca():
    from run import construir_aplicacion

    assert construir_aplicacion().test_client().get("/").status_code == 200
