"""
CAPA DE INFRAESTRUCTURA — Servidor web (Flask).

Este es el "adaptador de entrada" de la arquitectura hexagonal: recibe las
peticiones del navegador, las traduce a llamadas a los casos de uso y
devuelve JSON o archivos. Aquí NO hay lógica de pronóstico ni de métricas:
solo traducción entre el mundo HTTP y el núcleo de la aplicación.

Rutas del Módulo 1 (experimental):
    GET  /experimental                  -> pantalla del experimento.
    POST /api/experimental/evaluar      -> ejecuta la evaluación (serie única o lote).
    GET  /api/experimental/descargar/<token> -> Excel de evidencia.

Rutas del Módulo 2 (retail):
    GET  /pronostico                    -> pantalla de pronóstico.
    POST /api/pronostico/cargar         -> sube el Excel y lista productos.
    POST /api/pronostico/generar        -> genera el pronóstico con Prophet.
    GET  /api/pronostico/descargar/<token>   -> Excel del pronóstico.
"""

from __future__ import annotations

import io
import math
import sys
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from flask import Flask, jsonify, render_template, request, send_file

from src.aplicacion.casos_uso.evaluar_modelos import (
    UMBRAL_MAPE_TESIS,
    EvaluadorDeModelos,
    ResultadoLote,
)
from src.aplicacion.casos_uso.generar_pronostico import GeneradorDePronostico
from src.aplicacion.parametros import ParametrosPronostico
from src.aplicacion.puertos import PuertoExportadorPronostico, PuertoModeloPronostico
from src.dominio.entidades import (
    DIAS_MINIMOS_ELEGIBLE,
    ResultadoEvaluacion,
    SerieTemporal,
)
from src.dominio.excepciones import ErrorDeDominio, SerieNoElegibleError
from src.infraestructura.persistencia.exportador_excel import sha256_de
from src.infraestructura.persistencia.lector_archivos import LectorVentas


# ---------------------------------------------------------------------- #
# Rutas de recursos compatibles con PyInstaller                          #
# ---------------------------------------------------------------------- #
def _base_web() -> Path:
    """
    Carpeta donde viven templates/ y static/. En desarrollo es la carpeta de
    este archivo; dentro del ejecutable de PyInstaller es la carpeta temporal
    sys._MEIPASS donde el empaquetador descomprime los recursos.
    """
    if hasattr(sys, "_MEIPASS"):  # Atributo que solo existe dentro del .exe.
        return Path(sys._MEIPASS) / "web"
    return Path(__file__).parent


# ---------------------------------------------------------------------- #
# Almacén en memoria de la sesión                                        #
# ---------------------------------------------------------------------- #
# Guarda lo que el usuario subió o generó, identificado por un token UUID.
# Al ser una app LOCAL de un solo usuario, un diccionario en memoria basta;
# si el programa se cierra, los datos desaparecen (no se persiste nada).
ALMACEN: Dict[str, dict] = {}


def _json_error(mensaje: str, codigo: int):
    """Respuesta de error uniforme para que el JavaScript la muestre."""
    return jsonify({"error": mensaje}), codigo


def _fecha_iso(f: date) -> str:
    """date -> 'AAAA-MM-DD' (formato que Plotly entiende como fecha)."""
    return f.isoformat()


def _limpiar(valor: float) -> Optional[float]:
    """inf/nan no existen en JSON: se convierten a None (null)."""
    return None if (valor is None or not math.isfinite(valor)) else round(valor, 4)


def crear_app(
    evaluador: EvaluadorDeModelos,
    generador: GeneradorDePronostico,
    fabrica_modelo: Callable[[ParametrosPronostico], PuertoModeloPronostico],
    lector: LectorVentas,
    exportador: PuertoExportadorPronostico,
) -> Flask:
    """
    Fábrica de la aplicación Flask (patrón Application Factory).

    Recibe los casos de uso y adaptadores YA construidos (Inyección de
    Dependencias): el servidor no sabe cómo se crean, solo los usa.
    `fabrica_modelo` es una función que, dados los parámetros del usuario,
    devuelve un Prophet recién configurado (cada pronóstico usa uno nuevo).
    """
    base = _base_web()
    app = Flask(
        __name__,
        template_folder=str(base / "templates"),
        static_folder=str(base / "static"),
    )
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # Máximo 64 MB por archivo.

    # ------------------------------------------------------------------ #
    # Pantallas                                                          #
    # ------------------------------------------------------------------ #
    @app.get("/")
    def inicio():
        return render_template("index.html")

    @app.get("/experimental")
    def pantalla_experimental():
        return render_template("experimental.html", umbral=UMBRAL_MAPE_TESIS)

    @app.get("/pronostico")
    def pantalla_pronostico():
        return render_template("pronostico.html")

    # ------------------------------------------------------------------ #
    # Módulo 1: API del experimento                                      #
    # ------------------------------------------------------------------ #
    @app.post("/api/experimental/evaluar")
    def api_evaluar():
        archivo = request.files.get("archivo")
        if archivo is None or archivo.filename == "":
            return _json_error("Seleccione un archivo .xlsx o .csv.", 400)
        try:
            tabla = lector.leer(archivo.read(), archivo.filename)
            series = lector.construir_series_lote(tabla)
            fraccion = float(request.form.get("fraccion_prueba", 0.20))
            fraccion = min(max(fraccion, 0.05), 0.50)  # Se acota entre 5 % y 50 %.
            if len(series) == 1:
                respuesta = _evaluar_serie_unica(series[0], fraccion)
            else:
                respuesta = _evaluar_lote(series, fraccion)
            return jsonify(respuesta)
        except ErrorDeDominio as exc:
            return _json_error(str(exc), 400)
        except Exception as exc:  # Cualquier otro fallo: error 500 legible.
            return _json_error(f"Error inesperado: {exc}", 500)

    def _evaluar_serie_unica(serie: SerieTemporal, fraccion: float) -> dict:
        """Modo demostración: una sola serie, gráfico real-vs-predicho."""
        horizonte = max(1, int(round(len(serie) * fraccion)))
        evaluacion = evaluador.ejecutar(serie, horizonte)
        token = _guardar_evidencia_serie(evaluacion)
        ganador = evaluacion.ganador
        filas = [
            {
                "modelo": r.nombre_modelo,
                "mape": _limpiar(r.mape),
                "rmse": _limpiar(r.rmse),
                "rmsse": _limpiar(r.rmsse),
                "wape": _limpiar(r.wape),
                "mae": _limpiar(r.mae),
                "sesgo": _limpiar(r.sesgo),
                "segundos": _limpiar(r.segundos),
                "cumple_umbral": (r.rmsse < 1.0) if math.isfinite(r.rmsse) else False,
                "ganador": ganador is not None and r.nombre_modelo == ganador.nombre_modelo,
                "error": r.error,
            }
            for r in evaluacion.resultados
        ]
        # Predicciones de cada modelo sobre el tramo de prueba, para el gráfico.
        predicciones = [
            {
                "modelo": r.nombre_modelo,
                "valores": [_limpiar(v) for v in r.pronostico.valores],
            }
            for r in evaluacion.resultados
            if r.pronostico is not None
        ]
        return {
            "modo": "serie_unica",
            "serie": serie.nombre,
            "observaciones": len(serie),
            "horizonte": horizonte,
            "umbral_mape": UMBRAL_MAPE_TESIS,
            "ganador": ganador.nombre_modelo if ganador else None,
            "ganador_mape": _limpiar(ganador.mape) if ganador else None,
            "ganador_rmsse": _limpiar(ganador.rmsse) if ganador else None,
            "tabla": filas,
            "fechas_prueba": [_fecha_iso(f) for f in evaluacion.fechas_prueba],
            "valores_prueba": [_limpiar(v) for v in evaluacion.valores_prueba],
            "predicciones": predicciones,
            "token_evidencia": token,
        }

    def _evaluar_lote(series: List[SerieTemporal], fraccion: float) -> dict:
        """Modo tesis: muchas series, ranking agregado + pruebas estadísticas."""
        lote = evaluador.ejecutar_lote(series, fraccion_prueba=fraccion)
        token = _guardar_evidencia_lote(lote)
        ganador = lote.ganador
        resumen = [
            {
                "modelo": r.nombre_modelo,
                "mape_promedio": _limpiar(r.mape_promedio),
                "mape_desviacion": _limpiar(r.mape_desviacion),
                "rmse_promedio": _limpiar(r.rmse_promedio),
                "rmsse_promedio": _limpiar(r.rmsse_promedio),
                "rmsse_mediana": _limpiar(r.rmsse_mediana),
                "rmsse_desviacion": _limpiar(r.rmsse_desviacion),
                "wape_promedio": _limpiar(r.wape_promedio),
                "wape_mediana": _limpiar(r.wape_mediana),
                "mae_promedio": _limpiar(r.mae_promedio),
                "sesgo_promedio": _limpiar(r.sesgo_promedio),
                "segundos_promedio": _limpiar(r.segundos_promedio),
                "series_ganadas": r.series_ganadas,
                "series_evaluadas": r.series_evaluadas,
                "series_supera_ingenuo": r.series_supera_ingenuo,
                "cumple_umbral": r.rmsse_mediana < 1.0,
                "ganador": ganador is not None and r.nombre_modelo == ganador.nombre_modelo,
                "rmsses": [_limpiar(m) for m in r.rmsses],  # Para el boxplot (métrica principal).
                "mapes": [_limpiar(m) for m in r.mapes],
            }
            for r in lote.resumen_por_modelo
        ]
        pruebas = [
            {
                "comparacion": p.comparacion,
                "p_valor_t": _limpiar(p.p_valor_t),
                "p_valor_wilcoxon": _limpiar(p.p_valor_wilcoxon),
                "d_cohen": _limpiar(p.d_cohen),
                "n": p.n,
                "interpretacion": _interpretar_d(p.d_cohen),
            }
            for p in lote.pruebas
        ]
        return {
            "modo": "lote",
            "series_evaluadas": len(lote.detalle_por_serie),
            "series_omitidas": lote.series_omitidas,
            "umbral_mape": UMBRAL_MAPE_TESIS,
            "ganador": ganador.nombre_modelo if ganador else None,
            "ganador_mape": _limpiar(ganador.mape_promedio) if ganador else None,
            "ganador_rmsse": _limpiar(ganador.rmsse_mediana) if ganador else None,
            "ganador_supera": ganador.series_supera_ingenuo if ganador else None,
            "resumen": resumen,
            "pruebas": pruebas,
            "token_evidencia": token,
        }

    def _interpretar_d(d: float) -> str:
        """Umbrales clásicos de Cohen (1988) para el tamaño del efecto d."""
        magnitud = abs(d)
        if magnitud >= 0.8:
            return "grande"
        if magnitud >= 0.5:
            return "mediano"
        if magnitud >= 0.2:
            return "pequeño"
        return "trivial"

    # --- Evidencia descargable del Módulo 1 -------------------------------
    def _guardar_evidencia_serie(evaluacion: ResultadoEvaluacion) -> str:
        filas = [
            {
                "Serie": evaluacion.nombre_serie,
                "Modelo": r.nombre_modelo,
                "RMSSE": _limpiar(r.rmsse),
                "WAPE (%)": _limpiar(r.wape),
                "MAE (unid.)": _limpiar(r.mae),
                "Sesgo (unid.)": _limpiar(r.sesgo),
                "RMSE": _limpiar(r.rmse),
                "MAPE (%)": _limpiar(r.mape),
                "Tiempo (s)": _limpiar(r.segundos),
                "Ganador": (
                    "Sí"
                    if (evaluacion.ganador and r.nombre_modelo == evaluacion.ganador.nombre_modelo)
                    else "No"
                ),
                "Error": r.error or "",
            }
            for r in evaluacion.resultados
        ]
        return _guardar_excel(
            exportador.exportar_evaluacion(filas, []), "evidencia_experimento.xlsx"
        )

    def _guardar_evidencia_lote(lote: ResultadoLote) -> str:
        filas = []
        for evaluacion in lote.detalle_por_serie:
            for r in evaluacion.resultados:
                filas.append(
                    {
                        "Serie": evaluacion.nombre_serie,
                        "Modelo": r.nombre_modelo,
                        "RMSSE": _limpiar(r.rmsse),
                        "WAPE (%)": _limpiar(r.wape),
                        "MAE (unid.)": _limpiar(r.mae),
                        "Sesgo (unid.)": _limpiar(r.sesgo),
                        "RMSE": _limpiar(r.rmse),
                        "MAPE (%)": _limpiar(r.mape),
                        "Tiempo (s)": _limpiar(r.segundos),
                        "Ganador": (
                            "Sí"
                            if (
                                evaluacion.ganador
                                and r.nombre_modelo == evaluacion.ganador.nombre_modelo
                            )
                            else "No"
                        ),
                        "Error": r.error or "",
                    }
                )
        pruebas = [
            {
                "Comparación": p.comparacion,
                "p-valor (t pareada)": _limpiar(p.p_valor_t),
                "p-valor (Wilcoxon)": _limpiar(p.p_valor_wilcoxon),
                "d de Cohen": _limpiar(p.d_cohen),
                "N (pares)": p.n,
            }
            for p in lote.pruebas
        ]
        return _guardar_excel(
            exportador.exportar_evaluacion(filas, pruebas),
            "evidencia_experimento_lote.xlsx",
        )

    @app.get("/api/experimental/descargar/<token>")
    def api_descargar_evidencia(token: str):
        return _descargar(token)

    # ------------------------------------------------------------------ #
    # Módulo 2: API del pronóstico retail                                #
    # ------------------------------------------------------------------ #
    @app.post("/api/pronostico/cargar")
    def api_cargar():
        archivo = request.files.get("archivo")
        if archivo is None or archivo.filename == "":
            return _json_error("Seleccione un archivo .xlsx o .csv.", 400)
        try:
            tabla = lector.leer(archivo.read(), archivo.filename)
        except ErrorDeDominio as exc:
            return _json_error(str(exc), 400)
        token = uuid.uuid4().hex  # Identificador único de esta carga.
        ALMACEN[token] = {"tabla": tabla}
        fechas = tabla["fecha"]
        return jsonify(
            {
                "token_datos": token,
                "filas": int(len(tabla)),
                "productos": lector.productos(tabla),
                # RF03: días de historia y elegibilidad de cada serie, para que
                # la interfaz ADVIERTA y deshabilite los productos no elegibles.
                "elegibilidad": lector.productos_con_elegibilidad(tabla),
                "fecha_inicio": fechas.min().date().isoformat(),
                "fecha_fin": fechas.max().date().isoformat(),
            }
        )

    @app.post("/api/pronostico/generar")
    def api_generar():
        datos = request.get_json(silent=True) or {}
        registro = ALMACEN.get(datos.get("token_datos", ""))
        if registro is None or "tabla" not in registro:
            return _json_error("Vuelva a cargar el archivo de ventas.", 400)
        try:
            parametros = _leer_parametros(datos)
            serie = lector.construir_serie(registro["tabla"], datos.get("producto") or None)
            # RF03: la REGLA vive en el dominio (SerieTemporal.es_elegible); este
            # adaptador de entrada solo la APLICA y la traduce a un HTTP 400.
            # Es el mismo punto donde opera la prueba de caja negra CN-4.
            if not serie.es_elegible():
                raise SerieNoElegibleError(
                    f"'{serie.nombre}' tiene {len(serie)} días de historia continua; "
                    f"el pronóstico requiere al menos {DIAS_MINIMOS_ELEGIBLE} días "
                    "(un año) para capturar la estacionalidad anual (RF03). "
                    "Elija un producto elegible o complete el historial."
                )
            modelo = fabrica_modelo(parametros)  # Un Prophet NUEVO por pronóstico.
            pronostico, resumen = generador.ejecutar(modelo, serie, parametros.horizonte)
        except ErrorDeDominio as exc:
            return _json_error(str(exc), 400)
        except Exception as exc:
            return _json_error(f"Error inesperado: {exc}", 500)

        excel = exportador.exportar_pronostico(serie, pronostico, parametros.descripcion())
        nombre_archivo = f"pronostico_{serie.nombre[:40].replace(' ', '_')}.xlsx"
        token_excel = _guardar_excel(excel, nombre_archivo)

        # Historia reciente para el gráfico (máximo 365 días: legibilidad).
        fechas_hist = serie.fechas()[-365:]
        valores_hist = serie.valores()[-365:]

        # HU02: descomposición aditiva (tendencia + estacionalidades + feriados).
        # Solo la publican los modelos que la ofrecen (Prophet); si no, viaja
        # null y la interfaz oculta la vista. Tendencia y feriados se recortan
        # a la misma ventana de legibilidad que la historia (365 días + futuro).
        comp = pronostico.componentes
        componentes_json = None
        if comp is not None:
            recorte = 365 + parametros.horizonte
            componentes_json = {
                "tendencia": {
                    "fechas": [_fecha_iso(f) for f in comp.fechas[-recorte:]],
                    "valores": [_limpiar(v) for v in comp.tendencia[-recorte:]],
                },
                "semanal": (
                    None
                    if comp.perfil_semanal is None
                    else {
                        "dias": ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"],
                        "valores": [_limpiar(v) for v in comp.perfil_semanal],
                    }
                ),
                "anual": (
                    None
                    if comp.perfil_anual is None
                    else {
                        "dias": comp.perfil_anual_dias,
                        "valores": [_limpiar(v) for v in comp.perfil_anual],
                    }
                ),
                "feriados": (
                    None
                    if comp.feriados is None
                    else {
                        "fechas": [_fecha_iso(f) for f in comp.fechas[-recorte:]],
                        "valores": [_limpiar(v) for v in comp.feriados[-recorte:]],
                    }
                ),
            }
        return jsonify(
            {
                "serie": serie.nombre,
                "horizonte": parametros.horizonte,
                "historia": {
                    "fechas": [_fecha_iso(f) for f in fechas_hist],
                    "valores": [_limpiar(v) for v in valores_hist],
                },
                "pronostico": {
                    "fechas": [_fecha_iso(f) for f in pronostico.fechas],
                    "valores": [_limpiar(v) for v in pronostico.valores],
                    "inferior": [_limpiar(v) for v in (pronostico.limites_inferiores or [])],
                    "superior": [_limpiar(v) for v in (pronostico.limites_superiores or [])],
                },
                "componentes": componentes_json,
                "resumen": {
                    "total_proyectado": _limpiar(resumen.total_proyectado),
                    "total_periodo_anterior": (
                        _limpiar(resumen.total_periodo_anterior)
                        if resumen.total_periodo_anterior is not None
                        else None
                    ),
                    "variacion_porcentual": (
                        _limpiar(resumen.variacion_porcentual)
                        if resumen.variacion_porcentual is not None
                        else None
                    ),
                    "fecha_pico": _fecha_iso(resumen.fecha_pico),
                    "valor_pico": _limpiar(resumen.valor_pico),
                    "promedio_diario": _limpiar(resumen.promedio_diario),
                },
                "token_excel": token_excel,
                "sha256": sha256_de(excel),
            }
        )

    def _leer_parametros(datos: dict) -> ParametrosPronostico:
        """Traduce el JSON del formulario al DTO ParametrosPronostico."""
        feriados: List[tuple] = []
        for f in datos.get("feriados_personalizados", []):
            try:
                fecha = datetime.strptime(str(f.get("fecha", "")), "%Y-%m-%d").date()
            except ValueError:
                continue  # Una fecha mal escrita se ignora en lugar de romper todo.
            feriados.append((fecha, str(f.get("nombre", "Feriado"))[:60] or "Feriado"))
        pais = str(datos.get("pais_feriados", "") or "").upper()
        return ParametrosPronostico(
            horizonte=min(max(int(datos.get("horizonte", 28)), 1), 365),
            estacionalidad_anual=bool(datos.get("estacionalidad_anual", True)),
            estacionalidad_semanal=bool(datos.get("estacionalidad_semanal", True)),
            estacionalidad_mensual=bool(datos.get("estacionalidad_mensual", False)),
            pais_feriados=pais if pais in {"PE", "EC"} else None,
            feriados_personalizados=feriados,
            intervalo_confianza=min(max(float(datos.get("intervalo_confianza", 0.80)), 0.50), 0.99),
            flexibilidad_tendencia=min(
                max(float(datos.get("flexibilidad_tendencia", 0.05)), 0.001), 0.5
            ),
        )

    @app.get("/api/pronostico/descargar/<token>")
    def api_descargar_pronostico(token: str):
        return _descargar(token)

    # ------------------------------------------------------------------ #
    # Descarga genérica de archivos guardados en el almacén              #
    # ------------------------------------------------------------------ #
    def _guardar_excel(contenido: bytes, nombre: str) -> str:
        token = uuid.uuid4().hex
        ALMACEN[token] = {"excel": contenido, "nombre": nombre}
        return token

    def _descargar(token: str):
        registro = ALMACEN.get(token)
        if registro is None or "excel" not in registro:
            return _json_error("El archivo expiró. Genere el resultado de nuevo.", 404)
        return send_file(
            io.BytesIO(registro["excel"]),
            as_attachment=True,
            download_name=registro["nombre"],
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    return app
