"""
SPD — Punto de entrada (Composition Root).

Este es el ÚNICO archivo donde las piezas concretas se conectan entre sí:
aquí se instancian los 5 adaptadores de modelo, los casos de uso, el lector,
el exportador y el servidor Flask. El resto del sistema solo conoce
abstracciones (puertos). Para ejecutar en desarrollo:

    python run.py

y el navegador se abrirá solo en http://127.0.0.1:8765
"""
from __future__ import annotations

import threading
import webbrowser

from src.aplicacion.casos_uso.evaluar_modelos import EvaluadorDeModelos
from src.aplicacion.casos_uso.generar_pronostico import GeneradorDePronostico
from src.aplicacion.parametros import ParametrosPronostico
from src.infraestructura.estadistica.adaptador_scipy import AdaptadorPruebasScipy
from src.infraestructura.modelos.adaptador_arima import AdaptadorARIMA
from src.infraestructura.modelos.adaptador_holt_winters import AdaptadorHoltWinters
from src.infraestructura.modelos.adaptador_media_movil import AdaptadorMediaMovil
from src.infraestructura.modelos.adaptador_prophet import AdaptadorProphet
from src.infraestructura.modelos.adaptador_regresion_lineal import AdaptadorRegresionLineal
from src.infraestructura.persistencia.exportador_excel import ExportadorExcel
from src.infraestructura.persistencia.lector_archivos import LectorVentas
from src.infraestructura.web.servidor import crear_app

DIRECCION = "127.0.0.1"  # Solo accesible desde ESTA computadora (app local).
PUERTO = 8765


def construir_aplicacion():
    """Arma el grafo de dependencias completo y devuelve la app Flask."""
    # --- Módulo 1: los 5 competidores en igualdad de condiciones ----------
    # Prophet compite con configuración por defecto + feriados de Ecuador,
    # porque el dataset Corporación Favorita proviene de tiendas ecuatorianas
    # (decisión documentada en el plan de tesis).
    parametros_experimento = ParametrosPronostico(pais_feriados="EC")
    modelos = [
        AdaptadorProphet(parametros_experimento),
        AdaptadorARIMA(),
        AdaptadorHoltWinters(),
        AdaptadorMediaMovil(),
        AdaptadorRegresionLineal(),
    ]
    evaluador = EvaluadorDeModelos(modelos, AdaptadorPruebasScipy())

    # --- Módulo 2: Prophet configurable por el usuario ---------------------
    generador = GeneradorDePronostico()

    def fabrica_modelo(parametros: ParametrosPronostico) -> AdaptadorProphet:
        """Cada pronóstico del retail usa un Prophet NUEVO con SUS parámetros."""
        return AdaptadorProphet(parametros)

    return crear_app(
        evaluador=evaluador,
        generador=generador,
        fabrica_modelo=fabrica_modelo,
        lector=LectorVentas(),
        exportador=ExportadorExcel(),
    )


def abrir_navegador() -> None:
    """Abre la pantalla de inicio en el navegador predeterminado del usuario."""
    webbrowser.open(f"http://{DIRECCION}:{PUERTO}")


if __name__ == "__main__":
    app = construir_aplicacion()
    # Se programa la apertura del navegador 1.2 s después de arrancar, para
    # dar tiempo a que el servidor esté escuchando.
    threading.Timer(1.2, abrir_navegador).start()
    print("=" * 60)
    print("  SPD — Sistema de Pronóstico de Demanda")
    print(f"  Abriendo http://{DIRECCION}:{PUERTO} en su navegador…")
    print("  Para salir: cierre esta ventana o presione Ctrl+C.")
    print("=" * 60)
    # debug=False y use_reloader=False: imprescindible dentro del .exe
    # (el recargador lanzaría un segundo proceso y duplicaría todo).
    app.run(host=DIRECCION, port=PUERTO, debug=False, use_reloader=False)
