"""
CAPA DE APLICACIÓN — Caso de uso: Generar pronóstico (Módulo 2, retail).

Recibe la serie histórica de un producto y un modelo ya configurado con los
parámetros del usuario (estacionalidades, feriados, etc.), entrena, proyecta
y traduce el resultado a indicadores de negocio (ResumenGerencial) que el
dueño del retail entiende de un vistazo.
"""

from __future__ import annotations

from typing import Tuple

from src.aplicacion.puertos import PuertoModeloPronostico
from src.dominio.entidades import Pronostico, ResumenGerencial, SerieTemporal
from src.dominio.excepciones import SerieMuyCortaError

MINIMO_HISTORICO = 14  # Dos semanas: lo mínimo para detectar el patrón semanal.


class GeneradorDePronostico:
    """Caso de uso con una única responsabilidad: producir pronóstico + resumen."""

    def ejecutar(
        self,
        modelo: PuertoModeloPronostico,
        serie: SerieTemporal,
        horizonte: int,
    ) -> Tuple[Pronostico, ResumenGerencial]:
        """Entrena el modelo con la serie y devuelve (pronóstico, resumen)."""
        if len(serie) < MINIMO_HISTORICO:
            raise SerieMuyCortaError(
                f"El historial de '{serie.nombre}' tiene {len(serie)} días; "
                f"se necesitan al menos {MINIMO_HISTORICO} para pronosticar."
            )
        if horizonte < 1:
            raise SerieMuyCortaError("El horizonte debe ser de al menos 1 día.")
        modelo.entrenar(serie)
        pronostico = modelo.pronosticar(horizonte)
        return pronostico, self._resumir(serie, pronostico, horizonte)

    def _resumir(
        self, serie: SerieTemporal, pronostico: Pronostico, horizonte: int
    ) -> ResumenGerencial:
        """Convierte números de modelo en indicadores de negocio."""
        total_proyectado = sum(pronostico.valores)
        # Período anterior comparable: los últimos `horizonte` días del historial.
        valores_historicos = serie.valores()
        total_anterior = None
        variacion = None
        if len(valores_historicos) >= horizonte:
            total_anterior = sum(valores_historicos[-horizonte:])
            if total_anterior > 0:
                variacion = 100.0 * (total_proyectado - total_anterior) / total_anterior
        # Día pico: la fecha futura con mayor venta proyectada.
        indice_pico = max(range(len(pronostico.valores)), key=lambda i: pronostico.valores[i])
        return ResumenGerencial(
            total_proyectado=total_proyectado,
            total_periodo_anterior=total_anterior,
            variacion_porcentual=variacion,
            fecha_pico=pronostico.fechas[indice_pico],
            valor_pico=pronostico.valores[indice_pico],
            promedio_diario=total_proyectado / horizonte,
        )
