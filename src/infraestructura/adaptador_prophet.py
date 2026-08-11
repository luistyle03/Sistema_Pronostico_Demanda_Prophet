"""
CAPA DE INFRAESTRUCTURA — Adaptador del modelo Prophet (Taylor & Letham, 2018).

Este adaptador "traduce" entre el lenguaje del dominio (SerieTemporal,
Pronostico) y el lenguaje de la librería prophet de Meta (DataFrames con
columnas ds/y). Es el ÚNICO archivo del sistema que importa prophet.
"""
from __future__ import annotations

import logging

import pandas as pd
from prophet import Prophet

from src.aplicacion.parametros import ParametrosPronostico
from src.aplicacion.puertos import PuertoModeloPronostico
from src.dominio.entidades import ComponentesPronostico, Pronostico, SerieTemporal
from src.dominio.excepciones import ModeloNoEntrenadoError
from src.infraestructura.modelos.utilidades import recortar_negativos

# Silenciar la bitácora interna del motor de Prophet (cmdstanpy), que es
# muy ruidosa y no aporta al usuario final. cmdstanpy instala sus propios
# manejadores de log, por eso además de bajar el nivel se desactiva.
for _nombre in ("cmdstanpy", "prophet"):
    _bitacora = logging.getLogger(_nombre)
    _bitacora.setLevel(logging.ERROR)
    _bitacora.disabled = True


class AdaptadorProphet(PuertoModeloPronostico):
    """Implementación del puerto de modelo usando el algoritmo Prophet."""

    def __init__(self, parametros: ParametrosPronostico | None = None):
        self._parametros = parametros or ParametrosPronostico()
        self._modelo: Prophet | None = None

    @property
    def nombre(self) -> str:
        return "Prophet"

    def entrenar(self, serie: SerieTemporal) -> None:
        """Convierte la serie al formato ds/y de Prophet y ajusta el modelo."""
        p = self._parametros
        datos = pd.DataFrame(
            {"ds": pd.to_datetime(serie.fechas()), "y": serie.valores()}
        )
        # Feriados personalizados (ej. aniversario de la tienda): Prophet los
        # recibe como un DataFrame con columnas 'holiday' y 'ds' al construirse.
        feriados_df = None
        if p.feriados_personalizados:
            feriados_df = pd.DataFrame(
                {
                    "holiday": [nombre for _, nombre in p.feriados_personalizados],
                    "ds": pd.to_datetime([f for f, _ in p.feriados_personalizados]),
                }
            )
        modelo = Prophet(
            yearly_seasonality=p.estacionalidad_anual,
            weekly_seasonality=p.estacionalidad_semanal,
            daily_seasonality=False,  # Datos diarios: no hay patrón intradía.
            interval_width=p.intervalo_confianza,
            changepoint_prior_scale=p.flexibilidad_tendencia,
            holidays=feriados_df,
        )
        if p.estacionalidad_mensual:
            # Prophet no trae estacionalidad mensual de fábrica: se agrega como
            # un ciclo de 30.5 días con 5 términos de Fourier (valor usual).
            modelo.add_seasonality(name="mensual", period=30.5, fourier_order=5)
        if p.pais_feriados:
            # Calendario oficial de feriados del país ('PE' Perú, 'EC' Ecuador),
            # provisto por la librería `holidays` que Prophet usa internamente.
            modelo.add_country_holidays(country_name=p.pais_feriados)
        modelo.fit(datos)
        self._modelo = modelo

    def pronosticar(self, horizonte: int) -> Pronostico:
        """
        Proyecta `horizonte` días e incluye el intervalo de confianza y la
        descomposición en componentes (HU02): se predice el rango COMPLETO
        (historia + futuro) para poder separar las piezas de la ecuación.
        """
        if self._modelo is None:
            raise ModeloNoEntrenadoError("Prophet: debe llamarse entrenar() primero.")
        futuro = self._modelo.make_future_dataframe(periods=horizonte, freq="D")
        completo = self._modelo.predict(futuro)   # Historia ajustada + futuro.
        prediccion = completo.tail(horizonte)     # Solo el futuro, para el pronóstico.
        return Pronostico(
            nombre_modelo=self.nombre,
            fechas=[marca.date() for marca in prediccion["ds"]],
            valores=recortar_negativos(prediccion["yhat"]),
            limites_inferiores=recortar_negativos(prediccion["yhat_lower"]),
            limites_superiores=recortar_negativos(prediccion["yhat_upper"]),
            componentes=self._extraer_componentes(completo),
        )

    def _extraer_componentes(self, completo: pd.DataFrame) -> ComponentesPronostico:
        """
        HU02 · RF06 — La ecuación de Prophet es ADITIVA (Taylor & Letham, 2018):
        pronóstico = tendencia + estacionalidades + feriados (+ ruido). Este
        método separa esas piezas del DataFrame de predicción para que la
        interfaz las grafique y el dueño VEA el porqué del número.

        Los perfiles semanal y anual son series de Fourier que dependen solo
        del día de la semana / del año, por eso basta leerlos de una ventana
        representativa (7 y 365 días) en lugar de todo el rango.
        """
        componentes = ComponentesPronostico(
            fechas=[marca.date() for marca in completo["ds"]],
            tendencia=[float(v) for v in completo["trend"]],
        )
        if "weekly" in completo.columns:
            ultimos_7 = completo.tail(7)
            efecto_por_dia = {int(marca.weekday()): float(valor)
                              for marca, valor in zip(ultimos_7["ds"], ultimos_7["weekly"])}
            componentes.perfil_semanal = [efecto_por_dia[d] for d in range(7)]  # lun..dom
        if "yearly" in completo.columns:
            ventana_anual = completo.tail(365)
            efecto_por_fecha = {marca.strftime("%m-%d"): float(valor)
                                for marca, valor in zip(ventana_anual["ds"], ventana_anual["yearly"])}
            componentes.perfil_anual_dias = sorted(efecto_por_fecha)
            componentes.perfil_anual = [efecto_por_fecha[d] for d in componentes.perfil_anual_dias]
        if "holidays" in completo.columns:
            componentes.feriados = [float(v) for v in completo["holidays"]]
        return componentes
