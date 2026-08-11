"""
CAPA DE APLICACIÓN — Parámetros de pronóstico (DTO).

Agrupa todo lo que el usuario puede configurar en la pantalla del Módulo 2.
Es un objeto simple de transporte: la web lo arma desde el formulario y el
adaptador de Prophet lo traduce a argumentos del algoritmo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Tuple


@dataclass
class ParametrosPronostico:
    """Configuración elegida por el usuario para generar un pronóstico."""

    horizonte: int = 28                      # Días hacia el futuro a proyectar.
    estacionalidad_anual: bool = True        # Patrón que se repite cada año.
    estacionalidad_semanal: bool = True      # Patrón que se repite cada semana.
    estacionalidad_mensual: bool = False     # Patrón que se repite cada ~30.5 días.
    pais_feriados: Optional[str] = None      # 'PE', 'EC' o None (sin feriados de país).
    feriados_personalizados: List[Tuple[date, str]] = field(default_factory=list)
    intervalo_confianza: float = 0.80        # Ancho de la banda de incertidumbre.
    flexibilidad_tendencia: float = 0.05     # changepoint_prior_scale de Prophet.

    def descripcion(self) -> List[tuple]:
        """Pares (etiqueta, valor) para la hoja 'Parámetros' del Excel: trazabilidad."""
        feriados = "; ".join(f"{f.isoformat()} {n}" for f, n in self.feriados_personalizados)
        return [
            ("Horizonte (días)", self.horizonte),
            ("Estacionalidad anual", "Sí" if self.estacionalidad_anual else "No"),
            ("Estacionalidad semanal", "Sí" if self.estacionalidad_semanal else "No"),
            ("Estacionalidad mensual", "Sí" if self.estacionalidad_mensual else "No"),
            ("Feriados de país", self.pais_feriados or "Ninguno"),
            ("Feriados personalizados", feriados or "Ninguno"),
            ("Intervalo de confianza", f"{int(self.intervalo_confianza * 100)} %"),
            ("Flexibilidad de tendencia", self.flexibilidad_tendencia),
        ]
